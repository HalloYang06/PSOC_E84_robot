#include "can_transport.h"

#include <stdio.h>
#include <string.h>

#include "usart.h"

#ifndef CAN_TRANSPORT_DEBUG_UART
#define CAN_TRANSPORT_DEBUG_UART 1
#endif

enum
{
    CAN_TX_QUEUE_CAP = 16U
};

typedef struct
{
    uint8_t used;
    can_message_t message;
    can_tx_prio_t prio;
    uint32_t order;
} can_tx_slot_t;

typedef struct
{
    uint8_t valid;
    uint8_t cmd_id;
    uint8_t seq;
    uint8_t status;
    uint8_t payload[5];
    uint8_t payload_len;
} can_ack_cache_t;

static CAN_HandleTypeDef *s_hcan;
static uint32_t s_order_counter;
static uint16_t s_error_count;
static uint16_t s_rx_count;
static uint16_t s_tx_count;
static can_command_handler_t s_handler;
static void *s_handler_user;
static can_tx_slot_t s_tx_slots[CAN_TX_QUEUE_CAP];
static can_ack_cache_t s_ack_cache;

#if CAN_TRANSPORT_DEBUG_UART
static void can_uart_debug_write(const char *line, int len, uint32_t timeout_ms)
{
    if ((line == 0) || (len <= 0))
    {
        return;
    }

    (void)HAL_UART_Transmit(&huart1, (uint8_t *)line, (uint16_t)len, timeout_ms);
}

static void can_uart_debug_init_fail(const char *stage, const CAN_HandleTypeDef *hcan)
{
    char line[128];
    int len;

    if ((stage == 0) || (hcan == 0) || (hcan->Instance == 0))
    {
        return;
    }

    len = snprintf(line,
                   sizeof(line),
                   "CAN INIT %s FAIL state=%u err=0x%08lX MSR=0x%08lX ESR=0x%08lX\r\n",
                   stage,
                   (unsigned int)hcan->State,
                   (unsigned long)hcan->ErrorCode,
                   (unsigned long)hcan->Instance->MSR,
                   (unsigned long)hcan->Instance->ESR);
    if (len <= 0)
    {
        return;
    }
    if ((size_t)len >= sizeof(line))
    {
        len = (int)sizeof(line) - 1;
    }

    can_uart_debug_write(line, len, 100U);
}

static void can_uart_debug_init_ok(void)
{
    static const char line[] = "CAN INIT OK filter=7C0 std data\r\n";
    can_uart_debug_write(line, (int)(sizeof(line) - 1U), 100U);
}

static void can_uart_debug_frame(const char *prefix, uint32_t id, uint8_t dlc, const uint8_t *data)
{
    char line[128];
    int len;
    uint8_t i;

    if ((prefix == 0) || (data == 0))
    {
        return;
    }

    len = snprintf(line,
                   sizeof(line),
                   "%s id=%03lX dlc=%u data=",
                   prefix,
                   (unsigned long)(id & 0x7FFU),
                   (unsigned int)dlc);
    if (len < 0)
    {
        return;
    }

    for (i = 0U; (i < dlc) && (i < 8U); ++i)
    {
        int wrote = snprintf(line + len, sizeof(line) - (size_t)len, "%02X%s", data[i], (i + 1U < dlc) ? " " : "");
        if (wrote < 0)
        {
            return;
        }
        len += wrote;
        if ((size_t)len >= sizeof(line))
        {
            break;
        }
    }

    if ((size_t)len < sizeof(line) - 3U)
    {
        line[len++] = '\r';
        line[len++] = '\n';
        line[len] = '\0';
        can_uart_debug_write(line, len, 20U);
    }
}

static void can_uart_debug_rx_frame(const CAN_RxHeaderTypeDef *rx_header, const uint8_t *data, uint8_t matched)
{
    char prefix[32];
    int len;

    if ((rx_header == 0) || (data == 0))
    {
        return;
    }

    len = snprintf(prefix,
                   sizeof(prefix),
                   "CAN RX match=%u",
                   (unsigned int)matched);
    if (len <= 0)
    {
        return;
    }
    if ((size_t)len >= sizeof(prefix))
    {
        len = (int)sizeof(prefix) - 1;
        prefix[len] = '\0';
    }

    can_uart_debug_frame(prefix, rx_header->StdId, (uint8_t)rx_header->DLC, data);
}

