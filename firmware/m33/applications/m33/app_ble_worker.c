#include "app_ble_worker.h"

#include <string.h>

void app_ble_reassembly_reset(app_ble_reassembly_t *state)
{
    if (state == NULL)
    {
        return;
    }

    state->length = 0u;
    state->first_fragment_ms = 0u;
    state->dropping_oversize = 0u;
}

void app_ble_reassembly_init(app_ble_reassembly_t *state)
{
    if (state == NULL)
    {
        return;
    }

    memset(state, 0, sizeof(*state));
}

void app_ble_reassembly_sync_generation(app_ble_reassembly_t *state,
                                        uint32_t generation)
{
    if ((state == NULL) || (state->generation == generation))
    {
        return;
    }

    app_ble_reassembly_reset(state);
    state->generation = generation;
}

int app_ble_reassembly_expire(app_ble_reassembly_t *state, uint32_t now_ms)
{
    uint32_t elapsed;

    if ((state == NULL) ||
        ((state->length == 0u) && (state->dropping_oversize == 0u)))
    {
        return 0;
    }

    elapsed = now_ms - state->first_fragment_ms;
    if (elapsed < APP_BLE_PARTIAL_TIMEOUT_MS)
    {
        return 0;
    }

    app_ble_reassembly_reset(state);
    return 1;
}

uint32_t app_ble_reassembly_feed(app_ble_reassembly_t *state,
                                 const uint8_t *data,
                                 uint16_t length,
                                 uint32_t now_ms,
                                 app_ble_frame_handler_t handler,
                                 void *context)
{
    uint32_t emitted = 0u;
    uint16_t i;

    if ((state == NULL) || ((length != 0u) && (data == NULL)))
    {
        return 0u;
    }

    (void)app_ble_reassembly_expire(state, now_ms);
    for (i = 0u; i < length; ++i)
    {
        uint8_t value = data[i];

        if (value == (uint8_t)'\n')
        {
            if ((state->dropping_oversize == 0u) &&
                (state->length != 0u) &&
                (handler != NULL))
            {
                uint16_t frame_length = state->length;
                if ((frame_length != 0u) &&
                    (state->data[frame_length - 1u] == (uint8_t)'\r'))
                {
                    frame_length--;
                }
                if (frame_length != 0u)
                {
                    handler(state->data, frame_length, context);
                    emitted++;
                }
            }
            app_ble_reassembly_reset(state);
            continue;
        }

        if (state->dropping_oversize != 0u)
        {
            continue;
        }
        if (state->length == 0u)
        {
            state->first_fragment_ms = now_ms;
        }
        if (state->length >= APP_BLE_FRAME_MAX)
        {
            state->length = 0u;
            state->dropping_oversize = 1u;
            continue;
        }
        state->data[state->length++] = value;
    }

    return emitted;
}

#ifdef APP_BLE_WORKER_HOST_TEST

#define APP_BLE_HOST_OK 0
#define APP_BLE_HOST_ERROR (-1)
#define APP_BLE_HOST_FULL (-2)

static app_ble_rx_message_t g_app_ble_host_queue[APP_BLE_RX_QUEUE_DEPTH];
static app_ble_tx_message_t g_app_ble_host_ack_queue[APP_BLE_TX_ACK_QUEUE_DEPTH];
static app_ble_tx_message_t g_app_ble_host_telemetry;
static uint8_t g_app_ble_host_head;
static uint8_t g_app_ble_host_tail;
static uint8_t g_app_ble_host_count;
static uint8_t g_app_ble_host_ack_head;
static uint8_t g_app_ble_host_ack_tail;
static uint8_t g_app_ble_host_ack_count;
static uint8_t g_app_ble_host_telemetry_pending;
static uint32_t g_app_ble_generation;
static uint16_t g_app_ble_conn_id;
static uint32_t g_app_ble_rx_queue_drops;
static uint8_t g_app_ble_notify_busy;
static uint8_t g_app_ble_notify_buffer_returned;
static uint8_t g_app_ble_notify_operation_complete;
static app_ble_session_token_t g_app_ble_notify_token;

static void app_ble_worker_host_try_release_notify(void)
{
    if ((g_app_ble_notify_busy != 0u) &&
        (g_app_ble_notify_buffer_returned != 0u) &&
        (g_app_ble_notify_operation_complete != 0u))
    {
        g_app_ble_notify_busy = 0u;
        g_app_ble_notify_buffer_returned = 0u;
        g_app_ble_notify_operation_complete = 0u;
        memset(&g_app_ble_notify_token, 0, sizeof(g_app_ble_notify_token));
    }
}

