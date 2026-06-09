/****************************************************************************
* File Name        : Smart_Lights_Demo_config.c
*
* Description      : This source file contains the configuration object for WWD and NLU
*
* Related Document : See README.md
*
*****************************************************************************
* Copyright 2025, Cypress Semiconductor Corporation (an Infineon company)
* All rights reserved.
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
*****************************************************************************/

#include "Smart_Lights_Demo_config.h"

#include "mtb_ml.h"
#include "mtb_ml_model_16x8.h"
#include "AM_LSTM_tflm_model_int16x8.h"

#include "ifx_va_prms.h"
#include "ifx_sp_common_priv.h"

#include "Smart_Lights_Demo_U55_WWmodel.h"
#ifndef XIAOZHI_DEEPCRAFT_WW_ONLY
#include "Smart_Lights_Demo_U55_CMDmodel.h"
#include "U55_NMBmodel.h"
#endif

#include "Smart_Lights_Demo.h"
#include "Smart_Lights_Demo_ifx_va_config_prms.h"

/* Following am_tensor_arena has been counted as part of persistent memory total size */
/* Tensor_arena buffer must be in SOCMEM and aligned by 16 which are required by U55 */
static uint8_t am_tensor_arena[AM_LSTM_ARENA_SIZE] __attribute__((aligned(16)))
                                          __attribute__((section(".cy_socmem_data")));


static int16_t data_feed_int[N_SEQ * FEATURE_BUF_SZ] __attribute__((aligned(16)))
                                          __attribute__((section(".cy_socmem_data")));
static float mtb_ml_input_buffer[N_SEQ * FEATURE_BUF_SZ] __attribute__((aligned(16)))
                                          __attribute__((section(".cy_socmem_data")));

static float xIn[FRAME_SIZE_16K] __attribute__((aligned(16)))
                                          __attribute__((section(".cy_socmem_data")));
static float features[FEATURE_BUF_SZ] __attribute__((aligned(16)))
                                          __attribute__((section(".cy_socmem_data")));
static float output_scores[(N_PHONEMES + 1) * (1 + AM_LOOKBACK)] __attribute__((aligned(16)))
                                          __attribute__((section(".cy_socmem_data")));

//common buffers
static mtb_wwd_nlu_buff_t wwd_nlu_buff =
{
    .am_model_bin = { MTB_ML_MODEL_BIN_DATA(AM_LSTM) },
    .am_model_buffer = {
        .tensor_arena = am_tensor_arena,
        .tensor_arena_size = AM_LSTM_ARENA_SIZE
    },
    .data_feed_int = data_feed_int,
    .mtb_ml_input_buffer = mtb_ml_input_buffer,
    .output_scores = output_scores,
    .xIn = xIn,
    .features = features
};

// NLU setup array
static mtb_nlu_setup_array_t nlu_setup_array =
{
    .intent_name_list = Smart_Lights_Demo_intent_name_list,
    .variable_name_list = Smart_Lights_Demo_variable_name_list,
    .variable_phrase_list = Smart_Lights_Demo_variable_phrase_list,
    .unit_phrase_list = Smart_Lights_Demo_unit_phrase_list,
    .intent_map_array = Smart_Lights_Demo_intent_map_array,
    .intent_map_array_sizes = Smart_Lights_Demo_intent_map_array_sizes,
    .variable_phrase_sizes = Smart_Lights_Demo_variable_phrase_sizes,
    .unit_phrase_map_array = Smart_Lights_Demo_unit_phrase_map_array,
    .unit_phrase_map_array_sizes = Smart_Lights_Demo_unit_phrase_map_array_sizes,
    .NUM_UNIT_PHRASES = sizeof(Smart_Lights_Demo_unit_phrase_list),
};

// WW config
static mtb_wwd_conf_t ww_conf = {
    .ww_params = Smart_Lights_Demo_dfww_prms,
    .callback.cb_for_event = CY_EVENT_SOD,
    .callback.cb_function = Smart_Lights_Demo_wake_word_callback
};

// NLU config
static mtb_nlu_config_t nlu_conf = {
    .nlu_params = Smart_Lights_Demo_dfcmd_prms,
    .nlu_command_timeout = 5000,
};