static void can_uart_debug_tx_frame(const can_message_t *message, int32_t rc)
{
    char prefix[32];
    int len;
    static uint16_t sensor_tx_log_div;

    if (message == 0)
    {
        return;
    }
    if ((message->id == F103_CAN_ID_SENSOR_TX) && (rc == 0))
    {
        sensor_tx_log_div++;
        if (sensor_tx_log_div < 50U)
        {
            return;
        }
        sensor_tx_log_div = 0U;
    }

    len = snprintf(prefix,
                   sizeof(prefix),
                   "CAN TX rc=%ld",
                   (long)rc);
    if (len <= 0)
    {
        return;
    }
    if ((size_t)len >= sizeof(prefix))
    {
        len = (int)sizeof(prefix) - 1;
        prefix[len] = '\0';
    }

    can_uart_debug_frame(prefix, message->id, message->dlc, message->data);
}

static void can_uart_debug_ctrl_result(const can_proto_command_t *command,
                                       uint8_t status,
                                       uint8_t duplicate,
                                       int32_t ack_rc)
{
    char line[128];
    int len;

    if (command == 0)
    {
        return;
    }

    len = snprintf(line,
                   sizeof(line),
                   "CAN CMD cmd=%02X seq=%u status=%u dup=%u ack_rc=%ld q=%u err=%u rx=%u tx=%u\r\n",
                   (unsigned int)command->cmd_id,
                   (unsigned int)command->seq,
                   (unsigned int)status,
                   (unsigned int)duplicate,
                   (long)ack_rc,
                   (unsigned int)can_transport_queue_fill(),
                   (unsigned int)can_transport_error_count(),
                   (unsigned int)can_transport_rx_count(),
                   (unsigned int)can_transport_tx_count());
    if (len <= 0)
    {
        return;
    }
    if ((size_t)len >= sizeof(line))
    {
        len = (int)sizeof(line) - 1;
    }

    can_uart_debug_write(line, len, 20U);
}

static void can_uart_debug_ctrl_drop(const can_message_t *message)
{
    char line[80];
    int len;

    if (message == 0)
    {
        return;
    }

    len = snprintf(line,
                   sizeof(line),
                   "CAN CMD DROP id=%03lX dlc=%u err=%u\r\n",
                   (unsigned long)(message->id & 0x7FFU),
                   (unsigned int)message->dlc,
                   (unsigned int)can_transport_error_count());
    if (len <= 0)
    {
        return;
    }
    if ((size_t)len >= sizeof(line))
    {
        len = (int)sizeof(line) - 1;
    }

    can_uart_debug_write(line, len, 20U);
}
#endif

static int32_t can_low_level_send(const can_message_t *message)
{
    CAN_TxHeaderTypeDef tx_header;
    uint32_t mailbox;
    uint8_t dlc;

    if ((s_hcan == 0) || (message == 0))
    {
#if CAN_TRANSPORT_DEBUG_UART
        can_uart_debug_tx_frame(message, -1);
#endif
        return -1;
    }
    if ((message->id > 0x7FFU) || (HAL_CAN_GetTxMailboxesFreeLevel(s_hcan) == 0U))
    {
#if CAN_TRANSPORT_DEBUG_UART
        can_uart_debug_tx_frame(message, -1);
#endif
        return -1;
    }

    dlc = message->dlc;
    if (dlc > 8U)
    {
        dlc = 8U;
    }

    tx_header.StdId = message->id & 0x7FFU;
    tx_header.ExtId = 0U;
    tx_header.IDE = CAN_ID_STD;
    tx_header.RTR = CAN_RTR_DATA;
    tx_header.DLC = dlc;
    tx_header.TransmitGlobalTime = DISABLE;

    if (HAL_CAN_AddTxMessage(s_hcan, &tx_header, (uint8_t *)message->data, &mailbox) != HAL_OK)
    {
#if CAN_TRANSPORT_DEBUG_UART
        can_uart_debug_tx_frame(message, -1);
#endif
        return -1;
    }
    s_tx_count++;
#if CAN_TRANSPORT_DEBUG_UART
    can_uart_debug_tx_frame(message, 0);
#endif
    return 0;
}

