/***************************************************************************//**
 * \file mtb_wwd.c
 *
 * \brief
 * The file contains WWD related API
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
#include "mtb_wwd.h"

volatile int g_ifx_wwd_debug_stage;
volatile int g_ifx_wwd_debug_detail;
volatile int g_ifx_wwd_ethosu_stub_seen;

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

/* Global initialization information which also stores persistent memory
 * pointers */
static ifx_stc_pre_post_process_info_t* pre_proc_hpf_info = NULL;
static ifx_stc_pre_post_process_info_t* sod_info = NULL;
static ifx_stc_pre_post_process_info_t* feature_info = NULL;
static ifx_stc_pre_post_process_info_t* dfww_info = NULL;

static mtb_wwd_nlu_buff_t *wwd_nlu_buff;

/* For debugging */
#ifdef WWD_NLU_DEBUG
int frame_cnt;
int SODcnt;
#endif

/******************************************************************************
 * Functions
 *****************************************************************************/

static void ifx_reset_feature_buf(void)
{
    memset(wwd_nlu_buff->mtb_ml_input_buffer, 0,
           sizeof(float) * (FEATURE_BUF_SZ * N_SEQ));
}

static uint32_t ifx_reset_itsi_wwd(mtb_wwd_t *wwd_obj,
                                   mtb_wwd_nlu_config_t *config_obj)
{
    int error_code = 0;

    error_code =
        reset_mtb_va_common(&(wwd_obj->va_common_obj), config_obj->sod_params);
    if (error_code != MTB_VA_RSLT_SUCCESS)
        return error_code;

    ifx_reset_feature_buf();

    /* Clear output_scores buffer */
    memset(wwd_nlu_buff->output_scores, 0,
           sizeof(float) * ((N_PHONEMES + 1) * AM_LOOKBACK));

    /* Initial counters and flags */
    wwd_obj->sodtrigcnt = SOD_STARTING_COUNT;
    wwd_obj->wwd_result = CY_WWD_INIT_STATE; /* initial non-WWD state */
    wwd_obj->feature_buf_cnt = 0;

#ifdef WWD_NLU_DEBUG
    frame_cnt = 0;
    SODcnt = 0;
#endif

    return MTB_VA_RSLT_SUCCESS;
}

cy_rslt_t mtb_wwd_init(mtb_wwd_t *wwd_obj, mtb_wwd_nlu_config_t *config_obj)
{
    int error_code = 0;
    int32_t scratch_sz = 0;

    /* Validate parameters */
    if ((NULL == wwd_obj) || (NULL == config_obj)) {
        return MTB_VA_RSLT_INVALID_PARAM;
    }

    CY_VA_PRINTF_TRACE("Start initialization of WWD\r\n");

    /* Setup callbacks */
    wwd_obj->callback.cb_for_event = config_obj->ww_conf->callback.cb_for_event;
    wwd_obj->callback.cb_function = config_obj->ww_conf->callback.cb_function;

    /* Setup data buffers, now wwd_nlu_buff points to global buffer */
    wwd_nlu_buff = config_obj->wwd_nlu_buff_data;

    pre_proc_hpf_info = (ifx_stc_pre_post_process_info_t *)malloc(
        sizeof(ifx_stc_pre_post_process_info_t));
    sod_info = (ifx_stc_pre_post_process_info_t *)malloc(
        sizeof(ifx_stc_pre_post_process_info_t));
    feature_info = (ifx_stc_pre_post_process_info_t *)malloc(
        sizeof(ifx_stc_pre_post_process_info_t));
    dfww_info = (ifx_stc_pre_post_process_info_t *)malloc(
        sizeof(ifx_stc_pre_post_process_info_t));

    if (pre_proc_hpf_info == NULL || sod_info == NULL || dfww_info == NULL ||
        feature_info == NULL)
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

    /* AM NN model target for U55 */
    g_ifx_wwd_debug_stage = 1;
    error_code = ml_create_model(&mtb_ml_model_obj);
    g_ifx_wwd_debug_stage = 2;
    if (error_code != MTB_VA_RSLT_SUCCESS)
        return error_code;

    g_ifx_wwd_debug_stage = 3;
    error_code =
        ml_inference_init(&wwd_nlu_buff->am_model_bin,
                          &wwd_nlu_buff->am_model_buffer, mtb_ml_model_obj);
    if (error_code != MTB_VA_RSLT_SUCCESS)
    {
        ml_destroy_model(&mtb_ml_model_obj);
        return error_code;
    }
    g_ifx_wwd_debug_stage = 4;

    /* Step 2: Allocate memory (AMPREDICT persistent memory allocated in
     * previous step) */
    error_code = allocate_ifx_mem(pre_proc_hpf_info, sod_info, feature_info,
                                  dfww_info, NULL);
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

    /* Allocate total scratch memory & shared with all components */
    feature_info->memory.scratch_mem_pt = (char *)malloc(scratch_sz);
    if (feature_info->memory.scratch_mem_pt == NULL)
    {
        ml_destroy_model(&mtb_ml_model_obj);
        free_ifx_persistent_mem(pre_proc_hpf_info, sod_info, feature_info,
                                dfww_info, NULL);
        return MTB_VA_RSLT_MEM_ALLOC_ERROR;
    }

    wwd_nlu_buff->ifx_scratch.scratch_pad = feature_info->memory.scratch_mem_pt;
    wwd_nlu_buff->ifx_scratch.scratch_size = scratch_sz;
    wwd_nlu_buff->ifx_scratch.scratch_cnt = 0;
    dfww_info->memory.scratch_mem_pt = feature_info->memory.scratch_mem_pt;
    pre_proc_hpf_info->memory.scratch_mem_pt =
        feature_info->memory.scratch_mem_pt;
    sod_info->memory.scratch_mem_pt = feature_info->memory.scratch_mem_pt;

    /* Step 3: Initialize containers/objects */
#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    error_code = ifx_pre_post_process_init(
        config_obj->hpf_params, &(wwd_obj->va_common_obj.pre_proc_hpf_obj),
        pre_proc_hpf_info);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INIT_ERROR;
