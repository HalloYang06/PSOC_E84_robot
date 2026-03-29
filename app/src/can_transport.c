#include "can_transport.h"

#include <string.h>

enum
{
    CAN_TX_QUEUE_CAP = 20U,
    CAN_ACK_PENDING_CAP = 8U,
    CAN_ACK_TIMEOUT_MS = 30U,
    CAN_ACK_MAX_RETRY = 3U,
    CAN_BROADCAST_ID = 0x1FU
};

typedef struct
{
    uint8_t used;
    can_message_t message;
    can_tx_prio_t prio;
    uint32_t order;
    uint8_t expect_ack;
    uint8_t txn_id;
    uint8_t cmd_id;
    uint8_t dst;
} can_tx_slot_t;

typedef struct
{
    uint8_t active;
    can_message_t message;
    uint8_t txn_id;
    uint8_t cmd_id;
    uint8_t dst;
    uint8_t retry;
    uint32_t deadline_ms;
} can_ack_pending_t;

typedef struct
{
    uint8_t valid;
    uint8_t cmd_id;
    uint8_t txn_id;
    uint8_t ok;
    uint8_t payload[5];
    uint8_t payload_len;
} can_cmd_dedupe_t;

typedef struct
{
    uint8_t session_id;
    uint8_t total;
    uint8_t received;
    uint8_t len;
    uint8_t buffer[48];
} can_rx_fragment_ctx_t;

static CAN_HandleTypeDef *s_hcan;
static uint8_t s_node_id;
static uint8_t s_tx_seq;
static uint32_t s_order_counter;
static uint16_t s_error_count;
static can_command_handler_t s_handler;
static void *s_handler_user;
static can_tx_slot_t s_tx_slots[CAN_TX_QUEUE_CAP];
static can_ack_pending_t s_ack_slots[CAN_ACK_PENDING_CAP];
static can_cmd_dedupe_t s_dedupe;
static can_rx_fragment_ctx_t s_rx_frag;

static int32_t can_low_level_send(const can_message_t *message)
{
    CAN_TxHeaderTypeDef tx_header;
    uint32_t mailbox;

    if ((s_hcan == 0) || (message == 0))
    {
        return -1;
    }

    if (HAL_CAN_GetTxMailboxesFreeLevel(s_hcan) == 0U)
    {
        return -1;
    }

    tx_header.StdId = 0U;
    tx_header.ExtId = message->id & 0x1FFFFFFFU;
    tx_header.IDE = CAN_ID_EXT;
    tx_header.RTR = CAN_RTR_DATA;
    tx_header.DLC = message->dlc;
    tx_header.TransmitGlobalTime = DISABLE;

    if (HAL_CAN_AddTxMessage(s_hcan, &tx_header, (uint8_t *)message->data, &mailbox) != HAL_OK)
    {
        return -1;
    }

    return 0;
}

