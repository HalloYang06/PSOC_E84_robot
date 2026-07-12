/******************************************************************************
* File Name: mtb_ml_model_16x8_tflm_16x8.cpp
*
* Description: This file contains API calls to initialize and invoke Tflite-Micro
*              inference for model 16x8 generated from CY ML software.
*
*
*******************************************************************************
* (c) 2019-2022, Cypress Semiconductor Corporation (an Infineon company) or
* an affiliate of Cypress Semiconductor Corporation.  All rights reserved.
*******************************************************************************
* This software, including source code, documentation and related materials
* ("Software"), is owned by Cypress Semiconductor Corporation or one of its
* subsidiaries ("Cypress") and is protected by and subject to worldwide patent
* protection (United States and foreign), United States copyright laws and
* international treaty provisions. Therefore, you may use this Software only
* as provided in the license agreement accompanying the software package from
* which you obtained this Software ("EULA").
*
* If no EULA applies, Cypress hereby grants you a personal, non-exclusive,
* non-transferable license to copy, modify, and compile the Software source
* code solely for use in connection with Cypress's integrated circuit products.
* Any reproduction, modification, translation, compilation, or representation
* of this Software except as specified above is prohibited without the express
* written permission of Cypress.
*
* Disclaimer: THIS SOFTWARE IS PROVIDED AS-IS, WITH NO WARRANTY OF ANY KIND,
* EXPRESS OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, NONINFRINGEMENT, IMPLIED
* WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. Cypress
* reserves the right to make changes to the Software without notice. Cypress
* does not assume any liability arising out of the application or use of the
* Software or any product or circuit described in the Software. Cypress does
* not authorize its products for use in any products where a malfunction or
* failure of the Cypress product may reasonably be expected to result in
* significant property damage, injury or death ("High Risk Product"). By
* including Cypress's product in a High Risk Product, the manufacturer of such
* system or application assumes all risk of such use and in doing so agrees to
* indemnity Cypress against all liability.
*******************************************************************************/
#include <stdlib.h>
#include <inttypes.h>
#include "mtb_ml.h"
#include "mtb_ml_model_16x8.h"

#include <climits>

#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_op_resolver.h"
#include "tensorflow/lite/micro/recording_micro_interpreter.h"
#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_utils.h"
#include "tensorflow/lite/kernels/internal/tensor_ctypes.h"


namespace tflite {

static tflite::AllOpsResolver resolver;

template <typename inputT>
class MTBTFLiteMicro {
 public:
  // The lifetimes of model, op_resolver, tensor_arena must exceed
  // that of the created MicroBenchmarkRunner object.
  MTBTFLiteMicro(const uint8_t* model,
                       uint8_t* tensor_arena, int tensor_arena_size,
                       const tflite::MicroOpResolver& op_resolver)
      : interpreter_(GetModel(model), op_resolver, tensor_arena,
                     tensor_arena_size, &error_reporter_) {
      allocate_status_ = interpreter_.AllocateTensors();
      model_ = GetModel(model);
  }

  TfLiteStatus RunSingleIteration() {
    // Run the model on this input and return the status.
    return interpreter_.Invoke();
  }

  TfLiteTensor* Input(int index = 0)  { return interpreter_.input(index); }
  TfLiteTensor* Output(int index = 0) { return interpreter_.output(index); }

  TfLiteStatus AllocationStatus() { return allocate_status_; }

  /* Use for RNN state control. This will free subgraphs to the reset state */
  TfLiteStatus reset_all_variables() { return kTfLiteOk; }

  inputT* input_ptr(int index = 0) { return GetTensorData<inputT>(Input(index)); }
  size_t input_size(int index = 0) { return interpreter_.input(index)->bytes; }
  size_t input_elements(int index = 0) { return tflite::ElementCount(*(interpreter_.input(index)->dims)); }
  int    input_dims_len(int index=0) {return interpreter_.input(index)->dims->size; }
  int *  input_dims( int index=0) { return &interpreter_.input(index)->dims->data[0]; }
  int    input_zero_point( int index=0) { return interpreter_.input(index)->params.zero_point; }
  float  input_scale( int index=0) { return interpreter_.input(index)->params.scale; }
  int    output_zero_point( int index=0) { return interpreter_.output(index)->params.zero_point; }
  float  output_scale( int index=0) { return interpreter_.output(index)->params.scale; }

  inputT* output_ptr(int index = 0) { return GetTensorData<inputT>(Output(index)); }
  size_t output_size(int index = 0) { return interpreter_.output(index)->bytes; }
  size_t output_elements(int index = 0) { return  tflite::ElementCount(*(interpreter_.output(index)->dims));}
  int    output_dims_len(int index=0) {return interpreter_.output(index)->dims->size; }
  int *  output_dims( int index=0) { return &interpreter_.output(index)->dims->data[0]; }
  size_t get_used_arena_size() { return interpreter_.arena_used_bytes(); }
  int get_model_time_steps(int index=0) { return interpreter_.input(0)->dims->data[1]; }

