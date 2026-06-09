/******************************************************************************
* File Name: ifx_sp_utils_priv.h
*
* Description: This file contains private interface for speech utilities
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
#ifndef __IFX_SP_UTILS_PRIV_H
#define __IFX_SP_UTILS_PRIV_H

#if defined(__cplusplus)
extern "C" {
#endif

/*******************************************************************************
* Include header file
*******************************************************************************/
#include <stdint.h>
#include <stdbool.h>
#include "ifx_sp_common.h"
#include "ifx_sp_common_priv.h"

/*******************************************************************************
* Macros
*******************************************************************************/
#define IFX_SP_LPWWD_VERSION_MAJOR            2
#define IFX_SP_LPWWD_VERSION_MINOR            8
#define IFX_SP_LPWWD_VERSION_PATCH            0
#define IFX_SP_LPWWD_VERSION                  280

/*******************************************************************************
* Speech utilities data type & defines
*******************************************************************************/
#define MAX_FBANK_SIZE  (40)            /* Maximum # of mel_banks; should be between (10-40), typical number: 40 */
#define MIN_FBANK_SIZE  (2)             /* Minimum # of mel_banks */

#define AGC_PARMS_SIZE  (7)             /* Number of AGC parameters */

#define MAX_WW_SERIES   (2)             /* Maximum number of WWD series in low power WWD */
#define MAX_WW_TOKENS   (4)             /* Maximum number of WWD tokens in low power WWD */
/*******************************************************************************
* Structures and enumerations
*******************************************************************************/
/* Internally defined LPWWD data structures is pointed by ifx_component_pt */
typedef struct component_top_struct_t
{
    /*@{*/
    void* ifx_component_pt;             /**<: Infineon component data structure pointer */
    ifx_scratch_mem_t scratch;          /**<: Point to scratch memory structure */
    char* persistent_pad;               /**<: pointer to allocated persistent memory */
    int32_t persistent_size;            /**<: allocated persistent memory size */
    bool reset_flag;                    /**<: one time reset flag, 1: reset; 0: do nothing */
    ifx_cycle_profile_t profile;        /**<: cycle profile structure */
    /*@}*/
} component_top_struct;

typedef struct sod_top_struct_t
{
    /*@{*/
    component_top_struct sod_component; /**<: Infineon SOD component structure */
    int16_t gapsetting;                 /**<: Minimum non-speech time before onset (0,100,200,300,400,500,1000) milliseconds, 400 = nominal */
    int16_t senslevel;                  /**<: Detection sensitivity (0- 32767) 0 = least sensitive, 32767 = most sensitive, 16384 = nominal */
    bool enable_flag;                   /**<: 1: detect SOD (i.e. normal operation); 0: don't detect, just update statistics */
    /*@}*/
} sod_top_struct;

typedef struct spectrogram_top_struct_t
{
    /*@{*/
    component_top_struct spctrg_component;   /**<: Infineon internal spectrogram tranformation component structure */
    uint16_t mel_sample_rate;                /**<: Sampling frequncey in Hz */
    uint16_t mel_frame_size;                 /**<: frame_size in samples (PCM samples) */
    uint16_t mel_frame_shift;                /**<: input data frame shift in samples */
    uint16_t mel_block_size;                 /**<: FFT block size */
    uint8_t mel_num_fbank_bins;              /**<: # of mel_banks (10-40), typical number: 40 */
    uint8_t mel_num_mfcc_coeffs;             /**<: # of mfcc coefs, for log_mel it equals to zero */
    /*@}*/
} spectrogram_top_struct;

typedef struct hmms_postprocess_top_struc_t
{
    /*@{*/
    component_top_struct pp_component;       /**<: Infineon hmms post processing component structure */
    int32_t fps;                             /**<: frame per second rate should be on the order of 20-50Hz */
    int32_t lookback_buffer_length;          /**<: lookback buffer length in seconds, Q12 */
    int32_t stacked_frame_delay;             /**<: stacked frame delay in second, Q12 */
    int32_t detection_threshold;             /**<: upper 16bit is detection_threshold, lower 16bit is set (update) flag */
    /*@}*/
} hmms_postprocess_top_struct;

