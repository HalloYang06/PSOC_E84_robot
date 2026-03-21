/*******************************************************************
* THIS INFORMATION IS PROPRIETARY TO INFINEON CORP
*
*-------------------------------------------------------------------
*
*           Copyright (c) 2021 Infineon Corp.
*                      ALL RIGHTS RESERVED
*
********************************************************************

********************************************************************
*    File Name: ifx_asrc.h
*
*    Abstract:  Header file for ifx_asrc
*
*
*
*    $History:$
*
********************************************************************/

#ifndef _IFX_ASRC_H_
#define _IFX_ASRC_H_

// #include "legacy_interface/inc/types.h"
#include "IFX_asrc_types.h"
#include "rateconversionfilters.h"

/*******************************************************************************
 * Defines & Macros
 *******************************************************************************/

#define MIN_SF              8000
#define MAX_SF              96000
#define MAX_CLOCK_ADJUST    60     // 610us per second @ 96k = 58.56 samples
#define INPUT_BUFFER_MAX_8k 80     // largest 8k input buffer to upsample
#define INPUT_BUFFER_MAX    240    // options are 60 (HFP), 80, 120, 240 (ISO) and 128 (A2DP)
#define OUTPUT_BUFFER_MAX   (((long)((INPUT_BUFFER_MAX_8k*((MAX_SF)/((float)MIN_SF)))+1.0))+((long)(1.0+MAX_CLOCK_ADJUST*(INPUT_BUFFER_MAX/((float)MIN_SF))) +1))

#define Q_STEP              28
#define Q_CDPS              10

/*******************************************************************************
 * Structures & Enum
 *******************************************************************************/

typedef struct IFX_ASRC_STRUCT
{
    INT32       Dmemh[MAX_D_STAGES][MAX_FIR_ORDER];
    INT32       Umemh[MAX_U_STAGES][MAX_FIR_HALFORDER];
    INT16       Dndx[MAX_D_STAGES];
    INT16       Undx[MAX_U_STAGES];
    UINT16      Dstages;
    UINT16      Ustages;
    UINT16      baseDstages;
    UINT16      baseUstages;
    UINT32      sfi;
    UINT32      sfo;
    UINT32      sfopcdps;
    INT32       step;
    INT32       interpmem;
    INT32       xi;
    UINT8       cdflag;
    UINT8       skip[MAX_D_STAGES];
} IFX_ASRC_STRUCT_t;

typedef struct IFX_ASRC_IO_BUFFER
{
    INT32  *p_buf;
    UINT16 inIndex;
    UINT16 outIndex;
    UINT16 bufSize;
    UINT16 count;
} IFX_ASRC_IO_BUFFER_t;

/******************************************************************************
* Function Prototypes
******************************************************************************/

void init_IFX_asrc(IFX_ASRC_STRUCT_t *asrcmem, UINT32 sfi, UINT32 sfo);
void IFX_asrc(INT32 *xin, UINT16 xlen, INT32 *yout, UINT16 *ylen, IFX_ASRC_STRUCT_t *asrcmem);
void IFX_SetClockDrift(IFX_ASRC_STRUCT_t *asrcmem, INT32 cdps);

#endif // _IFX_ASRC_H_
