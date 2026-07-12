/******************************************************************************
* File Name: ifx_pre_post_process.c
*
* Description: This file contains functions to initialize and run frame by frame
*              Infineon pre and post process functions.
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
#include <ctype.h>
#include "stdlib.h"
#include "string.h"
#include "stdio.h"
#include "ifx_sp_utils_priv.h"
#include "ifx_sp_utils.h"
#include "ifx_sp_common_priv.h"
#include "ifx_pre_post_process.h"
#ifdef ENABLE_IFX_VA_WWD
#include "ifx_va_prms.h"
#endif
#ifdef PROFILER
#include "ifx_cycle_profiler.h"
#endif

/* Number of parameters is MAX_WW_TOKENS * 3 (i.e. prob thrshold, count threshold, & gap threshold) + 5 (Nww_series, ww_tokens, total_time, 2 garbage count thresholds) */
#define LPWWD_PP_PARMS_SIZE 17 /* Number of parameters for LPWWD post process */
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
int32_t ifx_pre_post_process_parse(int32_t* ip_prms_config, ifx_stc_pre_post_process_info_t* ip_infoPt)
{
    int32_t* int_idx = (int32_t*)ip_prms_config;
    int32_t sampling_rate, frame_size, frame_shift, num_feature, num_coeffs, ip_id, block_size, sz;
    int32_t ret;
    mem_info_t mem_info;

    //Warnings fix - Ununsed variable (results from enabling certain algos */
    (void)block_size; (void)num_coeffs; (void)num_feature; (void)frame_shift; (void)block_size; (void)ret; (void)mem_info;

    /* Sanity check of input arguments */
    if (ip_prms_config == NULL)
    {
        return IFX_SP_ENH_ERROR(IFX_SP_ENH_COMPONENT_ID_INVALID, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }
    /* read first five parameters which are always same definition */
    sz = *int_idx++;             /* Configurator version, no checking its validation for now */
    ip_infoPt->configurator_version = sz;
    ip_infoPt->libsp_version = IFX_SP_LPWWD_VERSION;
    sampling_rate = *int_idx++;  /* sampling rate */
    frame_size = *int_idx++;     /* frame size */
    ip_id = *int_idx++;          /* IP component ID */
    sz = *int_idx++;             /* number of following parameters */
    if (sz < 0)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_NUMBER_PARMS);
    }
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_ASRC_LPF || ip_id == IFX_PRE_PROCESS_IP_COMPONENT_HPF)
    {
        if (sampling_rate != 16000 && sampling_rate != 44100 && sampling_rate != 48000) {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
    }
    else if (sampling_rate != 16000)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
    }
    /* Sanity check of input arguments */
    if (ip_infoPt == NULL)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    ip_infoPt->component_id = ip_id;
    ip_infoPt->sampling_rate = sampling_rate;
    ip_infoPt->input_frame_size = frame_size;

#ifdef ENABLE_IFX_AGC
    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_AGC)
    {
        if (frame_size <= 0 || sz != AGC_PARMS_SIZE) /* AGC parameter size */
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        ip_infoPt->output_size = frame_size;
        /* fill zeros for parameter don't care or not applicable */
        ip_infoPt->frame_shift = 0;
        ip_infoPt->fft_block_size = 0;
    }
    else
#endif
#ifdef ENABLE_IFX_VA_WWD
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_DENOISE)
    {
        if (frame_size != 160 || sz != 1)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_NUMBER_PARMS);
        }
        ip_infoPt->output_size = *int_idx;  /* itsi feature output size */
        if (ip_infoPt->output_size != FEATURE_BUF_SZ)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        /* fill zeros for parameter don't care or not applicable */
        ip_infoPt->frame_shift = 0;    /* built in hidden parameter */
        ip_infoPt->fft_block_size = 0; /* built in hidden parameter */
    }
    else if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_DFWWD)
    {
        if (frame_size != 160 || sz != 1)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_NUMBER_PARMS);
        }
        /* fill zeros for parameter don't care or not applicable */
        ip_infoPt->output_size = 0;    /* itsi DFWWD output one value */
        ip_infoPt->frame_shift = 0;    /* built in hidden parameter */
        ip_infoPt->fft_block_size = 0; /* parameter not used */
    }
    else
#endif
#ifdef ENABLE_IFX_VA_CMD
    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_DFCMD)
    {
        if (frame_size != 160 || sz != 2)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_NUMBER_PARMS);
        }
        /* fill zeros for parameter don't care or not applicable */
        ip_infoPt->output_size = 0;    /* itsi DFCMD output one value */
        ip_infoPt->frame_shift = 0;    /* built in hidden parameter */
        ip_infoPt->fft_block_size = 0; /* parameter not used */
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
        ip_infoPt->output_size = frame_size;
        /* fill zeros for parameter don't care or not applicable */
        ip_infoPt->frame_shift = 0;
        ip_infoPt->fft_block_size = 0;
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
        ip_infoPt->output_size = frame_size;
        /* fill zeros for parameter don't care or not applicable */
        ip_infoPt->frame_shift = 0;
        ip_infoPt->fft_block_size = 0;
    }
    else
#endif
#if defined(ENABLE_IFX_LPWWD) || defined(ENABLE_IFX_FE)
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_MFCC || ip_id == IFX_PRE_PROCESS_IP_COMPONENT_LOG_MEL)
    {
        frame_shift = *int_idx++;    /* frame shift */
        sz--;
        if (sz < 1)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_NUMBER_PARMS);
        }
        else
        {
            num_feature = *int_idx++;    /* number of features */
            sz--;
        }
        if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_MFCC)
        {
            if (sz != 1)
            {
                return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_NUMBER_PARMS);
            }
            num_coeffs = *int_idx++;     /* number of DCT coeffs */
            sz = num_coeffs;
        }
        else
        {
            num_coeffs = 0;
            sz = num_feature;
        }
        if (num_feature < 0 || num_feature > MAX_FBANK_SIZE || num_coeffs > num_feature) /* num_coeffs is less than num_fbank_bins */
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        if (frame_shift > frame_size)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        block_size = (int32_t)pow(2, ceil((log(frame_size) / log(2)))); // Round-up to nearest power of 2.
        if ((block_size < 256) || (block_size > 1024))
        {/* Supported block_size is between 256 to 1024 */
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        ip_infoPt->fft_block_size = block_size;
        ip_infoPt->frame_shift = frame_shift;
        ip_infoPt->output_size = sz;
    }
    else
