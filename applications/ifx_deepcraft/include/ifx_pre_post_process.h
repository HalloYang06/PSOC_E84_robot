/******************************************************************************
* File Name: ifx_pre_post_process.h
*
* Description: This file contains public interface for Infineon pre and
*              post process
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
#ifndef __IFX_PRE_POST_PROCESS_H
#define __IFX_PRE_POST_PROCESS_H

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
* Structures and enumerations
*******************************************************************************/

/** Defines ifx pre and post process IP components */
typedef enum
{
    IFX_PRE_PROCESS_IP_COMPONENT_SOD = IFX_PRE_POST_IP_COMPONENT_START_ID,  /* Infineon LPWWD SOD IP component */
    IFX_PRE_PROCESS_IP_COMPONENT_HPF,
    IFX_PRE_PROCESS_IP_COMPONENT_DENOISE,
    IFX_PRE_PROCESS_IP_COMPONENT_AMPREDICT,
    IFX_PRE_PROCESS_IP_COMPONENT_ASRC_LPF,
    IFX_PRE_PROCESS_IP_COMPONENT_LOG_MEL,
    IFX_PRE_PROCESS_IP_COMPONENT_MFCC,
    IFX_POST_PROCESS_IP_COMPONENT_DFWWD,
    IFX_POST_PROCESS_IP_COMPONENT_HMMS,
    IFX_POST_PROCESS_IP_COMPONENT_DFCMD,
    IFX_POST_PROCESS_IP_COMPONENT_AGC,
    IFX_POST_PROCESS_IP_COMPONENT_LPWWD,
    IFX_POST_PROCESS_IP_COMPONENT_MAX_COUNT
} ifx_pre_post_ip_component_config_t;

typedef enum agc_mode_t {
    SPEECH_MODE, MUSIC_MODE
}agc_mode;

#define AGC_MAX_TARGET_LEVEL_DB  10
#define AGC_MIN_TARGET_LEVEL_DB  -30

/**
 * Shared control/model structure
 */
typedef struct ifx_stc_pre_post_process_info_t
{
    /*@{*/
    int component_id;           /**< pre or post process compnent ID */
    int sampling_rate;          /**< audio and voice data sampling rate in Hz */
    int input_frame_size;       /**< input data frame size in samples */
    int frame_shift;            /**< input data frame shift in samples */
    int fft_block_size;         /**< fft block size in samples */
    int output_size;            /**< spreech enhancement application output size in its data type */
    mem_info_t memory;          /**< memory structure contains info required for process */
    int libsp_version;          /**< version number of Infineon pre and post process IP library */
    int configurator_version;   /**< Configurator version number */
    /*@}*/
} ifx_stc_pre_post_process_info_t;


/******************************************************************************
* Function prototype
******************************************************************************/
/**
 * \addtogroup API
 * @{
 */

/**
 * \brief : ifx_pre_post_process_parse() is the API function to parse basic info and estimate memory
 *          needed by ip_id component block. This only needed for parse confiurator generated parameter file.
 *
 *
 * \param[in]  ip_prms_buffer   : Configuration parameter buffer which has component ID and related parameters
 *                              : For SOD, it contains SOD configuration parameter: [configuration version, sampling rate(Hz),
 *                              : input frame size (samples), SOD component ID, number of following parameters,
 *                              : GapSetting (0,100,200,300,400,500,1000)ms, SensLevel (0-32767)]
 *                              : For preprocess, it contains preprocess configuration parameter: [configuration version,
 *                              : sampling rate(Hz), input frame size (samples), compenent ID, number of following parameters,
 *                              : frame shift (samples), mel banks, dct coefficients (set to 0 for LOG MEL)]
 *                              : For post process, it contains post process configuration parameters: [configuration version,
 *                              : sampling rate(Hz), input frame size (samples), compenent ID, number of following parameters,
 *                              : frame rate per second, lookback buffer length in second in Q12, NN stacked frame delay in second
 *                              : in Q12, detection threshold (lower 16bit is set (i.e. update) flag, upper 16bit is detection 
 *                              : threshold (range -10 to 10); higher the threshold, the less detections and less fasle alarms, 
 *                              : lower threshold should cause more detections, more fasle alarms)]
 * \param[out] ip_infoPt        : Pointer to ifx_stc_pre_post_process_info_t structure
 * \return                      : Return 0 when success, otherwise return error code
 *                                INVALID_ARGUMENT if input or output argument is invalid
 *                                or error code from specific infineon pre and post process component.
 *                                Please note error code is 8bit LSB, line number where the error happened in
 *                                code is in 16bit MSB, and its IP component index if applicable will be at
 *                                bit 8 to 15 in the combined 32bit return value.
*/
int32_t ifx_pre_post_process_parse(int32_t * ip_prms_buffer, ifx_stc_pre_post_process_info_t *ip_infoPt);

