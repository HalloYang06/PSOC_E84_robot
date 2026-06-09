/******************************************************************************
* File Name: ifx_sp_common.h
*
* Description: This file contains public interface for Infineon speech common header
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
#ifndef __IFX_SP_COMMON_H
#define __IFX_SP_COMMON_H

#if defined(__cplusplus)
extern "C" {
#endif

/*******************************************************************************
* Include header file
*******************************************************************************/
#include <stdint.h>
#include <stdbool.h>
/*******************************************************************************
* Compile-time flags
*******************************************************************************/
#define OKIFX_INT8_NN       1
#define HEYGOOGLE_INT8_NN   2
#define ALEXA_INT8_NN       3
#define OKIFX_F32_NN        4
#define HEYGOOGLE_F32_NN    5
#define ALEXA_F32_NN        6
#define OKIFX_UNIT_TEST     7
#define HEYGOOGLE_UNIT_TEST 8
#define ALEXA_UNIT_TEST     9
#define OKIFX_ALEXA_FIRST_WAKEUP_INT8_NN        10
#define OKIFX_ALEXA_SECOND_WAKEUP_INT8_NN       11
#define OKIFX_ALEXA_FIRST_WAKEUP_F32_NN         12
#define OKIFX_ALEXA_SECOND_WAKEUP_F32_NN        13
#define ALEXA_HEYGOOGLE_FIRST_WAKEUP_INT8_NN    14
#define ALEXA_HEYGOOGLE_SECOND_WAKEUP_INT8_NN   15
#define ALEXA_HEYGOOGLE_FIRST_WAKEUP_F32_NN     16
#define ALEXA_HEYGOOGLE_SECOND_WAKEUP_F32_NN    17
#define XIAODU_XIAODU_F32_NN        18
#define XIAODU_XIAODU_INT8_NN       19
/**
 * User can define ACTIVE_KW elsewhere (may be in makefile) and also enable
 * HMMS_CONFIG_MODEL to choose model using the file hmms_model_config.c
 *
 * if the variable HMMS_CONFIG_MODEL is defined and ACTIVE_KW is not defined
 * then
 */
#ifndef ACTIVE_KW
#define ACTIVE_KW   OKIFX_UNIT_TEST
#endif

#define MAX_CLASS_ID_LENGTH (512)   /* Maximum characters used to describe NN inference output definitions */
#define NUM_PP_CLASS_2TOKEN_WW (4)  /* Output class size of two token keyword NN inference in the order of token0, token1, garbage, noise */
#define NUM_PP_CLASS_4TOKEN_WW (6)  /* Output class size of four token keyword NN inference in the order of token0, token1, token2, token3 garbage, noise*/
#define MAX_WW_TOKENS          (4)  /* Maximum number of WWD tokens in low power WWD */

/*******************************************************************************
* Infineon speech common data type & defines
*******************************************************************************/
#define IFX_SP_ENH_SUCCESS                  (0)

#define IFX_SP_ENH_LINE_SHIFT               (16u)
#define IFX_SP_ENH_LINE_MASK                (0xFFFF0000)

#define IFX_SP_ENH_COMPONENT_ID_SHIFT       (8u)
#define IFX_SP_ENH_COMPONENT_ID_MASK        (0x0000FF00)
#define IFX_SP_ENH_COMPONENT_ID_INVALID     (255u)

