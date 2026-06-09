/******************************************************************************
* File Name: ifx_sp_common_priv.h
*
* Description: This file contains private interface for Infineon speech common header
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
#ifndef __IFX_SP_COMMON_PRIV_H
#define __IFX_SP_COMMON_PRIV_H

#if defined(__cplusplus)
extern "C" {
#endif

/*******************************************************************************
* Include header file
*******************************************************************************/
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "ifx_sp_common.h"


#include "arm_math.h"

#ifdef ENABLE_IFX_DSES
#define ENABLE_IFX_PRIV_GDE /* Enable GDE as a private internal component */
#endif
#define NUM_METER_OUTPUTS         2
#ifdef ENABLE_IFX_PRIV_GDE
#define NUM_PRIV_COMPONENT        (NUM_METER_OUTPUTS + 1)
#else
#define NUM_PRIV_COMPONENT        (NUM_METER_OUTPUTS)
#endif

#if !EMBEDDED_DEV
#undef ARM_MATH_DSP
#undef ARM_MATH_LOOPUNROLL
#endif /* EMBEDDED_DEV */

#define FIXED16MAX ((1 << 15) - 1)
#define FIXED16MIN (-1 - FIXED16MAX)
#define FIXED8MAX ((1 << 7) - 1)
#define FIXED8MIN (-1 - FIXED8MAX)

#define ROUND(shift) ( (((int32_t)0x1) << (shift)) >> 1 )
#define OUTPUT_ROUND_RIGHT_SHIFT(a, b) (((a) + ROUND(b)) >> (b))

/*******************************************************************************
* Macros
*******************************************************************************/
#define BLOCK_SIZE (512)
#define FFT_SIZE (BLOCK_SIZE)
#define KFFT ((FFT_SIZE >> 1)+1)                // number of FFT bins (only half + 1 need to be kept)

#define ALIGN_SIZE(x, y) (((x) + (y) - 1) & ~((y) - 1))
#define ALIGN_WORD(x) ALIGN_SIZE(x, 4)

/* Maximum log buffer size */
#define PROFILE_MAX_LOG_SIZE   127

/* Defines non-configurable ifx speech enhancement process IP components */
typedef enum
{
    IFX_SP_ENH_IP_PRIV_COMPONENT_GDE = IFX_SP_ENH_IP_COMPONENT_INVALID - 3,
    IFX_SP_ENH_IP_PRIV_COMPONENT_INPUT_METER,
    IFX_SP_ENH_IP_PRIV_COMPONENT_OUTPUT_METER
} ifx_sp_enh_ip_priv_component_config_t;

/* Scratch memory structure */
typedef struct
{
    char* scratch_pad;          /* pointer to allocated scratch memory */
    int32_t scratch_cnt;        /* keep track scratch memory used size */
    int32_t scratch_size;       /* allocated scrtach memory size */
} ifx_scratch_mem_t;

/* Cycle profile structure */
typedef struct
{
    uint8_t profile_config;
    uint32_t cycles;
    uint32_t sum_frames;
    uint64_t sum_cycles;
    uint32_t peak_frame;
    uint32_t peak_cycles;
} ifx_cycle_profile_t;

#if PROFILER
typedef struct
{
    ifx_sp_profile_cb_fun log_cb;
    void* log_arg;
    char log_buf[PROFILE_MAX_LOG_SIZE + 1];
} ifx_profile_log_t;

extern ifx_profile_log_t profile_log;
#endif

typedef enum
{
    IFX_SP_DATA_UNKNOWN            = 0u,      /**< Unknown data type */
    IFX_SP_DATA_INT8               = 1u,      /**< 8-bit fixed-point */
    IFX_SP_DATA_INT16              = 2u,      /**< 16-bit fixed-point */
    IFX_SP_DATA_FLOAT              = 3u,      /**< 32-bit float-point */
} ifx_sp_data_type_t;

// complex datatype structure
typedef struct {
    float re;
    float im;
} complex_float;

#define COMPONENT_SET_FLAG(flag, component_id)       ((flag) | (1 << (component_id)))
#define COMPONENT_FLAG_IS_SET(flag, component_id)    ((flag) & (1 << (component_id)))
#define COMPONENT_CLEAR_FLAG(flag, component_id)  ((flag) & ~(1 << (component_id)))

typedef int16_t IFX_SP_DATA_TYPE_COEFF_T;
typedef int16_t IFX_SP_DATA_TYPE_STATE_T;  /* Not sure it should be 16bit or 32bit */
typedef int32_t IFX_SP_DATA_TYPE_ACCUM_T;

static inline void* ifx_mem_allocate(ifx_scratch_mem_t* dPt, uint32_t byte_size)
{
    void* addr;
    int32_t cnt;

    addr = dPt->scratch_pad + dPt->scratch_cnt;
    cnt = dPt->scratch_cnt + ALIGN_WORD(byte_size);
    if (cnt <= dPt->scratch_size)
    {
        dPt->scratch_cnt = cnt;
        return addr;
    }
    else
    {/* Over limit error and return NULL */
        return NULL;
    }
}

static inline void ifx_mem_free(ifx_scratch_mem_t* dPt, uint32_t byte_size)
{
    dPt->scratch_cnt -= ALIGN_WORD(byte_size);
    assert(dPt->scratch_cnt >= 0);
}

static inline void ifx_mem_reset(ifx_scratch_mem_t* dPt)
{/* Effectively free all memory */
    dPt->scratch_cnt = 0;
}

static inline int32_t ifx_mem_counter(ifx_scratch_mem_t* dPt)
{
    return dPt->scratch_cnt;
}

#if defined(__cplusplus)
}
#endif

#endif /*__IFX_SP_COMMON_PRIV_H */

/* [] END OF FILE */