typedef struct lpwwd_postprocess_top_struc_t
{
    /*@{*/
    component_top_struct pp_component;       /**<: Infineon lpwwd post processing component structure */
    uint8_t ww_series;                       /**<: number of WW series */
    uint8_t ww_tokens;                       /**<: number of WW tokens */
    uint16_t timeout_threshold;              /**<: total timeout threshold */
    /*@}*/
} lpwwd_postprocess_top_struct;

typedef struct preprocess_hpf_top_struct
{
    /*@{*/
    component_top_struct pre_proc_hpf;       /**<: Infineon internal pre processing HPF structure */
    uint32_t sample_rate;                    /**<: Sampling frequncey in Hz */
    uint32_t frame_size;                     /**<: frame_size in samples (PCM samples) */
    bool enable_flag;                        /**<: 1: enable HPF; 0: disable HPF (i.e. bypass) */
    /*@{*/
} preprocess_hpf_top_struct;

typedef struct preprocess_asrc_lpf_top_struct
{
    /*@{*/
    component_top_struct asrc_lpf;           /**<: Infineon internal pre processing ASRC LPF structure */
    uint32_t sample_rate;                    /**<: Sampling frequncey in Hz */
    uint32_t frame_size;                     /**<: frame_size in samples (PCM samples) */
    bool enable_flag;                        /**<: 1: enable ASRC LPF; 0: disable ASRC LPF (i.e. bypass) */
    /*@{*/
} preprocess_asrc_lpf_top_struct;

typedef struct itsi_feature_top_struct_t
{
    /*@{*/
    component_top_struct feature_extrct; /**<: Infineon ITSI feature (denoise) extraction component structure */
    /*@}*/
} itsi_feature_top_struct;

typedef struct itsi_am_top_struct_t
{
    /*@{*/
    component_top_struct am_predict; /**<: Infineon ITSI AM inference component structure */
    /*@}*/
} itsi_am_top_struct;

typedef struct itsi_dfwwd_top_struct_t
{
    /*@{*/
    component_top_struct dfwwd; /**<: Infineon ITSI data free WW detection component structure */
    float noactivty_timeout;    /**<: Maximum time in second between SOD and WW */
    /*@}*/
} itsi_dfwwd_top_struct;

typedef struct itsi_dfcmd_top_struct_t
{
    /*@{*/
    component_top_struct dfcmd; /**<: Infineon ITSI data free CMD detection component structure */
    float maxwwgap;             /**<: Maximum time in second allowed between the end of the WW and the beginning of the commands.
                                      If the start of a command has not yet been detected, the detection will time out. */
                                      /*@}*/
    float adj_factor;           /**<: Factor to decrease or increase maximum CMD duration until timeout. */
                                      /*@}*/
} itsi_dfcmd_top_struct;

typedef struct postprocess_agc_top_struct
{
    /*@{*/
    component_top_struct ifx_agc;            /**<: Infineon internal pre processing AGC structure */
    uint32_t sample_rate;                    /**<: Sampling frequncey in Hz */
    uint32_t frame_size;                     /**<: frame_size in samples (PCM samples) */
    uint32_t agc_mode;                       /**<: audio source type: 0: speech mode, 1: music mode */
    float agc_peak_db;                       /**<: User defined desired agc output peak db */
    bool enable_flag;                        /**<: 1: enable AGC; 0: disable AGC (i.e. bypass) */
    /*@{*/
} postprocess_agc_top_struct;

/**
 * void initSOD(void *SODmemPt, int16_t onsetgap, int16_t sensitivity)
 *
 * Purpose - initialize the SOD
 *
 * Input-
 *    *SODmemPt   - pointer to allocated memory block
 *    onsetgap    - the minimum non-speech time before onset (0,100,200,300,400,500,1000) milliseconds), 400 = nominal
 *    sensitivity - the detection sensitivity (0- 32767) 0 = least sensitive, 32767 = most sensitive, 16384 = nominal
 * Output-
 *    Initialized memory
 *
 */
void initSOD(void* SODmemPt, int16_t onsetgap, int16_t sensitivity);

/**
 * int16_t SOD(int16_t *in, void *SODmemPt)
 *
 * Purpose - Speech Onset Detection
 *
 * Input-
 *    *in   - pointer to input buffer of length FRAME_SIZE_16K+MAX_FIR_ORDER, with *in containing MAX_FIR_ORDER preceding.  Hence in[-MAX_FIR_ORDER] is valid.
 *            The SOD will overwrite the samples in this buffer.
 *    *SODmemPt  - pointer to initialized SOD memory
 *    *scratchPt - scratch memory pointer
 *
 * Output-
 *    none
 *
 * Return - 0 = no SOD, 1 = SOD
 */