/**
 * \brief : ifx_pre_post_process_init() is the API function to initilize component container based on component ID.
 *
 *
 * \param[out]  container       : Pointer to component ID's container that contains state memory and parameters
 * \param[out]  ip_infoPt       : Pointer to component ID's ifx_stc_pre_post_process_info_t
 * \param[in]   prms_buffer     : Manually generated parameter buffer which has component id and related parameters
 *                              : For SOD, it contains SOD configuration parameter: [configuration version, sampling rate(Hz),
 *                              : input frame size (samples), SOD component ID, number of following parameters,
 *                              : GapSetting (0,100,200,300,400,500,1000)ms, SensLevel (0-32767)]
 *                              : For preprocess, it contains preprocess configuration parameter: [configuration version,
 *                              : sampling rate(Hz), input frame size (samples), compenent ID, number of following parameters,
 *                              : frame shift (samples), mel banks, dct coefficients (set to 0 for LOG MEL)]
 *                              : For post process, it contains post process configuration parameters: [configuration version,
 *                              : sampling rate(Hz), input frame size (samples), compenent ID, number of following parameters,
 *                              : frame rate per second, lookback buffer length in second in Q12, NN stacked frame delay in second
 *                              : in Q12, detection threshold (lower 16bit is set (i.e. update) flag, upper 16bit is detection
 *                              : threshold (range -10 to 10); higher the threshold, the less detections and less fasle alarms,
 *                              : lower threshold should cause more detections, more fasle alarms)]
 * \return                      : Return 0 when success, otherwise return error code
 *                                INVALID_ARGUMENT if input or output argument is invalid
 *                                or error code from specific infineon pre and post process component.
 *                                Please note error code is 8bit LSB, line number where the error happened in
 *                                code is in 16bit MSB, and its IP component index if applicable will be at
 *                                bit 8 to 15 in the combined 32bit return value.
*/
int32_t ifx_pre_post_process_init(int32_t * prms_buffer, void **container, ifx_stc_pre_post_process_info_t *ip_infoPt);

/**
 * \brief : ifx_time_pre_process() is the API function to pre process in time domain given user's selected method.
 *
 *
 * \param[in]  preprocess_container : Pointer to preprocess container that contains state memory and parameters
 * \param[in]  component_id         : Infineon pre process component ID
 * \param[in]  input1               : Pointer to 1st input buffer (mic1 samples)
 * \param[in]  input2               : Pointer to 2nd input buffer (mic2 samples)
 * \param[out] output1              : pointer to buffer where preprocessed time domain output of one frame 1st input
 * \param[out] output2              : pointer to buffer where preprocessed time domain output of one frame 2nd input
 * \return                          : Return 0 when success, otherwise return error code
 *                                    INVALID_ARGUMENT if input or output argument is invalid
 *                                    or error code from specific infineon preprocess component.
 *                                    Please note error code is 8bit LSB, line number where the error happened in
 *                                    code is in 16bit MSB, and its IP component index if applicable will be at
 *                                    bit 8 to 15 in the combined 32bit return value.
*/
int32_t ifx_time_pre_process(IFX_SP_DATA_TYPE_T *input1, IFX_SP_DATA_TYPE_T* input2, void *preprocess_container, int32_t component_id, IFX_SP_DATA_TYPE_T *output1, IFX_SP_DATA_TYPE_T* output2);