#endif
#if defined(ENABLE_IFX_LPWWD)
    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_HMMS)
    {
#ifdef ENABLE_IFX_LPWWD_HMMS
        if (sz != 4)
        {/* Only four parameters */
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_NUMBER_PARMS);
        }
        /* fill zeros for parameter don't care or not applicable */
        ip_infoPt->frame_shift = 0;
        ip_infoPt->output_size = 0;
        ip_infoPt->fft_block_size = 0;
#else
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_COMPONENT_ID); /* Please define ENABLE_IFX_LPWWD_HMMS */
#endif
    }
    else if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_LPWWD)
    {
        if (sz != LPWWD_PP_PARMS_SIZE)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_NUMBER_PARMS);
        }
        uint8_t ww_series = *int_idx++;    /* number of  WW */
        uint8_t ww_tokens = *int_idx++;     /* number of WW tokens */
        if (ww_series == 0 || ww_series > MAX_WW_SERIES ||
            ww_tokens == 0 || ww_tokens > MAX_WW_TOKENS || (ww_series * ww_tokens > MAX_WW_TOKENS))
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        uint16_t garbage_count_threshold = *int_idx++; /* garbage count threshold */
        uint16_t garbage_count_2nd_threshold = *int_idx++;   /* garbage count 2nd threshold */
        uint16_t total_timeout_threshold = *int_idx++; /* total timeout threshold */
        if (total_timeout_threshold == 0 || total_timeout_threshold > INT16_MAX ||
            garbage_count_threshold > INT8_MAX ||
            garbage_count_2nd_threshold > INT8_MAX)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        IFX_PPINPUT_DATA_TYPE_T prob_threshold[MAX_WW_TOKENS];
        for (int i = 0; i < MAX_WW_TOKENS; i++)
        {
            prob_threshold[i] = *int_idx++; /* probability threshold for each token */
            if (prob_threshold[i] < 0 || prob_threshold[i] > INT16_MAX)
            {
                return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
            }
        }
        uint8_t count_threshold[MAX_WW_TOKENS];
        for (int i = 0; i < MAX_WW_TOKENS; i++)
        {
            count_threshold[i] = *int_idx++; /* count threshold for each token */
            if (count_threshold[i] > UINT8_MAX)
            {
                return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
            }
        }
        uint8_t gap_threshold[MAX_WW_TOKENS];
        for (int i = 0; i < MAX_WW_TOKENS; i++)
        {
            gap_threshold[i] = *int_idx++; /* gap threshold for each token */
            if (gap_threshold[i] > UINT8_MAX)
            {
                return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
            }
        }
        /* fill zeros for parameter don't care or not applicable */
        ip_infoPt->frame_shift = 0;
        ip_infoPt->output_size = 1;
        ip_infoPt->fft_block_size = 0;
    }
    else
#endif
#ifdef ENABLE_IFX_SOD
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_SOD)
    {
        if (frame_size != 160 || sz != 2)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        /* fill zeros for parameter don't care or not applicable */
        ip_infoPt->frame_shift = 0;
        ip_infoPt->output_size = 0;
        ip_infoPt->fft_block_size = 0;
    }
    else
#endif
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_FEATURE_NOT_SUPPORTED);
    }

#if defined(ENABLE_IFX_SOD) || defined(ENABLE_IFX_LPWWD) || \
    defined(ENABLE_IFX_PRE_PROCESS_HPF) || defined(ENABLE_IFX_PRE_PROCESS_ASRC_LPF) || \
    defined(ENABLE_IFX_VA_WWD) || defined(ENABLE_IFX_VA_CMD) || defined(ENABLE_IFX_FE) || defined(ENABLE_IFX_AGC)
    /* Get required memory for model configuration */
    ret = speech_utils_getMem(ip_prms_config, ip_id, &mem_info);
    if (ret != IFX_SP_ENH_SUCCESS)
    {
        return ret;
    }
    else
    {
        ip_infoPt->memory.scratch_mem = mem_info.scratch_mem;
        ip_infoPt->memory.persistent_mem = mem_info.persistent_mem;
    }
    return IFX_SP_ENH_SUCCESS;
#else
    return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_FEATURE_NOT_SUPPORTED);
#endif
}

int32_t ifx_pre_post_process_init(int32_t * ip_prms_config, void **ifx_container, ifx_stc_pre_post_process_info_t* ip_infoPt)
{
    int32_t* int_idx = (int32_t*)ip_prms_config;
    int32_t sampling_rate, frame_size, frame_shift = 0, num_feature, num_coeffs, ip_id, block_size, sz;

    //Warnings fix - Ununsed variable (results from enabling certain algos */
    (void)block_size; (void)num_coeffs; (void)num_feature; (void)frame_shift; (void)frame_size; (void)sz;

    /* Sanity check of input arguments */
    if (ip_prms_config == NULL)
    {
        return IFX_SP_ENH_ERROR(IFX_SP_ENH_COMPONENT_ID_INVALID, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    /* read first five parameters which are always same definition */
    sz = *int_idx++;                /* Configurator version, ignore for now */
    sampling_rate = *int_idx++;     /* sampling rate */
    frame_size    = *int_idx++;     /* frame size */
    ip_id = *int_idx++;             /* IP component ID */
    sz = *int_idx++;                /* number of following parameters */

    /* Sanity check of input arguments */
    if (ifx_container == NULL || ip_infoPt == NULL)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }
    if ((ip_infoPt->memory.persistent_mem_pt == NULL) || (ip_infoPt->memory.scratch_mem_pt == NULL))
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_ASRC_LPF || ip_id == IFX_PRE_PROCESS_IP_COMPONENT_HPF)
    {
        if (sampling_rate != 16000 && sampling_rate != 44100 && sampling_rate != 48000) {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
    }
    else if (sampling_rate != 16000)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
    }

#ifdef ENABLE_IFX_VA_WWD
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_DENOISE)
    {
        if (frame_size != 160 || sz != 1)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_NUMBER_PARMS);
        }
        sz = *int_idx;  /* itsi feature output size */
        if (sz != FEATURE_BUF_SZ)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        return itsi_feature_init(ifx_container, &(ip_infoPt->memory));
    }
    else if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_DFWWD)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_API); /* Please call itsi_dfwwd_init() function */
    }
    else
