/***************************************************************************
* File Name        : Smart_Lights_Demo_config.h
*
* Description      : This the header file of WWD and NLU configuration object
*
* Related Document : See README.md
*******************************************************************************
* Copyright 2025, Cypress Semiconductor Corporation (an Infineon company)
* All rights reserved.
*******************************************************************************
* This software, including source code, documentation and related materials
* ("Software"), is owned by Cypress Semiconductor Corporation or one of its
* subsidiaries ("Cypress") and is protected by and subject to worldwide patent
* protection (United States and foreign), United States copyright laws and
* international treaty provisions. Therefore, you may use this Software only
* as provided in the license agreement accompanying the software package from
* which you obtained this Software ("EULA").
*
* If no EULA applies, Cypress hereby grants you a personal, non-exclusive,
* non-transferable license to copy, modify, and compile the Software source
* code solely for use in connection with Cypress's integrated circuit products.
* Any reproduction, modification, translation, compilation, or representation
* of this Software except as specified above is prohibited without the express
* written permission of Cypress.
*
* Disclaimer: THIS SOFTWARE IS PROVIDED AS-IS, WITH NO WARRANTY OF ANY KIND,
* EXPRESS OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, NONINFRINGEMENT, IMPLIED
* WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. Cypress
* reserves the right to make changes to the Software without notice. Cypress
* does not assume any liability arising out of the application or use of the
* Software or any product or circuit described in the Software. Cypress does
* not authorize its products for use in any products where a malfunction or
* failure of the Cypress product may reasonably be expected to result in
* significant property damage, injury or death ("High Risk Product"). By
* including Cypress's product in a High Risk Product, the manufacturer of such
* system or application assumes all risk of such use and in doing so agrees to
* indemnity Cypress against all liability.
*******************************************************************************/
#ifndef PROJ_CM55_INC_SMART_LIGHTS_DEMO_CONFIG_H_
#define PROJ_CM55_INC_SMART_LIGHTS_DEMO_CONFIG_H_

#include "mtb_wwd_nlu_common.h"

#define SMART_LIGHTS_DEMO_NO_MAX_WAKE_WORD 8
#define SMART_LIGHTS_DEMO_NO_OF_WAKE_WORD 1

#define SMART_LIGHTS_DEMO_WAKE_WORD_1 0x01

#define SMART_LIGHTS_DEMO_ALL_WAKE_WORD 0x01
void Smart_Lights_Demo_wake_word_callback(mtb_wwd_nlu_events_t event);
extern char *Smart_Lights_Demo_ww_str[SMART_LIGHTS_DEMO_NO_OF_WAKE_WORD];

// configuration object
extern mtb_wwd_nlu_config_t *Smart_Lights_Demo_ww_nlu_configs[SMART_LIGHTS_DEMO_NO_OF_WAKE_WORD];

#endif /* PROJ_CM55_INC_SMART_LIGHTS_DEMO_CONFIG_H_ */