static void app_ble_worker_host_clear_queue(void)
{
    g_app_ble_host_head = 0u;
    g_app_ble_host_tail = 0u;
    g_app_ble_host_count = 0u;
}

static void app_ble_worker_host_clear_tx(void)
{
    g_app_ble_host_ack_head = 0u;
    g_app_ble_host_ack_tail = 0u;
    g_app_ble_host_ack_count = 0u;
    g_app_ble_host_telemetry_pending = 0u;
}

app_ble_worker_result_t app_ble_worker_init(void)
{
    app_ble_worker_host_clear_queue();
    app_ble_worker_host_clear_tx();
    g_app_ble_generation = 1u;
    g_app_ble_conn_id = 0u;
    g_app_ble_rx_queue_drops = 0u;
    g_app_ble_notify_busy = 0u;
    g_app_ble_notify_buffer_returned = 0u;
    g_app_ble_notify_operation_complete = 0u;
    memset(&g_app_ble_notify_token, 0, sizeof(g_app_ble_notify_token));
    return APP_BLE_HOST_OK;
}

app_ble_worker_result_t app_ble_worker_start(void)
{
    return APP_BLE_HOST_OK;
}

app_ble_worker_result_t app_ble_worker_begin_session(uint16_t conn_id)
{
    if (conn_id == 0u)
    {
        return APP_BLE_HOST_ERROR;
    }
    app_ble_worker_host_clear_queue();
    app_ble_worker_host_clear_tx();
    if (g_app_ble_notify_busy != 0u)
    {
        return APP_BLE_HOST_ERROR;
    }
    g_app_ble_generation++;
    g_app_ble_conn_id = conn_id;
    return APP_BLE_HOST_OK;
}

void app_ble_worker_reset_session(uint16_t conn_id)
{
    if ((conn_id != 0u) && (conn_id != g_app_ble_conn_id))
    {
        return;
    }
    g_app_ble_generation++;
    g_app_ble_conn_id = 0u;
    app_ble_worker_host_clear_queue();
    app_ble_worker_host_clear_tx();
}

app_ble_worker_result_t app_ble_worker_enqueue(uint16_t conn_id,
                                               const uint8_t *data,
                                               uint16_t length)
{
    app_ble_rx_message_t *message;

    if ((conn_id == 0u) || (conn_id != g_app_ble_conn_id) ||
        (data == NULL) || (length == 0u) ||
        (length > APP_BLE_RX_FRAGMENT_MAX))
    {
        return APP_BLE_HOST_ERROR;
    }
    if (g_app_ble_host_count >= APP_BLE_RX_QUEUE_DEPTH)
    {
        g_app_ble_rx_queue_drops++;
        return APP_BLE_HOST_FULL;
    }

    message = &g_app_ble_host_queue[g_app_ble_host_tail];
    message->generation = g_app_ble_generation;
    message->conn_id = conn_id;
    message->length = length;
    memcpy(message->data, data, length);
    g_app_ble_host_tail = (uint8_t)((g_app_ble_host_tail + 1u) % APP_BLE_RX_QUEUE_DEPTH);
    g_app_ble_host_count++;
    return APP_BLE_HOST_OK;
}

static app_ble_worker_result_t app_ble_worker_host_prepare_tx(
    app_ble_tx_message_t *message,
    app_ble_tx_kind_t kind,
    const app_ble_session_token_t *token,
    const uint8_t *data,
    uint16_t length)
{
    if ((message == NULL) || (token == NULL) ||
        !app_ble_worker_session_is_current(token->generation, token->conn_id) ||
        (data == NULL) ||
        (length == 0u) || (length > APP_BLE_TX_PAYLOAD_MAX))
    {
        return APP_BLE_HOST_ERROR;
    }

    message->generation = token->generation;
    message->conn_id = token->conn_id;
    message->length = length;
    message->kind = kind;
    memcpy(message->data, data, length);
    return APP_BLE_HOST_OK;
}

app_ble_worker_result_t app_ble_worker_get_session_token(app_ble_session_token_t *token)
{
    if ((token == NULL) || (g_app_ble_conn_id == 0u))
    {
        return APP_BLE_HOST_ERROR;
    }
    token->generation = g_app_ble_generation;
    token->conn_id = g_app_ble_conn_id;
    return APP_BLE_HOST_OK;
}

