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
 * @file mtb_nlu.h
 * @brief This the header file of ModusToolbox NLU middleware utility module
 *
 */

#ifndef VA_INC_MTB_NLU_H
#define VA_INC_MTB_NLU_H

#include "cy_result.h"
#include "mtb_wwd_nlu_common.h"
#include "stdbool.h"
#include <stdint.h>


#if defined(__cplusplus)
extern "C" {
#endif

/**
 * @defgroup nlu_api Natural Language Understanding (NLU) API
 * @brief API reference for NLU middleware.
 *
 * This module provides Natural Language Understanding functionality for speech
 * recognition and command interpretation.
 */

/**
 * @defgroup nlu_macros NLU Macros
 * @ingroup nlu_api
 * @brief Macros for NLU middleware.
 */

/**
 * @brief Minimum none speech time in ms for NLU.
 * @ingroup nlu_macros
 */
#define CY_NLU_NON_SPEECH_TIME_MIN WW_CMD_MIN_MAXWWGAP_MS

/**
 * @brief Minimum none speech time in ms for NLU.
 * @ingroup nlu_macros
 */
#define CY_NLU_NON_SPEECH_TIME_DEFAULT DEFAULT_WW_CMD_MAXWWGAP_MS

/**
 * @brief Default none speech time in ms for NLU.
 * @ingroup nlu_macros
 */
#define CY_NLU_NON_SPEECH_TIME_MAX WW_CMD_MAX_MAXWWGAP_MS

/**
 * @brief Minimum NLU duration factor for NLU.
 * @ingroup nlu_macros
 */
#define CY_NLU_DURATION_FACTOR_MIN CMD_TIMEOUT_MIN_LEVEL

/**
 * @brief Maximum NLU duration factor for NLU.
 * @ingroup nlu_macros
 */
#define CY_NLU_DURATION_FACTOR_MAX CMD_TIMEOUT_MAX_LEVEL

/**
 * @brief Minimum command timeout in ms for NLU.
 * @ingroup nlu_macros
 */
#define CY_NLU_COMMAND_TIMEOUT_MIN 0
/**
 * @brief Maximum command timeout in ms for NLU.
 * @ingroup nlu_macros
 */
#define CY_NLU_COMMAND_TIMEOUT_MAX 0xFFFFFFFF

/**
 * @brief NLU detection limit.
 * @ingroup nlu_macros
 */
#define NLU_DETECTION_LIMIT 50
/**
 * @brief Minimum intent index for NLU.
 * @ingroup nlu_macros
 */
#define CY_NLU_INTENT_INDEX_MIN 0

/**
 * @brief NLU process execution time in ms.
 * @ingroup nlu_macros
 */
#define NLU_PROCESS_EX_TIME 10

/**
 * @defgroup nlu_enums NLU Enumerated Types
 * @ingroup nlu_api
 * @brief Enumerated types for NLU middleware.
 */

/**
 * @defgroup nlu_structures NLU Structures
 * @ingroup nlu_api
 * @brief Data structures for NLU middleware.
 */

/**
 * @defgroup nlu_functions NLU Functions
 * @ingroup nlu_api
 * @brief Function prototypes for NLU middleware.
 */

/******************************************************************************
 * Macros
 *****************************************************************************/

/******************************************************************************
 * Typedefs
 *****************************************************************************/
/**
 * @enum mtb_nlu_rslt_t
 * @ingroup nlu_enums
 * @brief Enum which represents result codes for NLU operations.
 *
 * This enum represents the result of the NLU detection process. Each value
 * indicates either successful operation or a specific type of error condition
 * that occurred during NLU processing.
 */
typedef enum {
    /** Operation was successful. */
    CY_NLU_RSLT_SUCCESS = MTB_VA_RSLT_SUCCESS,
    /** Invalid input parameter. */
    CY_NLU_RSLT_INVALID_PARAM = MTB_VA_RSLT_INVALID_PARAM,
    /** Pre-silence timeout occurred. */
    CY_NLU_RSLT_PRE_SILENCE_TIMEOUT = MTB_VA_RSLT_PRE_SILENCE_TIMEOUT,
    /** Command timeout occurred. */
    CY_NLU_RSLT_COMMAND_TIMEOUT = MTB_VA_RSLT_COMMAND_TIMEOUT,
    /** NLU license expired. */
    CY_NLU_RSLT_LICENSE_ERROR = MTB_VA_RSLT_LICENSE_ERROR,
} mtb_nlu_rslt_t;

/**
 * @enum mtb_nlu_state_t
 * @ingroup nlu_enums
 * @brief NLU detection state.
 *
 * This enum represents the state of the NLU detection process throughout the
 * lifecycle of command detection. Each state indicates whether speech is being
 * processed, a decision has been made, or if the operation is idle.
 */
typedef enum {
    /** Initialization state. */
    CY_NLU_INIT_STATE = -2,
    /** No detection occurred. */
    CY_NLU_NOT_DETECTED = -1,
    /** Indecision in detection. */
    CY_NLU_INDECISION,
    /** Detection occurred. */
    CY_NLU_DETECTED
} mtb_nlu_state_t;

/******************************************************************************
 * Public definitions
 ******************************************************************************/

/******************************************************************************
 * Structures
 ******************************************************************************/
/**
 * @struct mtb_nlu_variable_t
 * @ingroup nlu_structures
 * @brief Structure for NLU variable value and its unit index.
 *
 * This structure holds a variable value and its associated unit index as
 * detected by the NLU engine.
 *
 * @var mtb_nlu_variable_t::value
 *   Detected variable value.
 * @var mtb_nlu_variable_t::unit_idx
 *   Index of the detected unit.
 */
typedef struct {
    int value;      /**< Detected variable value. */
    int unit_idx;   /**< Index of the detected unit. */
} mtb_nlu_variable_t;

/**
 * @struct mtb_nlu_t
 * @ingroup nlu_structures
 * @brief Main NLU object structure.
 *
 * This structure contains the state, configuration, and variable data for the
 * NLU engine.
 *
 * @var mtb_nlu_t::nlu_state
 *   Current NLU detection state.
 * @var mtb_nlu_t::nlu_config
 *   NLU configuration.
 * @var mtb_nlu_t::nlu_variable_data
 *   Pointer to variable data array.
 */
typedef struct {
    mtb_nlu_state_t nlu_state;                  /**< Current NLU detection state. */
    mtb_nlu_config_t nlu_config;                /**< NLU configuration. */
    mtb_nlu_setup_array_t *nlu_variable_data;   /**< Pointer to variable data array. */
} mtb_nlu_t;

/*******************************************************************************
 * Function Prototypes
 *******************************************************************************/
/**
 * \brief Initializes NLU detection
 *
 * This function initializes the Natural Language Understanding module with the
 * provided configuration. It allocates memory for audio processing components
 * (HPF, SOD, feature extraction, DFWW, DFCMD), initializes the ML model, and
 * sets up the NLU pipeline. The function can either create new common objects
 * or reuse those initialized by WWD.
 *
 * \param[in,out] nlu_obj   : Pointer to NLU object.
 * \param[in] config_obj    : Pointer to configuration structure.
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_INVALID_PARAM - invalid parameters or
 * timeout settings MTB_VA_RSLT_IFX_PARSE_ERROR - parameter parsing failed
 *                            MTB_VA_RSLT_MEM_ALLOC_ERROR - memory allocation
 * failed MTB_VA_RSLT_ML_INIT_ERROR - ML model initialization failed
 *                            MTB_VA_RSLT_IFX_INIT_ERROR - IFX component
 * initialization failed
 *
 * \note Pre-silence timeout must be between CY_NLU_PRE_SILENCE_MS_MIN and
 * CY_NLU_PRE_SILENCE_MS_MAX.
 * \note Command timeout must be between CY_NLU_COMMAND_TIMEOUT_MIN and
 * CY_NLU_COMMAND_TIMEOUT_MAX.
 * \note If WWD has already initialized common objects, NLU will reuse them.
 * \note This function must be called before mtb_nlu_process().
 *
 * \ingroup nlu_functions
 */
cy_rslt_t mtb_nlu_init(mtb_nlu_t *nlu_obj, mtb_wwd_nlu_config_t *config_obj);

/**
 * \brief Deinitializes NLU detection
 *
 * This function cleans up all NLU resources including DFCMD object, common
 * audio processing objects (if owned), ML model and persistent memory.
 *
 * \param[in] nlu_obj       : Pointer to NLU object.
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_IFX_INTERNAL_ERROR - internal error
 * during cleanup
 *
 * \note If WWD owns common objects, they will not be freed by this function.
 * \note All memory allocated during mtb_nlu_init() is freed.
 *
 * \ingroup nlu_functions
 */
cy_rslt_t mtb_nlu_denit(mtb_nlu_t *nlu_obj);

/**
 * \brief Processes mic data for NLU detection
 *
 * This function processes a frame of microphone data through the NLU pipeline:
 * 1. Runs Speech-On-Detection (SOD) to detect speech activity
 * 2. Applies high-pass filter (if enabled) for preprocessing
 * 3. Extracts acoustic features from the audio frame
 * 4. Runs ML inference to generate phoneme predictions
 * 5. Performs command detection and extraction
 *
 * \param[in] nlu_obj         : Pointer to NLU object.
 * \param[in] mic_frame       : Pointer to microphone data buffer (16kHz, 16-bit
 * PCM).
 * \param[out] nlu_state      : Pointer to NLU detection state:
 *                              - CY_NLU_INIT_STATE: Initial/reset state
 *                              - CY_NLU_INDECISION: Processing, no decision yet
 *                              - CY_NLU_DETECTED: Command detected
 *                              - CY_NLU_NOT_DETECTED: No command detected
 * \param[out] intent_index   : Pointer to store detected intent index.
 * \param[out] variable_values: Array for storing detected variable values.
 * \param[out] var_size       : Pointer to number of variables extracted.
 * \return                    : MTB_VA_RSLT_SUCCESS - success
 *                              MTB_VA_RSLT_INVALID_PARAM - invalid parameters
 *                              MTB_VA_RSLT_PRE_SILENCE_TIMEOUT - pre-silence
 * timeout expired MTB_VA_RSLT_COMMAND_TIMEOUT - command timeout expired
 *                              MTB_VA_RSLT_IFX_INTERNAL_ERROR - internal
 * processing error MTB_VA_RSLT_IFX_DFCMD_ERROR - command detection error
 *
 * \note intent_index and variable_values are only populated when
 * CY_NLU_DETECTED is returned.
 *
 * \ingroup nlu_functions
 */
cy_rslt_t mtb_nlu_process(mtb_nlu_t *nlu_obj, int16_t *mic_frame,
                          mtb_nlu_state_t *nlu_state, int *intent_index,
                          mtb_nlu_variable_t *variable_values, int *var_size);

/**
 * \brief Retrieves NLU detection data as a text string
 *
 * \param[in] nlu_obj       : Pointer to NLU object (currently unused but
 * reserved for future use).
 * \param[out] commandtext  : Pointer to buffer for storing the command text
 * string. Buffer must be large enough to hold the command text.
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_INVALID_PARAM - commandtext is NULL or
 * get command failed
 *
 * \note This function should be called after mtb_nlu_process() returns
 * CY_NLU_DETECTED.
 * \note The command text is retrieved from the internal DFCMD object.
 *
 * \ingroup nlu_functions
 */
cy_rslt_t mtb_nlu_get_command(mtb_nlu_t *nlu_obj, char *commandtext);

/**
 * \brief Resets NLU detection state
 *
 * \param[in] nlu_obj       : Pointer to NLU object.
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_INVALID_PARAM - invalid parameters
 *                            MTB_VA_RSLT_IFX_RESET_ERROR - component reset
 * failed
 *
 * \note This function should be called when restarting detection or after an
 * error.
 * \note All internal state is cleared, including feature buffers and ML
 * predictions.
 *
 * \ingroup nlu_functions
 */
cy_rslt_t mtb_nlu_reset(mtb_nlu_t *nlu_obj);

/**
 * \brief Resets NLU detection state
 *
 * \param[in] nlu_obj       : Pointer to NLU object.
 * \param[in] config_obj    : Pointer to configuration structure. Only
 *                            sod_params is accessed during reset.
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_INVALID_PARAM - invalid parameters
 *                            MTB_VA_RSLT_IFX_RESET_ERROR - component reset
 * failed
 *
 * \note This function can be called when restarting detection or after an error.
 * \note The model is not reloaded, but all internal states are cleared.
 *
 * \ingroup nlu_functions
 */
cy_rslt_t mtb_nlu_reset_state(mtb_nlu_t *nlu_obj,
                              mtb_wwd_nlu_config_t *config_obj);

/**
 * \brief Sets the command timeout for NLU detection
 *
 * \param[in] nlu_obj        : Pointer to NLU object.
 * \param[in] timeout       : Timeout in milliseconds. Must be between
 *                            CY_NLU_COMMAND_TIMEOUT_MIN and
 * CY_NLU_COMMAND_TIMEOUT_MAX.
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_INVALID_PARAM - timeout out of valid
 * range
 *
 * \ingroup nlu_functions
 */
cy_rslt_t mtb_nlu_timeout(mtb_nlu_t *nlu_obj, uint32_t timeout);

/**
 * \brief It is used to get detected command text process.
 *
 * \param[in]  DFcmdStrucPt      : Pointer to command data structure container
 * \param[out] commandtext       : pointer to character string of detected
 * command text
 * \return                       : Return 0 when success, otherwise return error
 * code from specific ifx  process module. Please note error code is 8bit LSB,
 * line number where the error happened in code is in 16bit MSB, and its IP
 * component index if applicable will be at bit 8 to 15 in the combined 32bit
 * return value.
 *
 * \ingroup nlu_functions
 */
uint32_t ifx_get_command(void *DFcmdStrucPt, char *commandtext);

/**
 * \brief  This function is used to get detected command details.
 * This function returns the command index or indices (*indices) that were
 detected.
 * These indices map back into the original command list that was trained for
 * detection. Note that one or two indices may be returned, depending on the
 * structure of the original command.  The number of indices actually returned
 is
 * given by the value of the returned parameter (*Nindices).
 *
 * This function also returns any numbers and appropriate units of such numbers.
 As
 * there are many types of number fields supported with different formats, the
 numbers
 * (such as time) that the higher level calling function can reformat or convert
 to
 * integers as desired.  The total number of numbers returned in the (*numbers)
 field is
 * given by the return value (*Nnumbers).
 *
 * The units corresponding to each number are returned in the char array
 * ((*units)[20]).  Based on the command recognized, the higher layers know what
 any
 * subsequent number returned refers to and whether or not that number includes
 any
 * units. The total number of units returned (which may not equal the number of
 numbers)
 * is returned in (* Nunits).
 *
 * As of the current release, the numbers fields supported include:
 * - Numbers - the format is 'xxx', NNumbers = 1
 *       units: degree(s), percent, level(s), hour(s), minute(s), second(s),
 *              day(s), no units
 *              Nunits = 1
 *
 * - Time - the format is 'xx:yy' where xx is the 12-hour hours, and yy is
 minutes, NNumbers = 1
 *       units: 'AM' or 'PM'
 *              Nunits = 1
 *
 * - Duration - the format is 'xxx', NNumbers = 1 to 3
 *       units: hour(s), minute(s), second(s)
 *              Nunits = NNumbers = 1 to 3
 *
 * - Ordinals - the format is 'xxx', NNumbers = 1
 *       units: none
 *              Nunits = 0
 *
 * \param[in]  DFcmdStrucPt      : Pointer to command data structure container
 * \param[out] indices           : pointer to detected command indices
 * \param[out] Nindices          : pointer to an integer specifies the number of
 detected command indices (1 or 2) is returned.
 * \param[out] numbers           : pointer to array of char of size 3 of
 detected numbers in char, each array of length 20 chars.
 * \param[out] Nnumbers          : pointer to integer specifies the number of
 numbers (-1 to 3) that are returned, with -1 represents no numbers was
 recognized but expected.
 * \param[out] units             : pointer to array of char of size 3 of
 detected unit, each array of length 20 chars.
 * \param[out] Nunits            : pointer to integer specifies the number of
 detected units (-1 to 3) that are returned, with -1 represents no number unit
 was recognized but expected.
 * \return                       : Return 0 when success, otherwise return error
 code from specific ifx process module.
 *                                 Please note error code is 8bit LSB, line
 number where the error happened in
 *                                 code is in 16bit MSB, and its IP component
 index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return
 value.
 *
 * \ingroup nlu_functions
 */
uint32_t ifx_get_command_indices_and_numbers(void *DFcmdStrucPt, int *indices,
                                             int *Nindices, char (*numbers)[20],
                                             int *Nnumbers, char (*units)[20],
                                             int *Nunits);

/**
 * @defgroup nlu_api Natural Language Understanding (NLU) API
 * @brief API reference for NLU middleware.
 */
/**
 * @addtogroup nlu_api
 * @{
 */

/** @} */

#if defined(__cplusplus)
}
#endif

#endif /* VA_INC_MTB_NLU_H */
