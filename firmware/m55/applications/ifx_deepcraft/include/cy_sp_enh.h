/******************************************************************************
* File Name: cy_sp_enh.h
*
* Description: Speech enhancement module header file with APIs and data structures.
*
* Related Document: See README.md
*
*******************************************************************************
* (c) 2023, Infineon Technologies Company. All rights reserved.
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
#ifndef __CY_SP_ENH_H
#define __CY_SP_ENH_H

#if defined(__cplusplus)
extern "C" {
#endif

#include "cy_errors.h"
#include "ifx_sp_enh.h"

#ifdef ENABLE_AUDIO_VOICE_CORE_LOGS
#define CY_SP_PRINTF(f_, ...) printf((f_), ##__VA_ARGS__)
#else
#define CY_SP_PRINTF(...)
#endif

typedef enum
{
    IFX_SP_MEM_ID_HANDLE,
    IFX_SP_MEM_ID_SCRATCH_MEM,
    IFX_SP_MEM_ID_PERSISTENT_MEM,
    IFX_SP_MEM_ID_BF_PERSISTENT_MEM,
    IFX_SP_MEM_ID_DSNS_SOCMEM_PERSISTENT_MEM,
    IFX_SP_MEM_ID_DSES_SOCMEM_PERSISTENT_MEM,
    IFX_SP_MEM_ID_GDE_PERSISTENT_MEM
} ifx_sp_mem_id;

typedef cy_rslt_t(*cy_sp_alloc_memory_callback_t)(ifx_sp_mem_id mem_id,
    uint32_t size, void** buffer);

typedef cy_rslt_t(*cy_sp_free_memory_callback_t)(ifx_sp_mem_id mem_id,
    void* buffer);

extern cy_sp_alloc_memory_callback_t cy_sp_alloc_memory;
extern cy_sp_free_memory_callback_t cy_sp_free_memory;

typedef struct
{
    /* run-time control params structure */
    int32_t ns_gain_dB;
    int32_t ns_es_type;
    int32_t bf_aggressiveness;
    int32_t es_aggressiveness;
    int32_t bulk_delay_msec;
} cy_sp_enh_control_params;

typedef struct
{
    int32_t sampling_rate;      /* audio and voice data sampling rate in Hz */
    int32_t input_frame_size;   /* input data frame size in samples */
    int32_t num_mics;           /* number of microphones */
    int32_t tail_len_msec;      /* AEC tail length in milliseconds */
    int32_t hpf_enable;         /* enable high-pass filter */
    int32_t aec_enable;         /* enable acoustic echo cancellation */
    int32_t bf_enable;          /* enable beamforming */
    int32_t drvb_enable;        /* enable dereverberation */
    int32_t es_enable;          /* enable echo suppression */
    int32_t ns_enable;          /* enable noise suppression */
    int32_t dsns_enable;        /* enable deep subband noise suppression */
    int32_t dses_enable;        /* enable deep subband echo suppression */
    int32_t anasyn_enable;      /* enable analysis/synthesis */
    int32_t meter_enable;       /* enable meters */
    cy_sp_enh_control_params* control_params; /* pointer to run-time control params structure */
} cy_sp_enh_config_params;

typedef struct
{
    ifx_stc_sp_enh_info_t sp_enh_info;
    void* sp_enh_handle;
} cy_sp_enh_handle;

#ifdef ENABLE_AFE_MW_SUPPORT
cy_rslt_t cy_sp_enh_init(int32_t* afe_filter_settings, uint8_t *mw_settings,
                        uint32_t mw_settings_length, cy_sp_enh_handle** handle);
#else
cy_rslt_t cy_sp_enh_init(cy_sp_enh_config_params* config_params, cy_sp_enh_handle** handle);
#endif
cy_rslt_t cy_sp_enh_process(cy_sp_enh_handle* handle, int16_t* input1, int16_t* input2, int16_t* reference, int16_t* output, int16_t* ifx_output,
     int16_t* meter_ouput);
cy_rslt_t cy_sp_enh_deinit(cy_sp_enh_handle* handle);

cy_rslt_t cy_sp_enh_enable_disable_component(cy_sp_enh_handle* handle,
        ifx_sp_enh_ip_component_config_t component_name, bool enable);

cy_rslt_t cy_sp_enh_update_config_value(cy_sp_enh_handle* handle,
        ifx_sp_enh_ip_component_config_t component_name, int32_t* value);

cy_rslt_t cy_sp_enh_get_config_value(cy_sp_enh_handle* handle,
        ifx_sp_enh_ip_component_config_t component_name, void* value_struct_pt);

cy_rslt_t cy_sp_enh_get_component_status(cy_sp_enh_handle* handle,
        ifx_sp_enh_ip_component_config_t component_name, bool* enable);

cy_rslt_t cy_sp_enh_configure_dbg_out(cy_sp_enh_handle* handle,
        ifx_sp_enh_ip_component_config_t component_name, bool enable);

#if defined(__cplusplus)
}
#endif

#endif /* __CY_SP_ENH_H */

/* [] END OF FILE */