static mtb_wwd_nlu_config_t ww_1_conf = {
    .ww_model_ptr = Smart_Lights_Demo_WWmodeldata,
#ifdef XIAOZHI_DEEPCRAFT_WW_ONLY
    .cmd_model_ptr = NULL,
    .nmb_model_ptr = NULL,
#else
    .cmd_model_ptr = Smart_Lights_Demo_CMDmodeldata,
    .nmb_model_ptr = NMBmodeldata,
#endif
    .wwd_nlu_buff_data = &wwd_nlu_buff,
    .sod_params = Smart_Lights_Demo_sod_prms,
    .hpf_params = Smart_Lights_Demo_pre_proc_hpf_prms,
    .denoise_params = Smart_Lights_Demo_denoise_prms,
    .ww_conf = &ww_conf,
#ifdef XIAOZHI_DEEPCRAFT_WW_ONLY
    .nlu_conf.nlu_config = NULL,
    .nlu_conf.nlu_variable_data = NULL,
#else
    .nlu_conf.nlu_config = &nlu_conf,
    .nlu_conf.nlu_variable_data = &nlu_setup_array,
#endif
};

mtb_wwd_nlu_config_t *Smart_Lights_Demo_ww_nlu_configs[SMART_LIGHTS_DEMO_NO_OF_WAKE_WORD] = {&ww_1_conf
};

char *Smart_Lights_Demo_ww_str[SMART_LIGHTS_DEMO_NO_OF_WAKE_WORD] = {"OK Infineon"};

const char* Smart_Lights_Demo_intent_name_list[SMART_LIGHTS_DEMO_NUM_INTENTS] = {
    "TurnOnLights",
    "TurnOffLights",
    "TurnOnAllLights",
    "ChangeLights",
};

const char* Smart_Lights_Demo_variable_name_list[SMART_LIGHTS_DEMO_NUM_VARIABLES] = {
    "LocationLightsOn",
    "LocationLightsOff",
    "Intensity",
};

const char* Smart_Lights_Demo_variable_phrase_list[SMART_LIGHTS_DEMO_NUM_VARIABLE_PHRASES] = {
    "kitchen", "bedroom", "living room", // LocationLightsOn
    "kitchen", "bedroom", "living room", // LocationLightsOff
    "", // Intensity
};

const char* Smart_Lights_Demo_unit_phrase_list[SMART_LIGHTS_DEMO_NUM_UNIT_PHRASES] = {
    "degree", "degrees", 
    "percent", 
    "level", "levels", 
    "hour", "hours", 
    "minute", "minutes", 
    "second", "seconds", 
    "day", "days", 
    "", 
    "AM", 
    "PM", 
};