#define IFX_SP_ENH_ERR_CODE_MASK            (0x000000FF)
#define IFX_SP_ENH_ERR_CONFIGURATOR_VERSION (0x01)
#define IFX_SP_ENH_ERR_OVER_MAX_SCRATCH_MEM (0x02)
#define IFX_SP_ENH_ERR_INVALID_ARGUMENT     (0x03)
#define IFX_SP_ENH_FEATURE_NOT_SUPPORTED    (0x04)
#define IFX_SP_ENH_ERR_PARAM                (0x05)
#define IFX_SP_ENH_MISMATCH_PARM_CHECKSUM   (0x06)
#define IFX_SP_ENH_ERR_API                  (0x07)
#define IFX_SP_ENH_ERR_INVALID_COMPONENT_ID (0x08)
#define IFX_SP_ENH_ERR_NUMBER_PARMS         (0x09)
#define IFX_SP_ENH_ERR_NOT_CONFIG_ID        (0x0a)
#define IFX_SP_ENH_ERR_INVALID_CONFIG       (0x0b)
#define IFX_SP_ENH_ERR_PARAM_RANGE          (0x0c)
#define IFX_SP_ENH_ERR_COEFF                (0x0d)
#define IFX_SP_ENH_ERR_COEFF_SIZE           (0x0e)
#define IFX_SP_ENH_ERR_PERSISTEMT_MEM       (0x0f)
#define IFX_SP_ENH_ERR_GLOBAL_PERSIST_MEM   (0x10)
#define IFX_SP_ENH_ERR_SCRATCH_MEM_NULL     (0x11)
#define IFX_SP_ENH_ERR_LICENSE              (0x12)
#define IFX_SP_ENH_ERR_MODEL_PARAM_INVALID  (0x13)
#define IFX_SP_ENH_ERR_MODEL_PARAM_RANGE    (0x14)
#define IFX_SP_ENH_ERR_INFERERCE            (0x15)
#define IFX_SP_ENH_ERR_FILE_IO              (0x16)
#define IFX_SP_ENH_ERR_MODEL_VERSION        (0x17)

#define IFX_SP_ENH_ERROR(x, y)              ((__LINE__ << IFX_SP_ENH_LINE_SHIFT) | \
                                            (((x) << IFX_SP_ENH_COMPONENT_ID_SHIFT) & IFX_SP_ENH_COMPONENT_ID_MASK) | \
                                            ((y) & IFX_SP_ENH_ERR_CODE_MASK))
#define IFX_SP_ENH_ERR_CODE(x)              (uint8_t)((x) & IFX_SP_ENH_ERR_CODE_MASK)
#define IFX_SP_ENH_ERR_COMPONENT_INDEX(x)   (uint8_t)(((x) & IFX_SP_ENH_COMPONENT_ID_MASK) >> IFX_SP_ENH_COMPONENT_ID_SHIFT)
#define IFX_SP_ENH_ERR_LINE_NUMBER(x)       (uint16_t)(((x) & IFX_SP_ENH_LINE_MASK) >> IFX_SP_ENH_LINE_SHIFT)


#define FEATURE_EXTRACTION_OUTPUT_8BIT      (1) /* Enable or disable 8bit feature extraction output */

#if FEATURE_EXTRACTION_OUTPUT_8BIT
typedef int8_t  IFX_FE_DATA_TYPE_T;
#define FEATURE_EXTRACTION_OUTPUT_8BIT_DYNAMIC  (0)     /* Enable or disable dynamic 8bit output */
#if !FEATURE_EXTRACTION_OUTPUT_8BIT_DYNAMIC
#define MEL_LOG_8BIT_OUTPUT_Q        (2)        /* CAUTION: Value subjucts change inside library so this is information example for fixed scaling Q value */
#define MFCC_8BIT_OUTPUT_Q           (0)        /* CAUTION: Value subjucts change inside library so this is information example for fixed scaling Q value */
#endif
#else
typedef int16_t  IFX_FE_DATA_TYPE_T;
#define MEL_LOG_16BIT_OUTPUT_Q       (9)        /* CAUTION: Value subjucts change inside library so this is information example for fixed scaling Q value */
#define MFCC_16BIT_OUTPUT_Q          (6)        /* CAUTION: Value subjucts change inside library so this is information example for fixed scaling Q value */
#endif

#define PP_SECOND_CONVERTION_Q       (12)       /* Post process look back buffer length and NN stacked frame delay convert from seconds to fixed value Q value */

