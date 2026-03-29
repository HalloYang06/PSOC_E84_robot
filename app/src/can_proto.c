#include "can_proto.h"

#include <string.h>

static uint8_t clamp_u8(float x)
{
    if (x < 0.0f)
    {
        return 0U;
    }
    if (x > 255.0f)
    {
        return 255U;
    }
    return (uint8_t)x;
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

int32_t can_proto_encode_sensor(const fusion_snapshot_t *snapshot, can_message_t *message)
{
    int16_t emg_filtered;
    uint8_t hr_filtered;
    uint8_t flags = 0U;

    if ((snapshot == 0) || (message == 0))
    {
        return -1;
    }

    emg_filtered = clamp_i16(snapshot->emg_filtered);
    hr_filtered = clamp_u8(snapshot->hr_filtered);
    if (snapshot->emg_valid != 0U)
    {
        flags |= 0x01U;
    }
    if (snapshot->hr_valid != 0U)
    {
        flags |= 0x02U;
    }

    message->id = F103_CAN_ID_SENSOR_TX;
    message->dlc = 8U;
    message->data[0] = (uint8_t)(snapshot->emg_raw & 0xFFU);
    message->data[1] = (uint8_t)((snapshot->emg_raw >> 8) & 0xFFU);
    message->data[2] = (uint8_t)(emg_filtered & 0xFF);
    message->data[3] = (uint8_t)((emg_filtered >> 8) & 0xFF);
    message->data[4] = (uint8_t)(snapshot->hr_raw & 0xFFU);
    message->data[5] = (uint8_t)((snapshot->hr_raw >> 8) & 0xFFU);
    message->data[6] = hr_filtered;
    message->data[7] = flags;
    return 0;
}

int32_t can_proto_encode_health(node_state_t state, uint16_t error_count, uint8_t q_fill, can_message_t *message)
{
    if (message == 0)
    {
        return -1;
    }

    message->id = F103_CAN_ID_HEALTH_TX;
    message->dlc = 8U;
    message->data[0] = (uint8_t)state;
    message->data[1] = (uint8_t)(error_count & 0xFFU);
    message->data[2] = (uint8_t)((error_count >> 8) & 0xFFU);
    message->data[3] = q_fill;
    message->data[4] = 0U;
    message->data[5] = 0U;
    message->data[6] = 0U;
    message->data[7] = 0U;
    return 0;
}

int32_t can_proto_decode_control(const can_message_t *message, can_proto_command_t *command)
{
    if ((message == 0) || (command == 0))
    {
        return -1;
    }

    if ((message->id != F103_CAN_ID_CTRL_RX) || (message->dlc != 8U))
    {
        return -1;
    }

    command->cmd_id = message->data[0];
    command->seq = message->data[1];
    command->payload_len = 6U;
    (void)memcpy(command->payload, &message->data[2], 6U);
    return 0;
}

int32_t can_proto_encode_ack(uint8_t cmd_id,
                             uint8_t seq,
                             uint8_t status,
                             const uint8_t *resp_payload,
                             uint8_t resp_len,
                             can_message_t *message)
{
    if (message == 0)
    {
        return -1;
    }

    message->id = F103_CAN_ID_ACK_TX;
    message->dlc = 8U;
    message->data[0] = cmd_id;
    message->data[1] = seq;
    message->data[2] = status;
    message->data[3] = 0U;
    message->data[4] = 0U;
    message->data[5] = 0U;
    message->data[6] = 0U;
    message->data[7] = 0U;

    if ((resp_payload != 0) && (resp_len > 0U))
    {
        if (resp_len > 5U)
        {
            resp_len = 5U;
        }
        (void)memcpy(&message->data[3], resp_payload, resp_len);
    }
    return 0;
}