#endif
#ifdef ENABLE_IFX_VA_CMD
    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_DFCMD)
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_API); /* Please call itsi_dfcmd_init() function */
    }
    else
#endif
#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_HPF)
    {/* Add HPF set up and init here */
        preprocess_hpf_top_struct * dPt = (preprocess_hpf_top_struct *)(ip_infoPt->memory.persistent_mem_pt);
        int32_t status;

        /* Set up pre-process AFE HPF data structure in persistent memory */
        sz = ALIGN_WORD(sizeof(preprocess_hpf_top_struct));
        memset(dPt, 0, sz);
        dPt->enable_flag = true; /* enable by default */
        dPt->sample_rate = sampling_rate;
        dPt->frame_size = frame_size;
        dPt->pre_proc_hpf.persistent_size = ip_infoPt->memory.persistent_mem;
        dPt->pre_proc_hpf.persistent_pad = ip_infoPt->memory.persistent_mem_pt;
        dPt->pre_proc_hpf.scratch.scratch_size = ip_infoPt->memory.scratch_mem;
        dPt->pre_proc_hpf.scratch.scratch_pad = ip_infoPt->memory.scratch_mem_pt;

        /* Initialize internal AFE HPF structure */
        dPt->pre_proc_hpf.ifx_component_pt = dPt->pre_proc_hpf.persistent_pad + sz;
        status = ifx_afe_hpf_init(dPt);
        *ifx_container = dPt;
        if (status != IFX_SP_ENH_SUCCESS)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        else
        {
            return IFX_SP_ENH_SUCCESS;
        }
    }
    else
#endif
#ifdef ENABLE_IFX_PRE_PROCESS_ASRC_LPF
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_ASRC_LPF)
    {/* Add HPF set up and init here */
        preprocess_asrc_lpf_top_struct* dPt = (preprocess_asrc_lpf_top_struct*)(ip_infoPt->memory.persistent_mem_pt);
        int32_t status;

        /* Set up pre-process AFE HPF data structure in persistent memory */
        sz = ALIGN_WORD(sizeof(preprocess_asrc_lpf_top_struct));
        memset(dPt, 0, sz);
        dPt->enable_flag = true; /* enable by default */
        dPt->sample_rate = sampling_rate;
        dPt->frame_size = frame_size;
        dPt->asrc_lpf.persistent_size = ip_infoPt->memory.persistent_mem;
        dPt->asrc_lpf.persistent_pad = ip_infoPt->memory.persistent_mem_pt;
        dPt->asrc_lpf.scratch.scratch_size = ip_infoPt->memory.scratch_mem;
        dPt->asrc_lpf.scratch.scratch_pad = ip_infoPt->memory.scratch_mem_pt;

        /* Initialize internal AFE HPF structure */
        dPt->asrc_lpf.ifx_component_pt = dPt->asrc_lpf.persistent_pad + sz;
        status = ifx_asrc_lpf_init(dPt);
        *ifx_container = dPt;
        if (status != IFX_SP_ENH_SUCCESS)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        else
        {
            return IFX_SP_ENH_SUCCESS;
        }
    }
    else
