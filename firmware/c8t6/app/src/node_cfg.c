#include "node_cfg.h"

void node_cfg_load_default(node_cfg_t *cfg)
{
    if (cfg == 0)
    {
        return;
    }

    cfg->emg_rate_hz = 1000U;
    cfg->hr_rate_hz = 50U;
    cfg->can_tx_rate_hz = 100U;
    cfg->node_id = 0x03U;
    cfg->host_id = 0x01U;
    cfg->protocol_version = 1U;
    cfg->stream_enabled = false;
}