#endif
    error_code = ifx_pre_post_process_init(
        config_obj->sod_params, &(wwd_obj->va_common_obj.sod_obj), sod_info);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INIT_ERROR;

    error_code = ifx_pre_post_process_init(config_obj->denoise_params,
                                           &(wwd_obj->va_common_obj.feature_obj),
                                           feature_info);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INIT_ERROR;

    error_code = itsi_dfwwd_init(
        config_obj->ww_model_ptr, &(wwd_obj->va_common_obj.dfww_obj),
        &(dfww_info->memory), config_obj->ww_conf->ww_params[DFWW_PARM_INDEX]);

    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INIT_ERROR;

    error_code = ifx_reset_itsi_wwd(wwd_obj, config_obj);
    if (error_code != MTB_VA_RSLT_SUCCESS)
        return error_code;

    wwd_obj->va_common_obj.is_initialized = true;
    wwd_obj->va_common_obj.is_owner = true;

    wwd_nlu_buff->is_initialized = true;
    wwd_nlu_buff->va_common_obj = wwd_obj->va_common_obj;
    wwd_nlu_buff->va_common_obj.is_owner =
        false; /* wwd_nlu_buff does not own these objects, wwd_obj does */

    CY_VA_PRINTF_TRACE("WWD initialized successfully\n\r");
    return MTB_VA_RSLT_SUCCESS;
}

cy_rslt_t mtb_wwd_deinit(mtb_wwd_t *wwd_obj)
{
    /* Free WWD and NLU persistent memory */
    int result = free_mtb_va_common(&(wwd_obj->va_common_obj));
    if (result != IFX_SP_ENH_SUCCESS)
        return result;

    /* Clear borrowed pointers in wwd_nlu_buff */
    wwd_nlu_buff->va_common_obj.dfww_obj = NULL;
    wwd_nlu_buff->va_common_obj.sod_obj = NULL;
    wwd_nlu_buff->va_common_obj.pre_proc_hpf_obj = NULL;
    wwd_nlu_buff->va_common_obj.feature_obj = NULL;
    wwd_nlu_buff->va_common_obj.is_initialized = false;
    wwd_nlu_buff->is_initialized = false;

    ml_destroy_model(&mtb_ml_model_obj);

    /* Free scratch memory */
    ifx_mem_reset(&wwd_nlu_buff->ifx_scratch);
    free(wwd_nlu_buff->ifx_scratch.scratch_pad);
    wwd_nlu_buff->ifx_scratch.scratch_pad = NULL;

    /* Free persistent memory */
    free_ifx_persistent_mem(pre_proc_hpf_info, sod_info, feature_info,
                            dfww_info, NULL);
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

    return MTB_VA_RSLT_SUCCESS;
}

