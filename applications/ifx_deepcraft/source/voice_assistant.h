/******************************************************************************
* File Name : voice_assistant.h
*
* Description :
* Header for the DEEPCRAFT voice assistant (VA)
********************************************************************************
* (c) 2025-2026, Infineon Technologies AG, or an affiliate of Infineon
* Technologies AG. All rights reserved.
* This software, associated documentation and materials ("Software") is
* owned by Infineon Technologies AG or one of its affiliates ("Infineon")
* and is protected by and subject to worldwide patent protection, worldwide
* copyright laws, and international treaty provisions. Therefore, you may use
* this Software only as provided in the license agreement accompanying the
* software package from which you obtained this Software. If no license
* agreement applies, then any use, reproduction, modification, translation, or
* compilation of this Software is prohibited without the express written
* permission of Infineon.
*
* Disclaimer: UNLESS OTHERWISE EXPRESSLY AGREED WITH INFINEON, THIS SOFTWARE
* IS PROVIDED AS-IS, WITH NO WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
* INCLUDING, BUT NOT LIMITED TO, ALL WARRANTIES OF NON-INFRINGEMENT OF
* THIRD-PARTY RIGHTS AND IMPLIED WARRANTIES SUCH AS WARRANTIES OF FITNESS FOR A
* SPECIFIC USE/PURPOSE OR MERCHANTABILITY.
* Infineon reserves the right to make changes to the Software without notice.
* You are responsible for properly designing, programming, and testing the
* functionality and safety of your intended application of the Software, as
* well as complying with any legal requirements related to its use. Infineon
* does not guarantee that the Software will be free from intrusion, data theft
* or loss, or other breaches ("Security Breaches"), and Infineon shall have
* no liability arising out of any Security Breaches. Unless otherwise
* explicitly approved by Infineon, the Software may not be used in any
* application where a failure of the Product or any consequences of the use
* thereof can reasonably be expected to result in personal injury.
*******************************************************************************/

#ifndef _VOICE_ASSISTANT_H_
#define _VOICE_ASSISTANT_H_

#if defined(__cplusplus)
extern "C" {
#endif /* __cplusplus */

#include "mtb_wwd_nlu_common.h"
#include "mtb_nlu.h"
#include "mtb_wwd.h"

/******************************************************************************
 * Macros
 *****************************************************************************/
#define VA_NLU_MAX_NUM_VARIABLES   4u

/******************************************************************************
 * Typedefs
 *****************************************************************************/
typedef enum
{
    VA_RSLT_SUCCESS = 0,
    VA_RSLT_FAIL = -1,
    VA_RSLT_INVALID_ARGUMENT = -2,
    VA_RSLT_LICENSE_ERROR = -3,
} va_rslt_t;

 typedef enum
{
    VA_NO_EVENT = 0,
    VA_EVENT_WW_DETECTED = 1,
    VA_EVENT_WW_NOT_DETECTED = 2,
    VA_EVENT_CMD_DETECTED = 3,
    VA_EVENT_CMD_TIMEOUT = 4,
    VA_EVENT_CMD_SILENCE_TIMEOUT = 5,
} va_event_t;

typedef enum
{
    VA_MODE_WW_SINGLE_CMD = 0,
    VA_MODE_WW_MULTI_CMD = 1,
    VA_MODE_WW_ONLY = 2,
    VA_MODE_CMD_ONLY = 3,
} va_mode_t;

typedef enum
{
    VA_RUN_WWD = 0,
    VA_RUN_CMD = 1,
} va_run_state_t;

/******************************************************************************
 * Structures
 ******************************************************************************/
typedef struct
{
    int     intent_index;
    int     num_var;
    mtb_nlu_variable_t variable[VA_NLU_MAX_NUM_VARIABLES];
} va_data_t;

/*******************************************************************************
 * Function Prototypes
 *******************************************************************************/
va_rslt_t voice_assistant_init(va_mode_t mode);
void      voice_assistant_change_state(va_run_state_t state);
va_rslt_t voice_assistant_process(int16_t *audio_frame, va_event_t *event, va_data_t *va_data);
va_rslt_t voice_assistant_set_command_timeout(uint32_t timeout_ms);
va_rslt_t voice_assistant_get_command(char *text);

#if defined(__cplusplus)
}
#endif /* __cplusplus */

#endif /* _VOICE_ASSISTANT_H_ */

/* [] END OF FILE */