#endif
#ifdef ENABLE_IFX_LPWWD
    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_HMMS)
    {
        int32_t ret;
#ifdef ENABLE_IFX_LPWWD_HMMS
        hmms_postprocess_top_struct* pp_ptr;
        int16_t detection_th, set_flag;

        if (sz != 4)
        {/* Only four parameters */
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        /* Set up post processing data structure in persistent memory */
        pp_ptr = (hmms_postprocess_top_struct*)(ip_infoPt->memory.persistent_mem_pt);
        memset(pp_ptr, 0, sizeof(hmms_postprocess_top_struct));

        pp_ptr->pp_component.persistent_size = ip_infoPt->memory.persistent_mem;
        pp_ptr->pp_component.persistent_pad = ip_infoPt->memory.persistent_mem_pt;
        pp_ptr->pp_component.scratch.scratch_size = ip_infoPt->memory.scratch_mem;
        pp_ptr->pp_component.scratch.scratch_pad = ip_infoPt->memory.scratch_mem_pt;

        /* Initialize internal post processing structure */
        pp_ptr->pp_component.ifx_component_pt = pp_ptr->pp_component.persistent_pad + ALIGN_WORD(sizeof(hmms_postprocess_top_struct));
        pp_ptr->fps = *int_idx++;
        pp_ptr->lookback_buffer_length = *int_idx++;
        pp_ptr->stacked_frame_delay = *int_idx++;
        pp_ptr->detection_threshold = *int_idx++;
        set_flag = (int16_t)(pp_ptr->detection_threshold & 0xFFFF); /* lower 16bit is set flag */
        detection_th = (int16_t)(pp_ptr->detection_threshold >> 16);/* upper 16bit is the detection threshold */
#if HMMS_CONFIG_MODEL //This compilation switch need to be set if target platform has no file IO support to read model data files.
        ret = fixed_init_lpwwd_post(pp_ptr->pp_component.ifx_component_pt, pp_ptr->lookback_buffer_length, pp_ptr->stacked_frame_delay, detection_th, set_flag);
#else
        extern int16_t* ppkwmodel;
        extern int16_t* ppgmodel;
        extern int16_t* ppnmodel;
        ret = fixed_init_lpwwd_post(pp_ptr->pp_component.ifx_component_pt, ppkwmodel, ppgmodel, ppnmodel, NULL, pp_ptr->lookback_buffer_length, pp_ptr->stacked_frame_delay, detection_th, set_flag);
#endif
        if (ret != 0)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
       *ifx_container = pp_ptr;
#else
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_INVALID_COMPONENT_ID); /* Please define ENABLE_IFX_LPWWD_HMMS */
#endif
        return ret;
    }
    else if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_LPWWD)
    {
        if (sz != LPWWD_PP_PARMS_SIZE)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_NUMBER_PARMS);
        }
        int32_t ret;
        uint8_t ww_series = *int_idx++;    /* number of  WW */
        uint8_t ww_tokens = *int_idx++;     /* number of WW tokens */
        if (ww_series == 0 || ww_series > MAX_WW_SERIES ||
            ww_tokens == 0 || ww_tokens > MAX_WW_TOKENS || (ww_series * ww_tokens > MAX_WW_TOKENS))
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        uint16_t garbage_count_threshold = *int_idx++; /* garbage count threshold */
        uint16_t garbage_count_2nd_threshold = *int_idx++;   /* garbage count 2nd threshold */
        uint16_t timeout_threshold = *int_idx++; /* total timeout threshold */
        if (timeout_threshold == 0 || timeout_threshold > INT16_MAX ||
            garbage_count_threshold > INT16_MAX ||
            garbage_count_2nd_threshold > INT16_MAX)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        IFX_PPINPUT_DATA_TYPE_T prob_threshold[MAX_WW_TOKENS];
        for (int i = 0; i < MAX_WW_TOKENS; i++)
        {
            prob_threshold[i] = *int_idx++; /* probability threshold for each token */
            if (prob_threshold[i] < 0 || prob_threshold[i] > INT16_MAX)
            {
                return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
            }
        }
        uint8_t count_threshold[MAX_WW_TOKENS];
        for (int i = 0; i < MAX_WW_TOKENS; i++)
        {
            count_threshold[i] = *int_idx++; /* count threshold for each token */
            if (count_threshold[i] > UINT8_MAX)
            {
                return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
            }
        }
        uint8_t gap_threshold[MAX_WW_TOKENS];
        for (int i = 0; i < MAX_WW_TOKENS; i++)
        {
            gap_threshold[i] = *int_idx++; /* gap threshold for each token */
            if (gap_threshold[i] > UINT8_MAX)
            {
                return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
            }
        }

        ret = ifx_lpwwd_post_process_init(ifx_container, &(ip_infoPt->memory), prob_threshold, count_threshold, gap_threshold,
                    ww_series, ww_tokens, timeout_threshold, garbage_count_threshold, garbage_count_2nd_threshold);
        return ret;
    }
    else
#endif
#ifdef ENABLE_IFX_SOD
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_SOD)
    {
        int32_t ret;
        ret = speech_utils_sod_init(ip_prms_config, ifx_container, &(ip_infoPt->memory));
        return ret;
    }
    else
#endif
#ifdef ENABLE_IFX_SOD
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_SOD)
    {
        int32_t ret;
        ret = speech_utils_sod_init(ip_prms_config, ifx_container, &(ip_infoPt->memory));
        return ret;
    }
    else
#endif
#if defined(ENABLE_IFX_LPWWD) || defined(ENABLE_IFX_FE)
    if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_MFCC || ip_id == IFX_PRE_PROCESS_IP_COMPONENT_LOG_MEL)
    {
        if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_MFCC)
        {/* mfcc option */
            if (sz != 3)
            {
                return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
            }
            frame_shift = *int_idx++;
            num_feature = *int_idx++;
            num_coeffs = *int_idx++;
        }
        else if (ip_id == IFX_PRE_PROCESS_IP_COMPONENT_LOG_MEL)
        {/* log-mel option */
            if (sz < 2 || sz > 3)
            {
                return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
            }
            frame_shift = *int_idx++;
            num_feature = *int_idx++;
            num_coeffs = 0; /* force set num_mfcc_coeffs to zero for log_ml case */
        }

        spectrogram_top_struct* dPt;
        if (frame_shift > frame_size)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        if (num_feature < 0 || num_feature > MAX_FBANK_SIZE || num_coeffs > num_feature) /* num_coeffs is less than num_fbank_bins */
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        /* Set up Spectrogram Transfomation data structure in persistent memory */
        dPt = (spectrogram_top_struct*)(ip_infoPt->memory.persistent_mem_pt);
        sz = ALIGN_WORD(sizeof(spectrogram_top_struct));
        memset(dPt, 0, sz);

        dPt->spctrg_component.persistent_size = ip_infoPt->memory.persistent_mem;
        dPt->spctrg_component.persistent_pad = ip_infoPt->memory.persistent_mem_pt;
        dPt->spctrg_component.scratch.scratch_size = ip_infoPt->memory.scratch_mem;
        dPt->spctrg_component.scratch.scratch_pad = ip_infoPt->memory.scratch_mem_pt;

        /* Initialize internal feature extraction structure */
        dPt->spctrg_component.ifx_component_pt = dPt->spctrg_component.persistent_pad + sz;
        sz += spectrogram_calculate_spctrg_component_size();

        block_size = ip_infoPt->fft_block_size;
        if ((block_size < 256) || (block_size > 1024))
        {/* Supported block_size is between 256 to 1024 */
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }

        dPt->mel_block_size = block_size;
        dPt->mel_sample_rate = sampling_rate;
        dPt->mel_frame_size = frame_size;
        dPt->mel_frame_shift = frame_shift;
        dPt->mel_num_fbank_bins = num_feature;
        dPt->mel_num_mfcc_coeffs = num_coeffs;

        /* Initialize internal Spectrogram Transfomation structure */
        mel_features_fix_init(dPt, sz);

        *ifx_container = dPt;

        return IFX_SP_ENH_SUCCESS;
    }
    else