static int32_t can_tx_pick_slot(uint8_t *index_out)
{
    uint8_t i;
    uint8_t picked = 0xFFU;

    if (index_out == 0)
    {
        return -1;
    }

    for (i = 0U; i < CAN_TX_QUEUE_CAP; ++i)
    {
        if (s_tx_slots[i].used == 0U)
        {
            continue;
        }
        if (picked == 0xFFU)
        {
            picked = i;
            continue;
        }
        if (s_tx_slots[i].prio < s_tx_slots[picked].prio)
        {
            picked = i;
            continue;
        }
        if ((s_tx_slots[i].prio == s_tx_slots[picked].prio) &&
            (s_tx_slots[i].order < s_tx_slots[picked].order))
        {
            picked = i;
        }
    }

    if (picked == 0xFFU)
    {
        return -1;
    }
    *index_out = picked;
    return 0;
}

static void can_tx_drain(void)
{
    uint8_t idx;

    if (s_hcan == 0)
    {
        return;
    }

    while (HAL_CAN_GetTxMailboxesFreeLevel(s_hcan) > 0U)
    {
        if (can_tx_pick_slot(&idx) != 0)
        {
            return;
        }
        if (can_low_level_send(&s_tx_slots[idx].message) != 0)
        {
            return;
        }
        s_tx_slots[idx].used = 0U;
    }
}

static void can_ack_cache_save(uint8_t cmd_id, uint8_t seq, uint8_t status, const uint8_t *payload, uint8_t payload_len)
{
    s_ack_cache.valid = 1U;
    s_ack_cache.cmd_id = cmd_id;
    s_ack_cache.seq = seq;
    s_ack_cache.status = status;
    s_ack_cache.payload_len = payload_len;
    if (s_ack_cache.payload_len > sizeof(s_ack_cache.payload))
    {
        s_ack_cache.payload_len = sizeof(s_ack_cache.payload);
    }
    (void)memset(s_ack_cache.payload, 0, sizeof(s_ack_cache.payload));
    if ((payload != 0) && (s_ack_cache.payload_len > 0U))
    {
        (void)memcpy(s_ack_cache.payload, payload, s_ack_cache.payload_len);
    }
}

int32_t can_transport_init(CAN_HandleTypeDef *hcan)
{
    CAN_FilterTypeDef filter;

    if (hcan == 0)
    {
        return -1;
    }

    s_hcan = hcan;
    s_order_counter = 0U;
    s_error_count = 0U;
    s_rx_count = 0U;
    s_tx_count = 0U;
    s_handler = 0;
    s_handler_user = 0;
    (void)memset(s_tx_slots, 0, sizeof(s_tx_slots));
    (void)memset(&s_ack_cache, 0, sizeof(s_ack_cache));

    (void)memset(&filter, 0, sizeof(filter));
    filter.FilterBank = 0U;
    filter.FilterMode = CAN_FILTERMODE_IDMASK;
    filter.FilterScale = CAN_FILTERSCALE_32BIT;
    /* Accept only the F103 control standard data frame. */
    filter.FilterIdHigh = (uint16_t)(F103_CAN_ID_CTRL_RX << 5U);
    filter.FilterIdLow = 0U;
    filter.FilterMaskIdHigh = (uint16_t)(0x7FFU << 5U);
    filter.FilterMaskIdLow = (uint16_t)(CAN_ID_EXT | CAN_RTR_REMOTE);
    filter.FilterFIFOAssignment = CAN_FILTER_FIFO0;
    filter.FilterActivation = CAN_FILTER_ENABLE;
    filter.SlaveStartFilterBank = 14U;

    if (HAL_CAN_ConfigFilter(s_hcan, &filter) != HAL_OK)
    {
#if CAN_TRANSPORT_DEBUG_UART
        can_uart_debug_init_fail("FILTER", s_hcan);
#endif
        return -1;
    }
    if (HAL_CAN_Start(s_hcan) != HAL_OK)
    {
#if CAN_TRANSPORT_DEBUG_UART
        can_uart_debug_init_fail("START", s_hcan);
#endif
        return -1;
    }
    if (HAL_CAN_ActivateNotification(s_hcan,
                                      CAN_IT_RX_FIFO0_MSG_PENDING |
                                      CAN_IT_ERROR |
                                      CAN_IT_ERROR_WARNING |
                                      CAN_IT_ERROR_PASSIVE |
                                      CAN_IT_BUSOFF |
                                      CAN_IT_LAST_ERROR_CODE) != HAL_OK)
    {
#if CAN_TRANSPORT_DEBUG_UART
        can_uart_debug_init_fail("NOTIFY", s_hcan);
#endif
        return -1;
    }
#if CAN_TRANSPORT_DEBUG_UART
    can_uart_debug_init_ok();
#endif
    return 0;
}

