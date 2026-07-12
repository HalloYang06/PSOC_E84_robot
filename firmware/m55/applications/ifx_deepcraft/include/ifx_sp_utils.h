/******************************************************************************
* File Name: ifx_sp_utils.h
*
* Description: This file contains public interface for Infineon speech utilities
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
#ifndef __IFX_SP_UTILS_H
#define __IFX_SP_UTILS_H

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
* Speech utilities data type & defines
*******************************************************************************/

/*******************************************************************************
* Structures and enumerations
*******************************************************************************/

/******************************************************************************
* Function prototype
******************************************************************************/
/**
 * \addtogroup API
 * @{
 */

/**
 * \brief : speech_utils_sod_reset() is the API function to reset SOD to initial memory settings.
 *
 *
 * \param[in/out]  sod_container    : Pointer to SOD container that contains state memory and its params
 * \param[in]  sod_prms_buffer      : Configuration parameter buffer of the given ip_id component block
 *                                  : For SOD, it contains SOD configuration parameter: [frame_size (samples), sampling_rate(Hz),
 *                                  : GapSetting (0,100,200,300,400,500,1000)ms (400 suggested), SensLevel (0-32767) (16384 suggested)]
 *                                  : Note: Only GapSetting and SensLevel can be reconfigured during reset.
 * \return                          : Return 0 when success, otherwise return error code
 *                                    IFX_SP_ENH_ERR_INVALID_ARGUMENT if input or output argument is invalid
 *                                    or error code from specific ifx audio & voice enhancement proces module.
 *                                    Please note error code is 8bit LSB, line number where the error happened in
 *                                    code is in 16bit MSB, and its IP component index if applicable will be at
 *                                    bit 8 to 15 in the combined 32bit return value.
*/
int32_t speech_utils_sod_reset(int32_t* sod_prms_buffer, void* sod_container);

/**
 * \brief : speech_utils_hmms_post_process_get_threshold() is the API function to get detection threshold from post process.
 *
 *
 * \param[out] threshold                : Post process detection threshold
 * \param[in]  postprocess_container    : Pointer to post process container that contains state memory and its params
 * \return                              : Return 0 when success, otherwise return error code
 *                                        IFX_SP_ENH_ERR_INVALID_ARGUMENT if input or output argument is invalid
 *                                        or error code from specific ifx audio & voice enhancement proces module.
 *                                        Please note error code is 8bit LSB, line number where the error happened in
 *                                        code is in 16bit MSB, and its IP component index if applicable will be at
 *                                        bit 8 to 15 in the combined 32bit return value.
*/
int32_t speech_utils_hmms_post_process_get_threshold(void* postprocess_container, float* threshold);

/**
 * \brief : speech_utils_hmms_post_process_get_score() is the API function to get detection score from post process.
 *
 *
 * \param[out] score                    : Post process detection score
 * \param[in]  postprocess_container    : Pointer to post process container that contains state memory and its params
 * \return                              : Return 0 when success, otherwise return error code
 *                                        IFX_SP_ENH_ERR_INVALID_ARGUMENT if input or output argument is invalid
 *                                        or error code from specific ifx audio & voice enhancement proces module.
 *                                        Please note error code is 8bit LSB, line number where the error happened in
 *                                        code is in 16bit MSB, and its IP component index if applicable will be at
 *                                        bit 8 to 15 in the combined 32bit return value.
*/
int32_t speech_utils_hmms_post_process_get_score(void* postprocess_container, float* score);

/**
 * \brief : speech_utils_lpwwd_post_process_get_results() is the API function to get detection results from lpwwd post process.
 *
 *
 * \param[out] total_tokens             : Total number of tokens in wake word
 * \param[out] token_count              : LPWWD post process detection each token counter value
 * \param[out] gap_count                : LPWWD post process detection between each token gap value
 * \param[out] timeout_count            : LPWWD post process timeout counter value
 * \param[out] garbage_count            : LPWWD post process garbage counter value
 * \param[out] noise_count              : LPWWD post process noise counter value
 * \param[out] state                    : LPWWD post process state value
 * \param[in]  postprocess_container    : Pointer to lpwwd post process container that contains state memory and its params
 * \return                              : Return 0 when success, otherwise return error code
 *                                        IFX_SP_ENH_ERR_INVALID_ARGUMENT if input or output argument is invalid
 *                                        or error code from specific ifx audio & voice enhancement proces module.
 *                                        Please note error code is 8bit LSB, line number where the error happened in
 *                                        code is in 16bit MSB, and its IP component index if applicable will be at
 *                                        bit 8 to 15 in the combined 32bit return value.
*/uint32_t speech_utils_lpwwd_post_process_get_results(void *postprocess_container, uint16_t *total_tokens, uint16_t *token_count,
         uint16_t *gap_count, uint16_t *timeout_count, uint16_t *garbage_count, uint16_t *noise_count, int16_t *state);

#if defined(__cplusplus)
}
#endif

#endif /*__IFX_SP_UTILS_H */

/* [] END OF FILE */