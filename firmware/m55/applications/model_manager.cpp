#include "model_manager.h"

#include <rtdevice.h>
#include <rtthread.h>

#include "tensorflow/lite/c/common.h"
#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/version.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace
{
struct ModelSlot
{
    bool configured;
    bool ready;
    model_slot_config_t config;
    const unsigned char *model_data;
    size_t model_size;
    const tflite::Model *model;
    tflite::MicroInterpreter *interpreter;
    TfLiteTensor *input;
    TfLiteTensor *output;
    uint8_t *tensor_arena;
};

static tflite::MicroErrorReporter g_micro_error_reporter;
static tflite::AllOpsResolver g_all_ops_resolver;
static bool g_initialized = false;
static ModelSlot g_slots[MODEL_MANAGER_MAX_SLOTS];

static bool valid_slot(model_slot_id_t slot)
{
    return (slot >= MODEL_SLOT_WAKE_WORD) && (slot <= MODEL_SLOT_FUSION);
}

static model_slot_config_t default_config_for(model_slot_id_t slot)
{
    model_slot_config_t cfg;

    rt_memset(&cfg, 0, sizeof(cfg));
    cfg.arena_bytes = 64U * 1024U;
    cfg.threshold_permille = 750U;

    switch (slot)
    {
    case MODEL_SLOT_WAKE_WORD:
    case MODEL_SLOT_VAD:
    case MODEL_SLOT_ASR_FRONTEND:
        cfg.input_kind = MODEL_INPUT_PCM_S16;
        cfg.sample_rate = 16000U;
        cfg.channels = 1U;
        break;
    case MODEL_SLOT_IMU:
    case MODEL_SLOT_EMG:
    case MODEL_SLOT_FUSION:
        cfg.input_kind = MODEL_INPUT_FLOAT32;
        cfg.sample_rate = 0U;
        cfg.channels = 0U;
        break;
    default:
        break;
    }

    return cfg;
}

static rt_err_t ensure_initialized()
{
    int i;

    if (g_initialized)
    {
        return RT_EOK;
    }

    rt_memset(g_slots, 0, sizeof(g_slots));
    for (i = 0; i < MODEL_MANAGER_MAX_SLOTS; i++)
    {
        g_slots[i].config = default_config_for((model_slot_id_t)i);
    }
    g_initialized = true;
    return RT_EOK;
}

static rt_err_t allocate_arena(ModelSlot &slot)
{
    if (slot.tensor_arena != RT_NULL)
    {
        return RT_EOK;
    }

    slot.tensor_arena = static_cast<uint8_t *>(rt_malloc_align(slot.config.arena_bytes, 16));
    if (slot.tensor_arena == RT_NULL)
    {
        return -RT_ENOMEM;
    }

    rt_memset(slot.tensor_arena, 0, slot.config.arena_bytes);
    return RT_EOK;
}

static rt_err_t rebuild_interpreter(ModelSlot &slot)
{
    if ((slot.model_data == nullptr) || (slot.model_size == 0U))
    {
        return -RT_EINVAL;
    }

    slot.model = tflite::GetModel(slot.model_data);
    if ((slot.model == nullptr) || (slot.model->version() != TFLITE_SCHEMA_VERSION))
    {
        return -RT_ERROR;
    }

    rt_memset(slot.tensor_arena, 0, slot.config.arena_bytes);
    delete slot.interpreter;
    slot.interpreter = new tflite::MicroInterpreter(
        slot.model,
        g_all_ops_resolver,
        slot.tensor_arena,
        slot.config.arena_bytes,
        &g_micro_error_reporter);

    if (slot.interpreter == nullptr)
    {
        return -RT_ENOMEM;
    }

    if (slot.interpreter->AllocateTensors() != kTfLiteOk)
    {
        delete slot.interpreter;
        slot.interpreter = nullptr;
        return -RT_ERROR;
    }

    slot.input = slot.interpreter->input(0);
    slot.output = slot.interpreter->output(0);
    slot.ready = (slot.input != nullptr) && (slot.output != nullptr);
    return slot.ready ? RT_EOK : -RT_ERROR;
}

static rt_err_t fill_input_from_pcm16(ModelSlot &slot, const int16_t *samples, rt_size_t sample_count)
{
    rt_size_t i;
    rt_size_t needed;

    if ((slot.input == nullptr) || (samples == RT_NULL))
    {
        return -RT_EINVAL;
    }

    needed = slot.input->bytes / ((slot.input->type == kTfLiteFloat32) ? sizeof(float) : sizeof(int8_t));
    if ((needed == 0U) || (sample_count < needed))
    {
        return -RT_EINVAL;
    }

    if (slot.input->type == kTfLiteFloat32)
    {
        float *dst = slot.input->data.f;
        for (i = 0; i < needed; i++)
        {
            dst[i] = (float)samples[i] / 32768.0f;
        }
        return RT_EOK;
    }

    if (slot.input->type == kTfLiteInt8)
    {
        int8_t *dst = slot.input->data.int8;
        const float scale = (slot.input->params.scale == 0.0f) ? 1.0f : slot.input->params.scale;
        const int zero_point = slot.input->params.zero_point;

        for (i = 0; i < needed; i++)
        {
            float normalized = (float)samples[i] / 32768.0f;
            int quantized = (int)(normalized / scale) + zero_point;
            if (quantized > 127)
            {
                quantized = 127;
            }
            else if (quantized < -128)
            {
                quantized = -128;
            }
            dst[i] = (int8_t)quantized;
        }
        return RT_EOK;
    }

    return -RT_ENOSYS;
}

static float read_output_score(ModelSlot &slot)
{
    if (slot.output == nullptr)
    {
        return 0.0f;
    }

    if (slot.output->type == kTfLiteFloat32)
    {
        return slot.output->data.f[0];
    }

    if (slot.output->type == kTfLiteInt8)
    {
        return ((float)slot.output->data.int8[0] - (float)slot.output->params.zero_point) *
               slot.output->params.scale;
    }

    if (slot.output->type == kTfLiteUInt8)
    {
        return ((float)slot.output->data.uint8[0] - (float)slot.output->params.zero_point) *
               slot.output->params.scale;
    }

    return 0.0f;
}
} // namespace