/* Define inference output data_type to be same as MTB-ML ml-inference */
typedef enum
{
    IFX_ML_DATA_UNKNOWN = 0u,    /**< Unknown data type */
    IFX_ML_DATA_INT8 = 1u,       /**< 8-bit fixed-point */
    IFX_ML_DATA_INT16 = 2u,      /**< 16-bit fixed-point */
    IFX_ML_DATA_FLOAT = 3u,      /**< 32-bit float-point */
} ifx_ml_data_type_t;

/** Defines configurable ifx speech enhancement process IP components */
typedef enum
{
    IFX_SP_ENH_IP_COMPONENT_INVALID = 0,
    IFX_SP_ENH_IP_COMPONENT_HPF,
    IFX_SP_ENH_IP_COMPONENT_AEC,
    IFX_SP_ENH_IP_COMPONENT_BF,
    IFX_SP_ENH_IP_COMPONENT_DRVB,
    IFX_SP_ENH_IP_COMPONENT_ANALYSIS,
    IFX_SP_ENH_IP_COMPONENT_SYNTHESIS,
    IFX_SP_ENH_IP_COMPONENT_DSNS,
    IFX_SP_ENH_IP_COMPONENT_DSES,
    IFX_SP_ENH_IP_COMPONENT_DSNS2,
    IFX_SP_ENH_IP_COMPONENT_ES,
    IFX_SP_ENH_IP_COMPONENT_NS,
    IFX_SP_ENH_IP_COMPONENT_RESERVED3,
    IFX_SP_ENH_IP_COMPONENT_RESERVED2,
    IFX_SP_ENH_IP_COMPONENT_RESERVED1,
    IFX_SP_ENH_IP_COMPONENT_RESERVED0,
    IFX_PRE_POST_IP_COMPONENT_START_ID  /* Infineon LPWWD pre and post process component IP starting index */
} ifx_sp_enh_ip_component_config_t;

typedef struct
{
    /*@{*/
    int32_t scratch_mem;        /**< scratch memory byte size required for post process */
    int32_t persistent_mem;     /**< persistent memory byte size required for post process */
    void* scratch_mem_pt;       /**< scratch memory pointer */
    void* persistent_mem_pt;    /**< persistent memory pointer */
    /*@}*/
} mem_info_t;

typedef struct
{
    /*@{*/
    int32_t persistent_mem;     /**< persistent memory byte size required for post process */
    void* persistent_mem_pt;    /**< persistent memory pointer */
    /*@}*/
} persistent_mem_info_t;

/** Defines profile settings */
#define IFX_SP_ENH_PROFILE_FRAME            (0x01)
#define IFX_SP_ENH_PROFILE_COMPONENT        (0x02)
#define IFX_SP_ENH_PROFILE_APP              (0x04)

typedef enum
{
    IFX_SP_ENH_PROFILE_DISABLE                     = 0,
    IFX_SP_ENH_PROFILE_ENABLE_APP                  = IFX_SP_ENH_PROFILE_APP,
    IFX_SP_ENH_PROFILE_ENABLE_COMPONENT            = IFX_SP_ENH_PROFILE_COMPONENT,
    IFX_SP_ENH_PROFILE_ENABLE_APP_PER_FRAME        = (IFX_SP_ENH_PROFILE_APP | IFX_SP_ENH_PROFILE_FRAME),
    IFX_SP_ENH_PROFILE_ENABLE_COMPONENT_PER_FRAME  = (IFX_SP_ENH_PROFILE_COMPONENT | IFX_SP_ENH_PROFILE_FRAME),
} ifx_sp_enh_profile_config_t;

typedef int16_t IFX_SP_DATA_TYPE_T;

typedef int16_t  IFX_PPINPUT_DATA_TYPE_T;

typedef int (*ifx_sp_profile_cb_fun) (void* arg, char* buf, int32_t type);


#if defined(__cplusplus)
}
#endif

#endif /*__IFX_SP_COMMON_H */

/* [] END OF FILE */
