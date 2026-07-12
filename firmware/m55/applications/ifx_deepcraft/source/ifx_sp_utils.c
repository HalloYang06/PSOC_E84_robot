/******************************************************************************
* File Name: ifx_sp_utils.c
*
* Description: This file contains functions to get memory and initialize
*      Infineon LPWWD IP component. Specifically, functions calculate memory
*      need, initializes container and setup working/state memories.
*
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
* Include header file
******************************************************************************/
#include "stdlib.h"
#include "string.h"
#include "stdio.h"
#include "ifx_sp_utils_priv.h"
#include "ifx_sp_utils.h"
#include "ifx_sp_common.h"
#include "ifx_sp_common_priv.h"
#ifdef PROFILER
#include "ifx_cycle_profiler.h"
#endif
#include "ifx_pre_post_process.h"

/******************************************************************************
* Global variables
*****************************************************************************/

/* IP component common fisrt five configuration parameters:
 * configurator version,
 * sampling_rate,
 * frame_size,
 * IP_compnent_id,
 * number of parameters.
 */

int32_t speech_utils_getMem(int32_t* ip_prms_buffer, int32_t ip_id, mem_info_t* mem_infoPt)
{
    int32_t sampling_rate, frame_size, sz;
    int32_t *int_idx = (int32_t *)ip_prms_buffer;
    int32_t persistent_sz = 0;
    int32_t scratch_sz = 0;

    //Warnings fix, variables are enabled under conditional algo inclusions.
    (void)sampling_rate; (void)frame_size;(void)sz;(void)persistent_sz;(void)scratch_sz;

    /* Sanity check of input arguments */
    if ((ip_id < 0) || (ip_id >= IFX_POST_PROCESS_IP_COMPONENT_MAX_COUNT))
    {
        return IFX_SP_ENH_ERROR(IFX_SP_ENH_COMPONENT_ID_INVALID, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }
    if (ip_prms_buffer == NULL || mem_infoPt == NULL)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    /* read first five parameters which are always same definition */
    sz = *int_idx++;             /* Configurator version, ignore for now */
    sampling_rate = *int_idx++;  /* sampling rate */
    frame_size = *int_idx++;     /* frame size */
    sz = *int_idx++;             /* IP component ID */
    if (sz != ip_id)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
    }
    sz = *int_idx++;             /* number of following parameters */

    /* Adjust persistent & scratch memory sizes based on data struct & type */
#ifdef ENABLE_IFX_VA_WWD
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_DENOISE)
    {
        if (frame_size != 160 || sz != 1)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        persistent_sz = itsi_feature_process_calculate_persistent_mem_size();
        scratch_sz = itsi_feature_process_calculate_scratch_mem_size();
    }
    else if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_DFWWD)
    {
        if (frame_size != 160 || sz != 1)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        persistent_sz = dfww_calculate_persistent_mem_size();
        scratch_sz = dfww_calculate_scratch_mem_size();
    }
    else
#endif
#ifdef ENABLE_IFX_VA_CMD
    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_DFCMD)
    {
        if (frame_size != 160 || sz != 2)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        persistent_sz = dfcmd_calculate_persistent_mem_size();
        scratch_sz = dfcmd_calculate_scratch_mem_size();
    }
    else
#endif
#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_HPF)
    {
        if (frame_size <= 0 || sz != 0)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        persistent_sz = ALIGN_WORD(sizeof(preprocess_hpf_top_struct)) + afe_hpf_calculate_persistent_mem_size();
        scratch_sz = ALIGN_WORD(1);     /* Avoid zero */
    }
    else
#endif
#ifdef ENABLE_IFX_PRE_PROCESS_ASRC_LPF
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_ASRC_LPF)
    {
        if (frame_size <= 0 || sz != 0)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        persistent_sz = ALIGN_WORD(sizeof(preprocess_asrc_lpf_top_struct)) + asrc_lpf_calculate_persistent_mem_size();
        scratch_sz = ALIGN_WORD(1);     /* Avoid zero */
    }
    else
#endif
#ifdef ENABLE_IFX_LPWWD
    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_HMMS)
    {
#ifdef ENABLE_IFX_LPWWD_HMMS
        if (sampling_rate != 16000)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        persistent_sz = ALIGN_WORD(sizeof(hmms_postprocess_top_struct)) + fixed_lpwwd_post_hmms_calculate_persistent_mem_size();
        scratch_sz = ALIGN_WORD(1);     /* Avoid zero */
#else
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_COMPONENT_ID); /* Please define ENABLE_IFX_LPWWD_HMMS */
#endif
    }
    else if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_LPWWD)
    {
        if (sampling_rate != 16000)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        persistent_sz = ALIGN_WORD(sizeof(lpwwd_postprocess_top_struct)) + ifx_lpwwd_post_process_calculate_persistent_mem_size();
        scratch_sz = ALIGN_WORD(1);     /* Avoid zero */
    }
    else
