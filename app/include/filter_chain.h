#ifndef FILTER_CHAIN_H
#define FILTER_CHAIN_H

#include <stdint.h>

typedef struct filter_iface filter_iface_t;

struct filter_iface
{
    void (*init)(filter_iface_t *self, float param0);
    float (*process)(filter_iface_t *self, float in);
    void (*reset)(filter_iface_t *self);
    int32_t (*set_param)(filter_iface_t *self, uint16_t param_id, float value);
    void *ctx;
};

#define FILTER_CHAIN_MAX_STAGES 4U

typedef struct
{
    filter_iface_t *stages[FILTER_CHAIN_MAX_STAGES];
    uint8_t stage_count;
} filter_chain_t;

typedef struct
{
    float alpha;
    float state;
} ema_filter_ctx_t;

#define MOVING_AVG_MAX_WINDOW 16U

typedef struct
{
    uint8_t window;
    uint8_t count;
    uint8_t index;
    float sum;
    float samples[MOVING_AVG_MAX_WINDOW];
} moving_avg_filter_ctx_t;

void filter_chain_init(filter_chain_t *chain);
int32_t filter_chain_add_stage(filter_chain_t *chain, filter_iface_t *iface);
float filter_chain_process(filter_chain_t *chain, float in);
void filter_chain_reset(filter_chain_t *chain);
int32_t filter_chain_set_param(filter_chain_t *chain, uint8_t stage_idx, uint16_t param_id, float value);

void filter_create_ema(filter_iface_t *iface, ema_filter_ctx_t *ctx, float alpha);
void filter_create_moving_avg(filter_iface_t *iface, moving_avg_filter_ctx_t *ctx, uint8_t window);

#endif
