#include "can_proto.h"

#include <string.h>

enum
{
    CAN_ID_PRIORITY_SHIFT = 26,
    CAN_ID_SRC_SHIFT = 21,
    CAN_ID_DST_SHIFT = 16,
    CAN_ID_TYPE_SHIFT = 12,
    CAN_ID_FLAGS_SHIFT = 8,
    CAN_ID_SEQ_SHIFT = 0
};

static uint16_t clamp_u16(float x)
{
    if (x < 0.0f)
    {
        return 0U;
    }
    if (x > 65535.0f)
    {
        return 65535U;
    }
    return (uint16_t)x;
}

static int16_t clamp_i16(float x)
{
    if (x < -32768.0f)
    {
        return -32768;
    }
    if (x > 32767.0f)
    {
        return 32767;
    }
    return (int16_t)x;
}

uint32_t can_proto_build_id(const can_proto_id_fields_t *fields)
{
    uint32_t id = 0U;

    if (fields == 0)
    {
        return 0U;
    }

    id |= ((uint32_t)(fields->priority & 0x07U) << CAN_ID_PRIORITY_SHIFT);
    id |= ((uint32_t)(fields->src & 0x1FU) << CAN_ID_SRC_SHIFT);
    id |= ((uint32_t)(fields->dst & 0x1FU) << CAN_ID_DST_SHIFT);
    id |= ((uint32_t)(fields->type & 0x0FU) << CAN_ID_TYPE_SHIFT);
    id |= ((uint32_t)(fields->flags & 0x0FU) << CAN_ID_FLAGS_SHIFT);
    id |= ((uint32_t)(fields->seq) << CAN_ID_SEQ_SHIFT);
    return id;
}

void can_proto_parse_id(uint32_t id, can_proto_id_fields_t *fields)
{
    if (fields == 0)
    {
        return;
    }

    fields->priority = (uint8_t)((id >> CAN_ID_PRIORITY_SHIFT) & 0x07U);
    fields->src = (uint8_t)((id >> CAN_ID_SRC_SHIFT) & 0x1FU);
    fields->dst = (uint8_t)((id >> CAN_ID_DST_SHIFT) & 0x1FU);
    fields->type = (uint8_t)((id >> CAN_ID_TYPE_SHIFT) & 0x0FU);
    fields->flags = (uint8_t)((id >> CAN_ID_FLAGS_SHIFT) & 0x0FU);
    fields->seq = (uint8_t)(id & 0xFFU);
}

int32_t can_proto_encode_telemetry(const fusion_snapshot_t *snapshot,
                                   uint8_t src,
                                   uint8_t dst,
                                   uint8_t seq,
                                   can_message_t *message)
{
    can_proto_id_fields_t idf;
    int16_t emg_filtered_q;
    uint16_t hr_filtered_q;
    uint8_t flags = 0U;

    if ((snapshot == 0) || (message == 0))
    {
        return -1;
    }

    idf.priority = 1U;
    idf.src = src;
    idf.dst = dst;
    idf.type = (uint8_t)CAN_MSG_TELEMETRY;
    idf.flags = 0U;
    idf.seq = seq;

    emg_filtered_q = clamp_i16(snapshot->emg_filtered);
    hr_filtered_q = clamp_u16(snapshot->hr_filtered * 10.0f);
    if (snapshot->emg_valid != 0U)
    {
        flags |= 0x01U;
    }
    if (snapshot->hr_valid != 0U)
    {
        flags |= 0x02U;
    }

    message->id = can_proto_build_id(&idf);
    message->dlc = 8U;
    message->data[0] = (uint8_t)(snapshot->emg_raw & 0xFFU);
    message->data[1] = (uint8_t)((snapshot->emg_raw >> 8) & 0xFFU);
    message->data[2] = (uint8_t)(emg_filtered_q & 0xFF);
    message->data[3] = (uint8_t)((emg_filtered_q >> 8) & 0xFF);
    message->data[4] = (uint8_t)(snapshot->hr_raw & 0xFFU);
    message->data[5] = (uint8_t)((snapshot->hr_raw >> 8) & 0xFFU);
    message->data[6] = (uint8_t)(hr_filtered_q & 0xFFU);
    message->data[7] = flags;
    return 0;
}