int16_t SOD(int16_t* in, void* SODmemPt, ifx_scratch_mem_t* scratchPt);

int SOD_calculate_persistent_mem_size();

int SOD_calculate_scratch_mem_size(int frame_size);

/**
 * \brief : speech_utils_getMem() is the API function to estimate memory needed by ip_id component block.
 *
 *
 * \param[in]  ip_prms_buffer   : Configuration parameter buffer of the given ip_id component block
 *                              : For SOD, it contains SOD configuration parameter: [configuration version, sampling_rate(Hz),
 *                              : input frame_size (samples), SOD component ID, number of following parameters,
 *                              : GapSetting (0,100,200,300,400,500,1000)ms, SensLevel (0-32767)]
 *                              : For preprocess, it contains preprocess configuration parameter: [configuration version,
 *                              : sampling_rate(Hz), input frame size (samples), compenent ID, number of following parameters,
 *                              : frame shift (samples), mel_banks, dct_coefs (set to 0 for LOG MEL)]
 *                              : For postprocess, its contains to be defined
 * \param[in]  ip_id            : The given IP component block's id number
 * \param[out] mem_infoPt       : Pointer to mem_info_t structure, output scratch and persistent memory sizes when success
 * \return                      : Return 0 when success, otherwise return error code
 *                                IFX_SP_ENH_ERR_INVALID_ARGUMENT if input or output argument is invalid
 *                                or error code from specific ifx audio & voice enhancement proces module.
 *                                Please note error code is 8bit LSB, line number where the error happened in
 *                                code is in 16bit MSB, and its IP component index if applicable will be at
 *                                bit 8 to 15 in the combined 32bit return value.
*/
int32_t speech_utils_getMem(int32_t* ip_prms_buffer, int32_t ip_id, mem_info_t* mem_infoPt);

/**
 * \brief : speech_utils_sod_init() is the API function to initilize SOD given user options.
 *
 *
 * \param[out]  sod_container       : Pointer to SOD container that contains state memory
 * \param[in]   sod_mem_infoPt      : Pointer to SOD's mem_info_t struct
 * \param[in]   sod_prms_buffer     : Configuration parameter buffer of the given ip_id component block
 *                                  : For SOD, it contains SOD configuration parameter: [configuration version, sampling_rate(Hz),
 *                                  : frame_size (samples), SOD component ID, number of following parameters,
 *                                  : GapSetting (0,100,200,300,400,500,1000)ms, SensLevel (0-32767)]
 *                                  : Note - at this time, frame_size=160, sampling_rate=16000 only are valid
 * \return                          : Return 0 when success, otherwise return error code
 *                                    IFX_SP_ENH_ERR_INVALID_ARGUMENT if input or output argument is invalid
 *                                    or error code from specific ifx audio & voice enhancement proces module.
 *                                    Please note error code is 8bit LSB, line number where the error happened in
 *                                    code is in 16bit MSB, and its IP component index if applicable will be at
 *                                    bit 8 to 15 in the combined 32bit return value.
*/
int32_t speech_utils_sod_init(int32_t* sod_prms_buffer, void** sod_container, mem_info_t* sod_mem_infoPt);

int fixed_lpwwd_post_hmms_calculate_persistent_mem_size(); /* HMMS post process internal persistent memory size */

int ifx_lpwwd_post_process_calculate_persistent_mem_size(); /* LPWWD post process internal persistent memory size */

uint32_t ifx_lpwwd_post_process_init(void **ifx_container, mem_info_t* mem_infoPt, IFX_PPINPUT_DATA_TYPE_T *prob_threshold, uint8_t *count_threshold,
         uint8_t *gap_threshold, uint8_t ww_series, uint8_t ww_tokens, uint16_t timeout_threshold, uint16_t garbage_count_threshold, uint16_t garbage_count_2nd_threshold);

/***************************************************************************************
* Function: fixed_lpwwd_post_get_float_score(void *postprocPt)
*
* Purpose:  LPWWD post processing obtain the normalized log likelihood score used in
*           final decision.
*
*
* Inputs:
*   void *postprocPt    :  the postprocessing hmm memory pointer which pointing to PPHMM_struct * pphmmmem
*
* Outputs:
*
* Return:   float
*
****************************************************************************************/
float fixed_lpwwd_post_get_float_score(void* postprocPt);

