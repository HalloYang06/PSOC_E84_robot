#ifndef INTENT_TFLM_RUNTIME_H
#define INTENT_TFLM_RUNTIME_H

#include <rtthread.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define INTENT_TFLM_FEATURE_COUNT 20
#define INTENT_TFLM_CLASS_COUNT 4

typedef struct
{
    int predicted_index;
    rt_uint16_t confidence_permille;
    int8_t output_int8[INTENT_TFLM_CLASS_COUNT];
    const char *label;
} intent_tflm_result_t;

int intent_tflm_runtime_init(void);
int intent_tflm_runtime_infer_int8(const int8_t *input,
                                   size_t input_len,
                                   intent_tflm_result_t *result);
const char *intent_tflm_label(int index);

#ifdef __cplusplus
}
#endif

#endif