extern "C" rt_err_t model_manager_init(void)
{
    return ensure_initialized();
}

extern "C" rt_err_t model_manager_configure_slot(model_slot_id_t slot, const model_slot_config_t *config)
{
    rt_err_t err;
    ModelSlot *s;

    err = ensure_initialized();
    if (err != RT_EOK)
    {
        return err;
    }
    if (!valid_slot(slot) || (config == RT_NULL))
    {
        return -RT_EINVAL;
    }

    s = &g_slots[(int)slot];
    s->config = *config;
    s->configured = true;

    if (s->tensor_arena != RT_NULL)
    {
        rt_free_align(s->tensor_arena);
        s->tensor_arena = RT_NULL;
    }
    delete s->interpreter;
    s->interpreter = nullptr;
    s->input = nullptr;
    s->output = nullptr;
    s->ready = false;

    return RT_EOK;
}

extern "C" rt_err_t model_manager_load_tflm_model(model_slot_id_t slot, const void *model_data, rt_size_t model_size)
{
    rt_err_t err;
    ModelSlot *s;

    err = ensure_initialized();
    if (err != RT_EOK)
    {
        return err;
    }
    if (!valid_slot(slot) || (model_data == RT_NULL) || (model_size == 0U))
    {
        return -RT_EINVAL;
    }

    s = &g_slots[(int)slot];
    err = allocate_arena(*s);
    if (err != RT_EOK)
    {
        return err;
    }

    s->model_data = static_cast<const unsigned char *>(model_data);
    s->model_size = (size_t)model_size;
    return rebuild_interpreter(*s);
}

extern "C" rt_bool_t model_manager_is_ready(model_slot_id_t slot)
{
    if (!valid_slot(slot))
    {
        return RT_FALSE;
    }
    return g_slots[(int)slot].ready ? RT_TRUE : RT_FALSE;
}

extern "C" rt_err_t model_manager_get_info(model_slot_id_t slot, model_slot_info_t *info)
{
    ModelSlot *s;

    if (!valid_slot(slot) || (info == RT_NULL))
    {
        return -RT_EINVAL;
    }

    s = &g_slots[(int)slot];
    rt_memset(info, 0, sizeof(*info));
    info->ready = s->ready ? RT_TRUE : RT_FALSE;
    info->arena_bytes = s->config.arena_bytes;
    info->input_kind = s->config.input_kind;
    info->sample_rate = s->config.sample_rate;
    info->channels = s->config.channels;
    info->threshold_permille = s->config.threshold_permille;

    if (s->ready)
    {
        info->input_type = (rt_uint32_t)s->input->type;
        info->output_type = (rt_uint32_t)s->output->type;
        info->input_bytes = (rt_uint32_t)s->input->bytes;
        info->output_bytes = (rt_uint32_t)s->output->bytes;
    }

    return RT_EOK;
}

extern "C" rt_err_t model_manager_run_pcm16(model_slot_id_t slot,
                                            const int16_t *samples,
                                            rt_size_t sample_count,
                                            float *score_out,
                                            int *detected_out)
{
    ModelSlot *s;
    float score;
    rt_err_t err;

    if (!valid_slot(slot))
    {
        return -RT_EINVAL;
    }

    s = &g_slots[(int)slot];
    if (!s->ready)
    {
        return -RT_EEMPTY;
    }
    if (s->config.input_kind != MODEL_INPUT_PCM_S16)
    {
        return -RT_ENOSYS;
    }

    err = fill_input_from_pcm16(*s, samples, sample_count);
    if (err != RT_EOK)
    {
        return err;
    }

    if (s->interpreter->Invoke() != kTfLiteOk)
    {
        return -RT_ERROR;
    }

    score = read_output_score(*s);
    if (score_out != RT_NULL)
    {
        *score_out = score;
    }
    if (detected_out != RT_NULL)
    {
        *detected_out = (score * 1000.0f >= (float)s->config.threshold_permille) ? 1 : 0;
    }

    return RT_EOK;
}