#endif
#ifdef ENABLE_IFX_AGC
    if (ip_id == IFX_POST_PROCESS_IP_COMPONENT_AGC)
    {/* Add AGC set up and init here */
        postprocess_agc_top_struct* dPt = (postprocess_agc_top_struct*)(ip_infoPt->memory.persistent_mem_pt);
        int16_t agcParms[AGC_PARMS_SIZE];
        int32_t status;

        /* Set up post-process AGC data structure in persistent memory */
        sz = ALIGN_WORD(sizeof(postprocess_agc_top_struct));
        memset(dPt, 0, sz);
        dPt->enable_flag = true; /* enable by default */
        dPt->sample_rate = sampling_rate;
        dPt->frame_size = frame_size;
        dPt->ifx_agc.persistent_size = ip_infoPt->memory.persistent_mem;
        dPt->ifx_agc.persistent_pad = ip_infoPt->memory.persistent_mem_pt;
        dPt->ifx_agc.scratch.scratch_size = ip_infoPt->memory.scratch_mem;
        dPt->ifx_agc.scratch.scratch_pad = ip_infoPt->memory.scratch_mem_pt;

        /* Initialize internal AGC structure */
        dPt->ifx_agc.ifx_component_pt = dPt->ifx_agc.persistent_pad + sz;

        for (int i = 0; i < AGC_PARMS_SIZE; i++)
        {/* Copy agc configuable parameters for ifx_agc_config_prms.h */
            agcParms[i] = (int16_t)(*int_idx++);
        }
        status = ifx_agc_init(dPt, agcParms);
        *ifx_container = dPt;
        if (status != IFX_SP_ENH_SUCCESS)
        {
            return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_ERR_PARAM);
        }
        else
        {
            return IFX_SP_ENH_SUCCESS;
        }
    }
    else
#endif
    {
        return IFX_SP_ENH_ERROR(ip_id, IFX_SP_ENH_FEATURE_NOT_SUPPORTED);
    }
}

int32_t ifx_time_pre_process(IFX_SP_DATA_TYPE_T* input1, IFX_SP_DATA_TYPE_T* input2, void* preprocess_container, int32_t component_id, IFX_SP_DATA_TYPE_T* output1, IFX_SP_DATA_TYPE_T* output2)
{
    (void)component_id;
    /* Sanity check of input arguments */
    if (preprocess_container == NULL || (input1 == NULL && input2 == NULL) || (output1 == NULL && output2 == NULL))
    {
        return IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }
#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_HPF)
    {
        preprocess_hpf_top_struct* dPt = (preprocess_hpf_top_struct *)preprocess_container;
        if (dPt->pre_proc_hpf.reset_flag)
        {/* one time reset */
            int32_t status;
            dPt->pre_proc_hpf.reset_flag = false;
            status = ifx_afe_hpf_reset(preprocess_container);
            if (status != IFX_SP_ENH_SUCCESS)
            {
                return IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_ERR_PARAM);
            }
        }
#ifdef PROFILER
        ifx_cycle_profile_start(&(dPt->pre_proc_hpf.profile));
#endif
        if (dPt->enable_flag)
        {
            ifx_afe_hpf(preprocess_container, input1, input2, output1, output2);
        }
        else
        {
            uint32_t size = (dPt->frame_size) * sizeof(IFX_SP_DATA_TYPE_T);
            if (input1 != NULL && output1 != NULL && input1 != output1)
            {
                memcpy(output1, input1, size);
            }
            if (input2 != NULL && output2 != NULL && input2 != output2)
            {
                memcpy(output2, input2, size);
            }
        }
#ifdef PROFILER
        ifx_cycle_profile_stop(&(dPt->pre_proc_hpf.profile));
#endif
        return IFX_SP_ENH_SUCCESS;
    }
    else
#endif
#ifdef ENABLE_IFX_PRE_PROCESS_ASRC_LPF
    if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_ASRC_LPF)
    {
        preprocess_asrc_lpf_top_struct* dPt = (preprocess_asrc_lpf_top_struct*)preprocess_container;
        if (dPt->asrc_lpf.reset_flag)
        {/* one time reset */
            int32_t status;
            dPt->asrc_lpf.reset_flag = false;
            status = ifx_asrc_lpf_reset(preprocess_container);
            if (status != IFX_SP_ENH_SUCCESS)
            {
                return IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_ERR_PARAM);
            }
        }
#ifdef PROFILER
        ifx_cycle_profile_start(&(dPt->asrc_lpf.profile));
#endif
        if (dPt->enable_flag)
        {
            ifx_asrc_lpf(preprocess_container, input1, input2, output1, output2);
        }
        else
        {
            uint32_t size = (dPt->frame_size) * sizeof(IFX_SP_DATA_TYPE_T);
            if (input1 != NULL && output1 != NULL && input1 != output1)
            {
                memcpy(output1, input1, size);
            }
            if (input2 != NULL && output2 != NULL && input2 != output2)
            {
                memcpy(output2, input2, size);
            }
        }
#ifdef PROFILER
        ifx_cycle_profile_stop(&(dPt->asrc_lpf.profile));
#endif
        return IFX_SP_ENH_SUCCESS;
    }
    else
#endif
    return IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_FEATURE_NOT_SUPPORTED);
}

