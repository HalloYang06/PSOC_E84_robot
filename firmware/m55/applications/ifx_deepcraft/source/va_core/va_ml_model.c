/***************************************************************************//**
 * \file va_ml_model.c
 *
 * \brief
 * The file contains model related component
 *
 *******************************************************************************
 * (c) 2019-2025, Cypress Semiconductor Corporation (an Infineon company) or
 * an affiliate of Cypress Semiconductor Corporation.  All rights reserved.
 *******************************************************************************/

/*******************************************************************************
 * Include header file
 ******************************************************************************/
#include "va_ml_model.h"

#include <math.h>
#include <stdint.h>
#include <stdlib.h>

#include "va_config_params.h"
#include "ifx_pre_post_process.h"
#include "mtb_ml.h"
#include "mtb_wwd_nlu_common.h"

extern volatile int g_ifx_wwd_debug_stage;
extern volatile int g_ifx_wwd_debug_detail;

/*******************************************************************************
 * Function Name: mtb_ml_create_model
 ********************************************************************************
 * Summary:
 *  Creates a new ML neural network model instance.
 *
 * Parameters:
 *  mtb_ml_model_obj: Pointer to the model object.
 *
 * Returns:
 *  The status of the model creation.
 *
 *******************************************************************************/
uint32_t ml_create_model(mtb_ml_model_16x8_t **mtb_ml_model_obj)
{
    if (mtb_ml_model_obj == NULL || *mtb_ml_model_obj != NULL)
    {
        return MTB_VA_RSLT_INVALID_PARAM;
    }

    /* AM NN model target for U55 */
    int32_t am_predict_sz = sizeof(mtb_ml_model_16x8_t);
    *mtb_ml_model_obj = (mtb_ml_model_16x8_t *)calloc(1u, am_predict_sz);
    if (*mtb_ml_model_obj == NULL)
    {
        return MTB_VA_RSLT_ML_INIT_ERROR;
    }

    CY_VA_PRINTF_TRACE("ML model created\n\r");
    return MTB_VA_RSLT_SUCCESS;
}

/*******************************************************************************
 * Function Name: mtb_ml_inference_init
 ********************************************************************************
 * Summary:
 *  Initializes the neural network.
 *
 * Parameters:
 *  am_model_bin: Acoustic model binary.
 *  am_model_buffer: Acoustic model buffer.
 *  mtb_ml_model_obj: Pointer to the ML model object.
 *
 * Returns:
 *  The status of the initialization.
 *
 *******************************************************************************/
uint32_t ml_inference_init(const mtb_ml_model_bin_t *am_model_bin,
                           const mtb_ml_model_buffer_t *am_model_buffer,
                           mtb_ml_model_16x8_t *mtb_ml_model_obj)
{
    uint32_t result;
    if (am_model_bin == NULL || am_model_buffer == NULL ||
        mtb_ml_model_obj == NULL)
    {
        return CY_RSLT_TYPE_ERROR;
    }

    /* Initialize the Neural Network */
    result =
        mtb_ml_model_16x8_init(am_model_bin, am_model_buffer, mtb_ml_model_obj);
    if (MTB_ML_RESULT_SUCCESS != result)
    {
        g_ifx_wwd_debug_detail = (int)result;
        return MTB_VA_RSLT_ML_INIT_ERROR;
    }
    g_ifx_wwd_debug_stage = 5;
    result = mtb_ml_model_16x8_rnn_reset_all_parameters(mtb_ml_model_obj);
    if (MTB_ML_RESULT_SUCCESS != result)
    {
        g_ifx_wwd_debug_detail = (int)result;
        return MTB_VA_RSLT_ML_INIT_ERROR;
    }
    g_ifx_wwd_debug_stage = 6;
    mtb_ml_model_obj->profiling = MTB_ML_PROFILE_DISABLE;

    /* Set the priority of NPU interrupt handler */
    result = mtb_ml_init(NPU_PRIORITY);
    if (MTB_ML_RESULT_SUCCESS != result)
    {
        g_ifx_wwd_debug_detail = (int)result;
        return MTB_VA_RSLT_ML_INIT_ERROR;
    }

    CY_VA_PRINTF_TRACE("ML inference initialized\n\r");
    return MTB_VA_RSLT_SUCCESS;
}

/*******************************************************************************
 * Function Name: mtb_ml_destroy_model
 ********************************************************************************
 * Summary:
 *  Destroys the ML model instance and frees allocated memory.
 *
 * Parameters:
 *  mtb_ml_model_obj: Pointer to the model object.
 *
 * Returns:
 *  None
 *
 *******************************************************************************/
void ml_destroy_model(mtb_ml_model_16x8_t **mtb_ml_model_obj)
{
    if (mtb_ml_model_obj != NULL && *mtb_ml_model_obj != NULL)
    {
        mtb_ml_model_16x8_deinit(*mtb_ml_model_obj);
        free(*mtb_ml_model_obj);
        *mtb_ml_model_obj = NULL;
    }

    mtb_ml_deinit();
}

/*******************************************************************************
 * Function Name: mtb_ml_process
 ********************************************************************************
 * Summary:
 *  Process input data through the ML model and produces output scores.
 *
 * Parameters:
 *  mtb_ml_model_obj: Pointer to the ML model object.
 *  data_feed_int: Pointer to the integer data feed.
 *  buf_pt_base: Pointer to the updated buffer containing the input data.
 *  output_scores: Pointer to the buffer for storing the output scores. The
 *scores are stored in float32 format.
 *
 * Returns:
 *  The status of the processing.
 *
 *******************************************************************************/
uint32_t ml_process(mtb_ml_model_16x8_t *mtb_ml_model_obj,
                    int16_t *data_feed_int, float *buf_pt_base,
                    float *output_scores)
{
    uint32_t result;

    /* Validate buffer pointers */
    if (buf_pt_base == NULL || mtb_ml_model_obj == NULL ||
        data_feed_int == NULL || output_scores == NULL)
    {
        return MTB_VA_RSLT_INVALID_PARAM;
    }

    int16_t *qntz_out = data_feed_int;
    float factor = 1.0f / mtb_ml_model_obj->input_scale;
    int pos_i;
    float val;

    /* Quantization of the input */
    const float input_offset = mtb_ml_model_obj->input_zero_point;
    for (pos_i = 0; pos_i < mtb_ml_model_obj->input_size; pos_i++)
    {
        val = buf_pt_base[pos_i] * factor + input_offset;
        val += (val > 0.0f) ? 0.5f : -0.5f;
        qntz_out[pos_i] = (int16_t)(__SSAT((int32_t)(val), 16));
    }

    result = mtb_ml_model_16x8_rnn_reset_all_parameters(mtb_ml_model_obj);
    if (CY_RSLT_SUCCESS != result)
    {
        return MTB_VA_RSLT_ML_INFERENCE_ERROR;
    }

    /* Feed the Model */
    result = mtb_ml_model_16x8_run(mtb_ml_model_obj, data_feed_int);
    if (CY_RSLT_SUCCESS != result)
    {
        return MTB_VA_RSLT_ML_INFERENCE_ERROR;
    }

    /* Convert result_buffer to output_scores */
    const int output_offset = mtb_ml_model_obj->output_zero_point;
    factor = mtb_ml_model_obj->output_scale;
    for (pos_i = 0; pos_i < mtb_ml_model_obj->output_size; pos_i++)
    {
        /* Convert inference output to float32 */
        output_scores[pos_i] =
            ((int)(mtb_ml_model_obj->output[pos_i]) - output_offset) * factor;
    }

    return MTB_VA_RSLT_SUCCESS;
}
