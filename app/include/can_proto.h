#ifndef CAN_PROTO_H
#define CAN_PROTO_H

#include <stdint.h>

#include "app_types.h"
#include "data_fusion.h"

#define F103_CAN_ID_CTRL_RX 0x7C0U
#define F103_CAN_ID_ACK_TX 0x7C1U
#define F103_CAN_ID_SENSOR_TX 0x7C2U
#define F103_CAN_ID_HEALTH_TX 0x7C3U

typedef enum
{
    CAN_CMD_SET_RATE = 0x01,
    CAN_CMD_SET_FILTER_PARAM = 0x02,
    CAN_CMD_START_STREAM = 0x03,
    CAN_CMD_STOP_STREAM = 0x04,
    CAN_CMD_GET_STATUS = 0x05,
    CAN_CMD_SET_STATE = 0x06
} can_cmd_id_t;

typedef struct
{
    uint32_t id;
    uint8_t dlc;
    uint8_t data[8];
} can_message_t;

typedef struct
{
    uint8_t cmd_id;
    uint8_t seq;
    uint8_t payload[6];
    uint8_t payload_len;
} can_proto_command_t;

int32_t can_proto_encode_sensor(const fusion_snapshot_t *snapshot, can_message_t *message);
int32_t can_proto_encode_health(node_state_t state,
                                uint16_t error_count,
                                uint8_t q_fill,
                                uint16_t rx_count,
                                uint16_t tx_count,
                                can_message_t *message);
int32_t can_proto_decode_control(const can_message_t *message, can_proto_command_t *command);
int32_t can_proto_encode_ack(uint8_t cmd_id,
                             uint8_t seq,
                             uint8_t status,
                             const uint8_t *resp_payload,
                             uint8_t resp_len,
                             can_message_t *message);

#endif