/**
 * \brief : ifx_agc_set_target_level_and_mode() is the API function to set AGC Target level in db and AGC mode by user.
 *
 *
 * \param[in/out]  agc_container    : Pointer to AGC container that contains state memory and parameters
 * \param[in] agcTargetLevelDB      : AGC Target level in dB
 * \param[in] agcMode               : AGC mode defined by enumerations of agc_mode
 * \return                          : Return 0 when success, otherwise return error code
 *                                    INVALID_ARGUMENT if input or output argument is invalid
 *                                    or error code from specific infineon preprocess component.
 *                                    Please note error code is 8bit LSB, line number where the error happened in
 *                                    code is in 16bit MSB, and its IP component index if applicable will be at
 *                                    bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_agc_set_target_level_and_mode(void* agcTopPt, float agcTargetLevelDB, int agcMode);

/**
 * \brief : ifx_time_post_process() is the API function to post process in time domain given user's selected method.
 *
 *
 * \param[in]  postprocess_container: Pointer to postprocess container that contains state memory and parameters
 * \param[in]  component_id         : Infineon post process component ID (current only support IFX_POST_PROCESS_IP_COMPONENT_AGC)
 * \param[in]  input                : Pointer to input buffer
 * \param[out] output               : pointer to buffer where postprocessed time domain output of one frame
 * \return                          : Return 0 when success, otherwise return error code
 *                                    INVALID_ARGUMENT if input or output argument is invalid
 *                                    or error code from specific infineon preprocess component.
 *                                    Please note error code is 8bit LSB, line number where the error happened in
 *                                    code is in 16bit MSB, and its IP component index if applicable will be at
 *                                    bit 8 to 15 in the combined 32bit return value.
*/
int32_t ifx_time_post_process(IFX_SP_DATA_TYPE_T* input, void* postprocess_container, int32_t component_id, IFX_SP_DATA_TYPE_T* output);

/**
 * \brief : ifx_sod_process() is the API function to do SOD process.
 *
 *
 * \param[out] vad               : pointer to SOD detection is written, 1=SOD detected, 0=NO SOD detected
 * \param[in/out]  sod_container : Pointer to SOD container that contains state memory and its params
 * \param[in]  in                : Pointer to PCM samples input
 * \return                       : Return 0 when success, otherwise return error code
 *                                 IFX_SP_ENH_ERR_INVALID_ARGUMENT if input or output argument is invalid
 *                                 or error code from specific ifx audio & voice enhancement proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
int32_t ifx_sod_process(IFX_SP_DATA_TYPE_T* in, void* sod_container, bool* vad);

/**
 * \brief : ifx_spectrogram_transfer() is the API function to do spectrogram transformation given user's method.
 *
 *
 * \param[out] fe_out               : pointer to buffer where feature for one frame is kept
 * \param[out] out_q                : pointer to output fixed-point Q value
 * \param[in]  preprocess_container : Pointer to preprocess container that contains state memory and parameters
 * \param[in]  input                : Pointer to input samples
 * \return                          : Return 0 when success, otherwise return error code
 *                                    INVALID_ARGUMENT if input or output argument is invalid
 *                                    or error code from specific infineon preprocess component.
 *                                    Please note error code is 8bit LSB, line number where the error happened in
 *                                    code is in 16bit MSB, and its IP component index if applicable will be at
 *                                    bit 8 to 15 in the combined 32bit return value.
*/
int32_t ifx_spectrogram_transfer(IFX_SP_DATA_TYPE_T *input, void *spectrogram_container, IFX_FE_DATA_TYPE_T *fe_out, int32_t *out_q);

