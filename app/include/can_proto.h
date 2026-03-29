#ifndef CAN_PROTO_H
#define CAN_PROTO_H

#include <stdbool.h>
#include <stdint.h>

#include "app_types.h"
#include "data_fusion.h"

typedef enum
{
    CAN_MSG_TELEMETRY = 0x1,
    CAN_MSG_COMMAND = 0x2,
    CAN_MSG_ACK = 0x3,
    CAN_MSG_NACK = 0x4,
    CAN_MSG_HEARTBEAT = 0x5,
    CAN_MSG_FRAGMENT = 0x6
} can_msg_type_t;

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
    uint8_t priority;
    uint8_t src;
    uint8_t dst;
    uint8_t type;
    uint8_t flags;
    uint8_t seq;
} can_proto_id_fields_t;

typedef struct
{
    uint8_t cmd_id;
    uint8_t txn_id;
    uint8_t payload[6];
    uint8_t payload_len;
} can_proto_command_t;

typedef struct
{
    uint8_t session_id;
    uint8_t index;
    uint8_t total;
    uint8_t payload_len;
    uint8_t payload[4];
} can_proto_fragment_t;

uint32_t can_proto_build_id(const can_proto_id_fields_t *fields);
void can_proto_parse_id(uint32_t id, can_proto_id_fields_t *fields);

int32_t can_proto_encode_telemetry(const fusion_snapshot_t *snapshot,
                                   uint8_t src,
                                   uint8_t dst,
                                   uint8_t seq,
                                   can_message_t *message);
int32_t can_proto_encode_heartbeat(node_state_t state,
                                   uint8_t src,
                                   uint8_t dst,
                                   uint8_t seq,
                                   uint16_t error_count,
                                   can_message_t *message);
int32_t can_proto_decode_command(const can_message_t *message, can_proto_command_t *command);
int32_t can_proto_encode_ack(uint8_t src,
                             uint8_t dst,
                             uint8_t seq,
                             uint8_t cmd_id,
                             uint8_t txn_id,
                             bool ok,
                             const uint8_t *resp_payload,
                             uint8_t resp_len,
                             can_message_t *message);
int32_t can_proto_encode_fragment(uint8_t src,
                                  uint8_t dst,
                                  uint8_t seq,
                                  const can_proto_fragment_t *fragment,
                                  can_message_t *message);
int32_t can_proto_decode_fragment(const can_message_t *message, can_proto_fragment_t *fragment);

#endif