int32_t can_proto_encode_heartbeat(node_state_t state,
                                   uint8_t src,
                                   uint8_t dst,
                                   uint8_t seq,
                                   uint16_t error_count,
                                   can_message_t *message)
{
    can_proto_id_fields_t idf;

    if (message == 0)
    {
        return -1;
    }

    idf.priority = 0U;
    idf.src = src;
    idf.dst = dst;
    idf.type = (uint8_t)CAN_MSG_HEARTBEAT;
    idf.flags = 0U;
    idf.seq = seq;

    message->id = can_proto_build_id(&idf);
    message->dlc = 8U;
    message->data[0] = (uint8_t)state;
    message->data[1] = (uint8_t)(error_count & 0xFFU);
    message->data[2] = (uint8_t)((error_count >> 8) & 0xFFU);
    message->data[3] = 0U;
    message->data[4] = 0U;
    message->data[5] = 0U;
    message->data[6] = 0U;
    message->data[7] = 0U;
    return 0;
}

int32_t can_proto_decode_command(const can_message_t *message, can_proto_command_t *command)
{
    can_proto_id_fields_t idf;
    uint8_t payload_len;

    if ((message == 0) || (command == 0))
    {
        return -1;
    }

    can_proto_parse_id(message->id, &idf);
    if (idf.type != (uint8_t)CAN_MSG_COMMAND)
    {
        return -1;
    }

    if (message->dlc < 2U)
    {
        return -1;
    }

    command->cmd_id = message->data[0];
    command->txn_id = message->data[1];

    payload_len = (uint8_t)(message->dlc - 2U);
    if (payload_len > sizeof(command->payload))
    {
        payload_len = sizeof(command->payload);
    }
    command->payload_len = payload_len;
    if (payload_len > 0U)
    {
        (void)memcpy(command->payload, &message->data[2], payload_len);
    }
    return 0;
}

int32_t can_proto_encode_ack(uint8_t src,
                             uint8_t dst,
                             uint8_t seq,
                             uint8_t cmd_id,
                             uint8_t txn_id,
                             bool ok,
                             const uint8_t *resp_payload,
                             uint8_t resp_len,
                             can_message_t *message)
{
    can_proto_id_fields_t idf;
    uint8_t max_resp;

    if (message == 0)
    {
        return -1;
    }

    idf.priority = 0U;
    idf.src = src;
    idf.dst = dst;
    idf.type = (uint8_t)(ok ? CAN_MSG_ACK : CAN_MSG_NACK);
    idf.flags = 0U;
    idf.seq = seq;

    message->id = can_proto_build_id(&idf);
    message->data[0] = cmd_id;
    message->data[1] = txn_id;
    message->data[2] = (uint8_t)(ok ? 0U : 1U);

    max_resp = 5U;
    if ((resp_payload != 0) && (resp_len > 0U))
    {
        if (resp_len > max_resp)
        {
            resp_len = max_resp;
        }
        (void)memcpy(&message->data[3], resp_payload, resp_len);
    }
    else
    {
        resp_len = 0U;
    }

    while ((3U + resp_len) < 8U)
    {
        message->data[3U + resp_len] = 0U;
        resp_len++;
    }
    message->dlc = 8U;
    return 0;
}

int32_t can_proto_encode_fragment(uint8_t src,
                                  uint8_t dst,
                                  uint8_t seq,
                                  const can_proto_fragment_t *fragment,
                                  can_message_t *message)
{
    can_proto_id_fields_t idf;

    if ((fragment == 0) || (message == 0) || (fragment->payload_len > 4U))
    {
        return -1;
    }

    idf.priority = 1U;
    idf.src = src;
    idf.dst = dst;
    idf.type = (uint8_t)CAN_MSG_FRAGMENT;
    idf.flags = 0U;
    idf.seq = seq;

    message->id = can_proto_build_id(&idf);
    message->dlc = 8U;
    message->data[0] = fragment->session_id;
    message->data[1] = fragment->index;
    message->data[2] = fragment->total;
    message->data[3] = fragment->payload_len;
    message->data[4] = 0U;
    message->data[5] = 0U;
    message->data[6] = 0U;
    message->data[7] = 0U;
    if (fragment->payload_len > 0U)
    {
        (void)memcpy(&message->data[4], fragment->payload, fragment->payload_len);
    }
    return 0;
}

int32_t can_proto_decode_fragment(const can_message_t *message, can_proto_fragment_t *fragment)
{
    can_proto_id_fields_t idf;

    if ((message == 0) || (fragment == 0))
    {
        return -1;
    }

    can_proto_parse_id(message->id, &idf);
    if (idf.type != (uint8_t)CAN_MSG_FRAGMENT)
    {
        return -1;
    }

    if (message->dlc != 8U)
    {
        return -1;
    }

    fragment->session_id = message->data[0];
    fragment->index = message->data[1];
    fragment->total = message->data[2];
    fragment->payload_len = message->data[3];
    if (fragment->payload_len > 4U)
    {
        return -1;
    }

    if (fragment->payload_len > 0U)
    {
        (void)memcpy(fragment->payload, &message->data[4], fragment->payload_len);
    }
    return 0;
}
