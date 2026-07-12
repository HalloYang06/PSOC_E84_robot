/***************************************************************************//**
* \file mtb_ml_model.h
*
* \brief
* This is the header file of ModusToolbox ML middleware NN model module.
*
*******************************************************************************
* (c) 2019-2024, Cypress Semiconductor Corporation (an Infineon company) or
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
#if !defined(__MTB_ML_MODEL_16X8_H__)
#define __MTB_ML_MODEL_16X8_H__

#include "mtb_ml_common.h"

#if defined(__cplusplus)
extern "C" {
#endif

/**
 * ML model runtime object structure
 */
typedef struct
{
/** @name
 *  Model runtime object common fields
 */
/**@{*/
    char name[MTB_ML_MODEL_NAME_LEN];   /**< the name of ML model */
    int model_size;                     /**< the size of ML model */
    int buffer_size;                    /**<the size of ML model working buffer */
    int input_size;                     /**< array size of input data */
    int output_size;                    /**< array size of output data */
    int lib_error;                      /**< error code from ML inference library */
    int16_t *output;                    /**< pointer of ML inference output buffer */
    int16_t*input;                      /**< pointer of ML inference input buffer */
    void *tflm_obj;                     /**< pointer of Tflite-micro runtime object */
    int model_time_steps;               /*< number of model time steps */
    int recurrent_ts_size;              /**< number of data time steps in NN. 0 if non streaming RNN */
    int input_zero_point;               /**< zero point of input data */
    float input_scale;                  /**< scale of input data*/
    int output_zero_point;              /**< zero point of output data */
    float output_scale;                 /**< scale of output data */
    mtb_ml_profile_config_t profiling;  /**< flags of profiling */
    uint32_t m_cpu_cycles;              /**< CPU profiling cycles */
    uint32_t m_sum_frames;              /**< profiling frames */
    uint64_t m_cpu_sum_cycles;          /**< CPU profiling total cycles */
    uint32_t m_cpu_peak_frame;          /**< CPU profiling peak frame */
    uint32_t m_cpu_peak_cycles;         /**< CPU profiling peak cycles */
    bool is_rnn_streaming;              /**< Is the model an RNN streaming model */
/**@}*/
#if defined(COMPONENT_U55)
/** @name COMPONENT_U55
 *  Model runtime object fields for NPU cycle count
 */
/**@{*/
    uint64_t m_npu_cycles;          /**< NPU profiling cycles */
    uint64_t m_npu_sum_cycles;      /**< NPU total cycles */
    uint32_t m_npu_peak_frame;      /**< NPU profiling peak frame */
    uint32_t m_npu_peak_cycles;     /**< NPU profiling peak cycles */
/**@}*/
#endif
#if defined(COMPONENT_ML_TFLM)
/** @name COMPONENT_ML_TFLM
 *  Model runtime object fields for TFLM with interpreter
 */
/**@{*/
    uint8_t *arena_buffer;              /**< pointer of allocated tensor arena buffer */
#endif
#if defined(COMPONENT_ML_TFLM_LESS)
/** @name COMPONENT_ML_TFLM_LESS
 *  Model runtime object fields for TFLM without interpreter
 */
/**@{*/
    tflm_rmf_apis_t rmf_apis;           /**< data structure of Tflite-micro APIs */
/**@}*/
#endif
} mtb_ml_model_16x8_t;

/******************************************************************************
* Function prototype
******************************************************************************/
/**
 * \addtogroup Model_API
 * @{
 */

/**
 * \brief : Allocate and initialize 16x8 NN model runtime object based on model data. Only intended to be called once.
 *
 * \param[in]   bin      : Pointer of model binary data.
 * \param[in]   buffer   : Pointer of buffer data structure for statically allocated persistent and scratch buffer.
 *                         This is optional, if no passed-in buffer, the API will allocate memory as persistent and
 *                         scratch buffer.
 * \param[out] object    : Pointer of 16x8 model object.
 *
 * \return               : MTB_ML_RESULT_SUCCESS - success
 *                       : MTB_ML_RESULT_BAD_ARG - if input parameter is invalid.
 *                       : MTB_ML_RESULT_ALLOC_ERR - if memory allocation failure.
 *                       : MTB_ML_RESULT_BAD_MODEL - if model parsing or initialization error.
 */
cy_rslt_t mtb_ml_model_16x8_init(const mtb_ml_model_bin_t *bin, const mtb_ml_model_buffer_t *buffer, mtb_ml_model_16x8_t *object);

/**
 * \brief : Delete 16x8 NN model runtime object and free all dynamically allocated memory. Only intended to be called once.
 *
 * \param[in] object     : Pointer of 16x8 model object.
 *
 * \return               : MTB_ML_RESULT_SUCCESS - success
 *                       : MTB_ML_RESULT_BAD_ARG - if input parameter is invalid.
 */
cy_rslt_t mtb_ml_model_16x8_deinit(mtb_ml_model_16x8_t *object);

/**
 * \brief : Perform 16x8 NN model inference
 *
 * \param[in] object     : Pointer of 16x8 model object.
 * \param[in] input      : Pointer of input data buffer
 *
 * \return               : MTB_ML_RESULT_SUCCESS - success
 *                       : MTB_ML_RESULT_BAD_ARG - if input parameter is invalid.
 *                       : MTB_ML_RESULT_INFERENCE_ERROR - if inference failure
 */
cy_rslt_t mtb_ml_model_16x8_run(mtb_ml_model_16x8_t *object, int16_t *input);

/**
 * \brief : Get 16x8 NN model input data size
 *
 * \param[in] object     : Pointer of 16x8 model object.
 *
 * \return               : Input data size
 *                       : 0 - if input parameter is invalid.
 */
int mtb_ml_model_16x8_get_input_size(const mtb_ml_model_16x8_t *object);

/**
 * \brief : Get 16x8 NN model output buffer and size
 *
 * \param[in] object     : Pointer of 16x8 model object.
 * \param[out] out_pptr  : Pointer of output buffer pointer
 * \param[out] size_ptr  : Pointer of output size
 *
 * \return               : Output data size
 *                       : 0 - if input parameter is invalid.
 */
cy_rslt_t mtb_ml_model_16x8_get_output(const mtb_ml_model_16x8_t *object, int16_t **out_pptr, int* size_ptr);

/**
 * \brief : Reset 16x8 model parameters
 *
 * \param[in] object     : Pointer of 16x8 model object.
 *
 * \return               : MTB_ML_RESULT_SUCCESS - success
 *                       : MTB_ML_RESULT_BAD_ARG - if input parameter is invalid.
 */
cy_rslt_t mtb_ml_model_16x8_rnn_reset_all_parameters(mtb_ml_model_16x8_t *object);

#if defined(__cplusplus)
}
#endif

#endif /* __MTB_ML_MODEL_16X8_H__ */