void can_transport_register_command_handler(can_command_handler_t handler, void *user_ctx)
{
    s_handler = handler;
    s_handler_user = user_ctx;
}

int32_t can_tx_submit(const can_message_t *message, can_tx_prio_t prio)
{
    uint8_t i;

    if ((message == 0) || (message->id > 0x7FFU))
    {
        return -1;
    }

    for (i = 0U; i < CAN_TX_QUEUE_CAP; ++i)
    {
        if (s_tx_slots[i].used == 0U)
        {
            s_tx_slots[i].used = 1U;
            s_tx_slots[i].message = *message;
            s_tx_slots[i].prio = prio;
            s_tx_slots[i].order = s_order_counter++;
            return 0;
        }
    }

    s_error_count++;
    return -1;
}

void can_transport_process(uint32_t now_ms)
{
    (void)now_ms;
    can_tx_drain();
}

void can_transport_poll_rx(void)
{
    CAN_RxHeaderTypeDef rx_header;
    can_message_t message;
    CAN_TypeDef *can;
    uint32_t rir;
    uint32_t rdtr;
    uint32_t rdlr;
    uint32_t rdhr;

    if (s_hcan == 0)
    {
        return;
    }
    can = s_hcan->Instance;
    if (can == 0)
    {
        return;
    }

    while ((can->RF0R & CAN_RF0R_FMP0) > 0U)
    {
        (void)memset(&message, 0, sizeof(message));

        rir = can->sFIFOMailBox[CAN_RX_FIFO0].RIR;
        rdtr = can->sFIFOMailBox[CAN_RX_FIFO0].RDTR;
        rdlr = can->sFIFOMailBox[CAN_RX_FIFO0].RDLR;
        rdhr = can->sFIFOMailBox[CAN_RX_FIFO0].RDHR;

        rx_header.IDE = rir & CAN_RI0R_IDE;
        rx_header.RTR = rir & CAN_RI0R_RTR;
        rx_header.StdId = (rir & CAN_RI0R_STID) >> CAN_RI0R_STID_Pos;
        rx_header.DLC = (rdtr & CAN_RDT0R_DLC) >> CAN_RDT0R_DLC_Pos;
        if (rx_header.DLC > 8U)
        {
            rx_header.DLC = 8U;
        }
        rx_header.ExtId = 0U;
        rx_header.Timestamp = 0U;
        rx_header.FilterMatchIndex = (rdtr & CAN_RDT0R_FMI) >> CAN_RDT0R_FMI_Pos;

        message.data[0] = (uint8_t)(rdlr & 0xFFU);
        message.data[1] = (uint8_t)((rdlr >> 8U) & 0xFFU);
        message.data[2] = (uint8_t)((rdlr >> 16U) & 0xFFU);
        message.data[3] = (uint8_t)((rdlr >> 24U) & 0xFFU);
        message.data[4] = (uint8_t)(rdhr & 0xFFU);
        message.data[5] = (uint8_t)((rdhr >> 8U) & 0xFFU);
        message.data[6] = (uint8_t)((rdhr >> 16U) & 0xFFU);
        message.data[7] = (uint8_t)((rdhr >> 24U) & 0xFFU);

        SET_BIT(can->RF0R, CAN_RF0R_RFOM0);

        if ((rx_header.IDE != CAN_ID_STD) || (rx_header.RTR != CAN_RTR_DATA))
        {
            continue;
        }
        message.id = rx_header.StdId & 0x7FFU;
        message.dlc = (uint8_t)rx_header.DLC;
        if (message.dlc > 8U)
        {
            message.dlc = 8U;
        }
        s_rx_count++;
#if CAN_TRANSPORT_DEBUG_UART
        can_uart_debug_rx_frame(&rx_header, message.data, (uint8_t)(message.id == F103_CAN_ID_CTRL_RX));
#endif
        (void)can_rx_dispatch(&message);
    }

    if ((can->RF0R & (CAN_RF0R_FULL0 | CAN_RF0R_FOVR0)) != 0U)
    {
        SET_BIT(can->RF0R, CAN_RF0R_FULL0 | CAN_RF0R_FOVR0);
    }
    __HAL_CAN_ENABLE_IT(s_hcan, CAN_IT_RX_FIFO0_MSG_PENDING);
}

