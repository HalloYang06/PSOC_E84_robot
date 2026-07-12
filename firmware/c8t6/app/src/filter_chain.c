#include "filter_chain.h"

#include <string.h>

enum
{
    FILTER_PARAM_ALPHA = 1,
    FILTER_PARAM_WINDOW = 2
};

static void ema_init(filter_iface_t *self, float param0)
{
    ema_filter_ctx_t *ctx = (ema_filter_ctx_t *)self->ctx;
    if (ctx == 0)
    {
        return;
    }

    ctx->alpha = param0;
    if (ctx->alpha < 0.01f)
    {
        ctx->alpha = 0.01f;
    }
    if (ctx->alpha > 0.99f)
    {
        ctx->alpha = 0.99f;
    }
    ctx->state = 0.0f;
}

static float ema_process(filter_iface_t *self, float in)
{
    ema_filter_ctx_t *ctx = (ema_filter_ctx_t *)self->ctx;
    if (ctx == 0)
    {
        return in;
    }

    /* EMA 用于抑制高频抖动，同时保持较小计算开销。 */
    ctx->state = ctx->state + (ctx->alpha * (in - ctx->state));
    return ctx->state;
}

static void ema_reset(filter_iface_t *self)
{
    ema_filter_ctx_t *ctx = (ema_filter_ctx_t *)self->ctx;
    if (ctx != 0)
    {
        ctx->state = 0.0f;
    }
}

static int32_t ema_set_param(filter_iface_t *self, uint16_t param_id, float value)
{
    ema_filter_ctx_t *ctx = (ema_filter_ctx_t *)self->ctx;

    if (ctx == 0)
    {
        return -1;
    }

    if (param_id != FILTER_PARAM_ALPHA)
    {
        return -1;
    }

    if ((value < 0.01f) || (value > 0.99f))
    {
        return -1;
    }

    ctx->alpha = value;
    return 0;
}

static void moving_avg_init(filter_iface_t *self, float param0)
{
    moving_avg_filter_ctx_t *ctx = (moving_avg_filter_ctx_t *)self->ctx;
    uint8_t window = (uint8_t)param0;

    if (ctx == 0)
    {
        return;
    }

    if ((window == 0U) || (window > MOVING_AVG_MAX_WINDOW))
    {
        window = 4U;
    }

    ctx->window = window;
    ctx->count = 0U;
    ctx->index = 0U;
    ctx->sum = 0.0f;
    (void)memset(ctx->samples, 0, sizeof(ctx->samples));
}

static float moving_avg_process(filter_iface_t *self, float in)
{
    moving_avg_filter_ctx_t *ctx = (moving_avg_filter_ctx_t *)self->ctx;
    float out;

    if ((ctx == 0) || (ctx->window == 0U))
    {
        return in;
    }

    ctx->sum -= ctx->samples[ctx->index];
    ctx->samples[ctx->index] = in;
    ctx->sum += in;

    ctx->index = (uint8_t)((ctx->index + 1U) % ctx->window);
    if (ctx->count < ctx->window)
    {
        ctx->count++;
    }

    out = ctx->sum / (float)ctx->count;
    return out;
}

static void moving_avg_reset(filter_iface_t *self)
{
    moving_avg_filter_ctx_t *ctx = (moving_avg_filter_ctx_t *)self->ctx;
    if (ctx == 0)
    {
        return;
    }

    ctx->count = 0U;
    ctx->index = 0U;
    ctx->sum = 0.0f;
    (void)memset(ctx->samples, 0, sizeof(ctx->samples));
}

static int32_t moving_avg_set_param(filter_iface_t *self, uint16_t param_id, float value)
{
    moving_avg_filter_ctx_t *ctx = (moving_avg_filter_ctx_t *)self->ctx;
    uint8_t window;

    if ((ctx == 0) || (param_id != FILTER_PARAM_WINDOW))
    {
        return -1;
    }

    window = (uint8_t)value;
    if ((window == 0U) || (window > MOVING_AVG_MAX_WINDOW))
    {
        return -1;
    }

    ctx->window = window;
    moving_avg_reset(self);
    return 0;
}

void filter_create_ema(filter_iface_t *iface, ema_filter_ctx_t *ctx, float alpha)
{
    if ((iface == 0) || (ctx == 0))
    {
        return;
    }

    iface->ctx = ctx;
    iface->init = ema_init;
    iface->process = ema_process;
    iface->reset = ema_reset;
    iface->set_param = ema_set_param;
    iface->init(iface, alpha);
}

void filter_create_moving_avg(filter_iface_t *iface, moving_avg_filter_ctx_t *ctx, uint8_t window)
{
    if ((iface == 0) || (ctx == 0))
    {
        return;
    }

    iface->ctx = ctx;
    iface->init = moving_avg_init;
    iface->process = moving_avg_process;
    iface->reset = moving_avg_reset;
    iface->set_param = moving_avg_set_param;
    iface->init(iface, (float)window);
}

void filter_chain_init(filter_chain_t *chain)
{
    uint8_t i;

    if (chain == 0)
    {
        return;
    }

    chain->stage_count = 0U;
    for (i = 0U; i < FILTER_CHAIN_MAX_STAGES; ++i)
    {
        chain->stages[i] = 0;
    }
}

int32_t filter_chain_add_stage(filter_chain_t *chain, filter_iface_t *iface)
{
    if ((chain == 0) || (iface == 0))
    {
        return -1;
    }

    if (chain->stage_count >= FILTER_CHAIN_MAX_STAGES)
    {
        return -1;
    }

    chain->stages[chain->stage_count] = iface;
    chain->stage_count++;
    return 0;
}

float filter_chain_process(filter_chain_t *chain, float in)
{
    uint8_t i;
    float out = in;

    if (chain == 0)
    {
        return in;
    }

    for (i = 0U; i < chain->stage_count; ++i)
    {
        if ((chain->stages[i] != 0) && (chain->stages[i]->process != 0))
        {
            out = chain->stages[i]->process(chain->stages[i], out);
        }
    }

    return out;
}

void filter_chain_reset(filter_chain_t *chain)
{
    uint8_t i;

    if (chain == 0)
    {
        return;
    }

    for (i = 0U; i < chain->stage_count; ++i)
    {
        if ((chain->stages[i] != 0) && (chain->stages[i]->reset != 0))
        {
            chain->stages[i]->reset(chain->stages[i]);
        }
    }
}

int32_t filter_chain_set_param(filter_chain_t *chain, uint8_t stage_idx, uint16_t param_id, float value)
{
    filter_iface_t *iface;

    if ((chain == 0) || (stage_idx >= chain->stage_count))
    {
        return -1;
    }

    iface = chain->stages[stage_idx];
    if ((iface == 0) || (iface->set_param == 0))
    {
        return -1;
    }

    return iface->set_param(iface, param_id, value);
}