/***************************************************************************************
* Function: fixed_lpwwd_post_get_threshold(void *postprocPt)
*
* Purpose:  LPWWD post processing obtain the threshold used in final decision
*
*
* Inputs:
*   void *postprocPt    :  the postprocessing hmm memory pointer which pointing to PPHMM_struct * pphmmmem
*
* Outputs:
*
* Return:   int16_t (Q12)
*
****************************************************************************************/
int16_t fixed_lpwwd_post_get_threshold(void* postprocPt);

/***************************************************************************************
* Function: fixed_reset_lpwwd_post(void *postprocPt)
*
* Purpose:  Reset memory to initial values in preparation for post processing of a new
*           WW candidate.
*
*           init_lpwwd_post() must be called once before any WW candidates are processed.
*           Subsequent WW candidates only need this reset function.
*
* Inputs:
*   void *postprocPt    : the postprocessing hmm memory pointer which pointing to PPHMM_struct * pphmmmem
*
* Outputs:  * ppmem            :  reset memory
*
* Return:   void()                   :
*
****************************************************************************************/
void fixed_reset_lpwwd_post(void* postprocPt);

/***************************************************************************************
* Function: fixed_init_lpwwd_post(struct PP_struct *ppmem, int method, int16_t *ppkwmodel,
*                           int16_t *ppgmodel)
*
* Purpose:  Read the supplied Post Processing model(s) and use to initialize the memory
*           containing the hmm models.  Call reset_lpwwd_post() to set the dynamic
*           memory.
*
*           init_lpwwd_post() must be called once before any WW candidates are processed.
*           Subsequent WW candidates only need this reset function.
*
* Inputs:
*   struct PP_struct * ppmem   : the postprocessing hmm mem
*   int16_t *ppkwmodel         : the Post Processing keyword model
*
*                                      Q   - the number of states
*                                      Dim - number of features/NNoutputs/tokens
*                                      TH  - threshold for detection
*                                      Qend - end state for detection
*                                      minKWL - min keyword length (in units of input frames)
*                                      maxKWL - max keyword length (in units of input frames)
*                                      TO - TimeOut length when sequence is rejected
*                                      transP - log transition probabilities, ordered p(Q(i)->Q(i), p(Q_i->Q_i+1), i=1..Q
*                                      stateBank - the gmm's for each hmm state
*
*                                                   gmm[0] = (dim)*log(2*pi)+ log(det(cov))
*                                                   gmm[1] = mu(1)
*                                                   gmm[2] = 1/var(1)
*                                                   gmm[3] = mu(2)
*                                                   gmm[4] = 1/var(2)
*                                                       .....
*                                                   gmm[]  = mu(dim)
*                                                   gmm[]  = 1/var(dim)
*
*   int16_t *ppgmodel      : the Post Processing garbage model
*   int16_t *pprejectmodel : the Post Processing rejection model
*
* Outputs:  * ppmem        :  initialized and reset memory
*
*
****************************************************************************************/
#if HMMS_CONFIG_MODEL
int fixed_init_lpwwd_post(void* postprocPt, int16_t lookbackbuffertime, int16_t nnstackedframedelay, int16_t PPth /* Q12 */, int16_t SetPPthFLAG);
#else
int fixed_init_lpwwd_post(void* postprocPt, int16_t* ppkwmodel, int16_t* ppgmodel, int16_t* ppnmodel, int16_t* pprejectmodel, int16_t lookbackbuffertime, int16_t nnstackedframedelay, int16_t PPth /* Q12 */, int16_t SetPPthFLAG);
#endif

/***************************************************************************************
* Function: fixed_lpwwd_post(void *postprocPt, int16_t *feature)
*
* Purpose:  LPWWD post processing main function
*
*           Analyze posterior probabilities for each output class of the the NN, and make
*           a decision on the presence or absence of the WW
*
* Inputs:
*   void *postprocPt    : the postprocessing hmm memory pointer which pointing to PPHMM_struct * pphmmmem
*   int16_t *feature    : posterior probabilities feature vector for the current frame.
*
* Outputs:
*
* Return:   int()                   : 1 = WW Detection
*                                    -1 = WW Rejection
*                                     0 = undecided (continue with further frames)
*
****************************************************************************************/
int fixed_lpwwd_post(void* postprocPt, int16_t* feature);