app_ble_worker_result_t app_ble_worker_enqueue_ack(const app_ble_session_token_t *token,
                                                   const uint8_t *data,
                                                   uint16_t length)
{
    app_ble_tx_message_t *message;

    if (g_app_ble_host_ack_count >= APP_BLE_TX_ACK_QUEUE_DEPTH)
    {
        return APP_BLE_HOST_FULL;
    }
    message = &g_app_ble_host_ack_queue[g_app_ble_host_ack_tail];
    if (app_ble_worker_host_prepare_tx(message, APP_BLE_TX_KIND_ACK,
                                       token, data, length) != APP_BLE_HOST_OK)
    {
        return APP_BLE_HOST_ERROR;
    }
    g_app_ble_host_ack_tail =
        (uint8_t)((g_app_ble_host_ack_tail + 1u) % APP_BLE_TX_ACK_QUEUE_DEPTH);
    g_app_ble_host_ack_count++;
    return APP_BLE_HOST_OK;
}

app_ble_worker_result_t app_ble_worker_publish_telemetry(const app_ble_session_token_t *token,
                                                         const uint8_t *data,
                                                         uint16_t length)
{
    if (app_ble_worker_host_prepare_tx(&g_app_ble_host_telemetry,
                                       APP_BLE_TX_KIND_TELEMETRY,
                                       token, data, length) != APP_BLE_HOST_OK)
    {
        return APP_BLE_HOST_ERROR;
    }
    g_app_ble_host_telemetry_pending = 1u;
    return APP_BLE_HOST_OK;
}

int app_ble_worker_host_dequeue(app_ble_rx_message_t *message)
{
    if ((message == NULL) || (g_app_ble_host_count == 0u))
    {
        return 0;
    }
    *message = g_app_ble_host_queue[g_app_ble_host_head];
    g_app_ble_host_head = (uint8_t)((g_app_ble_host_head + 1u) % APP_BLE_RX_QUEUE_DEPTH);
    g_app_ble_host_count--;
    return (int)sizeof(*message);
}

int app_ble_worker_host_dequeue_tx(app_ble_tx_message_t *message)
{
    if (message == NULL)
    {
        return 0;
    }
    if (g_app_ble_host_ack_count != 0u)
    {
        *message = g_app_ble_host_ack_queue[g_app_ble_host_ack_head];
        g_app_ble_host_ack_head =
            (uint8_t)((g_app_ble_host_ack_head + 1u) % APP_BLE_TX_ACK_QUEUE_DEPTH);
        g_app_ble_host_ack_count--;
        return (int)sizeof(*message);
    }
    if (g_app_ble_host_telemetry_pending != 0u)
    {
        *message = g_app_ble_host_telemetry;
        g_app_ble_host_telemetry_pending = 0u;
        return (int)sizeof(*message);
    }
    return 0;
}

int app_ble_worker_session_is_current(uint32_t generation, uint16_t conn_id)
{
    return ((generation == g_app_ble_generation) &&
            (conn_id != 0u) &&
            (conn_id == g_app_ble_conn_id));
}

int app_ble_worker_is_current_thread(void)
{
    return 1;
}

int app_ble_worker_notify_try_acquire(const app_ble_session_token_t *token)
{
    if ((token == NULL) || (g_app_ble_notify_busy != 0u) ||
        !app_ble_worker_session_is_current(token->generation, token->conn_id))
    {
        return 0;
    }
    g_app_ble_notify_busy = 1u;
    g_app_ble_notify_buffer_returned = 0u;
    g_app_ble_notify_operation_complete = 0u;
    g_app_ble_notify_token = *token;
    return 1;
}

void app_ble_worker_notify_buffer_returned(void)
{
    if (g_app_ble_notify_busy != 0u)
    {
        g_app_ble_notify_buffer_returned = 1u;
        app_ble_worker_host_try_release_notify();
    }
}

void app_ble_worker_notify_operation_complete(uint16_t conn_id)
{
    if ((g_app_ble_notify_busy != 0u) &&
        (conn_id == g_app_ble_notify_token.conn_id))
    {
        g_app_ble_notify_operation_complete = 1u;
        app_ble_worker_host_try_release_notify();
    }
}

void app_ble_worker_notify_abort(const app_ble_session_token_t *token)
{
    if ((token != NULL) && (g_app_ble_notify_busy != 0u) &&
        (token->generation == g_app_ble_notify_token.generation) &&
        (token->conn_id == g_app_ble_notify_token.conn_id))
    {
        g_app_ble_notify_buffer_returned = 1u;
        g_app_ble_notify_operation_complete = 1u;
        app_ble_worker_host_try_release_notify();
    }
}

uint32_t app_ble_worker_drop_count(void)
{
    return g_app_ble_rx_queue_drops;
}

#else

#include "app_ble_diag.h"
#include "app_ble_protocol.h"
#include "bt_app_gatt_handler.h"
#include "rehab_mode_manager.h"

typedef struct
{
    uint32_t generation;
    uint16_t conn_id;
} app_ble_frame_context_t;

