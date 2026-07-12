#include "sensor_factory.h"

#include "bsp_MAX30100.h"
#include "bsp_MuElec.h"
#include "stm32f1xx.h"

#include "adc.h"
#include "i2c.h"
#include "tim.h"

typedef struct
{
    sensor_cfg_t cfg;
    sensor_status_t status;
    uint8_t started;
} emg_sensor_ctx_t;

typedef struct
{
    sensor_cfg_t cfg;
    sensor_status_t status;
    uint8_t started;
    uint16_t last_ir;
    uint16_t last_red;
} hr_sensor_ctx_t;

static volatile uint16_t s_emg_dma_samples[SENSOR_FACTORY_ADC_CHANNEL_COUNT];
static emg_sensor_ctx_t s_emg_ctx;
static hr_sensor_ctx_t s_hr_ctx;
static sensor_iface_t s_emg_iface;
static sensor_iface_t s_hr_iface;

static int32_t emg_init(sensor_iface_t *self, const sensor_cfg_t *cfg)
{
    emg_sensor_ctx_t *ctx = (emg_sensor_ctx_t *)self->ctx;

    if ((self == 0) || (ctx == 0) || (cfg == 0))
    {
        return -1;
    }

    ctx->cfg = *cfg;
    ctx->status.sample_count = 0U;
    ctx->status.error_count = 0U;
    ctx->status.healthy = 1U;
    ctx->started = 0U;

    if (bsp_muelec_bind(&hadc1, &htim1) != 0)
    {
        return -1;
    }
    return 0;
}

static int32_t emg_start(sensor_iface_t *self)
{
    emg_sensor_ctx_t *ctx = (emg_sensor_ctx_t *)self->ctx;
    if ((self == 0) || (ctx == 0))
    {
        return -1;
    }

    if (bsp_muelec_start_dma((uint16_t *)s_emg_dma_samples, SENSOR_FACTORY_ADC_CHANNEL_COUNT) != 0)
    {
        ctx->status.error_count++;
        ctx->status.healthy = 0U;
        return -1;
    }

    ctx->started = 1U;
    return 0;
}

static int32_t emg_stop(sensor_iface_t *self)
{
    emg_sensor_ctx_t *ctx = (emg_sensor_ctx_t *)self->ctx;
    if ((self == 0) || (ctx == 0))
    {
        return -1;
    }

    (void)bsp_muelec_stop_dma();
    ctx->started = 0U;
    return 0;
}

static int32_t emg_read(sensor_iface_t *self, uint16_t *sample)
{
    emg_sensor_ctx_t *ctx = (emg_sensor_ctx_t *)self->ctx;
    uint32_t primask;
    uint8_t channel;

    if ((self == 0) || (ctx == 0) || (sample == 0) || (ctx->started == 0U))
    {
        return -1;
    }
    if (ctx->cfg.channel_or_addr >= SENSOR_FACTORY_ADC_CHANNEL_COUNT)
    {
        return -1;
    }

    primask = __get_PRIMASK();
    __disable_irq();
    channel = ctx->cfg.channel_or_addr;
    *sample = s_emg_dma_samples[channel];
    if ((primask & 0x1U) == 0U)
    {
        __enable_irq();
    }
    return 0;
}

int32_t sensor_factory_read_emg_channels(uint16_t samples[SENSOR_FACTORY_ADC_CHANNEL_COUNT])
{
    uint32_t primask;
    uint8_t i;

    if ((samples == 0) || (s_emg_ctx.started == 0U))
    {
        return -1;
    }

    primask = __get_PRIMASK();
    __disable_irq();
    for (i = 0U; i < SENSOR_FACTORY_ADC_CHANNEL_COUNT; ++i)
    {
        samples[i] = s_emg_dma_samples[i];
    }
    if ((primask & 0x1U) == 0U)
    {
        __enable_irq();
    }
    return 0;
}

static int32_t emg_get_status(sensor_iface_t *self, sensor_status_t *status)
{
    emg_sensor_ctx_t *ctx = (emg_sensor_ctx_t *)self->ctx;
    if ((ctx == 0) || (status == 0))
    {
        return -1;
    }
    *status = ctx->status;
    return 0;
}