 void SetInput(const inputT* custom_input, int recurrent_ts_size, int input_index = 0) {
    TfLiteTensor* input = interpreter_.input(input_index);
    inputT* input_buffer = tflite::GetTensorData<inputT>(input);
    int input_length = input->bytes / sizeof(inputT);
    for (int i = 0; i < input_length; i++) {
        input_buffer[i] = custom_input[i];
    }
  }

  void PrintAllocations() const {
    interpreter_.GetMicroAllocator().PrintAllocations();
  }

 private:
  tflite::RecordingMicroInterpreter interpreter_;
  tflite::MicroErrorReporter error_reporter_;
  TfLiteStatus allocate_status_;
  const Model* model_;

};

using MTB_TFLM_flt = MTBTFLiteMicro<float>;
using MTB_TFLM_int8 = MTBTFLiteMicro<int8_t>;
using MTB_TFLM_int16 = MTBTFLiteMicro<int16_t>;

} // namespace tflite


#define MTB_TFLM_Class MTB_TFLM_int16


#ifndef TFLM_RESVAR_COUNT
/* Set externally on demand by user. Disabled (0) by default */
#define TFLM_RESVAR_COUNT (0u)
#endif

#if (TFLM_RESVAR_COUNT != 0)
#if (TFLM_RESVAR_COUNT > 64)
#error "Maximum resource variables count has to be 64."
#else
static uint8_t var_arena[160 + 20 * TFLM_RESVAR_COUNT] __attribute__ ((aligned (16)));
#endif
#endif

