/******************************************************************************
* File Name : voice_assistant.c
*
* Description :
* Code for DEEPCRAFT voice assistant
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

/*******************************************************************************
* Header Files
*******************************************************************************/
#include "voice_assistant.h"

#include MTB_WWD_NLU_CONFIG_HEADER(PROJECT_PREFIX)

/*******************************************************************************
* Macros
*******************************************************************************/


/*******************************************************************************
* Global Variables
*******************************************************************************/
static mtb_wwd_t va_wwd_obj;
static mtb_nlu_t va_nlu_obj;
static va_mode_t va_mode = VA_MODE_WW_SINGLE_CMD;
static va_run_state_t va_state = VA_RUN_WWD;

/*******************************************************************************
 * Function Name: voice_assistant_init
 *******************************************************************************
 * Summary:
 * Initializes the voice assistant with the specified mode.
 *
 * Parameters:
 *  mode: New mode to set.
 *
 * Return:
 *  Returns VA_RSLT_SUCCESS if successful, otherwise returns an error code.
 *
 *******************************************************************************/
va_rslt_t voice_assistant_init(va_mode_t mode)
{
    cy_rslt_t result;

    va_mode = mode;

    switch (mode)
    {
        case VA_MODE_WW_SINGLE_CMD:
        case VA_MODE_WW_MULTI_CMD:
            result = mtb_wwd_init(&va_wwd_obj, MTB_WWD_NLU_CONFIG_STRUCT(PROJECT_PREFIX)[0]);
            if (result != MTB_VA_RSLT_SUCCESS)
            {
                return VA_RSLT_FAIL;
            }
            result = mtb_nlu_init(&va_nlu_obj, MTB_WWD_NLU_CONFIG_STRUCT(PROJECT_PREFIX)[0]);
            if (result != MTB_VA_RSLT_SUCCESS)
            {
                return VA_RSLT_FAIL;
            }
            va_state = VA_RUN_WWD;
            break;

        case VA_MODE_WW_ONLY:
            result = mtb_wwd_init(&va_wwd_obj, MTB_WWD_NLU_CONFIG_STRUCT(PROJECT_PREFIX)[0]);
            if (result != MTB_VA_RSLT_SUCCESS)
            {
                return VA_RSLT_FAIL;
            }
            va_state = VA_RUN_WWD;
            break;

        case VA_MODE_CMD_ONLY:
            result = mtb_nlu_init(&va_nlu_obj, MTB_WWD_NLU_CONFIG_STRUCT(PROJECT_PREFIX)[0]);
            if (result != MTB_VA_RSLT_SUCCESS)
            {
                return VA_RSLT_FAIL;
            }
            va_state = VA_RUN_CMD;
            break;

        default:
            return VA_RSLT_INVALID_ARGUMENT;
    }

    return VA_RSLT_SUCCESS;
}

/*******************************************************************************
 * Function Name: voice_assistant_change_state
 *******************************************************************************
 * Summary:
 * Changes the state of the voice assistant.
 *
 * Parameters:
 *  state: New state to set.
 *
 * Return:
 *  void
 *
 *******************************************************************************/
void voice_assistant_change_state(va_run_state_t state)
{
    va_state = state;
}

/*******************************************************************************
 * Function Name: voice_assistant_process
 *******************************************************************************
 * Summary:
 * Processes the audio data and detects the wake word or command.
 *
 * Parameters:
 *  audio_frame: Pointer to the audio data frame.
 *  event: Pointer to the event detected.
 *  va_data: Pointer to the data detected.
 *
 * Return:
 *  Returns VA_RSLT_SUCCESS if successful, otherwise returns an error code.
 *
 *******************************************************************************/