int spectrogram_calculate_spctrg_component_size();

/***********************************************************************
* Function: mel_features_fix_init(void* dPt, int persistent_count)
*
* Purpose:  This function initialize fixed-point feature extraction
*
*
* Input:   dPt               - is the data container structure pointer
*          persistent_count  - is persistent memory start size
*
* Outputs: NA
*
* Return: void
*
***********************************************************************/
void mel_features_fix_init(void* dPt, int persistent_count);

/***********************************************************************
* Function: mel_features_fix_compute(spectrogram_top_struct* topdPt, const int16_t* audio_data, int16_t* features)
*
* Purpose:  This function serves as fixed-point feature extraction
*
*
* Input:   topdPt       - is the data container structure pointer
*          audio_data   - is the 16-bit audio sample buffer
*
* Outputs: features     - is the 8-bit or 16-bit fixed-point feature ouput and Q = MFCC_Q or MEL_LOG_Q
*          out_q        - is the output fixed-point Q value pointer
*
* Return: true  - Algorithm completed.
*         false - Algorithm exist ealier.
*
***********************************************************************/
bool mel_features_fix_compute(spectrogram_top_struct* topdPt, const IFX_SP_DATA_TYPE_T* audio_data, IFX_FE_DATA_TYPE_T* features, int32_t* out_q);

/***********************************************************************
* Function: spectrogram_calculate_persistent_mem_size(uint16_t mel_sample_rate, uint16_t mel_block_size, uint16_t mel_num_fbank_bins, uint16_t mel_num_mfcc_coeffs)
*
* Purpose:  This function calculate persistent memory size needed for
*           fixed-point feature extraction
*
*
* Input:   mel_sample_rate     - is the sampling rate
*          mel_block_size      - is FFT block size
*          mel_num_fbank_bins  - is the number of mel filter bank bins
*          mel_num_mfcc_coeffs - is the number of MFCC coefficeints, set to 0 for LOG MEL.
*
* Outputs: NA
*
* Return: persistent memory size
*
***********************************************************************/
int spectrogram_calculate_persistent_mem_size(uint16_t mel_sample_rate, uint16_t mel_block_size, uint16_t mel_num_fbank_bins, uint16_t mel_num_mfcc_coeffs);

/***********************************************************************
* Function: spectrogram_calculate_scratch_mem_size(uint16_t mel_block_size, uint16_t mel_num_fbank_bins)
*
* Purpose:  This function calculate scratch memory size needed for
*           fixed-point feature extraction
*
*
* Input:   mel_block_size  - is FFT block size
*          mel_num_fbank_bins  - is the number of mel filter bank bins
*
* Outputs: NA
*
* Return: scratch memory size
*
***********************************************************************/
int spectrogram_calculate_scratch_mem_size(uint16_t mel_block_size, uint16_t mel_num_fbank_bins);

/***************************************************************************************
* Function: afe_hpf_calculate_persistent_mem_size(void)
*
* Purpose:  This function calculate persistent memory size needed for afe hpf
*
****************************************************************************************/
int afe_hpf_calculate_persistent_mem_size();

/***************************************************************************************
* Function: ifx_afe_hpf_init(void* afeHpfTopPt)
*
* Purpose:  This function init afe hpf process
*
****************************************************************************************/
int32_t ifx_afe_hpf_init(void* afeHpfTopPt);

/***************************************************************************************
* Function: ifx_afe_hpf(void* afeHpfTopPt, int16_t* inbuf1, int16_t* inbuf2, int16_t* outbuf1, int16_t* outbuf2)
*
* Purpose:  This function run frame by frame afe hpf process
*
****************************************************************************************/
void ifx_afe_hpf(void* afeHpfTopPt, int16_t* inbuf1, int16_t* inbuf2, int16_t* outbuf1, int16_t* outbuf2);

/***************************************************************************************
* Function: asrc_lpf_calculate_persistent_mem_size(void)
*
* Purpose:  This function calculate persistent memory size needed for afe hpf
*
****************************************************************************************/
int asrc_lpf_calculate_persistent_mem_size();

/***************************************************************************************
* Function: ifx_asrc_lpf_init(void* asrcLpfTopPt)
*
* Purpose:  This function init afe hpf process
*
****************************************************************************************/
int32_t ifx_asrc_lpf_init(void* asrcLpfTopPt);

