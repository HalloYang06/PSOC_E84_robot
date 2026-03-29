#ifndef CAN_TRANSPORT_H
#define CAN_TRANSPORT_H

#include <stdbool.h>
#include <stdint.h>

#include "can.h"
#include "can_proto.h"

typedef enum
{
    CAN_TX_PRIO_HIGH = 0,
    CAN_TX_PRIO_NORMAL = 1
} can_tx_prio_t;

typedef bool (*can_command_handler_t)(const can_proto_command_t *command,
                                      uint8_t *resp_payload,
                                      uint8_t *resp_len,
                                      void *user_ctx);

int32_t can_transport_init(CAN_HandleTypeDef *hcan);
void can_transport_register_command_handler(can_command_handler_t handler, void *user_ctx);
int32_t can_tx_submit(const can_message_t *message, can_tx_prio_t prio);
void can_transport_process(uint32_t now_ms);
void can_transport_poll_rx(void);
int32_t can_rx_dispatch(const can_message_t *message);
uint16_t can_transport_error_count(void);
uint8_t can_transport_queue_fill(void);

#endif