static int32_t can_ack_track_add(const can_tx_slot_t *slot, uint32_t now_ms)
{
    uint8_t i;

    if ((slot == 0) || (slot->expect_ack == 0U))
    {
        return 0;
    }

    for (i = 0U; i < CAN_ACK_PENDING_CAP; ++i)
    {
        if (s_ack_slots[i].active == 0U)
        {
            s_ack_slots[i].active = 1U;
            s_ack_slots[i].message = slot->message;
            s_ack_slots[i].txn_id = slot->txn_id;
            s_ack_slots[i].cmd_id = slot->cmd_id;
            s_ack_slots[i].dst = slot->dst;
            s_ack_slots[i].retry = 0U;
            s_ack_slots[i].deadline_ms = now_ms + CAN_ACK_TIMEOUT_MS;
            return 0;
        }
    }

    s_error_count++;
    return -1;
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

static void can_tx_drain(uint32_t now_ms)
{
    uint8_t idx;
    can_tx_slot_t slot;

    while (HAL_CAN_GetTxMailboxesFreeLevel(s_hcan) > 0U)
    {
        if (can_tx_pick_slot(&idx) != 0)
        {
            return;
        }

        slot = s_tx_slots[idx];
        if (can_low_level_send(&slot.message) != 0)
        {
            return;
        }

        s_tx_slots[idx].used = 0U;
        (void)can_ack_track_add(&slot, now_ms);
    }
}

static void can_ack_process(uint32_t now_ms)
{
    uint8_t i;

    for (i = 0U; i < CAN_ACK_PENDING_CAP; ++i)
    {
        if (s_ack_slots[i].active == 0U)
        {
            continue;
        }

        if (now_ms < s_ack_slots[i].deadline_ms)
        {
            continue;
        }

        if (s_ack_slots[i].retry >= CAN_ACK_MAX_RETRY)
        {
            s_ack_slots[i].active = 0U;
            s_error_count++;
            continue;
        }

        if (can_low_level_send(&s_ack_slots[i].message) == 0)
        {
            s_ack_slots[i].retry++;
            s_ack_slots[i].deadline_ms = now_ms + CAN_ACK_TIMEOUT_MS;
        }
    }
}

static void can_ack_on_rx(uint8_t cmd_id, uint8_t txn_id, uint8_t src)
{
    uint8_t i;

    for (i = 0U; i < CAN_ACK_PENDING_CAP; ++i)
    {
        if (s_ack_slots[i].active == 0U)
        {
            continue;
        }
        if ((s_ack_slots[i].txn_id == txn_id) &&
            (s_ack_slots[i].cmd_id == cmd_id) &&
            (s_ack_slots[i].dst == src))
        {
            s_ack_slots[i].active = 0U;
            return;
        }
    }
}

static void can_fragment_reset(void)
{
    s_rx_frag.session_id = 0U;
    s_rx_frag.total = 0U;
    s_rx_frag.received = 0U;
    s_rx_frag.len = 0U;
    (void)memset(s_rx_frag.buffer, 0, sizeof(s_rx_frag.buffer));
}

static void can_fragment_feed(const can_proto_fragment_t *fragment)
{
    uint8_t copy_len;
    uint8_t offset;

    if (fragment == 0)
    {
        return;
    }

    if ((fragment->index == 0U) || (fragment->total == 0U))
    {
        return;
    }

    if ((s_rx_frag.received == 0U) || (s_rx_frag.session_id != fragment->session_id))
    {
        can_fragment_reset();
        s_rx_frag.session_id = fragment->session_id;
        s_rx_frag.total = fragment->total;
    }

    if ((fragment->index > s_rx_frag.total) || (fragment->payload_len > 4U))
    {
        s_error_count++;
        return;
    }

    offset = (uint8_t)((fragment->index - 1U) * 4U);
    if (offset >= sizeof(s_rx_frag.buffer))
    {
        s_error_count++;
        return;
    }

    copy_len = fragment->payload_len;
    if ((uint16_t)offset + copy_len > sizeof(s_rx_frag.buffer))
    {
        copy_len = (uint8_t)(sizeof(s_rx_frag.buffer) - offset);
    }

    (void)memcpy(&s_rx_frag.buffer[offset], fragment->payload, copy_len);
    s_rx_frag.received++;
    if ((uint16_t)offset + copy_len > s_rx_frag.len)
    {
        s_rx_frag.len = (uint8_t)(offset + copy_len);
    }

    if (s_rx_frag.received >= s_rx_frag.total)
    {
        /* v1 先完成重组缓存，后续按业务类型再接入完整长包处理。 */
        can_fragment_reset();
    }
}

static int32_t can_submit_internal(const can_message_t *message,
                                   can_tx_prio_t prio,
                                   bool expect_ack,
                                   uint8_t txn_id,
                                   uint8_t cmd_id,
                                   uint8_t dst)
{
    uint8_t i;

    if (message == 0)
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
            s_tx_slots[i].expect_ack = (uint8_t)(expect_ack ? 1U : 0U);
            s_tx_slots[i].txn_id = txn_id;
            s_tx_slots[i].cmd_id = cmd_id;
            s_tx_slots[i].dst = dst;
            return 0;
        }
    }

    s_error_count++;
    return -1;
}

