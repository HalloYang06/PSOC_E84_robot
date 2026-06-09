/******************************************************************************
* File Name: ifx_sp_enh.h
*
* Description: This file contains public interface for Infineon HP speech enhancement app
*
* Related Document: See README.md
*
*******************************************************************************
* (c) 2021, Infineon Technologies Company. All rights reserved.
*******************************************************************************
* This software, including source code, documentation and related materials
* ("Software"), is owned by Infineon Technologies Company (Infineon) or one of its
* subsidiaries and is protected by and subject to worldwide patent
* protection (United States and foreign), United States copyright laws and
* international treaty provisions. Therefore, you may use this Software only
* as provided in the license agreement accompanying the software package from
* which you obtained this Software ("EULA").
*
* If no EULA applies, Infineon hereby grants you a personal, non-exclusive,
* non-transferable license to copy, modify, and compile the Software source
* code solely for use in connection with Infineon's integrated circuit products.
* Any reproduction, modification, translation, compilation, or representation
* of this Software except as specified above is prohibited without the express
* written permission of Infineon.
*
* Disclaimer: THIS SOFTWARE IS PROVIDED AS-IS, WITH NO WARRANTY OF ANY KIND,
* EXPRESS OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, NONINFRINGEMENT, IMPLIED
* WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. Infineon
* reserves the right to make changes to the Software without notice. Infineon
* does not assume any liability arising out of the application or use of the
* Software or any product or circuit described in the Software. Infineon does
* not authorize its products for use in any products where a malfunction or
* failure of the Infineon product may reasonably be expected to result in
* significant property damage, injury or death ("High Risk Product"). By
* including Infineon's product in a High Risk Product, the manufacturer of such
* system or application assumes all risk of such use and in doing so agrees to
* indemnify Infineon against all liability.
*******************************************************************************/

/*******************************************************************************
* Include guard
*******************************************************************************/
#ifndef __IFX_SP_ENH_H
#define __IFX_SP_ENH_H