/***************************************************************************************
* Function: ifx_asrc_lpf_reset(void* lpf_container)
*
* Purpose:  This function init afe hpf process
*
****************************************************************************************/
uint32_t ifx_asrc_lpf_reset(void* lpf_container);

/***************************************************************************************
* Function: ifx_asrc_lpf(void* asrcLpfTopPt, int16_t* inbuf1, int16_t* inbuf2, int16_t* outbuf1, int16_t* outbuf2)
*
* Purpose:  This function run frame by frame afe hpf process
*
****************************************************************************************/
void ifx_asrc_lpf(void* asrcLpfTopPt, int16_t* inbuf1, int16_t* inbuf2, int16_t* outbuf1, int16_t* outbuf2);


/***************************************************************************************
* Function: itsi_feature_process_calculate_scratch_mem_size(void)
*
* Purpose:  This function calculate scratch memory size needed for itsi feature
*
****************************************************************************************/
int itsi_feature_process_calculate_scratch_mem_size(void);

/***************************************************************************************
* Function: itsi_feature_process_calculate_persistent_mem_size(void)
*
* Purpose:  This function calculate persistent memory size needed for itsi feature
*
****************************************************************************************/
int itsi_feature_process_calculate_persistent_mem_size(void);

/***************************************************************************************
* Function: dfww_calculate_persistent_mem_size(void)
*
* Purpose:  This function calculate persistent memory size needed for dfww detection
*
****************************************************************************************/
uint32_t dfww_calculate_persistent_mem_size(void);

/***************************************************************************************
* Function: dfww_calculate_scratch_mem_size(void)
*
* Purpose:  This function calculate scratch memory size needed for dfww detection
*
****************************************************************************************/
uint32_t dfww_calculate_scratch_mem_size(void);

/***************************************************************************************
* Function: dfcmd_calculate_persistent_mem_size(void)
*
* Purpose:  This function calculate persistent memory size needed for dfcmd detection
*
****************************************************************************************/
uint32_t dfcmd_calculate_persistent_mem_size(void);

/***************************************************************************************
* Function: dfcmd_calculate_scratch_mem_size(void)
*
* Purpose:  This function calculate scratch memory size needed for dfcmd detection
*
****************************************************************************************/
uint32_t dfcmd_calculate_scratch_mem_size(void);

/***************************************************************************************
* Function: agc_calculate_scratch_mem_size(void)
*
* Purpose:  This function calculate scratch memory size needed for post process AGC
*
****************************************************************************************/
uint32_t agc_calculate_scratch_mem_size(void);

/***************************************************************************************
* Function: agc_calculate_persistent_mem_size(void)
*
* Purpose:  This function calculate persistent memory size needed for post process AGC
*
****************************************************************************************/
uint32_t agc_calculate_persistent_mem_size(void);

/***************************************************************************************
* Function: ifx_agc_init(void* agc_container, int16_t *agcParms)
*
* Purpose:  This function initialize post process AGC
*
****************************************************************************************/
uint32_t ifx_agc_init(void* agc_container, int16_t *agcParms);

/***************************************************************************************
* Function: ifx_agc_reset(void* agc_container)
*
* Purpose:  This function reset state in post process AGC
*
****************************************************************************************/
uint32_t ifx_agc_reset(void* agc_container);

/***************************************************************************************
* Function: ifx_agc(void* agc_container, int16_t* inbuf, int16_t* outbuf)
*
* Purpose:  This is post process AGC function
*
****************************************************************************************/
uint32_t ifx_agc(void* agc_container, int16_t* inbuf, int16_t* outbuf);

/***************************************************************************************
* Function: speech_utils_itsi_get_parm(void* container, int32_t ip_id, float* parm)
*
* Purpose:  This function get parameter coresponding to itsi component ID from its container
*
****************************************************************************************/
uint32_t speech_utils_itsi_get_parm(void* container, int32_t ip_id, float* parm);

/***************************************************************************************
* Function: speech_utils_itsi_set_parm(void* container, int32_t ip_id, float parm)
*
* Purpose:  This function set parameter coresponding to itsi component ID from its container
*
****************************************************************************************/
uint32_t speech_utils_itsi_set_parm(void* container, int32_t ip_id, float parm);

#if defined(__cplusplus)
}
#endif

#endif /*__IFX_SP_UTILS_PRIV_H */

/* [] END OF FILE */