int32_t ifx_time_post_process(IFX_SP_DATA_TYPE_T* input, void* postprocess_container, int32_t component_id, IFX_SP_DATA_TYPE_T* output)
{
    (void)component_id;
    /* Sanity check of input arguments */
    if (postprocess_container == NULL || input == NULL || output == NULL)
    {
        return IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }
#ifdef ENABLE_IFX_AGC
    int32_t status;
    if (component_id == IFX_POST_PROCESS_IP_COMPONENT_AGC)
    {
        postprocess_agc_top_struct* dPt = (postprocess_agc_top_struct *)postprocess_container;
        if (dPt->ifx_agc.reset_flag)
        {/* one time reset */
            dPt->ifx_agc.reset_flag = false;
            status = ifx_agc_reset(postprocess_container);
            if (status != IFX_SP_ENH_SUCCESS)
            {
                return status;
            }
        }
#ifdef PROFILER
        ifx_cycle_profile_start(&(dPt->ifx_agc.profile));
#endif
        if (dPt->enable_flag)
        {
            status = ifx_agc(postprocess_container, input, output);
        }
        else
        {
            uint32_t size = (dPt->frame_size) * sizeof(IFX_SP_DATA_TYPE_T);
            memcpy(output, input, size);
            status = IFX_SP_ENH_SUCCESS;
        }
#ifdef PROFILER
        ifx_cycle_profile_stop(&(dPt->ifx_agc.profile));
#endif
        return status;
    }
    else
#endif
    return IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_FEATURE_NOT_SUPPORTED);
}

int32_t ifx_spectrogram_transfer(IFX_SP_DATA_TYPE_T* in, void* spectrogram_container, IFX_FE_DATA_TYPE_T* fe_out, int32_t* out_q)
{
    (void)in, (void)spectrogram_container, (void)fe_out, (void)out_q;
#if defined(ENABLE_IFX_LPWWD) || defined(ENABLE_IFX_FE)
    spectrogram_top_struct* dPt;

    /* Sanity check of input arguments */
    if ((spectrogram_container == NULL) || (in == NULL))
    {
        return IFX_SP_ENH_ERROR(IFX_PRE_PROCESS_IP_COMPONENT_MFCC, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    dPt = (spectrogram_top_struct*)spectrogram_container;
    if (dPt->spctrg_component.reset_flag)
    {/* one time input sample tail (zero out) reset */
        int size = dPt->mel_block_size - dPt->mel_frame_size;
        if (size > 0)
        {
            memset(in, 0, size * sizeof(IFX_SP_DATA_TYPE_T));
        }
        dPt->spctrg_component.reset_flag = false;
    }
#ifdef PROFILER
    ifx_cycle_profile_start(&(dPt->spctrg_component.profile));
#endif
    mel_features_fix_compute(dPt, in, fe_out, out_q);
#ifdef PROFILER
    ifx_cycle_profile_stop(&(dPt->spctrg_component.profile));
#endif
#endif
    return IFX_SP_ENH_SUCCESS;
}

int32_t ifx_pre_post_process_mode_control(void* container, int32_t component_id, bool enable, bool reset)
{
    int32_t ErrIdx = IFX_SP_ENH_SUCCESS;
    (void)enable;
    /* Sanity check of input arguments */
    if ((container == NULL) || (component_id >= IFX_POST_PROCESS_IP_COMPONENT_MAX_COUNT) || (component_id < IFX_PRE_POST_IP_COMPONENT_START_ID))
    {
        return IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    if (reset)
    {
#ifdef ENABLE_IFX_SOD
        if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_SOD)
        {
            sod_top_struct* dPt;

            dPt = (sod_top_struct*)container;
            dPt->sod_component.reset_flag = true;
        }
        else
#endif
#ifdef ENABLE_IFX_PRE_PROCESS_HPF
        if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_HPF)
        {
            preprocess_hpf_top_struct* dPt;

            dPt = (preprocess_hpf_top_struct*)container;
            dPt->pre_proc_hpf.reset_flag = true;
        }
        else
#endif
#ifdef ENABLE_IFX_PRE_PROCESS_ASRC_LPF
        if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_ASRC_LPF)
        {
            preprocess_asrc_lpf_top_struct* dPt;

            dPt = (preprocess_asrc_lpf_top_struct*)container;
            dPt->asrc_lpf.reset_flag = true;
        }
        else
#endif
#if defined(ENABLE_IFX_LPWWD) || defined(ENABLE_IFX_FE)
        if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_MFCC || component_id == IFX_PRE_PROCESS_IP_COMPONENT_LOG_MEL)
        {/* set one time input sample tail (zero out) reset flag */
            spectrogram_top_struct* dPt;

            dPt = (spectrogram_top_struct*)container;
            dPt->spctrg_component.reset_flag = true;
        }
        else
#endif
#ifdef ENABLE_IFX_LPWWD
#ifdef ENABLE_IFX_LPWWD_HMMS
        if (component_id == IFX_POST_PROCESS_IP_COMPONENT_HMMS)
        {
            hmms_postprocess_top_struct* pp_ptr = (hmms_postprocess_top_struct*)container;
            pp_ptr->pp_component.reset_flag = true;
            fixed_reset_lpwwd_post(pp_ptr->pp_component.ifx_component_pt); /* this is optional since reset flag will trigger to call this */
        }
        else
#endif
        if (component_id == IFX_POST_PROCESS_IP_COMPONENT_LPWWD)
        {
            lpwwd_postprocess_top_struct* pp_ptr = (lpwwd_postprocess_top_struct*)container;
            pp_ptr->pp_component.reset_flag = true;
        }
        else
#endif
#ifdef ENABLE_IFX_AGC
        if (component_id == IFX_POST_PROCESS_IP_COMPONENT_AGC)
        {
            postprocess_agc_top_struct* dPt;

            dPt = (postprocess_agc_top_struct*)container;
            dPt->ifx_agc.reset_flag = true;
        }
        else
#endif
        {
            ErrIdx = IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_FEATURE_NOT_SUPPORTED);
        }
    }

    /* For now, enable/disable only applicable to SOD, HPF, ASRC LPF, AGC */
#ifdef ENABLE_IFX_SOD
    if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_SOD)
    {
        sod_top_struct* dPt;

        dPt = (sod_top_struct*)container;
        dPt->enable_flag = enable;
    }
#endif
#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_HPF)
    {
        preprocess_hpf_top_struct* dPt;

        dPt = (preprocess_hpf_top_struct*)container;
        dPt->enable_flag = enable;
    }
#endif
#ifdef ENABLE_IFX_PRE_PROCESS_ASRC_LPF
    if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_ASRC_LPF)
    {
        preprocess_asrc_lpf_top_struct* dPt;

        dPt = (preprocess_asrc_lpf_top_struct*)container;
        dPt->enable_flag = enable;
    }
