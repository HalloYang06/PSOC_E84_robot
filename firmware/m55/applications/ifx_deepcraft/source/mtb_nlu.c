/***************************************************************************//**
 * \file mtb_nlu.c
 *
 * \brief
 * The file contains NLU related API
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

/*******************************************************************************
 * Include header file
 ******************************************************************************/
#include "mtb_nlu.h"

#include <ctype.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>


#include "cy_audio_license.h"
#include "ifx_sp_common_priv.h"
#include "ifx_sp_utils.h"
#include "ifx_sp_utils_priv.h"
#include "ifx_va_prms.h"


#include "AM_LSTM_tflm_model_int16x8.h"
#include "cy_result.h"
#include "va_core/va_config_params.h"
#include "va_core/va_ml_model.h"
#include "va_core/va_utils.h"


/******************************************************************************
 * Defines
 *****************************************************************************/
#undef AM_LOOKBACK
#define AM_LOOKBACK 5

/******************************************************************************
 * Global Variables
 *****************************************************************************/
/* Model structure */
static mtb_ml_model_16x8_t *mtb_ml_model_obj;

static void *dfcmd_obj = NULL;
static mtb_va_common_t nlu_common = {NULL, NULL, NULL, NULL, false, false};

/* Global initialization information which also stores persistent memory
 * pointers */
static ifx_stc_pre_post_process_info_t* pre_proc_hpf_info = NULL;
static ifx_stc_pre_post_process_info_t* sod_info = NULL;
static ifx_stc_pre_post_process_info_t* feature_info = NULL;
static ifx_stc_pre_post_process_info_t* dfww_info = NULL;
static ifx_stc_pre_post_process_info_t* nlu_dfcmd_info = NULL;

static mtb_wwd_nlu_buff_t *wwd_nlu_buff;

/* -2 = init (or reset), -1 = no (i.e. rejected), 0 = indecision, 1 = yes (i.e.
 * detected) */
static mtb_nlu_state_t nlu_result;
static int32_t feature_buf_cnt;
static int sodtrigcnt;

static mtb_nlu_config_t nlu_config;

/* For debugging */
#ifdef WWD_NLU_DEBUG
int frame_cnt;
int SODcnt;
#endif

/******************************************************************************
 * Functions
 *****************************************************************************/
