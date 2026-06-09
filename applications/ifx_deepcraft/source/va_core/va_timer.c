/***************************************************************************//**
 * \file va_timer.c
 *
 * \brief
 * The file contains timer related functionality
 *
 *******************************************************************************
 * (c) 2019-2025, Cypress Semiconductor Corporation (an Infineon company) or
 * an affiliate of Cypress Semiconductor Corporation.  All rights reserved.
 *******************************************************************************/
#include "va_timer.h"
#include <stddef.h>

#define TIMER_COUNTER_RESET_VALUE 0xFFFFFFFF

void va_timer_reset(va_timer_t *timer)
{
    if (timer == NULL)
        return;
    timer->state = VA_TIMER_INACTIVE;
    timer->counter = TIMER_COUNTER_RESET_VALUE;
}

void va_timer_start(va_timer_t *timer, int32_t timeout_counter)
{
    if (timer == NULL || timer->state == VA_TIMER_DISABLED)
        return;

    if (timeout_counter <= 0)
    {
        timer->state = VA_TIMER_DISABLED;
        timer->counter = TIMER_COUNTER_RESET_VALUE;
        return;
    }

    timer->state = VA_TIMER_ACTIVE;
    timer->counter = timeout_counter;
}

va_timer_state_t va_timer_tick(va_timer_t *timer)
{
    if (timer == NULL)
        return VA_TIMER_NOT_INITIALIZED;

    if (timer->state != VA_TIMER_ACTIVE)
    {
        return timer->state;
    }

    if (timer->counter > 0)
    {
        timer->counter--;
        if (timer->counter == 0)
        {
            timer->state = VA_TIMER_EXPIRED;
        }
    }

    return timer->state;
}