#endif
#ifdef ENABLE_IFX_AGC
    if (component_id == IFX_POST_PROCESS_IP_COMPONENT_AGC)
    {
        postprocess_agc_top_struct* dPt;

        dPt = (postprocess_agc_top_struct*)container;
        dPt->enable_flag = enable;
    }
#endif

    return ErrIdx;
}

int32_t ifx_pre_post_process_status(void* container, int32_t component_id)
{
    int32_t status = true;
    (void)component_id;
    if (container == NULL)
    {/* Argument is invalid so set to false */
        status = false;
    }
#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    else if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_HPF)
    {
        preprocess_hpf_top_struct* dPt;

        dPt = (preprocess_hpf_top_struct*)container;
        status = dPt->enable_flag;
    }
    else
#endif
#ifdef ENABLE_IFX_PRE_PROCESS_ASRC_LPF
    if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_ASRC_LPF)
    {
    preprocess_asrc_lpf_top_struct* dPt;

    dPt = (preprocess_asrc_lpf_top_struct*)container;
    status = dPt->enable_flag;
    }
    else
#endif
#ifdef ENABLE_IFX_SOD
    if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_SOD)
    {
        sod_top_struct* dPt;

        dPt = (sod_top_struct*)container;
        status = dPt->enable_flag;
    }
    else
#endif
#if defined(ENABLE_IFX_LPWWD) || defined(ENABLE_IFX_FE)
    if (component_id == IFX_PRE_PROCESS_IP_COMPONENT_MFCC || component_id == IFX_PRE_PROCESS_IP_COMPONENT_LOG_MEL)
    {/* Feature extraction is always enabled */
        status = true;
    }
    else
#endif
#ifdef ENABLE_IFX_LPWWD
    if (component_id == IFX_POST_PROCESS_IP_COMPONENT_HMMS)
    {/* HMMS post process is always enabled */
#ifdef ENABLE_IFX_LPWWD_HMMS
        status = true;
#else
        status = false;
#endif
    }
    else if (component_id == IFX_POST_PROCESS_IP_COMPONENT_LPWWD)
    {/* LPWWD post process is always enabled */
        status = true;
    }
    else
#endif
#ifdef ENABLE_IFX_AGC
    if (component_id == IFX_POST_PROCESS_IP_COMPONENT_AGC)
    {
        postprocess_agc_top_struct* dPt;

        dPt = (postprocess_agc_top_struct*)container;
        status = dPt->enable_flag;
    }
    else
#endif
    {/* un-support componenet reture false */
        status = false;
    }

    return status;
}

int32_t ifx_post_process(IFX_PPINPUT_DATA_TYPE_T* in_probs, void* postprocess_container, int32_t component_id, int32_t* detection)
{
    (void)in_probs, (void)postprocess_container, (void)component_id, (void)detection;
#ifdef ENABLE_IFX_LPWWD
    /* Sanity check of input arguments */
    if ((postprocess_container == NULL) || (in_probs == NULL))
    {
        return IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    if (component_id == IFX_POST_PROCESS_IP_COMPONENT_HMMS)
    {
#ifdef ENABLE_IFX_LPWWD_HMMS
        hmms_postprocess_top_struct* dPt;

#ifdef PROFILER
        ifx_cycle_profile_start(&(dPt->pp_component.profile));
#endif
        dPt = (hmms_postprocess_top_struct*) postprocess_container;
        if (dPt->pp_component.reset_flag)
        {/* one time reset */
            fixed_reset_lpwwd_post(dPt->pp_component.ifx_component_pt);
            dPt->pp_component.reset_flag = false;
        }
        *detection = fixed_lpwwd_post(dPt->pp_component.ifx_component_pt, in_probs);
#ifdef PROFILER
        ifx_cycle_profile_stop(&(dPt->pp_component.profile));
#endif
#else
        return IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_ERR_INVALID_COMPONENT_ID); /* Please define ENABLE_IFX_LPWWD_HMMS */
#endif
    }
    else if (component_id == IFX_POST_PROCESS_IP_COMPONENT_LPWWD)
    {
        lpwwd_postprocess_top_struct* dPt;
#ifdef PROFILER
        ifx_cycle_profile_start(&(dPt->pp_component.profile));
#endif
        dPt = (lpwwd_postprocess_top_struct*) postprocess_container;
        if (dPt->pp_component.reset_flag)
        {/* one time reset */
            ifx_lpwwd_post_process_reset(postprocess_container);
            dPt->pp_component.reset_flag = false;
        }
        int32_t status = ifx_lpwwd_post_process(postprocess_container, in_probs, detection);
#ifdef PROFILER
        ifx_cycle_profile_stop(&(dPt->pp_component.profile));
#endif
        if (status != IFX_SP_ENH_SUCCESS)
        {
            return status;
        }
    }
    else
    {
        return IFX_SP_ENH_ERROR(component_id, IFX_SP_ENH_FEATURE_NOT_SUPPORTED);
    }
#endif
    return IFX_SP_ENH_SUCCESS;
}

