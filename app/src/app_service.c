#include "app_service.h"

#include <string.h>

#include "adc.h"
#include "can.h"
#include "event_queue.h"
#include "filter_chain.h"
#include "sensor_factory.h"
#include "bsp_MAX30100.h"

#include "can_proto.h"
#include "can_transport.h"
#include "data_fusion.h"
#include "node_cfg.h"

typedef struct
{
    event_queue_t queue;
    node_cfg_t cfg;
    node_state_t state;
    uint16_t error_count;
    uint32_t ms_now;
    uint32_t last_hr_poll_ms;
    uint32_t last_tx_ms;
    uint32_t last_hb_ms;
    uint8_t tx_seq;
    sensor_iface_t *emg_sensor;
    sensor_iface_t *hr_sensor;
    filter_chain_t emg_filter_chain;
    filter_chain_t hr_filter_chain;
    filter_iface_t emg_mavg_iface;
    moving_avg_filter_ctx_t emg_mavg_ctx;
    filter_iface_t emg_ema_iface;
    ema_filter_ctx_t emg_ema_ctx;
    filter_iface_t hr_mavg_iface;
    moving_avg_filter_ctx_t hr_mavg_ctx;
    filter_iface_t hr_ema_iface;
    ema_filter_ctx_t hr_ema_ctx;
    data_fusion_t fusion;
} app_runtime_t;

static app_runtime_t s_app;

static void app_push_event_from_isr(event_id_t id, uint32_t arg0, uint32_t arg1)
{
    event_t event;
    event.id = id;
    event.arg0 = arg0;
    event.arg1 = arg1;
    (void)event_queue_push_from_isr(&s_app.queue, &event);
}

static bool app_handle_can_command(const can_proto_command_t *command,
                                   uint8_t *resp_payload,
                                   uint8_t *resp_len,
                                   void *user_ctx)
{
    app_runtime_t *app = (app_runtime_t *)user_ctx;

    if ((command == 0) || (resp_payload == 0) || (resp_len == 0) || (app == 0))
    {
        return false;
    }

    *resp_len = 0U;
    switch (command->cmd_id)
    {
    case CAN_CMD_SET_RATE:
        if (command->payload_len < 3U)
        {
            return false;
        }
        if (command->payload[0] == 0U)
        {
            app->cfg.emg_rate_hz = (uint16_t)(((uint16_t)command->payload[2] << 8U) | command->payload[1]);
        }
        else if (command->payload[0] == 1U)
        {
            app->cfg.hr_rate_hz = (uint16_t)(((uint16_t)command->payload[2] << 8U) | command->payload[1]);
        }
        else if (command->payload[0] == 2U)
        {
            app->cfg.can_tx_rate_hz = (uint16_t)(((uint16_t)command->payload[2] << 8U) | command->payload[1]);
        }
        else
        {
            return false;
        }
        resp_payload[0] = command->payload[0];
        *resp_len = 1U;
        return true;

    case CAN_CMD_SET_FILTER_PARAM:
        /* payload = [sensor(0/1), stage, param_id, value_q(0.01 单位)] */
        if (command->payload_len < 4U)
        {
            return false;
        }
        {
            filter_chain_t *chain = (command->payload[0] == 0U) ? &app->emg_filter_chain : &app->hr_filter_chain;
            float value = (float)command->payload[3] / 100.0f;
            if (filter_chain_set_param(chain, command->payload[1], command->payload[2], value) != 0)
            {
                return false;
            }
            resp_payload[0] = command->payload[0];
            resp_payload[1] = command->payload[1];
            *resp_len = 2U;
            return true;
        }

    case CAN_CMD_START_STREAM:
        app->cfg.stream_enabled = true;
        resp_payload[0] = 1U;
        *resp_len = 1U;
        return true;

    case CAN_CMD_STOP_STREAM:
        app->cfg.stream_enabled = false;
        resp_payload[0] = 0U;
        *resp_len = 1U;
        return true;

    case CAN_CMD_GET_STATUS:
        resp_payload[0] = (uint8_t)app->state;
        resp_payload[1] = (uint8_t)(app->error_count & 0xFFU);
        resp_payload[2] = (uint8_t)((app->error_count >> 8) & 0xFFU);
        resp_payload[3] = can_transport_queue_fill();
        *resp_len = 4U;
        return true;

    case CAN_CMD_SET_STATE:
        if ((command->payload_len < 1U) || (command->payload[0] > (uint8_t)NODE_STATE_FAULT))
        {
            return false;
        }
        app->state = (node_state_t)command->payload[0];
        resp_payload[0] = (uint8_t)app->state;
        *resp_len = 1U;
        return true;

    default:
        return false;
    }
}

