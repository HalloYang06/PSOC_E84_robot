/*
 * (c) 2026, Infineon Technologies AG, or an affiliate of Infineon
 * Technologies AG. All rights reserved.
 * This software, associated documentation and materials ("Software") is
 * owned by Infineon Technologies AG or one of its affiliates ("Infineon")
 * and is protected by and subject to worldwide patent protection, worldwide
 * copyright laws, and international treaty provisions. Therefore, you may use
 * this Software only as provided in the license agreement accompanying the
 * software package from which you obtained this Software. If no license
 * agreement applies, then any use, reproduction, modification, translation, or
 * compilation of this Software is prohibited without the express written
 * permission of Infineon.
 *
 * Disclaimer: UNLESS OTHERWISE EXPRESSLY AGREED WITH INFINEON, THIS SOFTWARE
 * IS PROVIDED AS-IS, WITH NO WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
 * INCLUDING, BUT NOT LIMITED TO, ALL WARRANTIES OF NON-INFRINGEMENT OF
 * THIRD-PARTY RIGHTS AND IMPLIED WARRANTIES SUCH AS WARRANTIES OF FITNESS FOR A
 * SPECIFIC USE/PURPOSE OR MERCHANTABILITY.
 * Infineon reserves the right to make changes to the Software without notice.
 * You are responsible for properly designing, programming, and testing the
 * functionality and safety of your intended application of the Software, as
 * well as complying with any legal requirements related to its use. Infineon
 * does not guarantee that the Software will be free from intrusion, data theft
 * or loss, or other breaches ("Security Breaches"), and Infineon shall have
 * no liability arising out of any Security Breaches. Unless otherwise
 * explicitly approved by Infineon, the Software may not be used in any
 * application where a failure of the Product or any consequences of the use
 * thereof can reasonably be expected to result in personal injury.
 */

/**
 * @file va_ml_model.h
 * @brief This the header file of ModusToolbox NLU and WWD middleware ML model
 * utility module
 *
 */

#ifndef VA_INC_ML_MODEL_H
#define VA_INC_ML_MODEL_H

#include "mtb_ml.h"
#include "mtb_ml_model_16x8.h"
#include <ctype.h>


#if defined(__cplusplus)
extern "C" {
#endif

/**
 * @defgroup va_ml_model ML Model Functions
 * @brief Function prototypes for ML model operations.
 */

/*******************************************************************************
 * Function Prototypes
 *******************************************************************************/
/**
 * \brief Allocates a new ML neural network model instance
 *
 * \param[out] mtb_ml_model_obj    : Pointer to the model object pointer.
 * \return                         : MTB_VA_RSLT_SUCCESS - success
 *                                   MTB_VA_RSLT_INVALID_PARAM - invalid
 * parameters MTB_VA_RSLT_MEM_ALLOC_ERROR - memory allocation failed
 *
 * \note The model object must be destroyed using ml_destroy_model() to free
 * resources.
 * \note This function must be called before ml_inference_init().
 * \note Both mtb_ml_model_obj and am_predict_sz must be valid pointers.
 *
 * \ingroup va_ml_model
 */
uint32_t ml_create_model(mtb_ml_model_16x8_t **mtb_ml_model_obj);

/**
 * \brief Initializes the neural network model for inference
 *
 * \param[in] am_model_bin         : Pointer to the acoustic model binary data.
 * Must not be NULL.
 * \param[in] am_model_buffer      : Pointer to the acoustic model buffer
 * structure. Must not be NULL.
 * \param[in,out] mtb_ml_model_obj : Pointer to the ML model object to
 * initialize.
 * \return                         : MTB_VA_RSLT_SUCCESS - success
 *                                   MTB_VA_RSLT_INVALID_PARAM - invalid
 * parameters MTB_VA_RSLT_ML_INIT_ERROR - model initialization or RNN reset
 * failed
 *
 * \note This function must be called after ml_create_model() and before
 * ml_process().
 * \note The NPU interrupt priority is set to NPU_PRIORITY during
 * initialization.
 *
 * \ingroup va_ml_model
 */
uint32_t ml_inference_init(const mtb_ml_model_bin_t *am_model_bin,
                           const mtb_ml_model_buffer_t *am_model_buffer,
                           mtb_ml_model_16x8_t *mtb_ml_model_obj);

/**
 * \brief Destroys the ML model and frees allocated resources
 *
 * \param[in,out] mtb_ml_model_obj : Pointer to the model object pointer.
 *
 * \ingroup va_ml_model
 */
void ml_destroy_model(mtb_ml_model_16x8_t **mtb_ml_model_obj);

/**
 * \brief Processes input data through the ML model and runs inference
 *
 * \param[in,out] mtb_ml_model_obj : Pointer to the initialized ML model object.
 * \param[out] data_feed_int       : Buffer to store quantized input data.
 * \param[in] buf_pt_base          : Pointer to the updated buffer containing
 * the input data.
 * \param[out] output_scores       : Buffer to store output prediction scores.
 * \return                         : MTB_VA_RSLT_SUCCESS - success
 *                                   MTB_VA_RSLT_INVALID_PARAM - invalid
 * parameters MTB_VA_RSLT_ML_INFERENCE_ERROR - RNN reset or inference execution
 * failed
 *
 * \note Input values are quantized using the model's scale and zero_point
 * parameters.
 * \note Output values are dequantized using the model's output quantization
 * parameters.
 * \note RNN state is reset on each call to this function.
 *
 * \ingroup va_ml_model
 */
uint32_t ml_process(mtb_ml_model_16x8_t *mtb_ml_model_obj,
                    int16_t *data_feed_int, float *buf_pt_base,
                    float *output_scores);

#if defined(__cplusplus)
}
#endif

#endif /* VA_INC_ML_MODEL_H */
