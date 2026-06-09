
/*****************************************************************************
bulk_delay_measurement.h: Bulk delay estimation header file.

Copyright 2023 Infineon Technologies.  ALL RIGHTS RESERVED.
******************************************************************************/

#ifndef __BULK_DELAY_MEASUREMENT_H
#define __BULK_DELAY_MEASUREMENT_H

#if defined(__cplusplus)
extern "C" {
#endif

#include <stdint.h>
#include "arm_math.h"

typedef enum
{
    AFE_BDM_STOPPED = 0,
    AFE_BDM_STARTED,
    AFE_BDM_SUCCESS,
    AFE_BDM_FAILURE,
} afe_bdm_states_t;

typedef struct {
    uint32_t frame_size;
    uint32_t sampling_rate;
} param_struct_t;

typedef struct {
    arm_rfft_fast_instance_f32 arm_rfft_fast_instance;
    uint32_t frame_size;
    uint32_t sampling_rate;
    uint32_t min_num_valid_delays;
    uint32_t max_num_repeat;
    int16_t* swept_sine_ref;
    int16_t* swept_sine_mic;
    float* swept_sine_resp;
    int32_t swept_sine_length;
    int32_t swept_sine_ref_length;
    int32_t swept_sine_input_count;
    int32_t swept_sine_output_count;
    int32_t swept_sine_repeat_count;
    int32_t swept_sine_state;
    int32_t total_delay_samples;
    int32_t valid_delay_count;
    int32_t bulk_delay_msec;
} bdm_struct_t;

int32_t afe_bdm_init(param_struct_t* param_struct_pt, bdm_struct_t* bdm_struct_pt);
void afe_bdm_free(bdm_struct_t* bdm_struct_pt);
int32_t afe_bdm_process(bdm_struct_t* bdm_struct_pt, int16_t* ref_frame, int16_t* mic_frame, int16_t* resp_frame);
int16_t* afe_bdm_get_ref_signal(bdm_struct_t* bdm_struct_pt);
int32_t afe_bdm_get_ref_length(bdm_struct_t* bdm_struct_pt);
int32_t afe_bdm_get_state(bdm_struct_t* bdm_struct_pt);
int32_t afe_bdm_get_bulk_delay(bdm_struct_t* bdm_struct_pt);

#if defined(__cplusplus)
}
#endif

#endif // __BULK_DELAY_MEASUREMENT_H