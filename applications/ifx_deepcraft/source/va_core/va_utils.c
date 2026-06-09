/***************************************************************************//**
 * \file va_utils.c
 *
 * \brief
 * The file contains utility functions for the voice assistant
 *
 *******************************************************************************
 * (c) 2019-2025, Cypress Semiconductor Corporation (an Infineon company) or
 * an affiliate of Cypress Semiconductor Corporation.  All rights reserved.
 *******************************************************************************/

#include "va_utils.h"
#include "ifx_sp_utils.h"
#include <stddef.h>
#include <stdlib.h>

/******************************************************************************
 * Local Defines
 *****************************************************************************/
#define MAX_COMMAND_TEXT_LENGTH 250
#define MAX_INDICES 64
#define MAX_CELLS 3
#define MAX_NUMBERS 20
#define MAX_UNITS 20

/******************************************************************************
 * Global Variables For CMD Reading
 *****************************************************************************/
char commandtext[MAX_COMMAND_TEXT_LENGTH];
int indices[MAX_INDICES];
char number[MAX_CELLS][MAX_NUMBERS];
char units[MAX_CELLS][MAX_UNITS];

uint32_t parse_ifx_prms(ifx_stc_pre_post_process_info_t *ifx_info,
                        int32_t *prms_buffer)
{
    uint32_t error_code = 0;

    if (ifx_info != NULL)
    {
        error_code = ifx_pre_post_process_parse(prms_buffer, ifx_info);
        if (error_code != IFX_SP_ENH_SUCCESS)
            return MTB_VA_RSLT_IFX_PARSE_ERROR;
    }
    return MTB_VA_RSLT_SUCCESS;
}

void free_ifx_persistent_mem(ifx_stc_pre_post_process_info_t *hpf_info,
                             ifx_stc_pre_post_process_info_t *sod_info,
                             ifx_stc_pre_post_process_info_t *feature_info,
                             ifx_stc_pre_post_process_info_t *dfww_info,
                             ifx_stc_pre_post_process_info_t *dfcmd_info)
{
    if (hpf_info != NULL && hpf_info->memory.persistent_mem_pt != NULL)
    {
        free(hpf_info->memory.persistent_mem_pt);
        hpf_info->memory.persistent_mem_pt = NULL;
    }
    if (sod_info != NULL && sod_info->memory.persistent_mem_pt != NULL)
    {
        free(sod_info->memory.persistent_mem_pt);
        sod_info->memory.persistent_mem_pt = NULL;
    }
    if (feature_info != NULL &&
        feature_info->memory.persistent_mem_pt != NULL)
    {
        free(feature_info->memory.persistent_mem_pt);
        feature_info->memory.persistent_mem_pt = NULL;
    }
    if (dfww_info != NULL && dfww_info->memory.persistent_mem_pt != NULL)
    {
        free(dfww_info->memory.persistent_mem_pt);
        dfww_info->memory.persistent_mem_pt = NULL;
    }
    if (dfcmd_info != NULL && dfcmd_info->memory.persistent_mem_pt != NULL)
    {
        free(dfcmd_info->memory.persistent_mem_pt);
        dfcmd_info->memory.persistent_mem_pt = NULL;
    }
}

