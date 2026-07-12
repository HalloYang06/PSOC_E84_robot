/*
 * Copyright 2025, Cypress Semiconductor Corporation (an Infineon company) or
 * an affiliate of Cypress Semiconductor Corporation.  All rights reserved.
 *
 * This software, including source code, documentation and related
 * materials ("Software") is owned by Cypress Semiconductor Corporation
 * or one of its affiliates ("Cypress") and is protected by and subject to
 * worldwide patent protection (United States and foreign),
 * United States copyright laws and international treaty provisions.
 * Therefore, you may use this Software only as provided in the license
 * agreement accompanying the software package from which you
 * obtained this Software ("EULA").
 * If no EULA applies, Cypress hereby grants you a personal, non-exclusive,
 * non-transferable license to copy, modify, and compile the Software
 * source code solely for use in connection with Cypress's
 * integrated circuit products.  Any reproduction, modification, translation,
 * compilation, or representation of this Software except as specified
 * above is prohibited without the express written permission of Cypress.
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
 * including Cypress's product in a High Risk Product, the manufacturer
 * of such system or application assumes all risk of such use and in doing
 * so agrees to indemnify Cypress against all liability.
 */
/**
 * @file mtb_wwd.h
 * @brief This the header file of ModusToolbox WWD middleware utility module
 *
 */
#ifndef VA_INC_MTB_WWD_H
#define VA_INC_MTB_WWD_H

#include "cy_result.h"
#include "mtb_wwd_nlu_common.h"
#include "stdbool.h"
#include <stdint.h>