#ifdef __cplusplus
extern "C" {
#endif  // __cplusplus

extern volatile int g_ifx_wwd_debug_stage;
extern volatile int g_ifx_wwd_debug_detail;
extern volatile int g_ifx_wwd_ethosu_stub_seen;

/*******************************************************************************
 * Public Functions
*******************************************************************************/

uint32_t get_mtb_ml_model_container_mem_size()
{
    return sizeof(mtb_ml_model_16x8_t);
}

cy_rslt_t mtb_ml_model_16x8_init(const mtb_ml_model_bin_t *bin, const mtb_ml_model_buffer_t *buffer, mtb_ml_model_16x8_t *model_object)
{
    uint8_t * arena_buffer = NULL;
    int arena_size;
    tflite::MTB_TFLM_Class * TFLMClass;
    int ret = MTB_ML_RESULT_SUCCESS;

    /* Sanity check of input parameters */
    if (bin == NULL || bin->model_bin == NULL || buffer == NULL || model_object == NULL)
    {
        ret = MTB_ML_RESULT_BAD_ARG;
        g_ifx_wwd_debug_stage = 31;
        g_ifx_wwd_debug_detail = ret;
        goto ret_err;
    }

    /* Copy the model name */
    memcpy(model_object->name, bin->name, MTB_ML_MODEL_NAME_LEN);

    /* Get the arena size specified in model data file */
    arena_size = bin->arena_size;

    if (buffer->tensor_arena_size == 0 || buffer->tensor_arena == NULL)
    {
        ret = MTB_ML_RESULT_BAD_ARG;
        g_ifx_wwd_debug_stage = 32;
        g_ifx_wwd_debug_detail = ret;
        goto ret_err;
    }

    /* over-write with application provided value */
    arena_size = buffer->tensor_arena_size;
    arena_buffer = buffer->tensor_arena;

    /* Get model and buffer size */
    model_object->model_size = bin->model_size;
    model_object->buffer_size = arena_size;

    g_ifx_wwd_debug_stage = 33;
    TFLMClass = new tflite::MTB_TFLM_Class(bin->model_bin, arena_buffer, arena_size, tflite::resolver);
    g_ifx_wwd_debug_stage = 34;
    model_object->tflm_obj = reinterpret_cast<void *>(TFLMClass);
    if( model_object->tflm_obj == NULL)
    {
        ret = MTB_ML_RESULT_BAD_MODEL;
        g_ifx_wwd_debug_detail = ret;
        goto ret_err;
    }

    /* Check Tensor allocation failure */
    if (TFLMClass->AllocationStatus() != kTfLiteOk)
    {
        ret = MTB_ML_RESULT_ALLOC_ERR;
        g_ifx_wwd_debug_stage = g_ifx_wwd_ethosu_stub_seen ? 37 : 35;
        g_ifx_wwd_debug_detail = ret;
        goto ret_err;
    }
    g_ifx_wwd_debug_stage = 36;

    /* Input parameters */
    model_object->input = TFLMClass->input_ptr();
    model_object->input_size = TFLMClass->input_elements();
    model_object->input_zero_point = TFLMClass->input_zero_point();
    model_object->input_scale = TFLMClass->input_scale();
    model_object->model_time_steps = TFLMClass->get_model_time_steps();
    /* Output parameters*/
    model_object->output_size = TFLMClass->output_elements();
    model_object->output = TFLMClass->output_ptr();
    model_object->buffer_size = TFLMClass->get_used_arena_size();
    model_object->output_zero_point = TFLMClass->output_zero_point();
    model_object->output_scale = TFLMClass->output_scale();

ret_err:
    return ret;
}

cy_rslt_t mtb_ml_model_16x8_deinit(mtb_ml_model_16x8_t *object)
{
    /* Sanity check of input parameters */
    if (object == NULL)
    {
        return MTB_ML_RESULT_BAD_ARG;
    }
    delete reinterpret_cast<tflite::MTB_TFLM_Class *>(object->tflm_obj);

    return MTB_ML_RESULT_SUCCESS;
}

cy_rslt_t mtb_ml_model_16x8_run(mtb_ml_model_16x8_t *object, int16_t *input)
{
    TfLiteStatus ret;
    /* Sanity check of input parameters */
    if (object == NULL || input == NULL)
    {
        return MTB_ML_RESULT_BAD_ARG;
    }

    tflite::MTB_TFLM_Class *Tflm = reinterpret_cast<tflite::MTB_TFLM_Class *>(object->tflm_obj);

    /* Set input data */
    Tflm->SetInput(input, object->recurrent_ts_size);

#ifdef AFE_DSNS_ML_PROFILE_ENABLE
    /* Model profiling */
    if (object->profiling & MTB_ML_PROFILE_ENABLE_MODEL)
    {
        mtb_ml_model_profile_get_tsc((uint64_t *)&object->m_cpu_cycles);
    }
#endif
    ret = Tflm->RunSingleIteration();
    if ( ret != kTfLiteOk )
    {
        object->lib_error = ret;
        return MTB_ML_RESULT_INFERENCE_ERROR;
    }

    if (object->profiling & MTB_ML_PROFILE_ENABLE_MODEL)
    {
#ifdef AFE_DSNS_ML_PROFILE_ENABLE
        uint32_t cycles = 0U;
        mtb_ml_model_profile_get_tsc((uint64_t *)&cycles);
        uint32_t cpu_cycles_only = cycles - object->m_cpu_cycles;
#if defined(COMPONENT_U55) && !defined(COMPONENT_RTOS)
        /* mtb_ml_init() : mtb_ml_norm_clk_freq = npu_freq/cpu_freq */
        uint64_t norm_npu_cycles = (uint64_t)(((float)mtb_ml_npu_cycles) / mtb_ml_norm_clk_freq);
        /* Check for bad cpu/npu count values so we don't overflow */
        if (norm_npu_cycles > cpu_cycles_only)
        {
            return MTB_ML_RESULT_CYCLE_COUNT_ERROR;
        }

        object->m_npu_cycles = mtb_ml_npu_cycles;
        if (object->m_npu_cycles > object->m_npu_peak_cycles)
        {
            object->m_npu_peak_cycles = object->m_npu_cycles;
            object->m_npu_peak_frame = object->m_sum_frames;
        }
        object->m_npu_sum_cycles += object->m_npu_cycles;
        /* Subtracting NPU fraction */
        cpu_cycles_only -= norm_npu_cycles;
#endif
        if (cpu_cycles_only > object->m_cpu_peak_cycles)
        {
            object->m_cpu_peak_cycles = cpu_cycles_only;
            object->m_cpu_peak_frame = object->m_sum_frames;
        }
        object->m_cpu_sum_cycles += cpu_cycles_only;
        object->m_sum_frames++;
#endif /* AFE_DSNS_ML_PROFILE_ENABLE */
    }
    else if (object->profiling & MTB_ML_LOG_ENABLE_MODEL_LOG)
    {
       int16_t * output_ptr = object->output;
       /**
       * This string must track ML_PROFILE_OUTPUT_STRING in mtb_ml_stream_impl.h,
       * as the header file is currently unable to be included due to conflicts.
       */
       printf(" output:");
       for (int j = 0; j < object->output_size; j++)
       {
          printf("%d ", output_ptr[j]);
       }
       printf("\r\n");
    }

    return MTB_ML_RESULT_SUCCESS;
}

cy_rslt_t mtb_ml_model_16x8_get_output(const mtb_ml_model_16x8_t *object, int16_t **output_pptr, int *size_ptr)
{
    /* Sanity check of input parameters */
    if (object == NULL)
    {
        return MTB_ML_RESULT_BAD_ARG;
    }

    if (output_pptr != NULL)
    {
        *output_pptr = object->output;
    }

    if (size_ptr != NULL)
    {
        *size_ptr = object->output_size;
    }

    return MTB_ML_RESULT_SUCCESS;
}

int mtb_ml_model_16x8_get_input_size(const mtb_ml_model_16x8_t *object)
{
    return object->input_size;
}

cy_rslt_t mtb_ml_model_16x8_rnn_reset_all_parameters(mtb_ml_model_16x8_t *object)
{
    /* Sanity check of model object parameter */
    if (object == NULL)
    {
        return MTB_ML_RESULT_BAD_ARG;
    }
    tflite::MTB_TFLM_Class *Tflm = reinterpret_cast<tflite::MTB_TFLM_Class *>(object->tflm_obj);
    TfLiteStatus ret = Tflm->reset_all_variables();
    if (ret != kTfLiteOk)
    {
        object->lib_error = ret;
        return MTB_ML_RESULT_BAD_ARG;
    }
    return MTB_ML_RESULT_SUCCESS;
}

#ifdef __cplusplus
}
#endif  // __cplusplus