#endif
#if defined(ENABLE_IFX_LPWWD) || defined(ENABLE_IFX_FE)
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_MFCC || ip_id == IFX_PRE_PROCESS_IP_COMPONENT_LOG_MEL)
    {
        int32_t num_mel_features, num_mfcc_coeffs, block_size;
        if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_MFCC)
        {
            if (sz != 3)
            {
                return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
            }
        }
        else if (sz < 2)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        int_idx++;  /* skip frame_shift */
        num_mel_features = *int_idx++;
        num_mfcc_coeffs = *int_idx++;
        block_size = (int32_t)pow(2, ceil((log(frame_size) / log(2)))); // Round-up to nearest power of 2.
        if ((sampling_rate != 16000) || (num_mel_features < MIN_FBANK_SIZE) || (num_mel_features > MAX_FBANK_SIZE) || (block_size < 256) || (block_size > 1024))
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        if ((ip_id == IFX_PRE_PROCESS_IP_COMPONENT_MFCC) && (num_mfcc_coeffs > num_mel_features))
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_LOG_MEL)
        {/* force set num_mfcc_coeffs to zero for log_ml case */
            num_mfcc_coeffs = 0;
        }
        persistent_sz = spectrogram_calculate_persistent_mem_size(sampling_rate, block_size, num_mel_features, num_mfcc_coeffs);
        persistent_sz += ALIGN_WORD(sizeof(spectrogram_top_struct)) + spectrogram_calculate_spctrg_component_size();
        scratch_sz = spectrogram_calculate_scratch_mem_size(block_size, num_mel_features);
    }
    else
#endif
#ifdef ENABLE_IFX_SOD
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_SOD)
    {
        if ((sampling_rate != 16000) || (frame_size != 160))
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        persistent_sz = ALIGN_WORD(sizeof(sod_top_struct)) + SOD_calculate_persistent_mem_size();
        scratch_sz = SOD_calculate_scratch_mem_size(frame_size);
    }
    else
#endif
#ifdef ENABLE_IFX_AGC
    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_AGC)
    {
        if ((sampling_rate != 16000) || (frame_size <= 0))
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        persistent_sz = ALIGN_WORD(sizeof(postprocess_agc_top_struct)) + agc_calculate_persistent_mem_size();
        scratch_sz = ALIGN_WORD(agc_calculate_scratch_mem_size());
    }
    else
#endif
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_FEATURE_NOT_SUPPORTED);
    }

#if defined (ENABLE_IFX_PRE_PROCESS_HPF) || defined (ENABLE_IFX_PRE_PROCESS_ASRC_LPF) || defined (ENABLE_IFX_SOD) || \
    defined(ENABLE_IFX_LPWWD) || defined(ENABLE_IFX_VA_WWD) || defined(ENABLE_IFX_VA_CMD) || defined(ENABLE_IFX_FE) || defined(ENABLE_IFX_AGC)
    memset(mem_infoPt, 0, sizeof(*mem_infoPt));
    mem_infoPt->scratch_mem = scratch_sz;
    mem_infoPt->persistent_mem = persistent_sz;

    return IFX_SP_ENH_SUCCESS;
#else
    return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_FEATURE_NOT_SUPPORTED);
#endif
}

#ifdef ENABLE_IFX_SOD
/* SOD internal configuration parameters:
 *     GapSetting (0,100,200,300,400,500,1000)ms, SensLevel (0-32767)]
 * Preprocess internal configuration parameters:
 */