static struct rt_messagequeue g_app_ble_rx_mq;
static rt_uint8_t g_app_ble_rx_mq_pool[
    RT_MQ_BUF_SIZE(sizeof(app_ble_rx_message_t), APP_BLE_RX_QUEUE_DEPTH)];
static struct rt_messagequeue g_app_ble_tx_ack_mq;
static rt_uint8_t g_app_ble_tx_ack_mq_pool[
    RT_MQ_BUF_SIZE(sizeof(app_ble_tx_message_t), APP_BLE_TX_ACK_QUEUE_DEPTH)];
static app_ble_tx_message_t g_app_ble_telemetry;
static rt_bool_t g_app_ble_telemetry_pending;
static struct rt_thread g_app_ble_worker_thread;
static rt_uint8_t g_app_ble_worker_stack[APP_BLE_WORKER_STACK_SIZE];
static volatile rt_uint32_t g_app_ble_generation;
static volatile rt_uint16_t g_app_ble_conn_id;
static volatile rt_uint32_t g_app_ble_rx_queue_drops;
static volatile rt_bool_t g_app_ble_notify_busy;
static volatile rt_bool_t g_app_ble_notify_buffer_returned;
static volatile rt_bool_t g_app_ble_notify_operation_complete;
static app_ble_session_token_t g_app_ble_notify_token;
static rt_bool_t g_app_ble_worker_initialized;
static rt_bool_t g_app_ble_worker_started;

static rt_uint32_t app_ble_worker_next_generation(rt_uint32_t generation)
{
    generation++;
    return generation == 0u ? 1u : generation;
}

static void app_ble_worker_snapshot_session(rt_uint32_t *generation,
                                            rt_uint16_t *conn_id)
{
    rt_base_t level = rt_hw_interrupt_disable();
    if (generation != RT_NULL)
    {
        *generation = g_app_ble_generation;
    }
    if (conn_id != RT_NULL)
    {
        *conn_id = g_app_ble_conn_id;
    }
    rt_hw_interrupt_enable(level);
}

app_ble_worker_result_t app_ble_worker_get_session_token(app_ble_session_token_t *token)
{
    rt_base_t level;

    if (token == RT_NULL)
    {
        return -RT_EINVAL;
    }
    level = rt_hw_interrupt_disable();
    token->generation = g_app_ble_generation;
    token->conn_id = g_app_ble_conn_id;
    rt_hw_interrupt_enable(level);
    return token->conn_id == 0u ? -RT_ERROR : RT_EOK;
}

static int app_ble_worker_notify_is_busy(void)
{
    int busy;
    rt_base_t level = rt_hw_interrupt_disable();
    busy = g_app_ble_notify_busy;
    rt_hw_interrupt_enable(level);
    return busy;
}

int app_ble_worker_session_is_current(uint32_t generation, uint16_t conn_id)
{
    rt_uint32_t current_generation;
    rt_uint16_t current_conn_id;

    app_ble_worker_snapshot_session(&current_generation, &current_conn_id);
    return ((generation == current_generation) &&
            (conn_id != 0u) &&
            (conn_id == current_conn_id));
}

int app_ble_worker_is_current_thread(void)
{
    return rt_thread_self() == &g_app_ble_worker_thread;
}

static void app_ble_worker_notify_try_release_locked(void)
{
    if (g_app_ble_notify_busy && g_app_ble_notify_buffer_returned &&
        g_app_ble_notify_operation_complete)
    {
        g_app_ble_notify_busy = RT_FALSE;
        g_app_ble_notify_buffer_returned = RT_FALSE;
        g_app_ble_notify_operation_complete = RT_FALSE;
        rt_memset(&g_app_ble_notify_token, 0, sizeof(g_app_ble_notify_token));
    }
}

int app_ble_worker_notify_try_acquire(const app_ble_session_token_t *token)
{
    rt_base_t level;
    int acquired = 0;

    level = rt_hw_interrupt_disable();
    if ((token != RT_NULL) && !g_app_ble_notify_busy &&
        (token->generation == g_app_ble_generation) &&
        (token->conn_id != 0u) && (token->conn_id == g_app_ble_conn_id))
    {
        g_app_ble_notify_busy = RT_TRUE;
        g_app_ble_notify_buffer_returned = RT_FALSE;
        g_app_ble_notify_operation_complete = RT_FALSE;
        g_app_ble_notify_token = *token;
        acquired = 1;
    }
    rt_hw_interrupt_enable(level);
    return acquired;
}

void app_ble_worker_notify_buffer_returned(void)
{
    rt_base_t level = rt_hw_interrupt_disable();
    if (g_app_ble_notify_busy)
    {
        g_app_ble_notify_buffer_returned = RT_TRUE;
        app_ble_worker_notify_try_release_locked();
    }
    rt_hw_interrupt_enable(level);
}