va_rslt_t voice_assistant_process(int16_t *audio_frame, va_event_t *event, va_data_t *va_data)
{
    cy_rslt_t result;
    mtb_wwd_state_t wwd_state;
    mtb_nlu_state_t nlu_state;
    mtb_nlu_variable_t variable[VA_NLU_MAX_NUM_VARIABLES] = {0};
    
    if ((event == NULL) || (audio_frame == NULL))
    {
        return VA_RSLT_INVALID_ARGUMENT;
    }

    /* Check if the current VA state is WWD */
    if (va_state == VA_RUN_WWD)
    {
        /* Run the wake-word detection process */
        result = mtb_wwd_process(&va_wwd_obj, audio_frame, &wwd_state);

        if (result == MTB_VA_RSLT_LICENSE_ERROR)
        {
            return VA_RSLT_LICENSE_ERROR;
        } 
        else if (result != MTB_VA_RSLT_SUCCESS)
        {
            return VA_RSLT_FAIL;
        }

        /* Check if the wake-word was detected */
        if (wwd_state == CY_WWD_DETECTED)
        {
            *event = VA_EVENT_WW_DETECTED;

            /* Change state to detect command */
            if (va_mode != VA_MODE_WW_ONLY)
            {
                va_state = VA_RUN_CMD;
            }
        }
        else if (wwd_state == CY_WWD_NOT_DETECTED)
        {
            *event = VA_EVENT_WW_NOT_DETECTED;
        }
        else
        {
            *event = VA_NO_EVENT;
        }
    }
    /* Check if the current VA state is CMD */
    else if (va_state == VA_RUN_CMD)
    {
        if (va_data == NULL)
        {
            return VA_RSLT_INVALID_ARGUMENT;
        }

        /* Run the command detection process */
        result = mtb_nlu_process(&va_nlu_obj, audio_frame, &nlu_state, &va_data->intent_index, variable, &va_data->num_var);

        if (result == MTB_VA_RSLT_LICENSE_ERROR)
        {
            return VA_RSLT_LICENSE_ERROR;
        }

        /* Check if a command was detected */
        if (nlu_state == CY_NLU_DETECTED)
        {
            *event = VA_EVENT_CMD_DETECTED;

            if (va_mode == VA_MODE_WW_SINGLE_CMD)
            {
                va_state = VA_RUN_WWD;
            }
            
            for (int i = 0; i < va_data->num_var; i++)
            {
                va_data->variable[i].value = variable[i].value;
                va_data->variable[i].unit_idx = variable[i].unit_idx;
            }
        }
        else if (result == CY_NLU_RSLT_COMMAND_TIMEOUT)
        {
            *event = VA_EVENT_CMD_TIMEOUT;
            if (va_mode != VA_MODE_CMD_ONLY)
            {
                va_state = VA_RUN_WWD;
            }
        }
        else if (result == CY_NLU_RSLT_PRE_SILENCE_TIMEOUT)
        {
            *event = VA_EVENT_CMD_SILENCE_TIMEOUT;
            if ((va_mode != VA_MODE_CMD_ONLY) && (va_mode != VA_MODE_WW_MULTI_CMD))
            {
                va_state = VA_RUN_WWD;
            }
        }
        else
        {
            *event = VA_NO_EVENT;
        }
    }
    
    return VA_RSLT_SUCCESS;
}

/*******************************************************************************
 * Function Name: voice_assistant_set_command_timeout
 *******************************************************************************
 * Summary:
 * Sets the command timeout for NLU detection.
 *
 * Parameters:
 *  timeout_ms: Timeout in milliseconds.
 *
 * Return:
 *  Returns VA_RSLT_SUCCESS if successful, otherwise returns an error code.
 *
 *******************************************************************************/
va_rslt_t voice_assistant_set_command_timeout(uint32_t timeout_ms)
{
    cy_rslt_t result;

    result = mtb_nlu_timeout(&va_nlu_obj, timeout_ms);

    if (result != MTB_VA_RSLT_SUCCESS)
    {
        return VA_RSLT_FAIL;
    }

    return VA_RSLT_SUCCESS;
}

/*******************************************************************************
 * Function Name: voice_assistant_get_command
 *******************************************************************************
 * Summary:
 * Returns the command string detected by the voice-assistant.
 *
 * Parameters:
 *  text: detected command string
 *
 * Return:
 *  Returns VA_RSLT_SUCCESS if successful, otherwise returns an error code.
 *
 *******************************************************************************/
va_rslt_t voice_assistant_get_command(char *text)
{
    cy_rslt_t result;

    if (text == NULL)
    {
        return VA_RSLT_INVALID_ARGUMENT;
    }

    result = mtb_nlu_get_command(&va_nlu_obj, text);

    if (result != MTB_VA_RSLT_SUCCESS)
    {
        return VA_RSLT_FAIL;
    }

    return VA_RSLT_SUCCESS;
}