int32_t speech_utils_sod_init(int32_t * sod_prms_buffer, void **sod_container, mem_info_t *sod_mem_infoPt)
{
    int32_t* int_idx = (int32_t*)sod_prms_buffer;
    int32_t sampling_rate, frame_size, gapsetting, senslevel, sz;
    sod_top_struct *dPt;

    /* Sanity check of input arguments */
    if ((sod_container == NULL) || (sod_prms_buffer == NULL) || (sod_mem_infoPt == NULL))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    // read parameters
    sz = *int_idx++;                /* Configurator version, ignore for now */
    sampling_rate = *int_idx++;     /* sampling rate */
    frame_size = *int_idx++;        /* frame size */
    sz = *int_idx++;                /* IP component ID */
    if (sz != IFX_PRE_PROCESS_IP_COMPONENT_SOD)
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_PARAM);
    }
    sz = *int_idx++;                /* number of following parameters */
    if (sz != 2)
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_PARAM);
    }
    gapsetting    = *int_idx++;     /* gap setting */
    senslevel     = *int_idx;       /* sensitivity setting */
    if ((sampling_rate != 16000) || (frame_size != 160))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_PARAM);
    }
    if ((senslevel<0)||(senslevel>32767))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_PARAM);
    }
    if ((gapsetting!=0)&&(gapsetting!=100)&&(gapsetting!=200)&&(gapsetting!=300)&&(gapsetting!=400)&&(gapsetting!=500)&&(gapsetting!=1000))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_PARAM);
    }

    if ((sod_mem_infoPt->persistent_mem_pt == NULL) || (sod_mem_infoPt->scratch_mem_pt == NULL))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    if ((sod_mem_infoPt->persistent_mem != ALIGN_WORD(sizeof(sod_top_struct)) + SOD_calculate_persistent_mem_size()) ||
        (sod_mem_infoPt->scratch_mem != SOD_calculate_scratch_mem_size(frame_size)))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    /* Set up SOD data structure in persistent memory */
    dPt = (sod_top_struct*)(sod_mem_infoPt->persistent_mem_pt);
    memset(dPt, 0, sizeof(sod_top_struct));

    dPt->sod_component.persistent_size = sod_mem_infoPt->persistent_mem;
    dPt->sod_component.persistent_pad = sod_mem_infoPt->persistent_mem_pt;
    dPt->sod_component.scratch.scratch_size = sod_mem_infoPt->scratch_mem;
    dPt->sod_component.scratch.scratch_pad = sod_mem_infoPt->scratch_mem_pt;
    dPt->enable_flag = true; /* enable SOD detection */
    dPt->gapsetting = (int16_t)gapsetting;
    dPt->senslevel = (int16_t)senslevel;

    /* Initialize internal SOD structure */
    dPt->sod_component.ifx_component_pt = dPt->sod_component.persistent_pad + ALIGN_WORD(sizeof(sod_top_struct));
    initSOD(dPt->sod_component.ifx_component_pt, (int16_t)gapsetting, (int16_t)senslevel);

    *sod_container = dPt;
    return IFX_SP_ENH_SUCCESS;
}

int32_t speech_utils_sod_reset(int32_t * sod_prms_buffer, void *sod_container)
{
    int32_t* int_idx = (int32_t*)sod_prms_buffer;
    int32_t sampling_rate, frame_size, gapsetting, senslevel, sz;
    sod_top_struct* dPt;

    /* Sanity check of input arguments */
    if ((sod_container == NULL) || (int_idx == NULL))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

     // read parameters
    sz = *int_idx++;                /* Configurator version, ignore for now */
    sampling_rate = *int_idx++;     /* sampling rate */
    frame_size = *int_idx++;        /* frame size */
    sz = *int_idx++;                /* IP component ID */
    if (sz != IFX_PRE_PROCESS_IP_COMPONENT_SOD)
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_PARAM);
    }
    sz = *int_idx++;                /* number of following parameters */
    if (sz != 2)
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_PARAM);
    }
    gapsetting = *int_idx++;     /* gap setting */
    senslevel = *int_idx;       /* sensitivity setting */
    if ((sampling_rate != 16000) || (frame_size != 160))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_PARAM);
    }
    if ((senslevel<0)||(senslevel>32767))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_PARAM);
    }
    if ((gapsetting!=0)&&(gapsetting!=100)&&(gapsetting!=200)&&(gapsetting!=300)&&(gapsetting!=400)&&(gapsetting!=500)&&(gapsetting!=1000))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_PARAM);
    }

    dPt = (sod_top_struct*)sod_container;
    dPt->enable_flag = true; /* enable SOD detection */

    /* Initialize internal SOD structure */
    initSOD(dPt->sod_component.ifx_component_pt, (int16_t)gapsetting, (int16_t)senslevel);

    return IFX_SP_ENH_SUCCESS;
}

