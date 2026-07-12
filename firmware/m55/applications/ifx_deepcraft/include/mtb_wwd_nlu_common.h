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
 * @file mtb_wwd_nlu_common.h
 * @brief This the header file of ModusToolbox WWD and NLU Common middleware
 * utility module
 *
 */

#ifndef VA_INC_MTB_WWD_NLU_COMMON_H
#define VA_INC_MTB_WWD_NLU_COMMON_H

#include "cy_result.h"
#include "ifx_sp_common_priv.h"
#include "ifx_va_prms.h"
#include "mtb_ml.h"
#include "stdint.h"
#include "va_timer.h"
#include <stdbool.h>


/**
 * @defgroup va_common_api Voice Assistant Common API
 * @brief API reference for Voice Assistant (NLU and WWD) common middleware.
 *
 * This module provides common functionality shared between NLU and WWD modules.
 */

/**
 * @defgroup va_common_macros Voice Assistant Common Macros
 * @ingroup va_common_api
 * @brief Macros for Voice Assistant (NLU and WWD) common middleware.
 * @{
 */

/**
 * @brief Peak frame offset for Voice Assistant (NLU and WWD).
 * @ingroup va_common_macros
 */
#define PEAK_FRAME_OFFSET 3
/**
 * @brief NPU priority for Voice Assistant (NLU and WWD).
 * @ingroup va_common_macros
 */
#define NPU_PRIORITY 3
/**
 * @brief DFWW parameter index for WWD.
 * @ingroup nlu_macros
 */
#define DFWW_PARM_INDEX 5
/**
 * @brief DFCMD parameter 1 index for NLU.
 * @ingroup nlu_macros
 */
#define DFCMD_PARM1_INDEX 5
/**
 * @brief DFCMD parameter 2 index for NLU.
 * @ingroup nlu_macros
 */
#define DFCMD_PARM2_INDEX 6

/**
 * @brief Macro to merge two tokens.
 * @ingroup va_common_macros
 */
#define MERGE(x, y) x##y
/**
 * @brief Macro to expand and merge two tokens.
 * @ingroup va_common_macros
 */
#define EXPAND_AND_MERGE(x, y) MERGE(x, y)
/**
 * @brief Macro to stringify a token.
 * @ingroup va_common_macros
 */
#define STR2(x) #x
/**
 * @brief Macro to stringify a token (wrapper).
 * @ingroup va_common_macros
 */
#define STR(x) STR2(x)
/**
 * @brief Macro to generate header file name string.
 * @ingroup va_common_macros
 */
#define HEADER(name) STR(name.h)
/**
 * @brief Macro to generate app header file name string.
 * @ingroup va_common_macros
 */
#define APP_HEADER(name) STR(app_##name.h)
/**
 * @brief Macro to generate config header file name string.
 * @ingroup va_common_macros
 */
#define CONFIG_HEADER(name) <name ##     _config.h>
/**
 * @brief Macro to generate WWD NLU header file name string.
 * @ingroup va_common_macros
 */
#define MTB_WWD_NLU_HEADER(name) HEADER(name)
/**
 * @brief Macro to generate WWD NLU app header file name string.
 * @ingroup va_common_macros
 */
#define MTB_WWD_NLU_APP_HEADER(name) APP_HEADER(name)
/**
 * @brief Macro to generate WWD NLU config header file name string.
 * @ingroup va_common_macros
 */
#define MTB_WWD_NLU_CONFIG_HEADER(name) CONFIG_HEADER(name)
/**
 * @brief Macro to generate WWD NLU config struct name.
 * @ingroup va_common_macros
 */