int32_t can_transport_init(CAN_HandleTypeDef *hcan, uint8_t node_id)
{
    CAN_FilterTypeDef filter;

    if (hcan == 0)
    {
        return -1;
    }

    s_hcan = hcan;
    s_node_id = node_id;
    s_tx_seq = 0U;
    s_order_counter = 0U;
    s_error_count = 0U;
    s_handler = 0;
    s_handler_user = 0;
    (void)memset(s_tx_slots, 0, sizeof(s_tx_slots));
    (void)memset(s_ack_slots, 0, sizeof(s_ack_slots));
    (void)memset(&s_dedupe, 0, sizeof(s_dedupe));
    can_fragment_reset();

    (void)memset(&filter, 0, sizeof(filter));
    filter.FilterBank = 0U;
    filter.FilterMode = CAN_FILTERMODE_IDMASK;
    filter.FilterScale = CAN_FILTERSCALE_32BIT;
    filter.FilterIdHigh = 0U;
    filter.FilterIdLow = 0U;
    filter.FilterMaskIdHigh = 0U;
    filter.FilterMaskIdLow = 0U;
    filter.FilterFIFOAssignment = CAN_FILTER_FIFO0;
    filter.FilterActivation = CAN_FILTER_ENABLE;
    filter.SlaveStartFilterBank = 14U;

    if (HAL_CAN_ConfigFilter(s_hcan, &filter) != HAL_OK)
    {
        return -1;
    }
    if (HAL_CAN_Start(s_hcan) != HAL_OK)
    {
        return -1;
    }
    if (HAL_CAN_ActivateNotification(s_hcan, CAN_IT_RX_FIFO0_MSG_PENDING) != HAL_OK)
    {
        return -1;
    }

    return 0;
}

void can_transport_register_command_handler(can_command_handler_t handler, void *user_ctx)
{
    s_handler = handler;
    s_handler_user = user_ctx;
}

int32_t can_tx_submit(const can_message_t *message, can_tx_prio_t prio, bool expect_ack, uint8_t txn_id, uint8_t cmd_id)
{
    can_proto_id_fields_t idf;
    if (message == 0)
    {
        return -1;
    }

    can_proto_parse_id(message->id, &idf);
    return can_submit_internal(message, prio, expect_ack, txn_id, cmd_id, idf.dst);
}

int32_t can_transport_send_fragmented(uint8_t dst, uint8_t msg_type, const uint8_t *payload, uint8_t len)
{
    can_proto_fragment_t fragment;
    can_message_t message;
    uint8_t total;
    uint8_t index;
    uint8_t offset;

    if ((payload == 0) || (len == 0U))
    {
        return -1;
    }

    total = (uint8_t)((len + 3U) / 4U);
    fragment.session_id = (uint8_t)(s_tx_seq + msg_type);
    fragment.total = total;

    for (index = 1U; index <= total; ++index)
    {
        offset = (uint8_t)((index - 1U) * 4U);
        fragment.index = index;
        fragment.payload_len = (uint8_t)((len - offset) > 4U ? 4U : (len - offset));
        (void)memset(fragment.payload, 0, sizeof(fragment.payload));
        (void)memcpy(fragment.payload, &payload[offset], fragment.payload_len);

        if (can_proto_encode_fragment(s_node_id, dst, s_tx_seq++, &fragment, &message) != 0)
        {
            return -1;
        }
        if (can_submit_internal(&message, CAN_TX_PRIO_NORMAL, false, 0U, 0U, dst) != 0)
        {
            return -1;
        }
    }

    return 0;
}

void can_transport_process(uint32_t now_ms)
{
    if (s_hcan == 0)
    {
        return;
    }

    can_tx_drain(now_ms);
    can_ack_process(now_ms);
}