#if defined(__cplusplus)
extern "C" {
#endif

/**
 * @defgroup wwd_api Wake Word Detection (WWD) API
 * @brief API reference for WWD middleware.
 *
 * This module provides Wake Word Detection functionality for speech recognition
 * and wake word identification.
 */

/**
 * @defgroup wwd_macros WWD Macros
 * @ingroup wwd_api
 * @brief Macros for WWD middleware.
 */

/**
 * @brief Maximum number of WWD detections allowed.
 * @ingroup wwd_macros
 */
#define WWD_DETECTION_LIMIT 50

/**
 * @defgroup wwd_enums WWD Enumerated Types
 * @ingroup wwd_api
 * @brief Enumerated types for WWD middleware.
 */

/**
 * @defgroup wwd_structures WWD Structures
 * @ingroup wwd_api
 * @brief Data structures for WWD middleware.
 */

/**
 * @defgroup wwd_functions WWD Functions
 * @ingroup wwd_api
 * @brief Function prototypes for WWD middleware.
 */

/******************************************************************************
 * Typedefs
 *****************************************************************************/
/**
 * @enum mtb_wwd_rslt_t
 * @ingroup wwd_enums
 * @brief Result codes for WWD operations.
 *
 * This enum represents the result of the WWD detection process. Each value
 * indicates either successful operation or a specific type of error condition
 * that occurred during wake word detection processing.
 */
typedef enum {
    /** Operation was successful. */
    CY_WWD_RSLT_SUCCESS = MTB_VA_RSLT_SUCCESS,
    /** Invalid parameter. */
    CY_WWD_RSLT_INVALID_PARAM = MTB_VA_RSLT_INVALID_PARAM,
    /** WWD license expired. */
    CY_WWD_RSLT_LICENSE_ERROR = MTB_VA_RSLT_LICENSE_ERROR,
} mtb_wwd_rslt_t;

/**
 * @enum mtb_wwd_state_t
 * @ingroup wwd_enums
 * @brief WWD detection state.
 *
 * This enum represents the state of the WWD detection process throughout the
 * lifecycle of wake word detection. Each state indicates whether audio is being
 * analyzed, a wake word has been detected, or if the operation is idle.
 */
typedef enum {
    /** Initialization state. */
    CY_WWD_INIT_STATE = -2,
    /** No detection occurred. */
    CY_WWD_NOT_DETECTED = -1,
    /** Indecision in detection. */
    CY_WWD_INDECISION,
    /** Detection occurred. */
    CY_WWD_DETECTED
} mtb_wwd_state_t;

/******************************************************************************
 * Public definitions
 ******************************************************************************/

/******************************************************************************
 * Structures
 ******************************************************************************/
/**
 * @struct mtb_wwd_detection_data_t
 * @ingroup wwd_structures
 * @brief Structure for WWD detection data.
 *
 * @var mtb_wwd_detection_data_t::ww_index
 *   Index of the detected wake word.
 * @var mtb_wwd_detection_data_t::ww_text
 *   Pointer to the detected wake word text.
 */
typedef struct {
    int ww_index;            /**< Index of the detected wake word. */
    unsigned char *ww_text;  /**< Pointer to the detected wake word text. */
} mtb_wwd_detection_data_t;

/**
 * @struct mtb_wwd_t
 * @ingroup wwd_structures
 * @brief Main WWD object structure.
 *
 * @var mtb_wwd_t::wwd_state
 *   Current WWD detection state.
 * @var mtb_wwd_t::callback
 *   Callback settings for WWD events.
 * @var mtb_wwd_t::va_common_obj
 *   Objects common both to WWD and NLU modules.
 * @var mtb_wwd_t::sodtrigcnt
 *   SOD trigger count.
 * @var mtb_wwd_t::wwd_result
 *   WWD result status (-2 = init/reset, -1 = no, 1 = yes, 0 = indecision).
 * @var mtb_wwd_t::feature_buf_cnt
 *   Feature buffer count.
 */
typedef struct
{
    mtb_wwd_state_t wwd_state;                  /**< Current WWD detection state. */
    mtn_wwd_nlu_callback_setting_t callback;    /**< Callback settings for WWD events. */
    mtb_va_common_t va_common_obj;              /**< Common WWD/NLU objects. */
    int sodtrigcnt;                             /**< SOD trigger count. */
    int32_t wwd_result;                         /**< WWD result status (-2 = init/reset, -1 = no, 1 = yes, 0 = indecision). */
    int32_t feature_buf_cnt;                    /**< Feature buffer count. */
} mtb_wwd_t;

/*******************************************************************************
 * Function Prototypes
 *******************************************************************************/
/**
 * \brief Initializes wake word detection
 *
 * This function initializes the Wake Word Detection module with the provided
 * configuration. It allocates memory for audio processing components (HPF, SOD,
 * feature extraction, DFWW), initializes the ML model, sets up callbacks, and
 * prepares the WWD pipeline.
 *
 * \param[in,out] wwd_obj   : Pointer to WWD object.
 * \param[in] config_obj    : Pointer to configuration structure containing:
 *                            - wwd_nlu_buff_data: Buffer for processing
 *                            - ww_conf: Wake word configuration including
 * callbacks
 *                            - ww_model_ptr: Pointer to wake word model data
 * generated by DEEPCRAFT
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_INVALID_PARAM - invalid parameters
 *                            MTB_VA_RSLT_IFX_PARSE_ERROR - parameter parsing
 * failed MTB_VA_RSLT_MEM_ALLOC_ERROR - memory allocation failed
 *                            MTB_VA_RSLT_ML_INIT_ERROR - ML model
 * initialization failed MTB_VA_RSLT_IFX_INIT_ERROR - IFX component
 * initialization failed
 *
 * \note NLU can borrow common audio processing objects from the shared buffer
 * structure.
 * \note This function must be called before mtb_wwd_process().
 *
 * \ingroup wwd_functions
 */
cy_rslt_t mtb_wwd_init(mtb_wwd_t *wwd_obj, mtb_wwd_nlu_config_t *config_obj);

/**
 * \brief Deinitializes wake word detection
 *
 * This function cleans up all WWD resources including common audio processing
 * objects, ML model and persistent memory.
 *
 * \param[in] wwd_obj       : Pointer to WWD object.
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_IFX_INTERNAL_ERROR - internal error
 * during cleanup
 *
 * \ingroup wwd_functions
 */
cy_rslt_t mtb_wwd_deinit(mtb_wwd_t *wwd_obj);

/**
 * \brief Processes mic data for wake word detection
 *
 * This function processes a frame of microphone data through the WWD pipeline:
 * 1. Runs Speech-On-Detection (SOD) to detect speech activity
 * 2. Applies high-pass filter for preprocessing
 * 3. Extracts acoustic features from the audio frame
 * 4. Runs ML inference to generate phoneme predictions
 * 5. Performs wake word detection
 * 6. Triggers callbacks based on detection events
 *
 * \param[in] wwd_obj       : Pointer to WWD object.
 * \param[in] mic_frame     : Pointer to microphone data buffer (16kHz, 16-bit
 * PCM). Size must be FRAME_SIZE_16K samples.
 * \param[out] ww_state     : Pointer to store wake word detection state:
 *                            - CY_WWD_INIT_STATE: Initial/reset state
 *                            - CY_WWD_INDECISION: Processing, no decision yet
 *                            - CY_WWD_DETECTED: Wake word detected
 *                            - CY_WWD_NOT_DETECTED: No wake word detected
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_INVALID_PARAM - invalid parameters
 *                            MTB_VA_RSLT_LICENSE_ERROR - audio library license
 * expired MTB_VA_RSLT_IFX_INTERNAL_ERROR - internal processing error
 *                            MTB_VA_RSLT_IFX_WWD_ERROR - wake word detection
 * error MTB_VA_RSLT_IFX_RESET_ERROR - DFWW reset error
 *
 * \note NLU timer is reset when SOD trigger count reaches FRAMES_HOP.
 *
 * \ingroup wwd_functions
 */
cy_rslt_t mtb_wwd_process(mtb_wwd_t *wwd_obj, int16_t *mic_frame,
                          mtb_wwd_state_t *ww_state);

/**
 * \brief Resets wake word detection
 *
 * This function resets the Wake Word Detection module, clearing all internal
 * states and buffers. It is used to reinitialize the WWD pipeline without
 * fully deinitializing and reinitializing the module.
 *
 * \param[in,out] wwd_obj   : Pointer to WWD object.
 * \param[in] config_obj    : Pointer to configuration structure. Only
 *                            sod_params is accessed during reset.
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_INVALID_PARAM - invalid parameters
 *                            MTB_VA_RSLT_IFX_RESET_ERROR - DFWW reset error
 *
 * \note This function can be called when restarting detection or after an error.
 * \note The model is not reloaded, but all internal states are cleared.
 *
 * \ingroup wwd_functions
 */
cy_rslt_t mtb_wwd_reset_state(mtb_wwd_t *wwd_obj,
                              mtb_wwd_nlu_config_t *config_obj);

/**
 * @defgroup wwd_api Wake Word Detection (WWD) API
 * @brief API reference for WWD middleware.
 */
/**
 * @addtogroup wwd_api
 * @{
 */
/** @} */

#if defined(__cplusplus)
}
#endif

#endif /* VA_INC_MTB_WWD_H */