/**
 * \brief : ifx_post_process() is the API function to use output of the Neural Network and use post process to declare WWD. 
 *
 *
 * \param[in]  postprocess_container    : Pointer to postprocess container that contains state memory and parameters
 * \param[in]  component_id             : Infineon pre and post process component ID
 * \param[in]  in_probs                 : pointer for the buffer containing output probabilities from classifier in 
 *                                        the order of token 1, token 2, garbage, noise.
 * \param[out] detection                : WUP detection output; 0 means monitoring, 1 means detected, negtive means rejected.
 * \return                              : Return 0 when success, otherwise return error code
 *                                        INVALID_ARGUMENT if input or output argument is invalid
 *                                        or error code from specific infineon post process component.
 *                                        Please note error code is 8bit LSB, line number where the error happened in
 *                                        code is in 16bit MSB, and its IP component index if applicable will be at
 *                                        bit 8 to 15 in the combined 32bit return value.
*/
int32_t ifx_post_process(IFX_PPINPUT_DATA_TYPE_T *in_probs, void *postprocess_container, int32_t component_id, int32_t *detection);

/**
 * \brief : ifx_class_convertion_init() is the API function to process inference classification id_string and initilize output_id_array
 *          before call ifx_class_convertion_for_pp() function.
 *
 * \param[in]  id_string                : Pointer to string decribing the inference classification indetifications which must contain
 *                                        "WWDtoken0", "WWDtoken1", and "noise". Each ID should only occur once, and its position in the
 *                                        string corresponds to its inference classification position. Please notice that "garbage" is a
 *                                        optional ID since initilization process will treat other than above IDs as garbage. Each ID shall
 *                                        be seperated by ",".
 *                                        Note the inference classification IDs order is decided by the NN model during NN model training.
 *                                        For example, "WWDtoken0,WWDtoken1,WWDtoken2,WWDtoken3,garbage,noise" is a valid id_string for 4 token WW model.
 *                                        The number of classes is 6 with 4 token WW model. For 2 token KW model, the number of class is 4.
 *                                        For 2 token 2 WW model, the number of class is 6, and 2 WW model only support 2 token per WW.
 *                                        The last two are always garbage and noise.
 * \param[in]  size                     : Inference output classification size
 * \param[in]  ww_tokens                : Number of tokens in wake word
 * \param[out] output_id_array          : Pointer to the output buffer containing inference classification indetification number.
 * \return                              : Return 0 when success, otherwise return error code
 *                                        INVALID_ARGUMENT if input or output argument is invalid
 *                                        or error code from specific infineon post process component.
 *                                        Please note error code is 8bit LSB, line number where the error happened in
 *                                        code is in 16bit MSB, and its IP component index if applicable will be at
 *                                        bit 8 to 15 in the combined 32bit return value.
*/
int32_t ifx_class_convertion_init(const char* id_string, int* output_id_array, int size, int ww_tokens);

/**
 * \brief : ifx_class_convertion_for_pp() is the API function to convert multi-keyword inference output to one keyword post-process
 *          classification before using post process to declare WWD.
 *
 * \param[in]  input_score              : Pointer to two keyword inference output buffer
 * \param[in]  data_type                : Infineon inference output (input_score) data type, and it is also output_score data type.
 * \param[in]  id_array                 : Pointer to the buffer containing inference classification indetification number
 * \param[in]  size                     : Inference output classification size
 * \param[in]  ww_tokens                : Number of tokens in wake word
 * \param[out] output_score             : Corresponding one key word inference output buffer pointer.
 * \return                              : Return 0 when success, otherwise return error code
 *                                        INVALID_ARGUMENT if input or output argument is invalid
 *                                        or error code from specific infineon post process component.
 *                                        Please note error code is 8bit LSB, line number where the error happened in
 *                                        code is in 16bit MSB, and its IP component index if applicable will be at
 *                                        bit 8 to 15 in the combined 32bit return value.
*/
int32_t ifx_class_convertion_for_pp(void* input_score, int data_type, void* output_score, int* id_array, int size, int ww_tokens);

