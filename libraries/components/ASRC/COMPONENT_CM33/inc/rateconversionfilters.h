/*********************************************************************************/
/* rateconversionfilters.h                                                       */
/*                                                                               */
/* This file holds the static filter coefficients used by the ASRC for both      */
/* upsampling and downsampling.                                                  */
/*                                                                               */
/* Robert Zopf                                                                   */
/* Infineon Technologies                                                         */
/* 2021                                                                          */
/*********************************************************************************/
#ifndef RATECONVERSIONFILTERS_H
#define RATECONVERSIONFILTERS_H

#define MAX_D_STAGES    4
#define MAX_U_STAGES    3
#define MAX_FIR_ORDER   40

#define MAX_FIR_HALFORDER   20
#define D4_HALFORDER (8)
#define D3_HALFORDER (8)
#define D2_HALFORDER (12)
#define D1_HALFORDER (20)
#define U1_HALFORDER (20)
#define U2_HALFORDER (12)
#define U3_HALFORDER (8)

#define D4_ORDER (16)
#define D3_ORDER (16)
#define D2_ORDER (24)
#define D1_ORDER (40)

extern int32_t   *Dcfilter[];
extern uint16_t  Dhorder[];
extern int32_t   *Ucfilter[];
extern uint16_t  Uhorder[];

#endif