static void app_send_telemetry(void)
{
    fusion_snapshot_t snapshot;
    can_message_t message;

    if (s_app.cfg.stream_enabled == false)
    {
        return;
    }

    if (!data_fusion_get_snapshot(&s_app.fusion, &snapshot))
    {
        return;
    }

    if (can_proto_encode_telemetry(&snapshot,
                                   s_app.cfg.node_id,
                                   s_app.cfg.host_id,
                                   s_app.tx_seq++,
                                   &message) == 0)
    {
        if (can_tx_submit(&message, CAN_TX_PRIO_NORMAL, false, 0U, 0U) != 0)
        {
            s_app.error_count++;
        }
    }
}

static void app_send_heartbeat(void)
{
    can_message_t message;
    if (can_proto_encode_heartbeat(s_app.state,
                                   s_app.cfg.node_id,
                                   s_app.cfg.host_id,
                                   s_app.tx_seq++,
                                   s_app.error_count,
                                   &message) == 0)
    {
        (void)can_tx_submit(&message, CAN_TX_PRIO_HIGH, false, 0U, 0U);
    }
}

static void app_handle_event(const event_t *event)
{
    uint16_t raw;
    float filtered;
    uint16_t period_tx_ms;
    uint16_t period_hr_poll_ms;
    int32_t rc;

    if (event == 0)
    {
        return;
    }

    switch (event->id)
    {
    case EVENT_TICK_1MS:
        s_app.ms_now = event->arg0;
        period_tx_ms = (uint16_t)(1000U / (s_app.cfg.can_tx_rate_hz == 0U ? 1U : s_app.cfg.can_tx_rate_hz));
        period_hr_poll_ms = (uint16_t)(1000U / (s_app.cfg.hr_rate_hz == 0U ? 1U : s_app.cfg.hr_rate_hz));

        if ((s_app.ms_now - s_app.last_tx_ms) >= period_tx_ms)
        {
            s_app.last_tx_ms = s_app.ms_now;
            app_send_telemetry();
        }
        if ((s_app.ms_now - s_app.last_hb_ms) >= 1000U)
        {
            s_app.last_hb_ms = s_app.ms_now;
            app_send_heartbeat();
        }
        if ((s_app.ms_now - s_app.last_hr_poll_ms) >= period_hr_poll_ms)
        {
            s_app.last_hr_poll_ms = s_app.ms_now;
            /* INT 丢失时仍可通过轮询兜底，避免心率链路“静默失效”。 */
            event_t poll_event = {EVENT_HR_POLL, s_app.ms_now, 0U};
            (void)event_queue_push(&s_app.queue, &poll_event);
        }
        can_transport_process(s_app.ms_now);
        break;

    case EVENT_EMG_SAMPLE_READY:
        if ((s_app.emg_sensor != 0) && (s_app.emg_sensor->read(s_app.emg_sensor, &raw) == 0))
        {
            filtered = filter_chain_process(&s_app.emg_filter_chain, (float)raw);
            data_fusion_update_emg(&s_app.fusion, s_app.ms_now, raw, filtered);
            s_app.state = NODE_STATE_RUN;
        }
        else
        {
            s_app.error_count++;
            s_app.state = NODE_STATE_DEGRADED;
        }
        break;

    case EVENT_HR_INT:
    case EVENT_HR_POLL:
        rc = ((s_app.hr_sensor != 0) ? s_app.hr_sensor->read(s_app.hr_sensor, &raw) : -1);
        if (rc == 0)
        {
            filtered = filter_chain_process(&s_app.hr_filter_chain, (float)raw);
            data_fusion_update_hr(&s_app.fusion, s_app.ms_now, raw, filtered);
        }
        else if (rc < 0)
        {
            s_app.error_count++;
            s_app.state = NODE_STATE_DEGRADED;
        }
        break;

    case EVENT_CAN_RX_PENDING:
        can_transport_poll_rx();
        break;

    case EVENT_FAULT:
        s_app.state = NODE_STATE_FAULT;
        s_app.error_count++;
        break;

    default:
        break;
    }
}

