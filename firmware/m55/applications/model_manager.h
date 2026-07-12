#ifndef MODEL_MANAGER_H
#define MODEL_MANAGER_H

#include <rtthread.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MODEL_MANAGER_MAX_SLOTS 6

typedef enum
{
    MODEL_SLOT_WAKE_WORD = 0,
    MODEL_SLOT_VAD = 1,
    MODEL_SLOT_ASR_FRONTEND = 2,
    MODEL_SLOT_IMU = 3,
    MODEL_SLOT_EMG = 4,
    MODEL_SLOT_FUSION = 5
} model_slot_id_t;

typedef enum
{
    MODEL_INPUT_NONE = 0,
    MODEL_INPUT_PCM_S16 = 1,
    MODEL_INPUT_FLOAT32 = 2,
    MODEL_INPUT_INT16 = 3,
    MODEL_INPUT_UINT16 = 4
} model_input_kind_t;

typedef struct
{
    rt_uint32_t arena_bytes;
    rt_uint32_t input_kind;
    rt_uint32_t sample_rate;
    rt_uint32_t channels;
    rt_uint32_t threshold_permille;
} model_slot_config_t;

typedef struct
{
    rt_bool_t ready;
    rt_uint32_t input_type;
    rt_uint32_t output_type;
    rt_uint32_t input_bytes;
    rt_uint32_t output_bytes;
    rt_uint32_t arena_bytes;
    rt_uint32_t input_kind;
    rt_uint32_t sample_rate;
    rt_uint32_t channels;
    rt_uint32_t threshold_permille;
} model_slot_info_t;

rt_err_t model_manager_init(void);
rt_err_t model_manager_configure_slot(model_slot_id_t slot, const model_slot_config_t *config);
rt_err_t model_manager_load_tflm_model(model_slot_id_t slot, const void *model_data, rt_size_t model_size);
rt_bool_t model_manager_is_ready(model_slot_id_t slot);
rt_err_t model_manager_get_info(model_slot_id_t slot, model_slot_info_t *info);
rt_err_t model_manager_run_pcm16(model_slot_id_t slot,
                                 const int16_t *samples,
                                 rt_size_t sample_count,
                                 float *score_out,
                                 int *detected_out);

#ifdef __cplusplus
}
#endif

#endif