#if defined(__cplusplus)
extern "C" {
#endif

/*******************************************************************************
* Include header file
*******************************************************************************/
#include <stdint.h>
#include <stdbool.h>
#include "ifx_sp_common.h"
/*******************************************************************************
* Compile-time flags
*******************************************************************************/

/*******************************************************************************
* High performance speech enhancement data type & defines
*******************************************************************************/
#define HP_SP_ENH_SAMPLING_RATE   16000
#define HP_SP_ENH_FRAME_SAMPLES   160
#define MAX_NUM_MONITOR_COMPONENT 4
#define MAX_NUM_MONITOR_OUTPUT    10
#define MAX_CUTOFF_FREQ           200
#define MIN_CUTOFF_FREQ           20
#define MAX_INPUT_GAIN_DB         0
#define MIN_INPUT_GAIN_DB         -60
#define MAX_NS_GAIN_DB            20
#define MIN_NS_GAIN_DB            0
#define MAX_NUM_MICS              2
#define MIN_NUM_MICS              1
#define MAX_MIC_DISTANCE_MM       100
#define MIN_MIC_DISTANCE_MM       20
#define MAX_ANGLE_RANGE           180
#define MIN_ANGLE_RANGE           0
#define MAX_NUM_BEAMS             12
#define MIN_NUM_BEAMS             1
#define MAX_TAIL_LEN_MSEC         128
#define MIN_TAIL_LEN_MSEC         0
#define MAX_BULK_DELAY_MSEC       64
#define MIN_BULK_DELAY_MSEC       0


typedef struct
{
    int32_t cutoff_freq_hz;  /**< HPF cutoff frequency in Hz */
    int32_t gain_q8_dB[MAX_NUM_MICS];/**< attenuation gain in Q8 format unit dB, set during calibration */
} hpf_settings_struct_t;

typedef struct
{
    int32_t tail_len_msec;   /**< AEC tail length in ms */
    int32_t bulk_delay_msec; /**< AEC bulk delay in ms, set during calibration  */
} aec_settings_struct_t;

typedef struct
{
    int32_t mic_distance_mm;  /**< mic distance in mm unit */
    int32_t angle_range_start;/**< start angle range in degree */
    int32_t angle_range_stop; /**< end angle range in degree */
    int32_t num_beams;        /**< number of beams */
    int32_t aggressiveness;   /**< beamformer agressiveness setting */
} bf_settings_struct_t;

typedef struct
{
    int8_t aggressiveness;
} drvb_settings_struct_t;

typedef struct
{
    int32_t aggressiveness;   /**< echo suppressor agressiveness setting */
} es_settings_struct_t;

typedef struct
{
    int32_t aggressiveness;   /**< deep subband echo suppressor agressiveness setting */
} dses_settings_struct_t;

typedef struct
{
    int32_t ns_gain_dB;     /**< noise suppressor gain setting */
} ns_settings_struct_t;

typedef struct
{
    int32_t ns_gain_dB;   /**< deep subband noise suppressor gain setting */
} dsns_settings_struct_t;

typedef struct
{// global configuration-time settings
    int32_t sampling_rate;      /**< audio and voice data sampling rate */
    int32_t frame_size;         /**< input (output) frame size in audio samples */
    int32_t num_mics;           /**< number of mics */
    int32_t num_monitor_components;/**< Infineon spreech enhancement application number of monitor components */
    int32_t monitor_component_id[MAX_NUM_MONITOR_COMPONENT];  /**< list of monitor components; actuall valid items
                                                             in the array is determined by num_monitor_components */
} sp_enh_common_setting_struct_t;

/*******************************************************************************
* Structures and enumerations
*******************************************************************************/
/** Defines BF, ES aggressiveness level */
typedef enum
{
    IFX_SP_ENH_AGGRESSIVE_LOW = 0,
    IFX_SP_ENH_AGGRESSIVE_MEDIUM,
    IFX_SP_ENH_AGGRESSIVE_HIGH
} ifx_aggressiveness_config_t;

typedef enum
{
    ACTIVE_OFF = 0,
    ACTIVE_ON,
} ifx_active_control_config_t;

/**
 * Shared control/model structure
 */
typedef struct
{
    /*@{*/
    sp_enh_common_setting_struct_t common;
    hpf_settings_struct_t hpf_setting;
    aec_settings_struct_t aec_setting;
    bf_settings_struct_t bf_setting;
    drvb_settings_struct_t drvb_setting;
    es_settings_struct_t es_setting;
    dses_settings_struct_t dses_setting;
    ns_settings_struct_t ns_setting;
    dsns_settings_struct_t dsns_setting;
    int ns_es_type;             /**< noise & echo suppression type */
    int block_size;             /**< processing block size */
    int overlap_size;           /**< processing overlap size */
    int fft_size;               /**< FFT size */
    int kfft_size;              /**< FFT size up to Nyquist rate */
    int skip_size;              /**< number of freqency bins to skip during processing */
    int rfft_size;              /**< reduced number of FFT bints to be processed */
    int bulk_delay_buf_size;    /**< reference signal bulk delay buffer size */
    int num_config_components;  /**< total number of configured components in spreech enhancement application */
    int num_of_hpf;             /**< number of internal hpf */
    int num_of_ana;             /**< number of total analysis including required for DSES */
    int num_of_syn;             /**< number of total sythesis including required for monitor outputs */
    int num_of_monitor_outputs; /**< number of total monitor outputs */
    uint32_t enable_flag;       /**< component enable flag */
    uint32_t monitor_flag;      /**< component minitor flag */
    mem_info_t memory;          /**< memory structure contains info required for process */
    persistent_mem_info_t bf_pm;/**< beamforming persistent memory info */
    persistent_mem_info_t dsns_socmem;    /**< DSNS SOCMEM persistent memory info */
    persistent_mem_info_t dses_socmem;    /**< DSES SOCMEM persistent memory info */
    persistent_mem_info_t gde_pm;/**< GDE persistent memory info */
    int libsp_version;          /**< version number of speech enhancement IP library */
    int configurator_version;   /**< Audio Front-End configurator version number */
    /*@}*/
} ifx_stc_sp_enh_info_t;

/******************************************************************************
* Function prototype
******************************************************************************/
/**
 * \addtogroup API
 * @{
 */

/**
 * \brief : ifx_sp_enh_process() is the API function to perform audio & voice enhancement process.
 *
 * Ifx audio & voice enhancement proces API function targeted for ifx MCU embedded application.
 *
 * \param[in]      modelPt         : Pointer to ifx parsed audio & voice enhancement process model data container
 * \param[in, out] input1          : Data pointer to first audio (e.g. first microphone) input and output of HPF
 * \param[in, out] input2          : Data pointer to second audio (e.g. second microphone) input and output of HPF; NULL if there is no second audio/mic input
 * \param[in]      reference_input : AEC reference input data pointer; NULL if there is no AEC reference
 * \param[out]     output          : Ifx audio & voice enhancement proces output data pointer
 * \param[out]     ifx_output      : Output data pointer for Infineon internal useage, for example, up to 4 concatenated monitor outputs
 * \param[out]     meter_output    : Audio peak meter output pointer; 1st input, 2nd input (if 2 mic), output level values per frame.
 *
 * \return                  : Return 0 when success, otherwise return following error code
 *                            IFX_SP_ENH_ERR_INVALID_ARGUMENT if input or output argument is invalid
 *                            or error code from specific ifx audio & voice enhancement proces module.
 *                            Please note error code is 8bit LSB, line number where the error happened in
 *                            code is in 16bit MSB, and its IP component index if applicable will be at
 *                            bit 8 to 15 in the combined 32bit return value.
 */
int32_t ifx_sp_enh_process(void *modelPt, void *input1, void* input2, void *reference_input, void *output, void *ifx_output, void* meter_output);

/**
 * \brief : ifx_sp_enh_model_parse() is the API function to parse audio & voice enhancement process model parameters to get basic info.
 *
 * It will parse info from the audio & voice enhancement process model parameter buffer to get required basic info such as
 * persistent and scratch memory sizes, input data size, output classification size and stored
 * them in to ifx_stc_sp_enh_info_t structure.
 *
 * \param[in]   fn_prms       : Ifx audio & voice enhancement process model parameter buffer pointer
 * \param[out]  mdl_infoPt    : Pointer to ifx_stc_sp_enh_info_t structure
 *
 * \return                    : Return 0 when success, otherwise return following error code
 *                                IFX_SP_ENH_ERR_INVALID_ARGUMENT if input or output argument is invalid
 *                                Please note error code is 8bit LSB, line number where the error happened in
 *                                code is in 16bit MSB, and its IP component index if applicable will be at
 *                                bit 8 to 15 in the combined 32bit return value.
 */

int32_t ifx_sp_enh_model_parse(int32_t*fn_prms, ifx_stc_sp_enh_info_t *mdl_infoPt);

/**
 * \brief : ifx_sp_enh_init() is the API function to parse and initialize ifx audio & voice enhancement process data container.
 *
 * From the API inputs, it parses audio & voice enhancement process model and initializes its data container.
 *
 * \param[out]  dPt_container   : Pointer to ifx audio & voice enhancement process model data container pointer
 * \param[in]   mdl_infoPt      : Pointer to ifx_stc_sp_enh_info_t structure
 * \param[in]   fn_coeffs       : Ifx audio & voice enhancement process model coefficient buffer pointer
 * \param[in]   num_coeff_bytes : Number of bytes in coefficient data buffer
 *
 * \return                      : Return 0 when success, otherwise return error code
 *                                Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input or output argument is invalid,
 *                                Otherwise return other errors:
 *                                e.g. IFX_SP_ENH_ERR_PARAM if the audio & voice enhancement component IP parameter is invalid.
 *                                Please note error code is 8bit LSB, line number where the error happened in
 *                                code is in 16bit MSB, and its IP component index if applicable will be at bit 8 to 15
 *                                in the combined 32bit return value.
*/

int32_t ifx_sp_enh_init(void** dPt_container, ifx_stc_sp_enh_info_t* mdl_infoPt, uint8_t* fn_coeffs, int32_t num_coeff_bytes);

/**
 * \brief : ifx_sp_enh_mode_control() is the API function to control ifx audio & voice enhancement process compenent's mode.
 *
 * This API is used to control ifx audio & voice enhancement process IP component's mode. This API can be called after initilization.
 * If the ifx audio & voice enhancement process IP component is not configured as valid. This API will do nothing.
 *
 * \param[out]  modelPt         : Pointer to ifx audio & voice enhancement process model data container pointer
 * \param[in]   mdl_infoPt      : Pointer to ifx_stc_sp_enh_info_t structure
 * \param[in]   component_id    : ifx audio & voice enhancement process component ID
 * \param[in]   active          : Component_id active run-time on/off/no change
 * \param[in]   reset           : If value = true, reset component_id's state. If value = false, no change on component's state.
 * \param[in]   update          : If value = true, update component_id's parameter. If value = false, no change on component's parameter.
 * \param[in]   value_pt        : If update = true, this is new parameter pointer. If update = false, this is dummy and ignored by this function.
 *
 * \return                      : Return 0 when success, otherwise return error code
 *                                Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input argument is invalid.
*/

int32_t ifx_sp_enh_mode_control(void* modelPt, ifx_stc_sp_enh_info_t* mdl_infoPt, ifx_sp_enh_ip_component_config_t component_id, ifx_active_control_config_t active, bool reset, bool update, int32_t* value_pt);

/**
 * \brief : ifx_sp_enh_config_status() is the API function to query ifx audio & voice enhancement process compenent's configuration status.
 *
 * This API can be called after initilization.
 * If the ifx audio & voice enhancement process IP component is not configured as valid. This API will return status as not configured.
 *
 * \param[out]  modelPt         : Pointer to ifx audio & voice enhancement process model data container pointer
 * \param[in]   component_id    : ifx audio & voice enhancement process component ID
 *
 * \return                      : Return 0 means not configured
 *                                Return 1 means configured
*/

int32_t ifx_sp_enh_config_status(void* modelPt, ifx_sp_enh_ip_component_config_t component_id);

/**
 * \brief : ifx_sp_enh_active_status() is the API function to query ifx audio & voice enhancement process compenent's activity status.
 *
 * This API can be called after initilization.
 * If the ifx audio & voice enhancement process IP component is in by pass mode. This API will return status as not active.
 *
 * \param[out]  modelPt         : Pointer to ifx audio & voice enhancement process model data container pointer
 * \param[in]   component_id    : ifx audio & voice enhancement process component ID
 *
 * \return                      : Return 0 means not active
 *                                Return 1 means active
*/

int32_t ifx_sp_enh_active_status(void* modelPt, ifx_sp_enh_ip_component_config_t component_id);

/**
 * \brief : my_profile_get_tsc() is an API function to read time stamp counter (TSC) .
 *
 * Platform specific function to read HW time stamp counter or OS tick timer counter for profiling.
 * The application program developer should provide this function if profiling is enabled.
 *
 * \param[out]   val        : Pointer to time stamp counter return value
 *
 * \return                  : Return 0 when success, otherwise return error code
 */
int32_t platform_profile_get_tsc(uint32_t *val);

/**
 * \brief : Initialize profile configuration.
 *
 * This API is used to setup profile configuration and specify the callback function to handle the
 * profile log. If no callback function is specified, the profile log will be printed out on console.
 *
 * \param[in]  modelPt         : Pointer to ifx audio & voice enhancement process data container pointer
 * \param[in]  config          : Profile setting
 * \param[in]  cb_func         : Callback function to handle the profile result.
 * \param[in]  cb_arg          : Callback function argument
 *
 * \return                     : Return 0 when success, otherwise return error code
 *                               Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input parameter is invalid.
*/
int32_t ifx_sp_enh_profile_init(void *modelPt, int32_t config, ifx_sp_profile_cb_fun cb_func, void *cb_arg);

/**
 * \brief : Update  profile configuration.
 *
 * This API is used to update profile configuration.
 *
 * \param[in]  modelPt         : Pointer to ifx audio & voice enhancement process data container pointer
 * \param[in]  config          : Profile setting
 *
 * \return                     : Return 0 when success, otherwise return error code
 *                               Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input parameter is invalid.
*/
int32_t ifx_sp_enh_profile_control(void *modelPt, int32_t config);

/**
 * \brief : Print profile log.
 *
 *
 * \param[in]  modelPt         : Pointer to ifx audio & voice enhancement process data container pointer
 * \return                     : Return 0 when success, otherwise return error code
 *                               Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input parameter is invalid.
*/
int32_t ifx_sp_enh_profile_print(void *modelPt);

/**
 * \brief : ifx_sp_enh_get_mode_control_value() is the API function to get control value of ifx audio & voice enhancement process component.
 *
 * This API is used to get control value of ifx audio & voice enhancement process component. This API can be called after initilization.
 * If the ifx audio & voice enhancement process IP component is not configured as valid, this API will return error.
 *
 * \param[in]   modelPt         : Pointer to ifx audio & voice enhancement process model data container pointer
 * \param[in]   component_id    : ifx audio & voice enhancement process component ID
 * \param[out]  value_struct_pt : Parameter structure pointer and the structure is a copy of the component_id's settings structure.
 * \return                      : Return 0 when success, otherwise return error code
 *                                Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input argument is invalid.
*/
int32_t ifx_sp_enh_get_mode_control_value(void* modelPt, ifx_sp_enh_ip_component_config_t component_id, void *value_struct_pt);

/**
 * \brief : ifx_sp_enh_configure_monitor_out() is the API function to configure monitor output.
 *
 * This API is used to configure monitor output.
 *
 * \param[in]   container       : Pointer to ifx audio & voice enhancement process model data container pointer
 * \param[in]   component_id    : ifx audio & voice enhancement process component ID
 * \param[out]  enable          : If value = true, set component_id's monitor flag bit. If value = false, clear component_id's monitor flag bit.
 * \return                      : Return 0 when success, otherwise return error code
 *                                Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input argument is invalid.
*/
int32_t ifx_sp_enh_configure_monitor_out(void* container, ifx_sp_enh_ip_component_config_t component_id, bool enable);

/**
 * \brief : ifx_sp_enh_deinit_internal_mem() is the API function to deinit internal memory allocated for ifx_sp_enh_process().
 *
 * This API is used to free internal memory at the end of ifx_sp_enh_process().
 *
 * \param[in]   dPt_container   : Pointer to ifx audio & voice enhancement process model data container pointer
 * \return                      : Return 0 when success, otherwise return error code
 *                                Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input argument is invalid.
*/
int32_t ifx_sp_enh_deinit_internal_mem(void* dPt_container);

/**
 * @} end of API group
 */

#if defined(__cplusplus)
}
#endif

#endif /*__IFX_SP_ENH_H */

/* [] END OF FILE */