int32_t app_service_init(void)
{
    sensor_cfg_t emg_cfg;
    sensor_cfg_t hr_cfg;

    (void)memset(&s_app, 0, sizeof(s_app));
    event_queue_init(&s_app.queue);
    node_cfg_load_default(&s_app.cfg);
    data_fusion_init(&s_app.fusion);
    s_app.state = NODE_STATE_INIT;

    filter_chain_init(&s_app.emg_filter_chain);
    filter_chain_init(&s_app.hr_filter_chain);

    /* EMG 采用“滑动均值 + EMA”，在实时性和抑噪之间取平衡。 */
    filter_create_moving_avg(&s_app.emg_mavg_iface, &s_app.emg_mavg_ctx, 4U);
    filter_create_ema(&s_app.emg_ema_iface, &s_app.emg_ema_ctx, 0.15f);
    (void)filter_chain_add_stage(&s_app.emg_filter_chain, &s_app.emg_mavg_iface);
    (void)filter_chain_add_stage(&s_app.emg_filter_chain, &s_app.emg_ema_iface);

    filter_create_moving_avg(&s_app.hr_mavg_iface, &s_app.hr_mavg_ctx, 5U);
    filter_create_ema(&s_app.hr_ema_iface, &s_app.hr_ema_ctx, 0.10f);
    (void)filter_chain_add_stage(&s_app.hr_filter_chain, &s_app.hr_mavg_iface);
    (void)filter_chain_add_stage(&s_app.hr_filter_chain, &s_app.hr_ema_iface);

    emg_cfg.sample_rate_hz = s_app.cfg.emg_rate_hz;
    emg_cfg.channel_or_addr = 0U;
    s_app.emg_sensor = sensor_factory_create(SENSOR_TYPE_EMG, &emg_cfg);
    if ((s_app.emg_sensor == 0) || (s_app.emg_sensor->start(s_app.emg_sensor) != 0))
    {
        s_app.state = NODE_STATE_FAULT;
        return -1;
    }

    hr_cfg.sample_rate_hz = s_app.cfg.hr_rate_hz;
    hr_cfg.channel_or_addr = MAX30100_I2C_ADDR_7BIT;
    s_app.hr_sensor = sensor_factory_create(SENSOR_TYPE_HEART_RATE, &hr_cfg);
    if ((s_app.hr_sensor == 0) || (s_app.hr_sensor->start(s_app.hr_sensor) != 0))
    {
        s_app.state = NODE_STATE_FAULT;
        return -1;
    }

    if (can_transport_init(&hcan, s_app.cfg.node_id) != 0)
    {
        s_app.state = NODE_STATE_FAULT;
        return -1;
    }
    can_transport_register_command_handler(app_handle_can_command, &s_app);

    s_app.state = NODE_STATE_RUN;
    return 0;
}

void app_service_run_once(void)
{
    event_t event;
    if (event_queue_pop(&s_app.queue, &event))
    {
        app_handle_event(&event);
    }
    else
    {
        /* 空闲周期仍轮询 CAN 接收，避免通知丢失导致命令堆积。 */
        can_transport_poll_rx();
    }
}

node_state_t app_service_get_state(void)
{
    return s_app.state;
}

uint16_t app_service_get_error_count(void)
{
    return s_app.error_count + can_transport_error_count();
}

void app_service_on_systick_isr(void)
{
    event_t event;
    s_app.ms_now++;
    event.id = EVENT_TICK_1MS;
    event.arg0 = s_app.ms_now;
    event.arg1 = 0U;
    (void)event_queue_push_from_isr(&s_app.queue, &event);
}

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
    if ((hadc != 0) && (hadc->Instance == ADC1))
    {
        sensor_factory_on_emg_dma_complete_isr();
        app_push_event_from_isr(EVENT_EMG_SAMPLE_READY, 0U, 0U);
    }
}

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
    if (GPIO_Pin == GPIO_PIN_0)
    {
        app_push_event_from_isr(EVENT_HR_INT, 0U, 0U);
    }
}

void HAL_CAN_RxFifo0MsgPendingCallback(CAN_HandleTypeDef *hcan_cb)
{
    if ((hcan_cb != 0) && (hcan_cb->Instance == CAN1))
    {
        app_push_event_from_isr(EVENT_CAN_RX_PENDING, 0U, 0U);
    }
}
