/******************************************************************************
* File Name: ifx_sp_enh_priv.h
*
* Description: This file contains private interface for HP speech enhancement app
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
* Include guard
*******************************************************************************/
#ifndef __IFX_SP_ENH_PRIV_H
#define __IFX_SP_ENH_PRIV_H

#if defined(__cplusplus)
extern "C" {
#endif

/*******************************************************************************
* Include header file
*******************************************************************************/
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include "ifx_sp_common.h"
#include "ifx_sp_common_priv.h"
#include "ifx_sp_enh.h"

/*******************************************************************************
* Global and Compile-time flags
*******************************************************************************/

/*******************************************************************************
* Constants and Macros
*******************************************************************************/
#define IFX_SP_ENH_VERSION_MAJOR            1
#define IFX_SP_ENH_VERSION_MINOR            9
#define IFX_SP_ENH_VERSION_PATCH            9
#define IFX_SP_ENH_VERSION                  199

#define OVERLAP_SIZE (BLOCK_SIZE - HP_SP_ENH_FRAME_SAMPLES)
#define NUM_SHIFTS (2)                          // number of bit shifts
#define SKIP_SIZE (1<<NUM_SHIFTS)               // number of freqency bins to skip during processing
#define RFFT ((FFT_SIZE >> (1+NUM_SHIFTS))+1)   // reduced number of FFT bins to be processed

#define MAX_NUM_SYNTHESIS (IFX_PRE_POST_IP_COMPONENT_START_ID - 10)   // 6 for now, When AEC input/output are in frequency domain will + MAX_NUM_MICS
#define EXTRA_ANALYSIS (3)

#define BULK_DELAY_COMP_ADJUST_MSEC (2)    // bulk delay compensation adjustment amount to keep AEC operational in case delay is over-estimated

#define MAX_MIC_DISTANCE_COMBINED_DSNS    (30) // max mic distance (mm) to allow combined two channel DSNS

/*******************************************************************************
* extern variables
******************************************************************************/

/*******************************************************************************
* Structures and enumerations
******************************************************************************/
typedef enum
{
    IFX_HPSE_DATA_UNKNOWN = 0u,    /**< Unknown data type */
    IFX_HPSE_DATA_INT8 = 1u,       /**< 8-bit fixed-point */
    IFX_HPSE_DATA_INT16 = 2u,      /**< 16-bit fixed-point */
    IFX_HPSE_DATA_FLOAT = 3u,      /**< 32-bit float-point */
} cy_en_ml_data_type_t;

typedef enum
{/* set as bit flag */
    IFX_NS = 0,     // traditional noise suppression
    IFX_DSNS = 0x1, // deep subband noise suppression
    IFX_DSES = 0x2, // deep subband echo suppression
    IFX_DSXS_BITS = 0x3,
    IFX_ES = 0x4,   // traditional echo suppression
    IFX_ES_BITS = 0x6,
    IFX_NS_ES_BITS = 0x7
} cy_en_ns_type;

struct COEFF_HEADER
{
    int32_t size;
    int16_t type;
    int16_t component_id;
};

typedef struct {
    IFX_SP_DATA_TYPE_T* buffer_pt;
    int32_t buffer_size;
    int32_t write_idx;
    int32_t read_idx;
} circular_buffer_struct_t;

typedef struct
{
    void* coeff_struct;     /* point to coeff structure */
    void* state_struct[MAX_NUM_SYNTHESIS];    /* point to state structure array */
    void* settings_struct;  /* point to settings structure */
    uint32_t n_states;      /* size of state structure array */
    int32_t component_typeb; /* component id */
#if IFX_SP_FIXED_POINT
    int8_t sQ;              /* state Q value */
    int8_t coeffQ;          /* coefficient Q value */
#endif
    ifx_cycle_profile_t profile;
} component_struct_t;

typedef struct sp_enh_struct_t
{
    int32_t sampling_rate;
    int32_t frame_size;
    int32_t num_mics;
    int32_t num_monitor_components;
    int32_t monitor_component_id[MAX_NUM_MONITOR_COMPONENT];  /* actuall valid items in the array is determined by num_monitor_channels */
    int32_t block_size;
    int32_t overlap_size;
    int32_t fft_size;
    int32_t kfft_size;
    int32_t skip_size;
    int32_t rfft_size;
    int32_t n_components;

    int32_t ns_es_type;

    circular_buffer_struct_t farend_delay_buffer_struct;   /* aec reference signal bulk and/or group delay buffer structure */

    void* trans_struct;         /* analysis/synthesis tranform structure */
    void* table_struct;         /* NS lookup tables structure pointer */

    ifx_scratch_mem_t scratch;                   /* Scratch memory structure */
    complex_float* analysis_out_pt[MAX_NUM_MICS]; /* subband per mic shared input/output analysis scratch buffer pointers */
    complex_float* subband_out_pt;               /* subband shared input/output scratch buffer pointer */
    complex_float* subband_dses_ref_pt;          /* subband dses reference scratch buffer pointer */
    complex_float* subband_post_aec_pt;          /* subband post aec scratch buffer pointer */
    complex_float* subband_farend_pt;            /* subband farend (aec reference) scratch buffer pointer */
    float* dses_gain_mask;                       /* subband dses gain mask scratch buffer pointer */
    float* dsns_gain_mask;                       /* subband dsns gain mask scratch buffer pointer */
    IFX_SP_DATA_TYPE_T* dses_ref_pt;             /* dses reqiured aec reference (farend or echo estimate) scratch buffer pointer */
    IFX_SP_DATA_TYPE_T* aec_farend_pt;           /* dses nlp reqiured aec farend scratch buffer pointer */
    IFX_SP_DATA_TYPE_T* delay_farend_pt;         /* delayed buffer of aec farend persistent buffer pointer */
    IFX_SP_DATA_TYPE_T* main_mic_pt;             /* dses nlp reqiured main mic (pre-AFE) audio input scratch buffer pointer */

    char* persistent_pt;        /* pointer to allocated persistent memory */
    int32_t persistent_size;    /* cumulated allocated persistent memory size */

    uint32_t enable_flag;       /* each bit control enable/disable one component with bit 0 controls component 0. when set component is configured */
    uint32_t reset_flag;        /* each bit control reset one component with bit 0 controls component 0. when set component state will be rest */
    uint32_t active_flag;       /* each bit control one component run time active or not with bit 0 controls component 0. when set component will active i.e. ON */
    uint32_t monitor_flag;      /* each bit control one component monitor ouput ON or OFF */

    component_struct_t* l;      /* component array */
#if IFX_SP_FIXED_POINT
    int8_t data_q;              /* q factor of current component's input data */
#endif
    uint8_t component;          /* component index */
    uint8_t synthesis_proc_ind; /* synthesis processing order index */

    ifx_cycle_profile_t profile;    /* cycle profile structure */
} sp_enh_struct;

/*******************************************************************************
* Function prototypes of all IP components
******************************************************************************/
uint32_t ifx_dsns_reset(sp_enh_struct* dPt, component_struct_t* lPt);
int32_t ifx_dsns_init(sp_enh_struct* dPt, component_struct_t* lPt, persistent_mem_info_t socmem);
uint32_t ifx_dsns_free(sp_enh_struct *dPt, component_struct_t* lPt);
int32_t ifx_dsns_process(complex_float* subband_frame, complex_float* subband_frame1, sp_enh_struct* dPt, component_struct_t* lPt, int32_t target_attn_gain_dB, bool pp_flag);
uint32_t ifx_dsns_get_persistent_mem_size(int32_t* persist_mem_size);
uint32_t ifx_dsns_get_scratch_mem_size();
int32_t ifx_dsns_get_state_mem_size();
uint32_t ifx_dsns_get_socmem_persistent_mem_size();
int32_t combined_post_process(complex_float* out_pt, float* dsns_gain_mask, float* dses_gain_mask, int32_t size, int32_t target_attn_gain_dB, int32_t max_attn_gain_dB);

/* DSES function prototype */
uint32_t ifx_dses_reset(component_struct_t* lPt);
int32_t ifx_dses_init(sp_enh_struct* dPt, component_struct_t* lPt, persistent_mem_info_t socmem);
uint32_t ifx_dses_free(component_struct_t* lPt);
int32_t ifx_dses_process(complex_float* subband_frame, sp_enh_struct* dPt, component_struct_t* lPt, float* dsns_gain_mask, bool pp_flag);
uint32_t ifx_dses_get_persist_mem_size(int32_t* persist_mem_size);
uint32_t ifx_dses_get_scratch_mem_size();
uint32_t ifx_dses_get_coeff_mem_size();
uint32_t ifx_dses_get_socmem_persistent_mem_size();
int32_t ifx_dses_set_gain(int32_t aggressiveness);
uint32_t ifx_dses_nlp_get_state_mem_size();
int32_t ifx_dses_gde_init(component_struct_t* lPt, ifx_scratch_mem_t* scratch_ptr, bool reset_flag);
int32_t ifx_dses_gde_process(component_struct_t* lPt, int16_t* x, int16_t* y, uint32_t* delay);
uint32_t ifx_gde_get_state_mem_size();
uint32_t ifx_gde_get_coeff_mem_size();
uint32_t ifx_gde_get_scratch_mem_size();
uint32_t ifx_gde_get_delay_farend_persistent_mem_size();

int32_t ifx_ns_get_coeff_mem_size();
int32_t ifx_ns_get_state_mem_size();
int32_t ifx_ns_get_table_mem_size();
uint32_t ifx_ns_get_scratch_memory_size(uint32_t frame_size, uint32_t Kfft_size, uint32_t Rfft_size);
int32_t ifx_ns_init(ifx_scratch_mem_t* scratch_ptr, component_struct_t* lPt,
    uint32_t sample_rate, uint32_t frame_size, uint32_t kfft_size, uint32_t skip_size, uint32_t rfft_size, bool reset_only);
int32_t ifx_ns_process(complex_float* Y, void* tblePt, component_struct_t* lPt, float target_attn_gain_dB);
int32_t ifx_ns_free(void);
int32_t ifx_table_init(void* tblePt);

int32_t ifx_hpf_get_coeff_mem_size();
int32_t ifx_hpf_get_state_mem_size();
int32_t ifx_hpf_ceff_init(float* flt_idx, int num_coeff);
int32_t ifx_hpf_init(ifx_scratch_mem_t* scratch_ptr, component_struct_t* lPt, uint32_t frame_size, bool reset_only);
int32_t ifx_hpf_free(void);
int32_t ifx_hpf_process(int16_t* y, int seq_num, component_struct_t* lPt, int32_t gain_dB);

int32_t ifx_bf_get_coeff_mem_size();
int32_t ifx_bf_get_state_mem_size();
int32_t ifx_bf_get_cofigurable_coeff_size(uint32_t num_mics, uint32_t num_fft_bins, uint32_t num_beams);
uint32_t ifx_bf_configure_coeff_mem(sp_enh_struct* dPt, component_struct_t* lPt, persistent_mem_info_t bf_pm, uint32_t num_mics, uint32_t kfft_size, uint32_t num_beams);
int32_t ifx_bf_ceff_init(sp_enh_struct* dPt, float* flt_idx, int configed_beams);
int32_t ifx_bf_init(component_struct_t* lPt, uint32_t sample_rate, uint32_t frame_size, uint32_t num_mics, uint32_t num_fft_bins, uint32_t num_bands, uint32_t num_beams);
int32_t ifx_bf_free(void);
int32_t ifx_bf_process(component_struct_t* lPt, complex_float* Y, complex_float* X1, complex_float* X2);
void ifx_bf_set_weights(component_struct_t* lPt, int32_t aggressiveness);

int32_t ifx_drvb_get_scratch_memory_size();
int32_t ifx_drvb_get_persistent_memory_size();
int32_t ifx_drvb_get_persistent_struc_size();
int32_t ifx_drvb_get_prm_struc_size();
int32_t ifx_drvb_init(component_struct_t* lPt, ifx_scratch_mem_t* scratch_ptr, bool reset);
int32_t ifx_drvb_process(complex_float* in_out_pt, component_struct_t* lPt);

int ifx_meter_get_coeff_mem_size();
int ifx_meter_get_state_mem_size();
int ifx_meter_init(ifx_scratch_mem_t* scratch_ptr, component_struct_t* lPt, uint32_t sampling_rate, uint32_t frame_size);
void ifx_meter_process(int16_t* y, int seq_num, component_struct_t* lPt, int16_t* x);

int ifx_anasyn_get_coeff_mem_size();
int ifx_anasyn_get_state_mem_size();
int ifx_transform_get_trans_struc_size();
void ifx_transform_configure_persistent_mem(sp_enh_struct* dPt);
int transform_init(ifx_scratch_mem_t* scratch_ptr, void* transPt, int bl_sz, int fft_sz, int frm_sz, int ovlp_sz);
int transform_free(void);
int analysis_wloaFFT(complex_float* out_block, void* transPt, void* statePt, int16_t* in_frame);
int synthesis_wloaFFT(int16_t* out_frame, void* transPt, void* statePt, complex_float* in_block);
int ifx_anasyn_init(component_struct_t* lPt, float* delay_buffer, uint32_t block_size, uint32_t buffer_size, bool reset_only);
int ifx_ana_ceff_init(float* flt_idx, int num_coeff);
int ifx_syn_ceff_init(float* flt_idx, int num_coeff);

/* Caculate echo state required memory in bytes */
void ifx_echo_state_get_memory(int frame_size, int filter_length, int nb_mic, int nb_speakers, long* persistenet_size, long* scratch_size);
int32_t get_aec_coeff_struct_size();
int32_t get_aec_state_struct_size();
void* get_aec_state();
void echo_free();
int32_t ifx_aec_init(sp_enh_struct* dPt, component_struct_t* lPt, uint32_t frame_size);
void ifx_aec_reset(component_struct_t* lPt, int32_t frame_size);
int32_t ifx_aec_process(int16_t* y, int16_t* x, int32_t frame_size, void* state_pt);
int32_t ifx_aec_get_echo_reference(int16_t* out, void* state_pt);
int32_t convert_ms_to_samples_per_frame_size(int32_t sample_rate, int32_t frame_size, int32_t msec);
int32_t convert_ms_to_samples(int32_t sample_rate, int32_t msec);

/* Caculate preprocess state required memory in bytes */
int ifx_preprocess_state_get_memory(int frame_size, int nb_bands);
int32_t get_es_coeff_struct_size();
int32_t get_es_state_struct_size();
int32_t ifx_es_init(sp_enh_struct* dPt, component_struct_t* lPt, int32_t frame_size);
void ifx_es_reset(component_struct_t* lPt, int32_t frame_size, int32_t sampling_rate);
int32_t ifx_es_process(int16_t* y, void* state_pt);
void ifx_es_set_gain(void* state_pt, int32_t aggressiveness);

int32_t read_component_coeff(uint8_t* fn_coeffs, int32_t* byte_count, ifx_stc_sp_enh_info_t* mdl_infoPt, sp_enh_struct* dPt);

int init_component_structure_memory(sp_enh_struct* dPt, int32_t component_id, ifx_stc_sp_enh_info_t* mdl_infoPt, int32_t num_instances,
    int32_t coeff_struct_size, int32_t state_struct_size, int32_t settings_structure_size);

void init_delay_buffer(circular_buffer_struct_t* circular_buffer_struct, IFX_SP_DATA_TYPE_T* buffer_pt, int32_t buffer_size, bool reset);

void delay_compensation(circular_buffer_struct_t* circular_buffer_struct, IFX_SP_DATA_TYPE_T* data_frame, int32_t frame_size, int32_t delay);

void write_to_delay_buffer(circular_buffer_struct_t* circular_buffer_struct, IFX_SP_DATA_TYPE_T* data_frame, int32_t frame_size);

void read_from_delay_buffer(circular_buffer_struct_t* circular_buffer_struct, IFX_SP_DATA_TYPE_T* data_frame, int32_t frame_size, int32_t delay);

#if defined(__cplusplus)
}
#endif

#endif /*__IFX_SP_ENH_PRIV_H */

/* [] END OF FILE */