uint32_t allocate_ifx_mem(ifx_stc_pre_post_process_info_t *hpf_info,
                          ifx_stc_pre_post_process_info_t *sod_info,
                          ifx_stc_pre_post_process_info_t *feature_info,
                          ifx_stc_pre_post_process_info_t *dfww_info,
                          ifx_stc_pre_post_process_info_t *dfcmd_info)
{
    if (hpf_info != NULL)
    {
        hpf_info->memory.persistent_mem_pt =
            (char *)malloc(hpf_info->memory.persistent_mem);
        if (hpf_info->memory.persistent_mem_pt == NULL)
        {
            free_ifx_persistent_mem(hpf_info, sod_info, feature_info, dfww_info,
                                    dfcmd_info);
            return MTB_VA_RSLT_MEM_ALLOC_ERROR;
        }
    }

    if (sod_info != NULL)
    {
        sod_info->memory.persistent_mem_pt =
            (char *)malloc(sod_info->memory.persistent_mem);
        if (sod_info->memory.persistent_mem_pt == NULL)
        {
            free_ifx_persistent_mem(hpf_info, sod_info, feature_info, dfww_info,
                                    dfcmd_info);
            return MTB_VA_RSLT_MEM_ALLOC_ERROR;
        }
    }

    if (feature_info != NULL)
    {
        feature_info->memory.persistent_mem_pt =
            (char *)malloc(feature_info->memory.persistent_mem);
        if (feature_info->memory.persistent_mem_pt == NULL)
        {
            free_ifx_persistent_mem(hpf_info, sod_info, feature_info, dfww_info,
                                    dfcmd_info);
            return MTB_VA_RSLT_MEM_ALLOC_ERROR;
        }
    }

    if (dfww_info != NULL)
    {
        dfww_info->memory.persistent_mem_pt =
            (char *)malloc(dfww_info->memory.persistent_mem);
        if (dfww_info->memory.persistent_mem_pt == NULL)
        {
            free_ifx_persistent_mem(hpf_info, sod_info, feature_info, dfww_info,
                                    dfcmd_info);
            return MTB_VA_RSLT_MEM_ALLOC_ERROR;
        }
    }

    if (dfcmd_info != NULL)
    {
        dfcmd_info->memory.persistent_mem_pt =
            (char *)malloc(dfcmd_info->memory.persistent_mem);
        if (dfcmd_info->memory.persistent_mem_pt == NULL)
        {
            free_ifx_persistent_mem(hpf_info, sod_info, feature_info, dfww_info,
                                    dfcmd_info);
            return MTB_VA_RSLT_MEM_ALLOC_ERROR;
        }
    }

    return MTB_VA_RSLT_SUCCESS;
}

uint32_t reset_mtb_va_common(mtb_va_common_t *common_objs, int32_t *sod_prms)
{
    int error_code = 0;
    if (common_objs == NULL || sod_prms == NULL)
        return MTB_VA_RSLT_INVALID_PARAM;

#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    error_code = ifx_afe_hpf_reset(common_objs->pre_proc_hpf_obj);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_RESET_ERROR;
#endif
    error_code = speech_utils_sod_reset(sod_prms, common_objs->sod_obj);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_RESET_ERROR;
    error_code = ifx_itsi_feature_reset(common_objs->feature_obj);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_RESET_ERROR;
    error_code = ifx_dfww_state_reset(common_objs->dfww_obj);
    if (error_code != IFX_SP_ENH_SUCCESS)
        return MTB_VA_RSLT_IFX_RESET_ERROR;

    return MTB_VA_RSLT_SUCCESS;
}

uint32_t free_mtb_va_common(mtb_va_common_t *common_objs)
{
    if (common_objs == NULL)
        return MTB_VA_RSLT_INVALID_PARAM;

    if (!common_objs->is_owner)
    {
        /* This instance is not the owner of the underlying memory,
           skip freeing resources */
        common_objs->is_initialized = false;
        return MTB_VA_RSLT_SUCCESS;
    }

#ifdef ENABLE_IFX_PRE_PROCESS_HPF
    if (common_objs->pre_proc_hpf_obj != NULL)
    {
        free(common_objs->pre_proc_hpf_obj);
        common_objs->pre_proc_hpf_obj = NULL;
    }
#endif
    if (common_objs->sod_obj != NULL)
    {
        free(common_objs->sod_obj);
        common_objs->sod_obj = NULL;
    }
    if (common_objs->feature_obj != NULL)
    {
        int result = itsi_feature_deinit(common_objs->feature_obj);
        if (result != IFX_SP_ENH_SUCCESS)
            return MTB_VA_RSLT_IFX_INTERNAL_ERROR;
        free(common_objs->feature_obj);
        common_objs->feature_obj = NULL;
    }
    if (common_objs->dfww_obj != NULL)
    {
        free(common_objs->dfww_obj);
        common_objs->dfww_obj = NULL;
    }
    common_objs->is_initialized = false;
    return MTB_VA_RSLT_SUCCESS;
}