void app_ble_worker_notify_operation_complete(uint16_t conn_id)
{
    rt_base_t level = rt_hw_interrupt_disable();
    if (g_app_ble_notify_busy &&
        (conn_id == g_app_ble_notify_token.conn_id))
    {
        g_app_ble_notify_operation_complete = RT_TRUE;
        app_ble_worker_notify_try_release_locked();
    }
    rt_hw_interrupt_enable(level);
}

void app_ble_worker_notify_abort(const app_ble_session_token_t *token)
{
    rt_base_t level = rt_hw_interrupt_disable();
    if ((token != RT_NULL) && g_app_ble_notify_busy &&
        (token->generation == g_app_ble_notify_token.generation) &&
        (token->conn_id == g_app_ble_notify_token.conn_id))
    {
        g_app_ble_notify_buffer_returned = RT_TRUE;
        g_app_ble_notify_operation_complete = RT_TRUE;
        app_ble_worker_notify_try_release_locked();
    }
    rt_hw_interrupt_enable(level);
}

static rt_err_t app_ble_worker_send_tx(const app_ble_tx_message_t *message)
{
    if ((message == RT_NULL) ||
        !app_ble_worker_session_is_current(message->generation,
                                           message->conn_id))
    {
        app_ble_diag_note_tx_stale_drop();
        return -RT_ERROR;
    }
    return bt_app_gatt_notify_from_worker(message->generation,
                                          message->conn_id,
                                          message->data,
                                          message->length);
}

static void app_ble_worker_drain_tx(void)
{
    app_ble_tx_message_t message;
    app_ble_session_token_t token;
    rt_ssize_t recv_len;
    rt_bool_t message_pending = RT_FALSE;

    if (app_ble_worker_notify_is_busy())
    {
        return;
    }

    recv_len = rt_mq_recv(&g_app_ble_tx_ack_mq,
                          &message,
                          sizeof(message),
                          0);
    if (recv_len == (rt_ssize_t)sizeof(message))
    {
        message_pending = RT_TRUE;
    }

    if (!message_pending)
    {
        rt_enter_critical();
        if (g_app_ble_telemetry_pending)
        {
            message = g_app_ble_telemetry;
            g_app_ble_telemetry_pending = RT_FALSE;
            message_pending = RT_TRUE;
        }
        rt_exit_critical();
    }
    if (!message_pending)
    {
        return;
    }
    token.generation = message.generation;
    token.conn_id = message.conn_id;
    if (!app_ble_worker_notify_try_acquire(&token))
    {
        app_ble_diag_note_notify_failure();
        return;
    }
    if (app_ble_worker_send_tx(&message) != RT_EOK)
    {
        app_ble_worker_notify_abort(&token);
    }
}