/**
 * \brief : ifx_pre_post_process_mode_control() is the API function to control Infineon pre and post process compenent's mode.
 * This API is used to control Infineon pre and post process IP component's mode. This API can be called after initilization.
 * If the Infineon pre and post process IP component is not configured as valid. This API will do nothing.
 *
 * \param[out]  container       : Pointer to Infineon pre and post process model data container pointer
 * \param[in]   component_id    : Infineon pre and post process component ID
 * \param[in]   enable          : Enable or disable component specified by component_id
 * \param[in]   reset           : If value = true, reset component_id's state. If value = false, no change on component's state.
 *
 * \return                      : Return 0 when success, otherwise return error code
 *                                Return INVALID_ARGUMENT if input argument is invalid.
 *                                or error code from specific infineon post process component.
 *                                Please note error code is 8bit LSB, line number where the error happened in
 *                                code is in 16bit MSB, and its IP component index if applicable will be at
 *                                bit 8 to 15 in the combined 32bit return value.
*/
int32_t ifx_pre_post_process_mode_control(void* container, int32_t component_id, bool enable, bool reset);

/**
 * \brief : ifx_pre_post_process_status() is the API function to query Infineon pre and post process compenent's status.
 * This API can be called after initilization.
 * If the Infineon pre and post process IP component is not configured as valid. This API will return status as disabled.
 *
 * \param[out]  container       : Pointer to Infineon pre and post process model data container pointer
 * \param[in]   component_id    : ifx audio & voice enhancement process component ID
 *
 * \return                      : Return 0 means disabled
 *                                Return 1 means enabled
*/
int32_t ifx_pre_post_process_status(void* container, int32_t component_id);

/**
 * \brief : Initialize pre/post process profile configuration.
 *
 * This API is used to setup pre/post process profile configuration and specify the callback function to handle
 * the profile log. If no callback function is specified, the profile log will be printed out on console.
 *
 * \param[in]  modelPt         : Pointer to ifx pre/post process data container pointer
 * \param[in]  ip_id           : Pre/post process component ID number.
 * \param[in]  enable          : Profile setting enable (true) or disable (false).
 * \param[in]  cb_func         : Callback function to handle the profile result.
 * \param[in]  cb_arg          : Callback function argument
 *
 * \return                     : Return 0 when success, otherwise return error code
 *                               Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input parameter is invalid.
*/
int32_t ifx_pre_post_profile_init(void* modelPt, int32_t ip_id, uint8_t enable, ifx_sp_profile_cb_fun cb_func, void* cb_arg);

/**
 * \brief : Update pre/post process profile configuration.
 *
 * This API is used to update pre/post process profile configuration.
 *
 * \param[in]  modelPt         : Pointer to ifx pre/post process data container pointer
 * \param[in]  ip_id           : Pre/post process component ID number.
 * \param[in]  enable          : Profile setting enable (true) or disable (false).
 *
 * \return                     : Return 0 when success, otherwise return error code
 *                               Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input parameter is invalid.
*/
int32_t ifx_pre_post_profile_control(void* modelPt, int32_t ip_id, bool enable);

/**
 * \brief : Print pre/post process profile log.
 *
 *
 * \param[in]  lPt             : Pointer to profile data container pointer
 * \param[in]  ip_id           : Pre/post process component ID number.
 * \return                     : Return 0 when success, otherwise return error code
 *                               Return IFX_SP_ENH_ERR_INVALID_ARGUMENT if input parameter is invalid.
*/
int32_t ifx_pre_post_profile_print(void* lPt, int32_t ip_id);

/**
 * \brief : itsi_feature_process_frame() is the API function to do itsi feature extraction.
 *
 *
 * \param[out] fe_out               : pointer to buffer where feature for one frame is kept
 * \param[in]  featureContainerPt   : Pointer to itsi feature preprocess container that contains state memory and parameters
 * \param[in]  input                : Pointer to input samples
 * \return                          : Return 0 when success, otherwise return error code
 *                                    INVALID_ARGUMENT if input or output argument is invalid
 *                                    or error code from specific infineon preprocess component.
 *                                    Please note error code is 8bit LSB, line number where the error happened in
 *                                    code is in 16bit MSB, and its IP component index if applicable will be at
 *                                    bit 8 to 15 in the combined 32bit return value.
*/
int32_t itsi_feature_process_frame(float* input, void* featureContainerPt, float* fe_out);