const int Smart_Lights_Demo_intent_map_array[SMART_LIGHTS_DEMO_INTENT_MAP_ARRAY_TOTAL_SIZE] = {
    0, 1, 0, 0, // lights on (kitchen)
    0, 1, 0, 1, // lights on (bedroom)
    0, 1, 0, 2, // lights on (living room)
    0, 1, 0, 0, // lights on at (kitchen)
    0, 1, 0, 1, // lights on at (bedroom)
    0, 1, 0, 2, // lights on at (living room)
    0, 1, 0, 0, // lights on at the (kitchen)
    0, 1, 0, 1, // lights on at the (bedroom)
    0, 1, 0, 2, // lights on at the (living room)
    0, 1, 0, 0, // lights on in the (kitchen)
    0, 1, 0, 1, // lights on in the (bedroom)
    0, 1, 0, 2, // lights on in the (living room)
    0, 1, 0, 0, // switch on lights (kitchen)
    0, 1, 0, 1, // switch on lights (bedroom)
    0, 1, 0, 2, // switch on lights (living room)
    0, 1, 0, 0, // switch on lights at (kitchen)
    0, 1, 0, 1, // switch on lights at (bedroom)
    0, 1, 0, 2, // switch on lights at (living room)
    0, 1, 0, 0, // switch on lights at the (kitchen)
    0, 1, 0, 1, // switch on lights at the (bedroom)
    0, 1, 0, 2, // switch on lights at the (living room)
    0, 1, 0, 0, // switch on lights in the (kitchen)
    0, 1, 0, 1, // switch on lights in the (bedroom)
    0, 1, 0, 2, // switch on lights in the (living room)
    0, 1, 0, 0, // turn on lights (kitchen)
    0, 1, 0, 1, // turn on lights (bedroom)
    0, 1, 0, 2, // turn on lights (living room)
    0, 1, 0, 0, // turn on lights at (kitchen)
    0, 1, 0, 1, // turn on lights at (bedroom)
    0, 1, 0, 2, // turn on lights at (living room)
    0, 1, 0, 0, // turn on lights at the (kitchen)
    0, 1, 0, 1, // turn on lights at the (bedroom)
    0, 1, 0, 2, // turn on lights at the (living room)
    0, 1, 0, 0, // turn on lights in the (kitchen)
    0, 1, 0, 1, // turn on lights in the (bedroom)
    0, 1, 0, 2, // turn on lights in the (living room)
    1, 1, 1, 0, // lights off (kitchen)
    1, 1, 1, 1, // lights off (bedroom)
    1, 1, 1, 2, // lights off (living room)
    1, 1, 1, 0, // lights off at (kitchen)
    1, 1, 1, 1, // lights off at (bedroom)
    1, 1, 1, 2, // lights off at (living room)
    1, 1, 1, 0, // lights off at the (kitchen)
    1, 1, 1, 1, // lights off at the (bedroom)
    1, 1, 1, 2, // lights off at the (living room)
    1, 1, 1, 0, // lights off in the (kitchen)
    1, 1, 1, 1, // lights off in the (bedroom)
    1, 1, 1, 2, // lights off in the (living room)
    1, 1, 1, 0, // switch off lights (kitchen)
    1, 1, 1, 1, // switch off lights (bedroom)
    1, 1, 1, 2, // switch off lights (living room)
    1, 1, 1, 0, // switch off lights at (kitchen)
    1, 1, 1, 1, // switch off lights at (bedroom)
    1, 1, 1, 2, // switch off lights at (living room)
    1, 1, 1, 0, // switch off lights at the (kitchen)
    1, 1, 1, 1, // switch off lights at the (bedroom)
    1, 1, 1, 2, // switch off lights at the (living room)
    1, 1, 1, 0, // switch off lights in the (kitchen)
    1, 1, 1, 1, // switch off lights in the (bedroom)
    1, 1, 1, 2, // switch off lights in the (living room)
    1, 1, 1, 0, // turn off lights (kitchen)
    1, 1, 1, 1, // turn off lights (bedroom)
    1, 1, 1, 2, // turn off lights (living room)
    1, 1, 1, 0, // turn off lights at (kitchen)
    1, 1, 1, 1, // turn off lights at (bedroom)
    1, 1, 1, 2, // turn off lights at (living room)
    1, 1, 1, 0, // turn off lights at the (kitchen)
    1, 1, 1, 1, // turn off lights at the (bedroom)
    1, 1, 1, 2, // turn off lights at the (living room)
    1, 1, 1, 0, // turn off lights in the (kitchen)
    1, 1, 1, 1, // turn off lights in the (bedroom)
    1, 1, 1, 2, // turn off lights in the (living room)
    2, 0, // Turn on all lights
    3, 1, 2, -1, // dim lights at level <numbers10> {}
    3, 1, 2, -1, // dim lights with level <numbers10> {}
    3, 1, 2, -1, // dim lights to level <numbers10> {}
    3, 1, 2, -1, // turn lights at level <numbers10> {}
    3, 1, 2, -1, // turn lights with level <numbers10> {}
    3, 1, 2, -1, // turn lights to level <numbers10> {}
    3, 1, 2, -1, // set lights at level <numbers10> {}
    3, 1, 2, -1, // set lights with level <numbers10> {}
    3, 1, 2, -1, // set lights to level <numbers10> {}
};

const int Smart_Lights_Demo_intent_map_array_sizes[SMART_LIGHTS_DEMO_NUM_COMMANDS] = {
    4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 
    4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 
    4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 2, 4, 4, 
    4, 4, 4, 4, 4, 4, 4, 
};

const int Smart_Lights_Demo_variable_phrase_sizes[SMART_LIGHTS_DEMO_NUM_VARIABLES] = {
    3, // LocationLightsOn: (kitchen,bedroom,living room)
    3, // LocationLightsOff: (kitchen,bedroom,living room)
    0, // Intensity: None
};

const int Smart_Lights_Demo_unit_phrase_map_array[SMART_LIGHTS_DEMO_UNIT_PHRASE_MAP_ARRAY_TOTAL_SIZE] = {
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    0, // None
    1, 1, 13, // {}
    1, 1, 13, // {}
    1, 1, 13, // {}
    1, 1, 13, // {}
    1, 1, 13, // {}
    1, 1, 13, // {}
    1, 1, 13, // {}
    1, 1, 13, // {}
    1, 1, 13, // {}
};

const int Smart_Lights_Demo_unit_phrase_map_array_sizes[SMART_LIGHTS_DEMO_NUM_COMMANDS] = {
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 
    3, 3, 3, 3, 3, 3, 3, 
};



__attribute__((weak)) void Smart_Lights_Demo_wake_word_callback(mtb_wwd_nlu_events_t event)
{

}