static void app_ble_worker_handle_frame(const uint8_t *frame,
                                        uint16_t length,
                                        void *context)
{
    app_ble_frame_context_t *frame_context = (app_ble_frame_context_t *)context;
    app_ble_session_token_t token;
    app_ble_request_t request;
    rehab_app_mode_command_t command;
    rt_uint8_t ack[160];
    rt_err_t ret;
    int ack_length;

    if ((frame_context == RT_NULL) ||
        !app_ble_worker_session_is_current(frame_context->generation,
                                           frame_context->conn_id))
    {
        return;
    }

    if (app_ble_protocol_parse(frame, length, &request) != APP_BLE_PROTOCOL_OK)
    {
        return;
    }
    if (!app_ble_worker_session_is_current(frame_context->generation,
                                           frame_context->conn_id))
    {
        return;
    }
    if (request.type == APP_BLE_REQUEST_HEARTBEAT)
    {
        ret = rehab_mode_manager_note_app_heartbeat(frame_context->generation);
    }
    else if (request.type == APP_BLE_REQUEST_STOP)
    {
        ret = rehab_mode_manager_stop_app(frame_context->generation);
    }
    else if ((request.type == APP_BLE_REQUEST_MODE) ||
             (request.type == APP_BLE_REQUEST_TRAINING))
    {
        rt_memset(&command, 0, sizeof(command));
        if (request.type == APP_BLE_REQUEST_TRAINING)
        {
            switch (request.training)
            {
            case APP_BLE_TRAINING_CURL_J5:
                command.mode = REHAB_MODE_CURL;
                command.fixed_action = REHAB_FIXED_ACTION_NONE;
                break;
            case APP_BLE_TRAINING_FIXED_ELBOW_FLEX_EXTEND:
                command.mode = REHAB_MODE_FIXED_ACTION;
                command.fixed_action = REHAB_FIXED_ACTION_ELBOW_FLEX_EXTEND;
                break;
            case APP_BLE_TRAINING_FIXED_SHOULDER_PLANAR:
                command.mode = REHAB_MODE_FIXED_ACTION;
                command.fixed_action = REHAB_FIXED_ACTION_SHOULDER_PLANAR;
                break;
            case APP_BLE_TRAINING_FIXED_COORDINATED:
                command.mode = REHAB_MODE_FIXED_ACTION;
                command.fixed_action = REHAB_FIXED_ACTION_COORDINATED;
                break;
            default:
                command.mode = REHAB_MODE_PASSIVE;
                command.fixed_action = REHAB_FIXED_ACTION_NONE;
                break;
            }
        }
        else if (request.mode == APP_BLE_MODE_ACTIVE)
        {
            command.mode = REHAB_MODE_ACTIVE;
        }
        else if (request.mode == APP_BLE_MODE_ASSIST)
        {
            command.mode = REHAB_MODE_ASSIST;
        }
        else
        {
            command.mode = REHAB_MODE_RESIST;
        }
        command.joint_mask = request.joint_mask;
        command.request_id = request.request_id;
        command.session_generation = frame_context->generation;
        command.ttl_ms = request.ttl_ms;
        ret = rehab_mode_manager_apply_app_command(&command);
    }
    else
    {
        ret = -RT_EINVAL;
    }

    if (!app_ble_worker_session_is_current(frame_context->generation,
                                           frame_context->conn_id))
    {
        return;
    }
    ack_length = rt_snprintf((char *)ack,
                             sizeof(ack),
                             "{\"schema\":\"rehab_ble_v1\",\"type\":\"command_result\","
                             "\"request_id\":%lu,\"result\":\"%s\",\"code\":%d}\n",
                             (unsigned long)request.request_id,
                             (ret == RT_EOK) ? "applied" : "rejected",
                             (int)ret);
    if ((ack_length <= 0) || ((rt_size_t)ack_length >= sizeof(ack)))
    {
        return;
    }
    token.generation = frame_context->generation;
    token.conn_id = frame_context->conn_id;
    (void)app_ble_worker_enqueue_ack(&token, ack, (rt_uint16_t)ack_length);
}

static void app_ble_worker_entry(void *parameter)
{
    app_ble_reassembly_t reassembly;
    app_ble_rx_message_t message;
    app_ble_frame_context_t frame_context;
    rt_ssize_t recv_len;
    rt_uint32_t observed_generation;

    RT_UNUSED(parameter);
    app_ble_reassembly_init(&reassembly);
    app_ble_worker_snapshot_session(&observed_generation, RT_NULL);
    while (1)
    {
        rt_uint32_t current_generation;

        app_ble_worker_drain_tx();
        app_ble_worker_snapshot_session(&current_generation, RT_NULL);
        if (current_generation != observed_generation)
        {
            (void)rehab_mode_manager_note_app_disconnect(observed_generation);
            observed_generation = current_generation;
        }
        app_ble_reassembly_sync_generation(&reassembly, current_generation);

        recv_len = rt_mq_recv(&g_app_ble_rx_mq,
                              &message,
                              sizeof(message),
                              rt_tick_from_millisecond(50u));
        if (recv_len > 0)
        {
            if ((recv_len != (rt_ssize_t)sizeof(message)) ||
                !app_ble_worker_session_is_current(message.generation,
                                                   message.conn_id))
            {
                continue;
            }
            app_ble_reassembly_sync_generation(&reassembly,
                                                message.generation);
            frame_context.generation = message.generation;
            frame_context.conn_id = message.conn_id;
            (void)app_ble_reassembly_feed(&reassembly,
                                          message.data,
                                          message.length,
                                          (uint32_t)rt_tick_get_millisecond(),
                                          app_ble_worker_handle_frame,
                                          &frame_context);
        }
        else
        {
            (void)app_ble_reassembly_expire(
                &reassembly,
                (uint32_t)rt_tick_get_millisecond());
        }
    }
}