void removePrefixSpaces(char* str1)
{
    char* str2;
    str2 = str1;
    while (isspace((int)(*str2))) str2++;
    if (str2 != str1) memmove(str1, str2, strlen(str2) + 1);
}
/**
 * \brief : ifx_class_convertion_init() is the API function to process inference classification id_string and initilize output_id_array
 *          before call ifx_class_convertion_for_pp() function.
 *
 * \param[in]  id_string                : Pointer to string decribing the inference classification indetifications which must contain
 *                                        "WWDtoken0" to "WWDtoken3", and "noise". Each ID should only occur once, and its position in the
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
#define PP_CLASS_WWDTOKEN0  (0)     /* Wake word token0 is the first of one keyword NN inference output */
#define PP_CLASS_WWDTOKEN1  (1)     /* Wake word token1 is the second of one keyword NN inference output */
#define PP_CLASS_WWDTOKEN2  (2)     /* Wake word token2 is the third of one keyword NN inference output */
#define PP_CLASS_WWDTOKEN3  (3)     /* Wake word token3 is the fourth of one keyword NN inference output */
int32_t ifx_class_convertion_init(const char* id_string, int* output_id_array, int size, int ww_tokens)
{
    int class_num = ww_tokens + 2; // 2 for noise and garbage
    if (id_string == NULL || output_id_array == NULL || size < class_num)
    {
        return IFX_SP_ENH_ERROR(IFX_POST_PROCESS_IP_COMPONENT_HMMS, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }

    uint16_t num_neg_token = 0, num_noise_token = 0, num_pos_token = 0;
    char output_id_string_cpy[MAX_CLASS_ID_LENGTH]; // for making copy of output_id_string since strtok will modify it
    int garbage_pos = ww_tokens; // garbage position in the output_id_array (right after token ends)
    int noise_pos = ww_tokens+1; // noise position in the output_id_array (right after garbage ends)
    strcpy(output_id_string_cpy, id_string);
    char* token = strtok(output_id_string_cpy, ",");
    int output_count = 0;
    while (token != NULL)
    {// parse through output id string
        if (output_count == size)
        {
            return IFX_SP_ENH_ERROR(IFX_POST_PROCESS_IP_COMPONENT_HMMS, IFX_SP_ENH_ERR_NUMBER_PARMS);
        }
        removePrefixSpaces(token);
        if (strncmp(token, "WWDtoken0", 9) == 0)
        {
            num_pos_token++;
            output_id_array[output_count++] = PP_CLASS_WWDTOKEN0;
        }
        else if (strncmp(token, "WWDtoken1", 9) == 0)
        {
            num_pos_token++;
            output_id_array[output_count++] = PP_CLASS_WWDTOKEN1;
        }
        else if (strncmp(token, "WWDtoken2", 9) == 0)
        {
            num_pos_token++;
            output_id_array[output_count++] = PP_CLASS_WWDTOKEN2;
        }
        else if (strncmp(token, "WWDtoken3", 9) == 0)
        {
            num_pos_token++;
            output_id_array[output_count++] = PP_CLASS_WWDTOKEN3;
        }
        else if (strncmp(token, "noise", 5) == 0)
        {
            num_noise_token++;
            output_id_array[output_count++] = noise_pos; // noise position in the output_id_array
        }
        else
        {// negative IDs will be combined as "garbage".
            num_neg_token++;
            output_id_array[output_count++] = garbage_pos; // garbage position in the output_id_array
        }
        token = strtok(NULL, ",");
    }
    if (output_count < size)
    {
        return IFX_SP_ENH_ERROR(IFX_POST_PROCESS_IP_COMPONENT_HMMS, IFX_SP_ENH_ERR_NUMBER_PARMS);
    }
    if (size - num_neg_token != class_num - 1 || num_noise_token != 1 || num_pos_token < 2 || num_pos_token > 4)
    {
        return IFX_SP_ENH_ERROR(IFX_POST_PROCESS_IP_COMPONENT_HMMS, IFX_SP_ENH_ERR_PARAM_RANGE);
    }
    return IFX_SP_ENH_SUCCESS;
}

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
int32_t ifx_class_convertion_for_pp(void* input_score, int data_type, void* output_score, int* id_array, int size, int ww_tokens)
{
    if (input_score  == NULL || output_score == NULL || id_array == NULL )
    {
        return IFX_SP_ENH_ERROR(IFX_POST_PROCESS_IP_COMPONENT_HMMS, IFX_SP_ENH_ERR_INVALID_ARGUMENT);
    }
    if (data_type != IFX_ML_DATA_FLOAT && data_type != IFX_ML_DATA_INT16 && data_type != IFX_ML_DATA_INT8)
    {
        return IFX_SP_ENH_ERROR(IFX_POST_PROCESS_IP_COMPONENT_HMMS, IFX_SP_ENH_ERR_PARAM);
    }

    int32_t status = IFX_SP_ENH_SUCCESS;
    int garbage_pos = ww_tokens; // garbage position in the output_id_array (right after token ends)
    {
        int total_neg_score_int = 0;
        int8_t *int8_ptr, *out_int8_ptr;
        int16_t* int16_ptr, * out_int16_ptr;
        float total_neg_score_f32 = 0;
        float *f32_ptr, *out_f32_ptr;

        // save total negative score and other scores
        if (data_type == IFX_ML_DATA_FLOAT)
        {
            f32_ptr = (float*)input_score;
            out_f32_ptr = (float*)output_score;
            for (int i = 0; i < size; i++)
            {
                if (id_array[i] == garbage_pos)
                {// add all negative scores
                    total_neg_score_f32 += f32_ptr[i];
                }
                else
                {
                    out_f32_ptr[id_array[i]] = f32_ptr[i];
                }
            }
            out_f32_ptr[garbage_pos] = total_neg_score_f32;
        }
        else if (data_type == IFX_ML_DATA_INT16)
        {
            int16_ptr = (int16_t*)input_score;
            out_int16_ptr = (int16_t*)output_score;
            for (int i = 0; i < size; i++)
            {
                if (id_array[i] == garbage_pos)
                {// add all negative scores
                    total_neg_score_int += int16_ptr[i];
                }
                else
                {
                    out_int16_ptr[id_array[i]] = int16_ptr[i];
                }
            }
            out_int16_ptr[garbage_pos] = total_neg_score_int;
        }
        else
        {
            int8_ptr = (int8_t*)input_score;
            out_int8_ptr = (int8_t*)output_score;
            for (int i = 0; i < size; i++)
            {
                if (id_array[i] == garbage_pos)
                {// add all negative scores
                    total_neg_score_int += int8_ptr[i];
                }
                else
                {
                    out_int8_ptr[id_array[i]] = int8_ptr[i];
                }
            }
            out_int8_ptr[garbage_pos] = total_neg_score_int;
        }
    }
    return status;
}