/**
 * \brief : itsi_feature_init(void** feature_container, mem_info_t* mem_infoPt) is the API function to init itsi feature process
 *
 *
 * \param[in]  feature_container : Pointer to itsi feature container that contains state memory and parameters
 * \param[in]   mem_infoPt       : Pointer to mem_info_t data structure contains itsi feature persistent and scratch memry infomation
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t itsi_feature_init(void** feature_container, mem_info_t* mem_infoPt);

/**
 * \brief : ifx_itsi_feature_reset(void* feature_container) is the API function to reset itsi feature internal memory.
 *
 *
 * \param[in]  feature_container : Pointer to itsi feature container that contains state memory and parameters
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_itsi_feature_reset(void* feature_container);

/**
 * \brief : itsi_feature_deinit(void* feature_container) is the API function to release itsi feature internal memory
 *
 *
 * \param[in]  feature_container : Pointer to itsi feature container that contains state memory and parameters
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t itsi_feature_deinit(void* featureContainerPt);

/**
 * \brief : ifx_afe_hpf_reset(void* hpf_container) is the API function to reset itsi afe hpf internal memory.
 *
 *
 * \param[in]  hpf_container     : Pointer to itsi afe hpf container that contains state memory and parameters
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_afe_hpf_reset(void* hpf_container);

/**
 * \brief : itsi_dfwwd_init() is the API function to init data free wake word detection process.
 *
 * \param[in]   dfwwModelPrmPt   : Pointer to dfwwd model that contains dfww model parameters
 * \param[out]  container        : Pointer to dfwwd container that contains state memory and parameters
 * \param[in]   mem_infoPt       : Pointer to mem_info_t data structure contains dfwwd persistent and scratch memry infomation
 * \param[in]   timeout          : dfwwd tunable parameter to set maximum time in milisecond between SOD and WW
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t itsi_dfwwd_init(const char* dfwwModelPrmPt, void** container, mem_info_t* mem_infoPt, uint32_t timeout);

/**
 * \brief : ifx_dfww_state_reset() is the API function to reset the entire state of data free wake word detection process.
 *
 * \param[in/out]  container     : Pointer to dfwwd container that contains state memory and parameters
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_dfww_state_reset(void* StrucPt);

/**
 * \brief : ifx_reset_dfww() is the API function to reset data free wake word detection process.
 *
 * \param[win/out]  container    : Pointer to dfwwd container that contains state memory and parameters
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_reset_dfww(void* StrucPt);

/**
 * \brief : ifx_wwd() is the API function to run wake word detection process.
 *
 * \param[in/out]  container     : Pointer to dfwwd container that contains state memory and parameters
 * \param[in]  input             : Pointer to softmax score input
 * \param[out] decison           : pointer to Wake Word (WW) detection is written, 1=WW detected, -1=WW rejected, 0=indecision
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_wwd(void* StrucPt, float* input, int32_t* decision);

/**
 * \brief : itsi_dfcmd_init() is the API function to init data free command detection process.
 *
 * \param[in]   dfcmdModelPrmPt  : Pointer to dfcmd model that contains dfcmd model parameters
 * \param[in]   dfnmbModelPrmPt  : Pointer to dfnmb model that contains dfnmb model parameters
 * \param[out]  container        : Pointer to dfcmd container that contains state memory and parameters
 * \param[in]   mem_infoPt       : Pointer to mem_info_t data structure contains dfcmd persistent and scratch memry infomation
 * \param[in]   gap              : dfcmd tunable parameter to set maximum time in milisecond allowed between the end of the WW
 *                                 and the beginning of the commands
 * \param[in]   adj_level        : dfcmd tunable parameter to decrease or increase maximum CMD duration until timeout 
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t itsi_dfcmd_init(const char* dfcmdModelPrmPt, const char* dfnmbModelPrmPt, void** container, mem_info_t* mem_infoPt, uint32_t gap, int32_t adj_level);

/**
 * \brief : ifx_dfcmd_state_reset() is the API function to reset the entire state of data free command detection process.
 *
 * \param[in/out]  container     : Pointer to dfcmd container that contains state memory and parameters
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_dfcmd_state_reset(void* DFcmdStrucPt);

/**
 * \brief : ifx_reset_dfcmd() is the API function to reset data free command detection process.
 *
 * \param[in/out]  container     : Pointer to dfcmd container that contains state memory and parameters
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_reset_dfcmd(void* DFcmdStrucPt, int PrevCmd);

/**
 * \brief : ifx_cmd() is the API function to run command detection process.
 *
 * \param[in/out] DFwwStrucPt    : Pointer to dfwwd container that contains state memory and parameters
 * \param[in/out] DFcmdStrucPt   : Pointer to dfcmd container that contains state memory and parameters
 * \param[in]  input             : Pointer to softmax score input
 * \param[out] decison           : pointer to command detection is written, 1=CMD detected, -1=CMD rejected, 0=indecision
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_dfcmd(void* DFwwStrucPt, void* DFcmdStrucPt, float* input, int32_t* decison);

/**
 * \brief : itsi_get_ww_llscore() is the API function to get itsi WW log-likelihood score.
 *
 * \param[in] StrucPt            : Pointer to dfww data structure.
 * \param[out] *ww_llscore       : Return WW log-likelihood score.
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_get_ww_llscore(void* StrucPt, float* ww_llscore);

/**
 * \brief : itsi_get_cmd_llscore() is the API function to get itsi cmd log-likelihood score.
 *
 * \param[in] StrucPt            : Pointer to dfcmd data structure.
 * \param[out] *cmd_llscore      : Return cmd log-likelihood score.
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_get_cmd_llscore(void* StrucPt, float* cmd_llscore);

/**
 * \brief : itsi_get_nmb_llscore() is the API function to get itsi number log-likelihood score.
 *
 * \param[in] StrucPt            : Pointer to dfcmd data structure.
 * \param[out] *nmb_llscore      : Return number log-likelihood score.
 * \return                       : Return 0 when success, otherwise return error code from specific ifx itsi proces module.
 *                                 Please note error code is 8bit LSB, line number where the error happened in
 *                                 code is in 16bit MSB, and its IP component index if applicable will be at
 *                                 bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_get_nmb_llscore(void* StrucPt, float* nmb_llscore);

/**
 * \brief : ifx_lpwwd_post_process() is the API function to use output of the Neural Network and use lpwwd post process to declare WWD. 
 *
 *
 * \param[in]  postprocess_container    : Pointer to lpwwd postprocess container that contains state memory and parameters
 * \param[in]  in_probs                 : pointer for the buffer containing output probabilities from classifier in 
 *                                        the order of token 1, token 2, garbage, noise.
 * \param[out] detection                : Detection output; 0 means monitoring, positive means detected, negative means rejected.
 * \return                              : Return 0 when success, otherwise return error code
 *                                        INVALID_ARGUMENT if input or output argument is invalid
 *                                        or error code from specific infineon post process component.
 *                                        Please note error code is 8bit LSB, line number where the error happened in
 *                                        code is in 16bit MSB, and its IP component index if applicable will be at
 *                                        bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_lpwwd_post_process(void* postprocess_container, IFX_PPINPUT_DATA_TYPE_T* in_probs, int32_t* detection);


/**
 * \brief : ifx_lpwwd_post_process_reset() is the API function to reset lpwwd post process memory and state. 
 *
 *
 * \param[in]  postprocess_container    : Pointer to lpwwd postprocess container that contains state memory and parameters
 * \return                              : Return 0 when success, otherwise return error code
 *                                        INVALID_ARGUMENT if input or output argument is invalid
 *                                        or error code from specific infineon post process component.
 *                                        Please note error code is 8bit LSB, line number where the error happened in
 *                                        code is in 16bit MSB, and its IP component index if applicable will be at
 *                                        bit 8 to 15 in the combined 32bit return value.
*/
uint32_t ifx_lpwwd_post_process_reset(void* postprocess_container);

#if defined(__cplusplus)
}
#endif

#endif /*__IFX_PRE_POST_PROCESS_H */

/* [] END OF FILE */