app_ble_worker_result_t app_ble_worker_init(void)
{
    rt_err_t result;

    if (g_app_ble_worker_initialized)
    {
        return RT_EOK;
    }

    result = rt_mq_init(&g_app_ble_rx_mq,
                        "ble_rx",
                        g_app_ble_rx_mq_pool,
                        sizeof(app_ble_rx_message_t),
                        sizeof(g_app_ble_rx_mq_pool),
                        RT_IPC_FLAG_FIFO);
    if (result != RT_EOK)
    {
        return result;
    }

    result = rt_mq_init(&g_app_ble_tx_ack_mq,
                        "ble_ack",
                        g_app_ble_tx_ack_mq_pool,
                        sizeof(app_ble_tx_message_t),
                        sizeof(g_app_ble_tx_ack_mq_pool),
                        RT_IPC_FLAG_FIFO);
    if (result != RT_EOK)
    {
        (void)rt_mq_detach(&g_app_ble_rx_mq);
        return result;
    }

    result = rt_thread_init(&g_app_ble_worker_thread,
                            "ble_work",
                            app_ble_worker_entry,
                            RT_NULL,
                            g_app_ble_worker_stack,
                            sizeof(g_app_ble_worker_stack),
                            APP_BLE_WORKER_PRIORITY,
                            APP_BLE_WORKER_TICK);
    if (result != RT_EOK)
    {
        (void)rt_mq_detach(&g_app_ble_tx_ack_mq);
        (void)rt_mq_detach(&g_app_ble_rx_mq);
        return result;
    }

    g_app_ble_generation = 1u;
    g_app_ble_conn_id = 0u;
    g_app_ble_rx_queue_drops = 0u;
    g_app_ble_telemetry_pending = RT_FALSE;
    g_app_ble_notify_busy = RT_FALSE;
    g_app_ble_notify_buffer_returned = RT_FALSE;
    g_app_ble_notify_operation_complete = RT_FALSE;
    rt_memset(&g_app_ble_notify_token, 0, sizeof(g_app_ble_notify_token));
    g_app_ble_worker_initialized = RT_TRUE;
    return RT_EOK;
}

app_ble_worker_result_t app_ble_worker_start(void)
{
    rt_err_t result;

    if (!g_app_ble_worker_initialized)
    {
        return -RT_ERROR;
    }
    if (g_app_ble_worker_started)
    {
        return RT_EOK;
    }

    result = rt_thread_startup(&g_app_ble_worker_thread);
    if (result == RT_EOK)
    {
        g_app_ble_worker_started = RT_TRUE;
    }
    return result;
}

app_ble_worker_result_t app_ble_worker_begin_session(uint16_t conn_id)
{
    rt_base_t level;
    rt_err_t result;

    if (!g_app_ble_worker_initialized || (conn_id == 0u))
    {
        return -RT_ERROR;
    }

    result = rt_mq_control(&g_app_ble_rx_mq, RT_IPC_CMD_RESET, RT_NULL);
    if (result != RT_EOK)
    {
        return result;
    }
    rt_enter_critical();
    result = rt_mq_control(&g_app_ble_tx_ack_mq, RT_IPC_CMD_RESET, RT_NULL);
    if (result != RT_EOK)
    {
        rt_exit_critical();
        return result;
    }
    g_app_ble_telemetry_pending = RT_FALSE;

    level = rt_hw_interrupt_disable();
    if (g_app_ble_notify_busy)
    {
        rt_hw_interrupt_enable(level);
        rt_exit_critical();
        app_ble_diag_note_tx_session_busy_reject();
        return -RT_EBUSY;
    }
    g_app_ble_generation = app_ble_worker_next_generation(g_app_ble_generation);
    g_app_ble_conn_id = conn_id;
    rt_hw_interrupt_enable(level);
    rt_exit_critical();
    return RT_EOK;
}

void app_ble_worker_reset_session(uint16_t conn_id)
{
    rt_base_t level;

    if (!g_app_ble_worker_initialized)
    {
        return;
    }

    rt_enter_critical();
    level = rt_hw_interrupt_disable();
    if ((conn_id != 0u) && (conn_id != g_app_ble_conn_id))
    {
        rt_hw_interrupt_enable(level);
        rt_exit_critical();
        return;
    }
    g_app_ble_generation = app_ble_worker_next_generation(g_app_ble_generation);
    g_app_ble_conn_id = 0u;
    rt_hw_interrupt_enable(level);
    (void)rt_mq_control(&g_app_ble_tx_ack_mq, RT_IPC_CMD_RESET, RT_NULL);
    g_app_ble_telemetry_pending = RT_FALSE;
    rt_exit_critical();
    (void)rt_mq_control(&g_app_ble_rx_mq, RT_IPC_CMD_RESET, RT_NULL);
}