int32_t can_rx_dispatch(const can_message_t *message)
{
    can_proto_command_t command;
    can_message_t ack;
    uint8_t resp_payload[5];
    uint8_t resp_len = 0U;
    uint8_t status = 1U;
    bool ok = false;

    if (message == 0)
    {
        return -1;
    }
    if (can_proto_decode_control(message, &command) != 0)
    {
#if CAN_TRANSPORT_DEBUG_UART
        can_uart_debug_ctrl_drop(message);
#endif
        return 0;
    }

    /* 命令去重：重复 seq 直接返回缓存 ACK，避免重复副作用。 */
    if ((s_ack_cache.valid != 0U) &&
        (s_ack_cache.cmd_id == command.cmd_id) &&
        (s_ack_cache.seq == command.seq))
    {
        if (can_proto_encode_ack(command.cmd_id,
                                 command.seq,
                                 s_ack_cache.status,
                                 s_ack_cache.payload,
                                 s_ack_cache.payload_len,
                                 &ack) == 0)
        {
            int32_t ack_rc = can_tx_submit(&ack, CAN_TX_PRIO_HIGH);
#if CAN_TRANSPORT_DEBUG_UART
            can_uart_debug_ctrl_result(&command, s_ack_cache.status, 1U, ack_rc);
#endif
        }
        return 0;
    }

    if (s_handler != 0)
    {
        ok = s_handler(&command, resp_payload, &resp_len, s_handler_user);
    }
    if (ok)
    {
        status = 0U;
    }
    if (resp_len > sizeof(resp_payload))
    {
        resp_len = sizeof(resp_payload);
    }

    if (can_proto_encode_ack(command.cmd_id, command.seq, status, resp_payload, resp_len, &ack) == 0)
    {
        int32_t ack_rc = can_tx_submit(&ack, CAN_TX_PRIO_HIGH);
#if CAN_TRANSPORT_DEBUG_UART
        can_uart_debug_ctrl_result(&command, status, 0U, ack_rc);
#endif
        if (ack_rc != 0)
        {
            s_error_count++;
        }
    }
    else
    {
        s_error_count++;
    }

    can_ack_cache_save(command.cmd_id, command.seq, status, resp_payload, resp_len);
    return 0;
}

uint16_t can_transport_error_count(void)
{
    return s_error_count;
}

uint8_t can_transport_queue_fill(void)
{
    uint8_t i;
    uint8_t used = 0U;

    for (i = 0U; i < CAN_TX_QUEUE_CAP; ++i)
    {
        if (s_tx_slots[i].used != 0U)
        {
            used++;
        }
    }
    return used;
}

uint16_t can_transport_rx_count(void)
{
    return s_rx_count;
}

uint16_t can_transport_tx_count(void)
{
    return s_tx_count;
}