int32_t ifx_sod_process(IFX_SP_DATA_TYPE_T *in, void *sod_container, bool *vad)
{
    sod_top_struct* dPt;
    ifx_scratch_mem_t* scratchPt;
    bool TrigSet;

    /* Sanity check of input arguments */
    if ((sod_container == NULL) || (in == NULL))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_SOD, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    dPt = (sod_top_struct*)sod_container;
    TrigSet = dPt->enable_flag;
    scratchPt = &(dPt->sod_component.scratch);
    if (dPt->sod_component.reset_flag)
    {/* one time reset */
        /* Initialize internal SOD structure */
        initSOD(dPt->sod_component.ifx_component_pt, dPt->gapsetting, dPt->senslevel);
        dPt->sod_component.reset_flag = false;
    }
#ifdef PROFILER
    ifx_cycle_profile_start(&(dPt->sod_component.profile));
#endif
    *vad = SOD(in, dPt->sod_component.ifx_component_pt, scratchPt)&TrigSet;
#ifdef PROFILER
    ifx_cycle_profile_stop(&(dPt->sod_component.profile));
#endif

    return IFX_SP_ENH_SUCCESS;
}
#endif

#ifdef ENABLE_IFX_LPWWD
int32_t speech_utils_hmms_post_process_get_threshold(void* postprocess_container, float* threshold)
{
#ifdef ENABLE_IFX_LPWWD_HMMS
    hmms_postprocess_top_struct* dPt;

    /* Sanity check of input arguments */
    if (postprocess_container == NULL)
    {
        return IFX_SP_ENH_ERROR(IFX_POST_PROCESS_IP_COMPONENT_HMMS, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    dPt = (hmms_postprocess_top_struct*)postprocess_container;

    *threshold = (float)fixed_lpwwd_post_get_threshold(dPt->pp_component.ifx_component_pt) / (1 << PP_SECOND_CONVERTION_Q); //Q12
    return IFX_SP_ENH_SUCCESS;
#else
    *threshold = 0.0f;
    return IFX_SP_ENH_ERROR(IFX_POST_PROCESS_IP_COMPONENT_HMMS, IFX_SP_ENH_ERR_INVALID_COMPONENT_ID); /* Please define ENABLE_IFX_LPWWD_HMMS */
#endif
}

int32_t speech_utils_hmms_post_process_get_score(void* postprocess_container, float* score)
{
#ifdef ENABLE_IFX_LPWWD_HMMS
    hmms_postprocess_top_struct* dPt;

    /* Sanity check of input arguments */
    if (postprocess_container == NULL)
    {
        return IFX_SP_ENH_ERROR(IFX_POST_PROCESS_IP_COMPONENT_HMMS, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    dPt = (hmms_postprocess_top_struct*)postprocess_container;

    *score = fixed_lpwwd_post_get_float_score(dPt->pp_component.ifx_component_pt);
    return IFX_SP_ENH_SUCCESS;
#else
    *score = 0.0f;
    return IFX_SP_ENH_ERROR(IFX_POST_PROCESS_IP_COMPONENT_HMMS, IFX_SP_ENH_ERR_INVALID_COMPONENT_ID); /* Please define ENABLE_IFX_LPWWD_HMMS */
#endif
}
#endif

#if defined(ENABLE_IFX_VA_WWD) || defined(ENABLE_IFX_VA_CMD)
uint32_t speech_utils_itsi_get_parm(void* container, int32_t ip_id, float* parm)
{
    /* Sanity check of input arguments */
    if (container == NULL)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_DFWWD)
    {
        itsi_dfwwd_top_struct* dPt = (itsi_dfwwd_top_struct*)container;

        *parm = dPt->noactivty_timeout;
    }
    else if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_DFCMD)
    {
        itsi_dfcmd_top_struct* dPt = (itsi_dfcmd_top_struct*)container;

        *parm = dPt->maxwwgap;
    }
    else
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_COMPONENT_ID);
    }

    return IFX_SP_ENH_SUCCESS;
}

uint32_t speech_utils_itsi_set_parm(void* container, int32_t ip_id, float parm)
{
    /* Sanity check of input arguments */
    if (container == NULL)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_DFWWD)
    {
        itsi_dfwwd_top_struct* dPt = (itsi_dfwwd_top_struct*)container;

        dPt->noactivty_timeout = parm;
    }
    else if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_DFCMD)
    {
        itsi_dfcmd_top_struct* dPt = (itsi_dfcmd_top_struct*)container;

        dPt->maxwwgap = parm;
    }
    else
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_COMPONENT_ID);
    }

    return IFX_SP_ENH_SUCCESS;
}
#endif
