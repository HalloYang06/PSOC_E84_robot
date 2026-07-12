#ifndef __IFX_ASRC_TYPES_H__
#define __IFX_ASRC_TYPES_H__


#include <stdio.h>
#include <stddef.h>
#include <stdint.h>
#include <assert.h>

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

//! Unsigned 8-bit integer.
typedef uint8_t                 UINT8;
typedef uint8_t                 uint8;
typedef uint8_t                 BYTE;
// typedef uint8_t                 char_t;

//! Signed 8-bit integer.
typedef int8_t                  INT8;
typedef int8_t                  int8;

//! Unsigned 16-bit integer.
typedef uint16_t                UINT16;
typedef uint16_t                uint16;
typedef uint16_t                WORD;

//! Signed 16-bit integer.
typedef int16_t                 INT16;
typedef int16_t                 int16;

//! Unsigned 32-bit integer.
typedef uint32_t                UINT32;
typedef uint32_t                uint32;
typedef uint32_t                DWORD;

//! Signed 32-bit integer.
typedef int32_t                 INT32;
typedef int32_t                 int32;

//! Unsigned 64-bit integer.
typedef uint64_t                UINT64;

//! Signed 64-bit integer.
typedef int64_t                 INT64;

//! Boolean type in its most efficient form, for use in function arguments and return values.
// typedef uint32_t                BOOL32;

//! Boolean type in its most size-efficient form, for use in structures.
// typedef uint8_t                 BOOL8;

// //! bool should NOT be used, so it is defined so as to generate a compilation error.  This is in
// //! order to enforce the practice of using BOOL32 for efficiency in function arguments or return
// //! values, and BOOL8 for size efficiency in structures.  The same is true of BOOL and BOOLEAN,
// //! which are ambiguous in the size vs. efficiency tradeoff and should not be used.
// #ifndef __cplusplus
//     #define bool                    Do NOT Use
// #endif

// Code has slipped in that use these, they should be changed to not be used.
typedef uint32_t                BOOL;
typedef uint32_t                BOOLEAN;

// Legacy code ... DO NOT USE THESE!  Someday we will globally search and replace to remove them.
typedef int16_t                 SINT16;
// typedef int32_t                 SINT32;
// typedef int64_t                 SINT64;
typedef int16_t                 Word16;
typedef int32_t                 Word32;
typedef int                     Flag;

#endif /* __IFX_ASRC_TYPES_H__ */
