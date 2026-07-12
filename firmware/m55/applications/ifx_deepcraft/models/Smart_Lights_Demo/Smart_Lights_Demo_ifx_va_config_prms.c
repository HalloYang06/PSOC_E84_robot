/*****************************************************************************
* \file Smart_Lights_Demo_ifx_va_config_prms.c
*****************************************************************************
* \copyright
* Copyright 2025, Infineon Technologies.
* All rights reserved.
*****************************************************************************/

#include "Smart_Lights_Demo_ifx_va_config_prms.h"

int32_t Smart_Lights_Demo_sod_prms[] = {
    0,
    16000,
    160,
    IFX_PRE_PROCESS_IP_COMPONENT_SOD,
    2,
    400,
    16384
};

int32_t Smart_Lights_Demo_pre_proc_hpf_prms[] = {
    0,
    16000,
    160,
    IFX_PRE_PROCESS_IP_COMPONENT_HPF,
    0
};

int32_t Smart_Lights_Demo_denoise_prms[] = {
    0,
    16000,
    160,
    IFX_PRE_PROCESS_IP_COMPONENT_DENOISE,
    1,
    38
};

int32_t Smart_Lights_Demo_dfww_prms[] = {
    0,
    16000,
    160,
    IFX_POST_PROCESS_IP_COMPONENT_DFWWD,
    1,
    500
};

int32_t Smart_Lights_Demo_dfcmd_prms[] = {
    0,
    16000,
    160,
    IFX_POST_PROCESS_IP_COMPONENT_DFCMD,
    2,
    2000,
    0
};
