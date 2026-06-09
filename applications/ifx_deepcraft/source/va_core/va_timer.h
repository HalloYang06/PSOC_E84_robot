/*
 * (c) 2026, Infineon Technologies AG, or an affiliate of Infineon
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
 */

/**
 * @file va_timer.h
 * @brief This the header file of ModusToolbox NLU and WWD middleware timer
 * utility module
 *
 */

#ifndef VA_INC_TIMER_H
#define VA_INC_TIMER_H

#if defined(__cplusplus)
extern "C" {
#endif

#include <stdint.h>

/**
 * @defgroup va_timer VA Timer Types
 * @brief Types for voice-assistant timer.
 */

/******************************************************************************
 * Typedefs
 *****************************************************************************/
/**
 * @enum va_timer_state_t
 * @ingroup va_timer
 * @brief Timer state.
 *
 * This enum represents the state of the timer.
 */
typedef enum {
    VA_TIMER_NOT_INITIALIZED = 0,
    VA_TIMER_INACTIVE,
    VA_TIMER_ACTIVE,
    VA_TIMER_EXPIRED,
    VA_TIMER_DISABLED
} va_timer_state_t;

/******************************************************************************
 * Structures
 ******************************************************************************/
/**
 * @struct va_timer_t
 * @ingroup va_timer
 * @brief Timer structure.
 *
 * This structure holds the state and timing counter information for the timer.
 *
 * @var va_timer_t::state
 *   Current timer state.
 * @var va_timer_t::counter
 *   Current counter value.
 */
typedef struct {
    va_timer_state_t state; /**< Current timer state. */
    int32_t counter;        /**< Current counter value. */
} va_timer_t;

/*******************************************************************************
 * Function Prototypes
 *******************************************************************************/

/**
 * \brief Starts the timer with a specified timeout value
 *
 * \param[in,out] timer        : Pointer to the timer structure. If NULL, the
 * function returns without performing any action.
 * \param[in] timeout_counter  : The initial counter value. The timer will
 * expire after this many calls to va_timer_tick().
 *
 * \note Calling this function on an already active timer will restart it with
 * the new timeout.
 *
 * \ingroup va_timer
 */
void va_timer_start(va_timer_t *timer, int32_t timeout_counter);

/**
 * \brief Updates the timer state and counter
 *
 * \param[in,out] timer : Pointer to the timer structure.
 * \return              : VA_TIMER_NOT_INITIALIZED - timer is NULL
 *                        VA_TIMER_INACTIVE - timer is not active
 *                        VA_TIMER_ACTIVE - timer is counting down (counter > 0)
 *                        VA_TIMER_EXPIRED - timer has reached zero
 *
 * \note Only active timers are affected by this function. Inactive or expired
 * timers retain their state until explicitly started or reset.
 *
 * \ingroup va_timer
 */
va_timer_state_t va_timer_tick(va_timer_t *timer);

/**
 * \brief Stop the timer, reset it's counter and set it to inactive state
 *
 * \param[in,out] timer : Pointer to the timer structure.
 *
 * \ingroup va_timer
 */
void va_timer_reset(va_timer_t *timer);

#if defined(__cplusplus)
}
#endif

#endif /* VA_INC_TIMER_H */