static uint32_t reset_sod_detected(mtb_nlu_state_t *nlu_state)
{
    uint32_t ret;
    if (nlu_result == CY_NLU_INIT_STATE)
    {
        sodtrigcnt = 0;
    }
    nlu_result = CY_NLU_INDECISION;
    *nlu_state = nlu_result;

    ret = ifx_reset_dfww(nlu_common.dfww_obj);
    if (ret != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_RESET_ERROR;

    ret = ifx_reset_dfcmd(dfcmd_obj, -1);
    if (ret != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_RESET_ERROR;
    return MTB_VA_RSLT_SUCCESS;
}

static void ifx_reset_feature_buf(void)
{
    memset(wwd_nlu_buff->mtb_ml_input_buffer, 0,
           sizeof(float) * (FEATURE_BUF_SZ * N_SEQ));
}

static uint32_t ifx_reset_itsi_nlu(mtb_wwd_nlu_config_t *config_obj)
{
    int ErrorHdl = 0;

    ErrorHdl = reset_mtb_va_common(&nlu_common, config_obj->sod_params);
    if (ErrorHdl != MTB_VA_RSLT_SUCCESS)
        return ErrorHdl;

    ErrorHdl = ifx_dfcmd_state_reset(dfcmd_obj);
    if (ErrorHdl != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_RESET_ERROR;

    ifx_reset_feature_buf();
    /* Clear output_scores buffer */
    memset(wwd_nlu_buff->output_scores, 0,
           sizeof(float) * ((N_PHONEMES + 1) * AM_LOOKBACK));

    /* Initialize counters and flags */
    sodtrigcnt = SOD_STARTING_COUNT;
    nlu_result = CY_NLU_INIT_STATE; /* initial non-CMD state */
    feature_buf_cnt = 0;

#ifdef WWD_NLU_DEBUG
    frame_cnt = 0;
    SODcnt = 0;
#endif

    return MTB_VA_RSLT_SUCCESS;
}

static uint32_t init_common_objs(mtb_wwd_nlu_config_t *config_obj)
{
    int error_code = 0;
    int32_t scratch_sz = 0;

    pre_proc_hpf_info = (ifx_stc_pre_post_process_info_t *)malloc(
        sizeof(ifx_stc_pre_post_process_info_t));
    sod_info = (ifx_stc_pre_post_process_info_t *)malloc(
        sizeof(ifx_stc_pre_post_process_info_t));
    feature_info = (ifx_stc_pre_post_process_info_t *)malloc(
        sizeof(ifx_stc_pre_post_process_info_t));
    dfww_info = (ifx_stc_pre_post_process_info_t *)malloc(
        sizeof(ifx_stc_pre_post_process_info_t));
    nlu_dfcmd_info = (ifx_stc_pre_post_process_info_t *)malloc(
        sizeof(ifx_stc_pre_post_process_info_t));

    if (nlu_dfcmd_info == NULL || dfww_info == NULL || feature_info == NULL ||
        sod_info == NULL || pre_proc_hpf_info == NULL)
        return MTB_VA_RSLT_MEM_ALLOC_ERROR;

    /* Step 1: Parse and get required memory from configurations */
#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    error_code = parse_ifx_prms(pre_proc_hpf_info, config_obj->hpf_params);
    if (error_code != MTB_VA_RSLT_SUCCESS)
        return error_code;
#else
    pre_proc_hpf_info->memory.persistent_mem_pt = NULL;
    pre_proc_hpf_info->memory.persistent_mem = 0;
    pre_proc_hpf_info->memory.scratch_mem = 0;
#endif
    error_code = parse_ifx_prms(sod_info, config_obj->sod_params);
    if (error_code != MTB_VA_RSLT_SUCCESS)
        return error_code;
    error_code = parse_ifx_prms(feature_info, config_obj->denoise_params);
    if (error_code != MTB_VA_RSLT_SUCCESS)
        return error_code;
    error_code = parse_ifx_prms(dfww_info, config_obj->ww_conf->ww_params);
    if (error_code != MTB_VA_RSLT_SUCCESS)
        return error_code;
    error_code = parse_ifx_prms(nlu_dfcmd_info,
                                config_obj->nlu_conf.nlu_config->nlu_params);
    if (error_code != MTB_VA_RSLT_SUCCESS)
        return error_code;

    /* Step 2: Allocate memory (AMPREDICT persistent memory allocated in
     * previous step) */
    error_code = allocate_ifx_mem(pre_proc_hpf_info, sod_info, feature_info,
                                  dfww_info, nlu_dfcmd_info);
    if (error_code != MTB_VA_RSLT_SUCCESS)
    {
        ml_destroy_model(&mtb_ml_model_obj);
        return error_code;
    }

    /* Get maximum scratch memory size */
    scratch_sz = MAX(pre_proc_hpf_info->memory.scratch_mem, scratch_sz);
    scratch_sz = MAX(sod_info->memory.scratch_mem, scratch_sz);
    scratch_sz = MAX(feature_info->memory.scratch_mem, scratch_sz);
    scratch_sz = MAX(dfww_info->memory.scratch_mem, scratch_sz);
    scratch_sz = MAX(nlu_dfcmd_info->memory.scratch_mem, scratch_sz);

    /* Allocate total scratch memory & shared with all components */
    feature_info->memory.scratch_mem_pt = (char *)malloc(scratch_sz);
    if (feature_info->memory.scratch_mem_pt == NULL)
    {
        ml_destroy_model(&mtb_ml_model_obj);
        free_ifx_persistent_mem(pre_proc_hpf_info, sod_info, feature_info,
                                dfww_info, nlu_dfcmd_info);
        return MTB_VA_RSLT_MEM_ALLOC_ERROR;
    }

    wwd_nlu_buff->ifx_scratch.scratch_pad = feature_info->memory.scratch_mem_pt;
    wwd_nlu_buff->ifx_scratch.scratch_size = scratch_sz;
    wwd_nlu_buff->ifx_scratch.scratch_cnt = 0;

    dfww_info->memory.scratch_mem_pt = feature_info->memory.scratch_mem_pt;
    nlu_dfcmd_info->memory.scratch_mem_pt = feature_info->memory.scratch_mem_pt;
    pre_proc_hpf_info->memory.scratch_mem_pt =
        feature_info->memory.scratch_mem_pt;
    sod_info->memory.scratch_mem_pt = feature_info->memory.scratch_mem_pt;

    /* Step 3: Initialize containers/objects */
#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    error_code = ifx_pre_post_process_init(config_obj->hpf_params,
                                           &nlu_common.pre_proc_hpf_obj,
                                           pre_proc_hpf_info);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INIT_ERROR;
#endif
    error_code = ifx_pre_post_process_init(config_obj->sod_params,
                                           &nlu_common.sod_obj, sod_info);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INIT_ERROR;

    error_code = ifx_pre_post_process_init(
        config_obj->denoise_params, &nlu_common.feature_obj, feature_info);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INIT_ERROR;

    error_code = itsi_dfwwd_init(
        config_obj->ww_model_ptr, &nlu_common.dfww_obj, &(dfww_info->memory),
        config_obj->ww_conf->ww_params[DFWW_PARM_INDEX]);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INIT_ERROR;

    error_code = itsi_dfcmd_init(
        config_obj->cmd_model_ptr, config_obj->nmb_model_ptr, &dfcmd_obj,
        &(nlu_dfcmd_info->memory),
        config_obj->nlu_conf.nlu_config->nlu_params[DFCMD_PARM1_INDEX],
        config_obj->nlu_conf.nlu_config->nlu_params[DFCMD_PARM2_INDEX]);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INIT_ERROR;

    nlu_common.is_initialized = true;
    nlu_common.is_owner = true; /* NLU owns common objects and is
                                   responsible for freeing them */

    wwd_nlu_buff->is_initialized = true;
    wwd_nlu_buff->va_common_obj = nlu_common;
    wwd_nlu_buff->va_common_obj.is_owner =
        false; /* wwd_nlu_buff does not own these objects, nlu_common does */

    return MTB_VA_RSLT_SUCCESS;
}

cy_rslt_t mtb_nlu_init(mtb_nlu_t *nlu_obj, mtb_wwd_nlu_config_t *config_obj)
{
    int error_code = 0;

    /* Validate parameters */
    if ((NULL == nlu_obj) || (NULL == config_obj))
    {
        return MTB_VA_RSLT_INVALID_PARAM;
    }

    CY_VA_PRINTF_TRACE("Start initialization of NLU\r\n");

    /* Setup WWD and NLU data buffers */
    wwd_nlu_buff = config_obj->wwd_nlu_buff_data;
    nlu_config.nlu_command_timeout =
        config_obj->nlu_conf.nlu_config->nlu_command_timeout;
    nlu_obj->nlu_variable_data = config_obj->nlu_conf.nlu_variable_data;

    if ((config_obj->nlu_conf.nlu_config->nlu_params[DFCMD_PARM1_INDEX] <
         CY_NLU_NON_SPEECH_TIME_MIN) ||
        (config_obj->nlu_conf.nlu_config->nlu_params[DFCMD_PARM1_INDEX] >
         CY_NLU_NON_SPEECH_TIME_MAX) ||
        (config_obj->nlu_conf.nlu_config->nlu_params[DFCMD_PARM2_INDEX] <
         CY_NLU_DURATION_FACTOR_MIN) ||
        (config_obj->nlu_conf.nlu_config->nlu_params[DFCMD_PARM2_INDEX] >
         CY_NLU_DURATION_FACTOR_MAX))
    {
        return MTB_VA_RSLT_INVALID_PARAM;
    }

    va_timer_reset(&wwd_nlu_buff->nlu_timer);

    /* AM NN model target for U55 */
    error_code = ml_create_model(&mtb_ml_model_obj);
    if (error_code != MTB_VA_RSLT_SUCCESS)
        return error_code;

    error_code =
        ml_inference_init(&wwd_nlu_buff->am_model_bin,
                          &wwd_nlu_buff->am_model_buffer, mtb_ml_model_obj);
    if (error_code != MTB_VA_RSLT_SUCCESS)
    {
        ml_destroy_model(&mtb_ml_model_obj);
        return error_code;
    }

    /* If common memory is initialized init DFCMD separately */
    if (wwd_nlu_buff->is_initialized && wwd_nlu_buff->va_common_obj.is_initialized)
    {
        nlu_dfcmd_info = (ifx_stc_pre_post_process_info_t *)malloc(
            sizeof(ifx_stc_pre_post_process_info_t));
        if (nlu_dfcmd_info == NULL)
            return MTB_VA_RSLT_MEM_ALLOC_ERROR;

        /* Parse DFCMD params  */
        error_code = parse_ifx_prms(nlu_dfcmd_info,
                                    config_obj->nlu_conf.nlu_config->nlu_params);
        if (error_code != MTB_VA_RSLT_SUCCESS)
            return error_code;

        /* Allocate DFCMD memory  */
        nlu_dfcmd_info->memory.persistent_mem_pt =
            (char *)malloc(nlu_dfcmd_info->memory.persistent_mem);
        if (nlu_dfcmd_info->memory.persistent_mem_pt == NULL)
        {
            ml_destroy_model(&mtb_ml_model_obj);
            return MTB_VA_RSLT_MEM_ALLOC_ERROR;
        }
        nlu_dfcmd_info->memory.scratch_mem_pt = wwd_nlu_buff->ifx_scratch.scratch_pad;

        error_code = itsi_dfcmd_init(
            config_obj->cmd_model_ptr, config_obj->nmb_model_ptr, &dfcmd_obj,
            &(nlu_dfcmd_info->memory),
            config_obj->nlu_conf.nlu_config->nlu_params[DFCMD_PARM1_INDEX],
            config_obj->nlu_conf.nlu_config->nlu_params[DFCMD_PARM2_INDEX]);
        if (error_code != IFX_SP_ENH_SUCCESS)
            return MTB_VA_RSLT_IFX_INIT_ERROR;

        nlu_common = wwd_nlu_buff->va_common_obj;
        nlu_common.is_owner = false; // NLU doesn't own them
        CY_VA_PRINTF_TRACE("NLU is using objects initialized by WWD\n");
    }
    else
    {
        error_code = init_common_objs(config_obj);
        if (error_code != MTB_VA_RSLT_SUCCESS)
            return error_code;
        CY_VA_PRINTF_TRACE("NLU initialized its own objects\n");
    }

    error_code = ifx_reset_itsi_nlu(config_obj);
    if (error_code != MTB_VA_RSLT_SUCCESS)
        return error_code;

    CY_VA_PRINTF_TRACE("NLU initialized successfully\n\r");
    return MTB_VA_RSLT_SUCCESS;
}

cy_rslt_t mtb_nlu_denit(mtb_nlu_t *nlu_obj)
{
    /* Free WWD and NLU persistent memory */

    /* If nlu_common is a borrowed reference and should not be freed here.
       Only free common objects if NLU owns them.
       free_mtb_va_common() handles the ownership logic. */
    int result = free_mtb_va_common(&nlu_common);
    if (result != IFX_SP_ENH_SUCCESS)
        return result;

    /* Clear borrowed pointers in wwd_nlu_buff */
    wwd_nlu_buff->va_common_obj.dfww_obj = NULL;
    wwd_nlu_buff->va_common_obj.sod_obj = NULL;
    wwd_nlu_buff->va_common_obj.pre_proc_hpf_obj = NULL;
    wwd_nlu_buff->va_common_obj.feature_obj = NULL;
    wwd_nlu_buff->va_common_obj.is_initialized = false;
    wwd_nlu_buff->is_initialized = false;

    if (dfcmd_obj != NULL)
    {
        free(dfcmd_obj);
        dfcmd_obj = NULL;
    }

    ml_destroy_model(&mtb_ml_model_obj);

    /* Free scratch memory */
    if (wwd_nlu_buff->ifx_scratch.scratch_pad != NULL)
    {
        ifx_mem_reset(&wwd_nlu_buff->ifx_scratch);
        free(wwd_nlu_buff->ifx_scratch.scratch_pad);
        wwd_nlu_buff->ifx_scratch.scratch_pad = NULL;
    }

    /* Free persistent memory */
    free_ifx_persistent_mem(pre_proc_hpf_info, sod_info, feature_info,
                            dfww_info, nlu_dfcmd_info);
    if (pre_proc_hpf_info != NULL)
    {
        free(pre_proc_hpf_info);
        pre_proc_hpf_info = NULL;
    }
    if (sod_info != NULL)
    {
        free(sod_info);
        sod_info = NULL;
    }
    if (feature_info != NULL)
    {
        free(feature_info);
        feature_info = NULL;
    }
    if (dfww_info != NULL)
    {
        free(dfww_info);
        dfww_info = NULL;
    }
    if (nlu_dfcmd_info != NULL)
    {
        free(nlu_dfcmd_info);
        nlu_dfcmd_info = NULL;
    }
    return MTB_VA_RSLT_SUCCESS;
}

cy_rslt_t mtb_nlu_process(mtb_nlu_t *nlu_obj, int16_t *mic_frame,
                          mtb_nlu_state_t *nlu_state, int *intent_index,
                          mtb_nlu_variable_t *variable_values, int *var_size)
{
    static const int HOP = 1;
    static const int VALUE_TO_MOVE = (N_SEQ - HOP) * FEATURE_BUF_SZ;
    static const int OFFSET = HOP * FEATURE_BUF_SZ;

    if (nlu_obj == NULL || mic_frame == NULL)
    {
        return MTB_VA_RSLT_INVALID_PARAM;
    }

    /* NLU COMMAND Timeout Handler */

    /* First time executing NLU process after WWD detection, need to start the
     * timeout timer */
    if (wwd_nlu_buff->nlu_timer.state == VA_TIMER_INACTIVE)
    {
        CY_VA_PRINTF_TRACE("Start up NLU timer\r\n");
        int32_t timeout_counter =
            nlu_config.nlu_command_timeout / NLU_PROCESS_EX_TIME;
        va_timer_start(&wwd_nlu_buff->nlu_timer, timeout_counter);
    }

    const va_timer_state_t tmr_state = va_timer_tick(&wwd_nlu_buff->nlu_timer);
    if (tmr_state == VA_TIMER_EXPIRED)
    {
        CY_VA_PRINTF_TRACE("NLU Timer Expired\r\n");
        *nlu_state = nlu_result = CY_NLU_NOT_DETECTED;
        *intent_index = (int)nlu_result;
        return MTB_VA_RSLT_COMMAND_TIMEOUT;
    }

    /* Check for the license expiration of the audio library */
    if (cy_afe_lib_is_license_expired())
        return MTB_VA_RSLT_LICENSE_ERROR;

    uint32_t err_code = 0;

    /* Step 1: Run Start of Detection (SOD) Processing */
    bool is_sod_detected;
    err_code = ifx_sod_process((int16_t *)mic_frame, nlu_common.sod_obj,
                               &is_sod_detected);
    if (err_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INTERNAL_ERROR;
#ifdef WWD_NLU_DEBUG
    frame_cnt++;
#endif

    if (wwd_nlu_buff->WWD_DetectEvent)
    {
        wwd_nlu_buff->WWD_DetectEvent = false;

        err_code = reset_sod_detected(nlu_state);
        if (err_code != MTB_VA_RSLT_SUCCESS)
            return err_code;
    }

    if (is_sod_detected)
    {
        CY_VA_PRINTF_TRACE("NLU_SOD\r\n");
        err_code = reset_sod_detected(nlu_state);
        if (err_code != MTB_VA_RSLT_SUCCESS)
            return err_code;

#ifdef WWD_NLU_DEBUG
        SODcnt++;
        CY_VA_PRINTF_TRACE("SOD Detected: %d\n", SODcnt);
#endif
    }

#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    /* Run pre_process_hpf */
    ifx_time_pre_process(mic_frame, NULL, nlu_common.pre_proc_hpf_obj,
                         IFX_PRE_PROCESS_IP_COMPONENT_HPF, mic_frame, NULL);
#endif

    /* Do features and AM every frame */
    for (int i = 0; i < FRAME_SIZE_16K; i++)
    {
        wwd_nlu_buff->xIn[i] = (float)mic_frame[i];
    }

    /* Step 2: Compute Features */
    err_code = itsi_feature_process_frame(
        wwd_nlu_buff->xIn, nlu_common.feature_obj, wwd_nlu_buff->features);
    if (err_code != IFX_SP_ENH_SUCCESS)
    {
        return MTB_VA_RSLT_IFX_INTERNAL_ERROR;
    }

    /* Step 3: Inference */
    float *buf_pt_base = wwd_nlu_buff->mtb_ml_input_buffer;
    int i;

    /* Update input buffer */
    memmove(buf_pt_base, buf_pt_base + OFFSET, VALUE_TO_MOVE * sizeof(float));
    memcpy(buf_pt_base + VALUE_TO_MOVE, wwd_nlu_buff->features,
           OFFSET * sizeof(float));

    feature_buf_cnt++;
    if (feature_buf_cnt == FRAMES_HOP)
    {
        /* shift the output_scores */
        for (i = (N_PHONEMES + 1) * AM_LOOKBACK - 1; i >= (N_PHONEMES + 1);
             i--)
        {
            wwd_nlu_buff->output_scores[i] =
                wwd_nlu_buff->output_scores[i - (N_PHONEMES + 1)];
        }

        err_code = ml_process(mtb_ml_model_obj, wwd_nlu_buff->data_feed_int,
                              buf_pt_base, wwd_nlu_buff->output_scores);
        if (err_code != MTB_VA_RSLT_SUCCESS)
            return err_code;

        feature_buf_cnt = 0;
    }

    /* Step 4: Post-WWD CMD processing */
    *nlu_state = nlu_result;
    if ((nlu_result == CY_NLU_INDECISION) && (sodtrigcnt == 0))
    {
        /* This has to be called every FRAMES_HOP !! */
        int32_t dfcmd_state = nlu_result;
        err_code = ifx_dfcmd(
            nlu_common.dfww_obj, dfcmd_obj,
            &wwd_nlu_buff->output_scores[(N_PHONEMES + 1) * (AM_LOOKBACK - 2)],
            &dfcmd_state);
        if (err_code != IFX_SP_ENH_SUCCESS)
            return MTB_VA_RSLT_IFX_DFCMD_ERROR;
        *nlu_state = nlu_result = dfcmd_state;

        switch (nlu_result)
        {
        case CY_NLU_DETECTED: {
            nlu_result = CY_NLU_INIT_STATE;
            /* Get intent index and variable data */
            nlu_extract_command(dfcmd_obj, nlu_obj, intent_index,
                                variable_values, var_size);
        } break;
        case CY_NLU_NOT_DETECTED: {
            nlu_result = CY_NLU_INIT_STATE;
            return MTB_VA_RSLT_PRE_SILENCE_TIMEOUT;
        }
        default:
            break;
        }
    }

    sodtrigcnt++;
    if (sodtrigcnt == FRAMES_HOP)
    {
        /* This triggers DFWW/DFCMD to be called every FRAMES_HOP !! */
        sodtrigcnt = 0;
    }

    return MTB_VA_RSLT_SUCCESS;
}

cy_rslt_t mtb_nlu_reset_state(mtb_nlu_t *nlu_obj,
                              mtb_wwd_nlu_config_t *config_obj)
{
    uint32_t error_code = 0;

    /* Validate parameters */
    if (NULL == config_obj)
        return MTB_VA_RSLT_INVALID_PARAM;

    CY_VA_PRINTF_TRACE("Reset NLU called\r\n");

    error_code = ifx_reset_dfcmd(dfcmd_obj, -1);
    if (error_code != IFX_SP_ENH_SUCCESS)
    {
        CY_VA_PRINTF_TRACE("Reset DFCMD NLU failed: %lu\r\n", error_code);
        return MTB_VA_RSLT_IFX_RESET_ERROR;
    }

    error_code = ifx_reset_itsi_nlu(config_obj);
    if (error_code != MTB_VA_RSLT_SUCCESS)
    {
        CY_VA_PRINTF_TRACE("Reset ITSI NLU failed: %lu\r\n", error_code);
        return error_code;
    }

    /* Reset the command timeout timer so the next detection cycle starts
     * fresh without inheriting a partially elapsed or expired countdown. */
    va_timer_reset(&wwd_nlu_buff->nlu_timer);
    return MTB_VA_RSLT_SUCCESS;
}

cy_rslt_t mtb_nlu_get_command(mtb_nlu_t *nlu_obj, char *commandtext)
{
    /* Validate parameter */
    if (NULL == commandtext)
    {
        return MTB_VA_RSLT_INVALID_PARAM;
    }

    /* Get detected command string */
    if (ifx_get_command(dfcmd_obj, commandtext))
    {
        CY_VA_PRINTF_TRACE("Error! IFX get command Failed!!\n\r");
        return MTB_VA_RSLT_INVALID_PARAM;
    }
    return MTB_VA_RSLT_SUCCESS;
}

cy_rslt_t mtb_nlu_timeout(mtb_nlu_t *nlu_obj, uint32_t timeout)
{
    nlu_config.nlu_command_timeout = timeout;
    return MTB_VA_RSLT_SUCCESS;
}