app_ble_worker_result_t app_ble_worker_enqueue(uint16_t conn_id,
                                               const uint8_t *data,
                                               uint16_t length)
{
    app_ble_rx_message_t message;
    rt_base_t level;
    rt_err_t result;
    rt_uint32_t queue_depth;

    if (!g_app_ble_worker_initialized || (conn_id == 0u) ||
        (data == RT_NULL) || (length == 0u) ||
        (length > APP_BLE_RX_FRAGMENT_MAX))
    {
        return -RT_EINVAL;
    }

    level = rt_hw_interrupt_disable();
    if (conn_id != g_app_ble_conn_id)
    {
        rt_hw_interrupt_enable(level);
        return -RT_ERROR;
    }
    message.generation = g_app_ble_generation;
    message.conn_id = conn_id;
    rt_hw_interrupt_enable(level);
    message.length = length;
    rt_memcpy(message.data, data, length);

    result = rt_mq_send(&g_app_ble_rx_mq, &message, sizeof(message));
    if (result != RT_EOK)
    {
        level = rt_hw_interrupt_disable();
        g_app_ble_rx_queue_drops++;
        rt_hw_interrupt_enable(level);
        app_ble_diag_note_rx_drop();
    }
    else
    {
        level = rt_hw_interrupt_disable();
        queue_depth = g_app_ble_rx_mq.entry;
        rt_hw_interrupt_enable(level);
        app_ble_diag_note_rx_queue_depth(queue_depth);
    }
    return result;
}

static rt_err_t app_ble_worker_prepare_tx(app_ble_tx_message_t *message,
                                          app_ble_tx_kind_t kind,
                                          const app_ble_session_token_t *token,
                                          const uint8_t *data,
                                          uint16_t length)
{
    rt_base_t level;

    if (!g_app_ble_worker_initialized || (message == RT_NULL) ||
        (token == RT_NULL) || (data == RT_NULL) || (length == 0u) ||
        (length > APP_BLE_TX_PAYLOAD_MAX))
    {
        return -RT_EINVAL;
    }

    level = rt_hw_interrupt_disable();
    if ((token->generation != g_app_ble_generation) ||
        (token->conn_id == 0u) || (token->conn_id != g_app_ble_conn_id))
    {
        rt_hw_interrupt_enable(level);
        return -RT_ERROR;
    }
    message->generation = token->generation;
    message->conn_id = token->conn_id;
    rt_hw_interrupt_enable(level);
    message->length = length;
    message->kind = kind;
    rt_memcpy(message->data, data, length);
    return app_ble_worker_session_is_current(token->generation, token->conn_id)
               ? RT_EOK
               : -RT_ERROR;
}

app_ble_worker_result_t app_ble_worker_enqueue_ack(const app_ble_session_token_t *token,
                                                   const uint8_t *data,
                                                   uint16_t length)
{
    app_ble_tx_message_t message;
    rt_err_t result;
    rt_base_t level;
    rt_uint32_t queue_depth;

    result = app_ble_worker_prepare_tx(&message, APP_BLE_TX_KIND_ACK,
                                       token, data, length);
    if (result != RT_EOK)
    {
        return result;
    }
    rt_enter_critical();
    if (!app_ble_worker_session_is_current(token->generation, token->conn_id))
    {
        rt_exit_critical();
        app_ble_diag_note_tx_stale_drop();
        return -RT_ERROR;
    }
    result = rt_mq_send(&g_app_ble_tx_ack_mq, &message, sizeof(message));
    level = rt_hw_interrupt_disable();
    queue_depth = g_app_ble_tx_ack_mq.entry;
    rt_hw_interrupt_enable(level);
    rt_exit_critical();
    if (result != RT_EOK)
    {
        app_ble_diag_note_tx_ack_drop();
        return result;
    }
    if (!app_ble_worker_session_is_current(token->generation, token->conn_id))
    {
        app_ble_diag_note_tx_stale_drop();
        return -RT_ERROR;
    }

    app_ble_diag_note_tx_queue_depth(queue_depth);
    return RT_EOK;
}

app_ble_worker_result_t app_ble_worker_publish_telemetry(const app_ble_session_token_t *token,
                                                         const uint8_t *data,
                                                         uint16_t length)
{
    app_ble_tx_message_t message;
    rt_err_t result;
    rt_bool_t replaced;

    result = app_ble_worker_prepare_tx(&message,
                                       APP_BLE_TX_KIND_TELEMETRY,
                                       token, data, length);
    if (result != RT_EOK)
    {
        return result;
    }

    rt_enter_critical();
    if (!app_ble_worker_session_is_current(token->generation, token->conn_id))
    {
        rt_exit_critical();
        app_ble_diag_note_tx_stale_drop();
        return -RT_ERROR;
    }
    replaced = g_app_ble_telemetry_pending;
    g_app_ble_telemetry = message;
    g_app_ble_telemetry_pending = RT_TRUE;
    rt_exit_critical();
    if (replaced)
    {
        app_ble_diag_note_tx_telemetry_coalesced();
    }
    app_ble_diag_note_tx_queue_depth(1u);
    return RT_EOK;
}

uint32_t app_ble_worker_drop_count(void)
{
    rt_uint32_t drops;
    rt_base_t level = rt_hw_interrupt_disable();
    drops = g_app_ble_rx_queue_drops;
    rt_hw_interrupt_enable(level);
    return drops;
}

#endif