static int32_t hr_init(sensor_iface_t *self, const sensor_cfg_t *cfg)
{
    hr_sensor_ctx_t *ctx = (hr_sensor_ctx_t *)self->ctx;

    if ((self == 0) || (ctx == 0) || (cfg == 0))
    {
        return -1;
    }

    ctx->cfg = *cfg;
    ctx->status.sample_count = 0U;
    ctx->status.error_count = 0U;
    ctx->status.healthy = 1U;
    ctx->started = 0U;
    ctx->last_ir = 0U;
    ctx->last_red = 0U;

    if (bsp_max30100_init(&hi2c1) != 0)
    {
        ctx->status.error_count++;
        ctx->status.healthy = 0U;
        return -1;
    }
    return 0;
}

static int32_t hr_start(sensor_iface_t *self)
{
    hr_sensor_ctx_t *ctx = (hr_sensor_ctx_t *)self->ctx;
    if ((self == 0) || (ctx == 0))
    {
        return -1;
    }
    ctx->started = 1U;
    return 0;
}

static int32_t hr_stop(sensor_iface_t *self)
{
    hr_sensor_ctx_t *ctx = (hr_sensor_ctx_t *)self->ctx;
    if ((self == 0) || (ctx == 0))
    {
        return -1;
    }
    ctx->started = 0U;
    return 0;
}

static int32_t hr_read(sensor_iface_t *self, uint16_t *sample)
{
    hr_sensor_ctx_t *ctx = (hr_sensor_ctx_t *)self->ctx;
    int32_t rc;

    if ((self == 0) || (ctx == 0) || (sample == 0) || (ctx->started == 0U))
    {
        return -1;
    }

    rc = bsp_max30100_read_sample(&ctx->last_ir, &ctx->last_red);
    if (rc < 0)
    {
        ctx->status.error_count++;
        ctx->status.healthy = 0U;
        return -1;
    }
    if (rc > 0)
    {
        /* FIFO 当前无新样本，返回 1 交给上层忽略，不记为错误。 */
        return 1;
    }

    ctx->status.sample_count++;
    ctx->status.healthy = 1U;
    *sample = ctx->last_ir;
    return 0;
}

static int32_t hr_get_status(sensor_iface_t *self, sensor_status_t *status)
{
    hr_sensor_ctx_t *ctx = (hr_sensor_ctx_t *)self->ctx;
    if ((self == 0) || (ctx == 0) || (status == 0))
    {
        return -1;
    }

    *status = ctx->status;
    return 0;
}

sensor_iface_t *sensor_factory_create(sensor_type_t type, const sensor_cfg_t *cfg)
{
    if (cfg == 0)
    {
        return 0;
    }

    if (type == SENSOR_TYPE_EMG)
    {
        s_emg_iface.init = emg_init;
        s_emg_iface.start = emg_start;
        s_emg_iface.stop = emg_stop;
        s_emg_iface.read = emg_read;
        s_emg_iface.get_status = emg_get_status;
        s_emg_iface.ctx = &s_emg_ctx;
        s_emg_iface.type = SENSOR_TYPE_EMG;
        if (s_emg_iface.init(&s_emg_iface, cfg) != 0)
        {
            return 0;
        }
        return &s_emg_iface;
    }

    if (type == SENSOR_TYPE_HEART_RATE)
    {
        s_hr_iface.init = hr_init;
        s_hr_iface.start = hr_start;
        s_hr_iface.stop = hr_stop;
        s_hr_iface.read = hr_read;
        s_hr_iface.get_status = hr_get_status;
        s_hr_iface.ctx = &s_hr_ctx;
        s_hr_iface.type = SENSOR_TYPE_HEART_RATE;
        if (s_hr_iface.init(&s_hr_iface, cfg) != 0)
        {
            return 0;
        }
        return &s_hr_iface;
    }

    return 0;
}

void sensor_factory_on_emg_dma_complete_isr(void)
{
    if (s_emg_ctx.started != 0U)
    {
        /* DMA 完成中断只做计数，不做业务处理，保证 ISR 足够轻量。 */
        s_emg_ctx.status.sample_count++;
        s_emg_ctx.status.healthy = 1U;
    }
}
