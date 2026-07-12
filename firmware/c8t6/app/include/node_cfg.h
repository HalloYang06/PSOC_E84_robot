#ifndef NODE_CFG_H
#define NODE_CFG_H

#include <stdbool.h>
#include <stdint.h>

typedef struct
{
    uint16_t emg_rate_hz;
    uint16_t hr_rate_hz;
    uint16_t can_tx_rate_hz;
    uint8_t node_id;
    uint8_t host_id;
    uint8_t protocol_version;
    bool stream_enabled;
} node_cfg_t;

void node_cfg_load_default(node_cfg_t *cfg);

#endif