void nlu_extract_command(void *dfcmd_obj, mtb_nlu_t *nlu_obj, int *intent_index,
                         mtb_nlu_variable_t *variable_values, int *var_size)
{
    cy_rslt_t result;

    int num_units;
    int num_numbers;
    int num_indices;
    int num_variables;
    int intent;
    int index;
    int intent_map_array;
    int variable;
    int variable_value;
    int var_idx = 0;

    memset(commandtext, 0, MAX_COMMAND_TEXT_LENGTH);
    memset(indices, 0, MAX_INDICES * sizeof(int));
    memset(number, 0, MAX_CELLS * MAX_NUMBERS * sizeof(char));
    memset(units, 0, MAX_CELLS * MAX_UNITS * sizeof(char));

    CY_VA_PRINTF_TRACE("CMD detected \r\n");

    result = ifx_get_command(dfcmd_obj, commandtext);
    if (result != CY_RSLT_SUCCESS)
    {
        CY_VA_PRINTF_TRACE("Error! IFX get command Failed! Error code=%x\n\r",
                           result);
    }
    CY_VA_PRINTF_TRACE("Command is %s \r\n", commandtext);

    result = ifx_get_command_indices_and_numbers(
        dfcmd_obj, indices, &num_indices, number, &num_numbers, units,
        &num_units);
    if (result != CY_RSLT_SUCCESS)
    {
        CY_VA_PRINTF_TRACE("Error IFX get command indices! Error code=%x\n\r",
                           result);
        *var_size = var_idx;
        return;
    }

    CY_VA_PRINTF_TRACE(
        "N indices: %d (%d) : N numbers: %d (%s) : N Units: %d (%s) \n\r",
        num_indices, indices[0], num_numbers, number[0], num_units, units[0]);

    index = indices[0];
    intent_map_array = 0;
    for (int i = 0; i < index; i++)
    {
        intent_map_array +=
            nlu_obj->nlu_variable_data->intent_map_array_sizes[i];
    }
    intent = nlu_obj->nlu_variable_data->intent_map_array[intent_map_array];
    *intent_index = intent; /* Adding +1 to match with Intent Defines MACROS as
                               per SEROS Appendix 4 */
    CY_VA_PRINTF_TRACE("Intent: %s\n\r",
                       nlu_obj->nlu_variable_data->intent_name_list[intent]);

    num_variables =
        nlu_obj->nlu_variable_data->intent_map_array[intent_map_array + 1];
    CY_VA_PRINTF_TRACE("Num variables: %d\n\r", num_variables);

    if (num_variables == 0)
    {
        CY_VA_PRINTF_TRACE("No variables\n\r");
        *var_size = var_idx;
        return;
    }

    for (int v = 0; v < num_variables; v++)
    {
        const int variable_idx = intent_map_array + 2 * (v + 1);
        variable = nlu_obj->nlu_variable_data->intent_map_array[variable_idx];

        CY_VA_PRINTF_TRACE(
            "Var%d - Variable (%d) name: %s\n\r", v + 1, variable,
            nlu_obj->nlu_variable_data->variable_name_list[variable]);

        variable_value =
            nlu_obj->nlu_variable_data->intent_map_array[variable_idx + 1];

        if (variable_value >= 0)
        {
            int variable_map_array = 0;
            int no_var = 0;
            for (int i = 0; i < variable; i++)
            {
                no_var = nlu_obj->nlu_variable_data->variable_phrase_sizes[i];
                no_var = MAX(no_var, 1);
                variable_map_array += no_var;
            }

            variable_values[var_idx].value =
                variable_value + variable_map_array;
            variable_values[var_idx].unit_idx = -1;
            var_idx++;

            CY_VA_PRINTF_TRACE("Variable value: (%d + %d) %s\n\r",
                               variable_value, variable_map_array,
                               nlu_obj->nlu_variable_data
                                   ->variable_phrase_list[variable_value +
                                                          variable_map_array]);
        }
        else
        {
            CY_VA_PRINTF_TRACE("\r\n");
            for (int n = 0; n < num_numbers; n++)
            {
                variable_values[var_idx].value = atoi(number[n]);
                size_t numElements =
                    nlu_obj->nlu_variable_data->NUM_UNIT_PHRASES;
                for (size_t i = 0; i < numElements; i++)
                {
                    if (strcasecmp(units[n], nlu_obj->nlu_variable_data
                                                 ->unit_phrase_list[i]) == 0)
                    {
                        variable_values[var_idx].unit_idx = i;
                        break;
                    }
                }
                var_idx++;

                CY_VA_PRINTF_TRACE("Variable number %d\n\r", n);
                CY_VA_PRINTF_TRACE("Number value: %d\n\r",
                                   variable_values[var_idx].value);
                CY_VA_PRINTF_TRACE("Number unit: %s", units[n]);
            }
        }
    }

    *var_size = var_idx;
}