void can_transport_poll_rx(void)
{
    CAN_RxHeaderTypeDef rx_header;
    can_message_t message;

    if (s_hcan == 0)
    {
        return;
    }

    while (HAL_CAN_GetRxFifoFillLevel(s_hcan, CAN_RX_FIFO0) > 0U)
    {
        (void)memset(&message, 0, sizeof(message));
        if (HAL_CAN_GetRxMessage(s_hcan, CAN_RX_FIFO0, &rx_header, message.data) != HAL_OK)
        {
            s_error_count++;
            break;
        }

        message.id = (rx_header.IDE == CAN_ID_EXT) ? rx_header.ExtId : rx_header.StdId;
        message.dlc = (uint8_t)rx_header.DLC;
        (void)can_rx_dispatch(&message);
    }
}

int32_t can_rx_dispatch(const can_message_t *message)
{
    can_proto_id_fields_t idf;
    can_proto_command_t cmd;
    can_proto_fragment_t fragment;
    can_message_t ack;
    uint8_t resp_payload[5];
    uint8_t resp_len = 0U;
    bool ok = false;

    if (message == 0)
    {
        return -1;
    }

    can_proto_parse_id(message->id, &idf);
    if ((idf.dst != s_node_id) && (idf.dst != CAN_BROADCAST_ID))
    {
        return 0;
    }

    if ((idf.type == (uint8_t)CAN_MSG_ACK) || (idf.type == (uint8_t)CAN_MSG_NACK))
    {
        if (message->dlc >= 2U)
        {
            can_ack_on_rx(message->data[0], message->data[1], idf.src);
        }
        return 0;
    }

    if (idf.type == (uint8_t)CAN_MSG_FRAGMENT)
    {
        if (can_proto_decode_fragment(message, &fragment) == 0)
        {
            can_fragment_feed(&fragment);
        }
        else
        {
            s_error_count++;
        }
        return 0;
    }

    if (idf.type != (uint8_t)CAN_MSG_COMMAND)
    {
        return 0;
    }

    if (can_proto_decode_command(message, &cmd) != 0)
    {
        s_error_count++;
        return -1;
    }

    /* 命令幂等去重，重复事务直接回放上一次 ACK，避免重复执行副作用。 */
    if ((s_dedupe.valid != 0U) &&
        (s_dedupe.cmd_id == cmd.cmd_id) &&
        (s_dedupe.txn_id == cmd.txn_id))
    {
        (void)can_proto_encode_ack(s_node_id,
                                   idf.src,
                                   s_tx_seq++,
                                   cmd.cmd_id,
                                   cmd.txn_id,
                                   (s_dedupe.ok != 0U),
                                   s_dedupe.payload,
                                   s_dedupe.payload_len,
                                   &ack);
        (void)can_submit_internal(&ack, CAN_TX_PRIO_HIGH, false, 0U, 0U, idf.src);
        return 0;
    }

    if (s_handler != 0)
    {
        ok = s_handler(&cmd, resp_payload, &resp_len, s_handler_user);
    }
    else
    {
        ok = false;
    }

    (void)can_proto_encode_ack(s_node_id, idf.src, s_tx_seq++, cmd.cmd_id, cmd.txn_id, ok, resp_payload, resp_len, &ack);
    (void)can_submit_internal(&ack, CAN_TX_PRIO_HIGH, false, 0U, 0U, idf.src);

    s_dedupe.valid = 1U;
    s_dedupe.cmd_id = cmd.cmd_id;
    s_dedupe.txn_id = cmd.txn_id;
    s_dedupe.ok = (uint8_t)(ok ? 1U : 0U);
    s_dedupe.payload_len = (resp_len > sizeof(s_dedupe.payload)) ? sizeof(s_dedupe.payload) : resp_len;
    (void)memset(s_dedupe.payload, 0, sizeof(s_dedupe.payload));
    if (s_dedupe.payload_len > 0U)
    {
        (void)memcpy(s_dedupe.payload, resp_payload, s_dedupe.payload_len);
    }
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