#define MTB_WWD_NLU_CONFIG_STRUCT(name)                                        \
    EXPAND_AND_MERGE(name, _##ww_nlu_configs)
/**
 * @brief Macro to generate WWD NLU config callback name.
 * @ingroup va_common_macros
 */
#define MTB_WWD_NLU_CONFIG_CALLBACK(name)                                      \
    EXPAND_AND_MERGE(name, _##wake_word_callback)
/**
 * @brief Macro to generate WWD NLU config number of wake words.
 * @ingroup va_common_macros
 */
#define MTB_WWD_NLU_CONFIG_NUM_WAKE_WORD(name)                                 \
    EXPAND_AND_MERGE(name, _##NO_OF_WAKE_WORD)
/**
 * @brief Macro to generate WWD NLU config max number of wake words.
 * @ingroup va_common_macros
 */
#define MTB_WWD_NLU_CONFIG_MAX_NUM_WAKE_WORD(name)                             \
    EXPAND_AND_MERGE(name, _##NO_MAX_WAKE_WORD)
/**
 * @brief Macro to enable all wake words in WWD NLU config.
 * @ingroup va_common_macros
 */
#define MTB_WWD_NLU_CONFIG_EN_ALL_WAKE_WORD(name)                              \
    EXPAND_AND_MERGE(name, _##ALL_WAKE_WORD)
/**
 * @brief Macro to generate WWD NLU wake word string.
 * @ingroup va_common_macros
 */
#define MTB_WWD_NLU_CONFIG_WAKE_WORD_STR(name) EXPAND_AND_MERGE(name, _##ww_str)
/**
 * @brief Macro to generate NLU intent name list.
 * @ingroup va_common_macros
 */
#define MTB_NLU_INTENT_NAME_LIST(name)                                         \
    EXPAND_AND_MERGE(name, _##intent_name_list)
/**
 * @brief Macro to generate NLU variable name list.
 * @ingroup va_common_macros
 */
#define MTB_NLU_VARIABLE_NAME_LIST(name)                                       \
    EXPAND_AND_MERGE(name, _##variable_name_list)
/**
 * @brief Macro to generate NLU variable phrase list.
 * @ingroup va_common_macros
 */
#define MTB_NLU_VARIABLE_PHRASE_LIST(name)                                     \
    EXPAND_AND_MERGE(name, _##variable_phrase_list)
/**
 * @brief Macro to generate NLU unit phrase list.
 * @ingroup va_common_macros
 */
#define MTB_NLU_UNIT_PHRASE_LIST(name)                                         \
    EXPAND_AND_MERGE(name, _##unit_phrase_list)
/**
 * @brief Maximum number of NLU variables.
 * @ingroup va_common_macros
 */
#define MTB_NLU_MAX_NUM_VARIABLES (4U)

/** @} */

/**
 * @defgroup va_common_enums Voice Assistant Common Enumerated Types
 * @ingroup va_common_api
 * @brief Enumerated types for Voice Assistant (NLU and WWD) common middleware.
 */

/**
 * @defgroup va_common_typedefs Voice Assistant Common Typedefs
 * @ingroup va_common_api
 * @brief Type definitions for Voice Assistant (NLU and WWD) common middleware.
 */

/**
 * @defgroup va_common_structures Voice Assistant Common Structures
 * @ingroup va_common_api
 * @brief Data structures for Voice Assistant (NLU and WWD) common middleware.
 */

/******************************************************************************
 * Typedefs
 *****************************************************************************/
/**
 * @enum mtb_wwd_nlu_events_t
 * @ingroup va_common_enums
 * @brief Events for WWD/NLU processing.
 *
 * This enum defines the types of events that can trigger callbacks during
 * wake word detection processing. Events are triggered based on specific
 * detection results from SOD (Speech-On-Detection) and WWD (Wake Word
 * Detection) stages.
 */
typedef enum {
    CY_EVENT_SOD = 0,
    CY_EVENT_WWD,
    CY_EVENT_SOD_WWD,
} mtb_wwd_nlu_events_t;

/**
 * @typedef cy_callback_t
 * @ingroup va_common_typedefs
 * @brief Callback function type for WWD/NLU events.
 */
typedef void (*cy_callback_t)(mtb_wwd_nlu_events_t);

/******************************************************************************
 * Public definitions
 ******************************************************************************/

#define MTB_VA_RSLT_SUCCESS                 CY_RSLT_SUCCESS
#define MTB_VA_RSLT_INVALID_PARAM           CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 1)
#define MTB_VA_RSLT_PRE_SILENCE_TIMEOUT     CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 2)
#define MTB_VA_RSLT_COMMAND_TIMEOUT         CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 3)
#define MTB_VA_RSLT_LICENSE_ERROR           CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 4)
#define MTB_VA_RSLT_MEM_ALLOC_ERROR         CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 5)
#define MTB_VA_RSLT_ML_INFERENCE_ERROR      CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 6)
#define MTB_VA_RSLT_ML_INIT_ERROR           CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 7)
#define MTB_VA_RSLT_IFX_PARSE_ERROR         CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 8)
#define MTB_VA_RSLT_IFX_INIT_ERROR          CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 9)
#define MTB_VA_RSLT_IFX_RESET_ERROR         CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 10)
#define MTB_VA_RSLT_IFX_INTERNAL_ERROR      CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 11)
#define MTB_VA_RSLT_IFX_DFCMD_ERROR         CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 12)
#define MTB_VA_RSLT_IFX_WWD_ERROR           CY_RSLT_CREATE(CY_RSLT_TYPE_ERROR, CY_RSLT_MODULE_MIDDLEWARE_MW, 13)

/******************************************************************************
 * Structures
 ******************************************************************************/

/**
 * @struct mtb_va_common_t
 * @ingroup va_common_structures
 * @brief Common structure for WWD/NLU processing which encapsulates
 * speech-related containers.
 *
 * This structure implements a borrowing/ownership pattern to share audio
 * processing objects between WWD and NLU modules while preventing double-free
 * errors.
 *
 * @var mtb_va_common_t::pre_proc_hpf_obj
 *   Pre-processing HPF container.
 * @var mtb_va_common_t::sod_obj
 *   Common SOD container that contains state memory and its params.
 * @var mtb_va_common_t::feature_obj
 *   Common itsi feature container.
 * @var mtb_va_common_t::dfww_obj
 *   Common dfwwd container that contains state memory and parameters.
 * @var mtb_va_common_t::is_initialized
 *   Flag indicating if all the fields in the structure are initialized.
 * @var mtb_va_common_t::is_owner
 *   Flag indicating if this structure owns the objects and is responsible for
 * freeing them.
 *   - true: This instance created the objects and must free them in deinit
 *   - false: This instance borrowed the objects, must NOT free them
 */
typedef struct
{
    void *pre_proc_hpf_obj;             /**< Pre-processing HPF container */
    void *sod_obj;                      /**< Common SOD container */
    void *feature_obj;                  /**< Common itsi feature container */
    void *dfww_obj;                     /**< Common dfwwd container */
    bool is_initialized;                /**< Flag indicating if all the fields in the structure are initialized */
    bool is_owner;                      /**< Flag indicating if this structure owns the objects and is responsible for freeing them */
} mtb_va_common_t;

/**
 * @struct mtb_wwd_nlu_buff_t
 * @ingroup va_common_structures
 * @brief Buffer structure for WWD/NLU processing.
 *
 * @var mtb_wwd_nlu_buff_t::am_model_bin
 *   Acoustic model binary.
 * @var mtb_wwd_nlu_buff_t::am_model_buffer
 *   Acoustic model buffer.
 * @var mtb_wwd_nlu_buff_t::data_feed_int
 *   Pointer to integer data feed.
 * @var mtb_wwd_nlu_buff_t::mtb_ml_input_buffer
 *   Pointer to ML input buffer.
 * @var mtb_wwd_nlu_buff_t::ifx_scratch
 *   Scratch memory for IFX.
 * @var mtb_wwd_nlu_buff_t::output_scores
 *   Pointer to output scores.
 * @var mtb_wwd_nlu_buff_t::xIn
 *   Pointer to input features.
 * @var mtb_wwd_nlu_buff_t::features
 *   Pointer to extracted features.
 * @var mtb_wwd_nlu_buff_t::WWD_DetectEvent
 *   Flag to detect command right after wakeword.
 * @var mtb_wwd_nlu_buff_t::nlu_timer
 *   Timer object to control the NLU timeout.
 * @var mtb_wwd_nlu_buff_t::va_common_obj
 *   Objects that are common to both WWD and NLU modules.
 * @var mtb_va_common_t::is_initialized
 *   Flag indicating if the structure is initialized.
 */
typedef struct {
    mtb_ml_model_bin_t am_model_bin;       /**< Acoustic model binary. */
    mtb_ml_model_buffer_t am_model_buffer; /**< Acoustic model buffer. */
    int16_t *data_feed_int;                /**< Pointer to integer data feed. */
    float *mtb_ml_input_buffer;            /**< Pointer to ML input buffer. */
    ifx_scratch_mem_t ifx_scratch;         /**< Scratch memory for IFX. */
    float *output_scores;                  /**< Pointer to output scores. */
    float *xIn;                            /**< Pointer to input features. */
    float *features;                       /**< Pointer to extracted features. */
    bool WWD_DetectEvent;                  /**< Flag to detect command right after wakeword. */
    va_timer_t nlu_timer;                  /**< Timer object to control the NLU timeout. */
    mtb_va_common_t va_common_obj;         /**< Objects that are common to both WWD and NLU modules. */
    bool is_initialized;                   /**< Flag indicating if the structure is initialized. */
} mtb_wwd_nlu_buff_t;

/**
 * @struct mtn_wwd_nlu_callback_setting_t
 * @ingroup va_common_structures
 * @brief Callback setting structure for WWD/NLU.
 *
 * @var mtn_wwd_nlu_callback_setting_t::cb_for_event
 *   Event type for callback.
 * @var mtn_wwd_nlu_callback_setting_t::cb_function
 *   Callback function pointer.
 */
typedef struct {
    mtb_wwd_nlu_events_t cb_for_event;   /**< Event type for callback. */
    cy_callback_t cb_function;           /**< Callback function pointer. */
} mtn_wwd_nlu_callback_setting_t;

/**
 * @struct mtb_wwd_conf_t
 * @ingroup va_common_structures
 * @brief Configuration structure for WWD.
 *
 * @var mtb_wwd_conf_t::callback
 *   Callback settings for WWD.
 */
typedef struct {
    int *ww_params; /**< Pointer to WW configuration parameters. */
    mtn_wwd_nlu_callback_setting_t callback; /**< Callback settings for WWD. */
} mtb_wwd_conf_t;

/**
 * @struct mtb_nlu_setup_array_t
 * @ingroup va_common_structures
 * @brief Setup array structure for NLU.
 *
 * @var mtb_nlu_setup_array_t::intent_name_list
 *   List of intent names.
 * @var mtb_nlu_setup_array_t::variable_name_list
 *   List of variable names.
 * @var mtb_nlu_setup_array_t::variable_phrase_list
 *   List of variable phrases.
 * @var mtb_nlu_setup_array_t::unit_phrase_list
 *   List of unit phrases.
 * @var mtb_nlu_setup_array_t::intent_map_array
 *   Intent map array.
 * @var mtb_nlu_setup_array_t::intent_map_array_sizes
 *   Sizes of intent map arrays.
 * @var mtb_nlu_setup_array_t::variable_phrase_sizes
 *   Sizes of variable phrase lists.
 * @var mtb_nlu_setup_array_t::unit_phrase_map_array
 *   Unit phrase map array.
 * @var mtb_nlu_setup_array_t::unit_phrase_map_array_sizes
 *   Sizes of unit phrase map arrays.
 * @var mtb_nlu_setup_array_t::NUM_UNIT_PHRASES
 *   Number of unit phrases.
 */
typedef struct {
    const char **intent_name_list;       /**< List of intent names. */
    const char **variable_name_list;     /**< List of variable names. */
    const char **variable_phrase_list;   /**< List of variable phrases. */
    const char **unit_phrase_list;       /**< List of unit phrases. */
    const int *intent_map_array;         /**< Intent map array. */
    const int *intent_map_array_sizes;   /**< Sizes of intent map arrays. */
    const int *variable_phrase_sizes;    /**< Sizes of variable phrase lists. */
    const int *unit_phrase_map_array;    /**< Unit phrase map array. */
    const int
        *unit_phrase_map_array_sizes;    /**< Sizes of unit phrase map arrays. */
    const int NUM_UNIT_PHRASES;          /**< Number of unit phrases. */
} mtb_nlu_setup_array_t;

/**
 * @struct mtb_nlu_config_t
 * @ingroup va_common_structures
 * @brief Configuration structure for NLU.
 *
 * @var mtb_nlu_config_t::nlu_params
 *   Pointer to NLU configuration parameters.
 * @var mtb_nlu_config_t::nlu_command_timeout
 *   Command timeout for NLU.
 */
typedef struct {
    int *nlu_params; /**< Pointer to NLU configuration parameters. */
    unsigned int nlu_command_timeout; /**< Command timeout for NLU. */
} mtb_nlu_config_t;

/**
 * @struct mtb_nlu_conf_t
 * @ingroup va_common_structures
 * @brief Configuration structure for NLU.
 *
 * @var mtb_nlu_conf_t::nlu_config
 *   Pointer to NLU configuration.
 * @var mtb_nlu_conf_t::nlu_variable_data
 *   Pointer to NLU variable data.
 */
typedef struct {
    mtb_nlu_config_t *nlu_config; /**< Pointer to NLU configuration. */
    mtb_nlu_setup_array_t
        *nlu_variable_data; /**< Pointer to NLU variable data. */
} mtb_nlu_conf_t;

/**
 * @struct mtb_wwd_nlu_config_t
 * @ingroup va_common_structures
 * @brief WWD/NLU configuration structure.
 *
 * @var mtb_wwd_nlu_config_t::ww_model_ptr
 *   Pointer to wake word model.
 * @var mtb_wwd_nlu_config_t::cmd_model_ptr
 *   Pointer to command model.
 * @var mtb_wwd_nlu_config_t::nmb_model_ptr
 *   Pointer to NMB model.
 * @var mtb_wwd_nlu_config_t::sod_params
 *   Pointer to SOD configuration parameters.
 * @var mtb_wwd_nlu_config_t::hpf_params
 *   Pointer to HPF configuration parameters.
 * @var mtb_wwd_nlu_config_t::denoise_params
 *   Pointer to de-noise configuration parameters.
 * @var mtb_wwd_nlu_config_t::ww_conf
 *   Pointer to WWD configuration.
 * @var mtb_wwd_nlu_config_t::nlu_conf
 *   NLU configuration object.
 * @var mtb_wwd_nlu_config_t::wwd_nlu_buff_data
 *   Pointer to WWD/NLU buffer data.
 */
typedef struct {
    const char *ww_model_ptr;  /**< Pointer to wake word model. */
    const char *cmd_model_ptr; /**< Pointer to command model. */
    const char *nmb_model_ptr; /**< Pointer to NMB model. */
    int *sod_params;           /**< Pointer to SOD configuration parameters. */
    int *hpf_params;           /**< Pointer to HPF configuration parameters. */
    int *denoise_params;       /**< Pointer to de-noise configuration parameters. */
    mtb_wwd_conf_t *ww_conf;   /**< Pointer to WWD configuration. */
    mtb_nlu_conf_t nlu_conf;   /**< NLU configuration object. */
    mtb_wwd_nlu_buff_t
        *wwd_nlu_buff_data;    /**< Pointer to WWD/NLU buffer data. */
} mtb_wwd_nlu_config_t;

#if defined(__cplusplus)
}
#endif

#endif /* VA_INC_MTB_WWD_NLU_COMMON_H */
