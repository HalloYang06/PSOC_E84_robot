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
 * @file va_utils.h
 * @brief This the header file of ModusToolbox NLU and WWD middleware utility
 * module
 *
 */

#ifndef VA_INC_UTILS_H
#define VA_INC_UTILS_H

#include <ctype.h>

#include "ifx_pre_post_process.h"
#include "mtb_nlu.h"
#include "mtb_wwd_nlu_common.h"
#include "va_config_params.h"


/**
 * @defgroup va_utils_functions VA Utility Functions
 * @brief Function prototypes for voice assistant utility operations.
 */

/*******************************************************************************
 * Function Prototypes
 *******************************************************************************/
/**
 * \brief Parses audio preprocessing/postprocessing parameters and
 * configurations
 *
 * \param[in,out] ifx_info  : Pointer to the preprocessing/postprocessing info
 * structure to be populated.
 * \param[in] prms_buffer   : Pointer to the parameter buffer to parse.
 * \return                  : MTB_VA_RSLT_SUCCESS - success
 *                            MTB_VA_RSLT_IFX_PARSE_ERROR - parse failed
 *
 * \note This function must be called before allocate_ifx_mem() to determine
 * memory requirements.
 *
 * \ingroup va_utils_functions
 */
uint32_t parse_ifx_prms(ifx_stc_pre_post_process_info_t *ifx_info,
                        int32_t *prms_buffer);

/**
 * \brief Allocates persistent memory for all audio processing components
 *
 * \param[in,out] hpf_info     : Pointer to HPF info structure with
 * persistent_mem size set.
 * \param[in,out] sod_info     : Pointer to SOD info structure with
 * persistent_mem size set.
 * \param[in,out] feature_info : Pointer to feature info structure with
 * persistent_mem size set.
 * \param[in,out] dfww_info    : Pointer to DFWW info structure with
 * persistent_mem size set.
 * \param[in,out] dfcmd_info   : Pointer to DFCMD info structure with
 * persistent_mem size set.
 * \return                     : MTB_VA_RSLT_SUCCESS - success
 *                               MTB_VA_RSLT_MEM_ALLOC_ERROR - allocation failed
 * (all memory freed)
 *
 * \note parse_ifx_prms() must be called first to populate the persistent_mem
 * sizes.
 * \note On failure, this function automatically calls free_ifx_persistent_mem()
 * for cleanup.
 *
 * \ingroup va_utils_functions
 */
uint32_t allocate_ifx_mem(ifx_stc_pre_post_process_info_t *hpf_info,
                          ifx_stc_pre_post_process_info_t *sod_info,
                          ifx_stc_pre_post_process_info_t *feature_info,
                          ifx_stc_pre_post_process_info_t *dfww_info,
                          ifx_stc_pre_post_process_info_t *dfcmd_info);

/**
 * \brief Frees persistent memory for all audio processing components
 *
 * \param[in,out] hpf_info     : Pointer to HPF info structure.
 * \param[in,out] sod_info     : Pointer to SOD info structure.
 * \param[in,out] feature_info : Pointer to feature info structure.
 * \param[in,out] dfww_info    : Pointer to DFWW info structure.
 * \param[in,out] dfcmd_info   : Pointer to DFCMD info structure.
 *
 * \ingroup va_utils_functions
 */
void free_ifx_persistent_mem(ifx_stc_pre_post_process_info_t *hpf_info,
                             ifx_stc_pre_post_process_info_t *sod_info,
                             ifx_stc_pre_post_process_info_t *feature_info,
                             ifx_stc_pre_post_process_info_t *dfww_info,
                             ifx_stc_pre_post_process_info_t *dfcmd_info);

/**
 * \brief Resets the state of all shared WWD/NLU audio processing objects
 *
 * \param[in,out] common_objs : Pointer to the common objects structure
 * containing the objects to reset.
 * \param[in] sod_prms        : Pointer to SOD parameters required for reset.
 * \return                    : MTB_VA_RSLT_SUCCESS - success
 *                              MTB_VA_RSLT_INVALID_PARAM - invalid parameters
 *                              MTB_VA_RSLT_IFX_RESET_ERROR - component reset
 * failed
 *
 * \note This function resets: HPF (conditional), SOD, feature extraction, and
 * DFWW objects.
 * \note DFCMD is not reset by this function as it has separate lifecycle
 * management.
 *
 * \ingroup va_utils_functions
 */
uint32_t reset_mtb_va_common(mtb_va_common_t *common_objs, int32_t *sod_prms);

/**
 * \brief Frees shared WWD/NLU audio processing objects with ownership checking
 *
 * \param[in,out] common_objs : Pointer to the common objects structure.
 *                              If is_owner is false, only the is_initialized
 * flag is cleared. If is_owner is true, all objects are freed and pointers set
 * to NULL.
 * \return                    : MTB_VA_RSLT_SUCCESS - success
 *                              MTB_VA_RSLT_INVALID_PARAM - invalid parameters
 *                              MTB_VA_RSLT_IFX_INTERNAL_ERROR - feature object
 * deinit failed
 *
 * \note This function implements the ownership pattern - only the owner frees
 * memory.
 * \note Borrowers can safely call this function without double-free risk.
 *
 * \ingroup va_utils_functions
 */
uint32_t free_mtb_va_common(mtb_va_common_t *common_objs);

/**
 * \brief Extracts detected command intent and variable values from NLU
 * recognition
 *
 * This function retrieves the recognized command text, parses it to extract the
 * intent and associated variable values (numbers and units), and populates the
 * output structures. It handles both predefined variable phrases and numeric
 * values with optional units.
 *
 * \param[in] dfcmd_obj        : Pointer to the DFCMD object containing the
 * detected command.
 * \param[in] nlu_obj           : Pointer to the NLU object containing
 * intent/variable mapping data.
 * \param[out] intent_index    : Pointer to store the detected intent index.
 * \param[out] variable_values : Array to store extracted variable values and
 * their unit indices. Must be large enough to hold all variables for the
 * intent.
 * \param[out] var_size        : Pointer to store the number of variables
 * extracted.
 *
 * \ingroup va_utils_functions
 */
void nlu_extract_command(void *dfcmd_obj, mtb_nlu_t *nlu_obj, int *intent_index,
                         mtb_nlu_variable_t *variable_values, int *var_size);

#endif /* VA_INC_UTILS_H */
