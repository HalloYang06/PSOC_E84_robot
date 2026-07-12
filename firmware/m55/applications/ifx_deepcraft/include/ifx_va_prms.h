/******************************************************************************
* File Name: ifx_va_prms.h
*
* Description: This file contains Voice Assitance (VA) prameter constants for Infineon VA header
*
*
*******************************************************************************
* (c) 2024, Infineon Technologies Company. All rights reserved.
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
#ifndef __IFX_VA_PRMS_H
#define __IFX_VA_PRMS_H
#include <stdint.h>

#ifndef MAX
#define MAX(a,b) (((a) > (b)) ? (a) : (b))
#endif

#ifndef MIN
#define MIN(a,b) (((a) < (b)) ? (a) : (b))
#endif

//Please do not change these defined values
#define FRAME_SIZE_16K 160 // 10ms

#define MAX_WW_MODEL_SIZE   10000
#define MAX_CMD_MODEL_SIZE  100000
#define MAX_NMB_MODEL_SIZE 100000

#define AM_FRAME_SET ((int)(AM_FRAME_SIZE/FRAME_SIZE_16K))

#define FEATURE_BUF_SZ 38
#define FRAMES_HOP 4
#define N_PHONEMES 40
#define N_SEQ (23)

#define VA_SAMPLE_RATE (16000)

#ifndef SOD_LOOKBACK_MS
#define SOD_LOOKBACK_MS  (200)  /* 200 ms */
#endif
#ifndef SOD_LOOKBACK
#define SOD_LOOKBACK    ((((int64_t)SOD_LOOKBACK_MS*VA_SAMPLE_RATE/1000)/FRAME_SIZE_16K)) /* divide 1000 convert SOD_LOOKBACK_MS to unit of second */
#endif

#define AM_LOOKBACK ((int)(SOD_LOOKBACK/ FRAMES_HOP))

#define AM_OUT_SZ_FOR_BUFFER (256)

#define DEFAULT_SOD_GAP_SETTING_MS (400)
#define DEFAULT_SOD_SENSITIVITY (16384)

#define DEFAULT_SOD_WW_NOACTIVITY_TIMEOUT_MS (500)
#define SOD_WW_MIN_NOACTIVITY_TIMEOUT_MS (300)
#define SOD_WW_MAX_NOACTIVITY_TIMEOUT_MS (1000)

#define DEFAULT_WW_CMD_MAXWWGAP_MS (1500)
#define WW_CMD_MIN_MAXWWGAP_MS (1000)
#define WW_CMD_MAX_MAXWWGAP_MS (2000)

#define DEFAULT_CMD_TIMEOUT_ADJ_LEVEL (0)
#define CMD_TIMEOUT_MIN_LEVEL (-32768)
#define CMD_TIMEOUT_MAX_LEVEL (32767)
#define CMD_TIMEOUT_MAX_MAG (32768)

#define DFSOD_PARM1_INDEX 5  // gap setting
#define DFSOD_PARM2_INDEX 6  // sensitivity
#define DFWW_PARM_INDEX 5    // noactivty_timeout
#define DFCMD_PARM1_INDEX 5   // maxwwgap
#define DFCMD_PARM2_INDEX 6   // adj_level

extern int32_t sod_prms[];
extern int32_t pre_proc_hpf_prms[];
extern int32_t denoise_prms[];
extern int32_t dfww_prms[];
extern int32_t dfcmd_prms[];

#endif /* __IFX_VA_PRMS_H */