cy_rslt_t mtb_wwd_process(mtb_wwd_t *wwd_obj, int16_t *mic_frame,
                          mtb_wwd_state_t *ww_state)
{
    static const int HOP = 1;
    static const int VALUE_TO_MOVE = (N_SEQ - HOP) * FEATURE_BUF_SZ;
    static const int OFFSET = HOP * FEATURE_BUF_SZ;

    uint32_t err_code = 0;

    if (wwd_obj == NULL || mic_frame == NULL) {
        return MTB_VA_RSLT_INVALID_PARAM;
    }

    /* Check for the license expiration of the audio library */
    if (cy_afe_lib_is_license_expired())
        return MTB_VA_RSLT_LICENSE_ERROR;

    /* Step 1: Run SOD */
    bool is_sod_detected;
    err_code = ifx_sod_process((int16_t *)mic_frame,
                               wwd_obj->va_common_obj.sod_obj, &is_sod_detected);
    if (err_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INTERNAL_ERROR;
#ifdef WWD_NLU_DEBUG
    frame_cnt++;
#endif

    if (is_sod_detected)
    {
        if (wwd_obj->wwd_result == CY_WWD_INIT_STATE)
        {
            wwd_obj->sodtrigcnt = 0;
        }
        wwd_obj->wwd_result = CY_WWD_INDECISION;
        *ww_state = wwd_obj->wwd_result;

        err_code = ifx_reset_dfww(wwd_obj->va_common_obj.dfww_obj);
        if (err_code != IFX_SP_ENH_SUCCESS)
            return MTB_VA_RSLT_IFX_RESET_ERROR;

        if ((NULL != wwd_obj->callback.cb_function) &&
            ((CY_EVENT_SOD == wwd_obj->callback.cb_for_event) ||
             (CY_EVENT_SOD_WWD == wwd_obj->callback.cb_for_event)))
        {
            wwd_obj->callback.cb_function(CY_EVENT_SOD);
            CY_VA_PRINTF_TRACE("wwd callback executed on SOD\r\n");
        }

#ifdef WWD_NLU_DEBUG
        SODcnt++;
        CY_VA_PRINTF_TRACE("SOD Detected: %d\n", SODcnt);
#endif
    }

    /* Run pre_process_hpf */
    ifx_time_pre_process(mic_frame, NULL,
                         wwd_obj->va_common_obj.pre_proc_hpf_obj,
                         IFX_PRE_PROCESS_IP_COMPONENT_HPF, mic_frame, NULL);

    /* Do features and AM every frame */
    for (int i = 0; i < FRAME_SIZE_16K; i++)
    {
        wwd_nlu_buff->xIn[i] = (float)mic_frame[i];
    }

    /* Step 2: Compute Features */
    err_code = itsi_feature_process_frame(wwd_nlu_buff->xIn,
                                          wwd_obj->va_common_obj.feature_obj,
                                          wwd_nlu_buff->features);
    if (err_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_INTERNAL_ERROR;

    /* Step 3: Inference */
    float *buf_pt_base = wwd_nlu_buff->mtb_ml_input_buffer;
    int i;

    /* Update input buffer */
    memmove(buf_pt_base, buf_pt_base + OFFSET, VALUE_TO_MOVE * sizeof(float));
    memcpy(buf_pt_base + VALUE_TO_MOVE, wwd_nlu_buff->features,
           OFFSET * sizeof(float));

    wwd_obj->feature_buf_cnt++;
    if (wwd_obj->feature_buf_cnt == FRAMES_HOP)
    {
        /* Shift the output_scores */
        for (i = (N_PHONEMES + 1) * AM_LOOKBACK - 1; i >= (N_PHONEMES + 1);
             i--)
        {
            wwd_nlu_buff->output_scores[i] =
                wwd_nlu_buff->output_scores[i - (N_PHONEMES + 1)];
        }

        err_code = ml_process(mtb_ml_model_obj, wwd_nlu_buff->data_feed_int,
                              buf_pt_base, wwd_nlu_buff->output_scores);
        if (MTB_VA_RSLT_SUCCESS != err_code)
            return err_code;

        wwd_obj->feature_buf_cnt = 0;
    }

    /* Step 4: Post-inference processing */
    if ((wwd_obj->wwd_result == CY_WWD_INDECISION) &&
        (wwd_obj->sodtrigcnt == 0))
    {
        /* This has to be called every FRAMES_HOP !! */
        err_code = ifx_wwd(
            wwd_obj->va_common_obj.dfww_obj,
            &wwd_nlu_buff->output_scores[(N_PHONEMES + 1) * (AM_LOOKBACK - 1)],
            &(wwd_obj->wwd_result));
        if (err_code != IFX_SP_ENH_SUCCESS)
            return MTB_VA_RSLT_IFX_WWD_ERROR;

        *ww_state = wwd_obj->wwd_result;

        switch (wwd_obj->wwd_result)
        {
        case CY_WWD_DETECTED: {
            wwd_obj->wwd_result = CY_WWD_INIT_STATE;
            err_code = ifx_reset_dfww(wwd_obj->va_common_obj.dfww_obj);
            if (err_code != IFX_SP_ENH_SUCCESS)
                return MTB_VA_RSLT_IFX_RESET_ERROR;
            wwd_nlu_buff->WWD_DetectEvent = true;

            /* Check callback is configured for wake-word detection */
            if ((NULL != wwd_obj->callback.cb_function) &&
                ((CY_EVENT_WWD == wwd_obj->callback.cb_for_event) ||
                 (CY_EVENT_SOD_WWD == wwd_obj->callback.cb_for_event)))
            {
                wwd_obj->callback.cb_function(CY_EVENT_WWD);
                CY_VA_PRINTF_TRACE("wwd callback executed on SOD\r\n");
            }
        } break;
        case CY_WWD_NOT_DETECTED: {
            wwd_obj->wwd_result = CY_WWD_INIT_STATE;
            err_code = ifx_reset_dfww(wwd_obj->va_common_obj.dfww_obj);
            if (err_code != IFX_SP_ENH_SUCCESS)
                return MTB_VA_RSLT_IFX_RESET_ERROR;
        } break;
        case CY_WWD_INDECISION:
        default:
            break;
        }
    }

    wwd_obj->sodtrigcnt++;
    if (wwd_obj->sodtrigcnt == FRAMES_HOP)
    {
        /* This triggers DFWW/DFCMD to be called every FRAMES_HOP !! */
        wwd_obj->sodtrigcnt = 0;

        /* Set shared timeout timer */
        va_timer_reset(&wwd_nlu_buff->nlu_timer);
    }

    return MTB_VA_RSLT_SUCCESS;
}

cy_rslt_t mtb_wwd_reset_state(mtb_wwd_t *wwd_obj,
                              mtb_wwd_nlu_config_t *config_obj)
{
    uint32_t error_code = 0;

    if (wwd_obj == NULL || config_obj == NULL)
        return MTB_VA_RSLT_INVALID_PARAM;

    CY_VA_PRINTF_TRACE("Reset WWD\r\n");

    error_code = ifx_reset_dfww(wwd_obj->va_common_obj.dfww_obj);
    if (error_code != IFX_SP_ENH_SUCCESS)
    {
        CY_VA_PRINTF_TRACE("Reset DFWW failed: %lu\r\n", error_code);
        return MTB_VA_RSLT_IFX_RESET_ERROR;
    }
    
    error_code = ifx_reset_itsi_wwd(wwd_obj, config_obj);
    if (error_code != MTB_VA_RSLT_SUCCESS)
    {
        CY_VA_PRINTF_TRACE("Reset ITSI WWD failed: %lu\r\n", error_code);
        return error_code;
    }

    /* Reset the shared NLU timer so that NLU does not start with a stale or
     * already-expired timer after a WWD reset. */
    va_timer_reset(&wwd_nlu_buff->nlu_timer);
    return MTB_VA_RSLT_SUCCESS;
}
