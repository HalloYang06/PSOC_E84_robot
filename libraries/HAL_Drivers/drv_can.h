/*
 * Copyright (c) 2006-2021, RT-Thread Development Team
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Change Logs:
 * Date           Author       Notes
 * 2026-03-19     ASUS       the first version
 */
#ifndef __DRV_CAN_H__
#define __DRV_CAN_H__

#include <rthw.h>
#include <rtdevice.h>

#include "board.h"
#include "cy_canfd.h"

#define canfd_isr_callback(name) name##_isr_callback

#define IFX_CAN_CMD_POLL_RX 0x1001

struct ifx_can_config
{
    const char *name;
    CANFD_Type *can_x;
    uint32_t channel;
#if defined(SOC_SERIES_IFX_XMC)
    rt_uint32_t intrSrc;
#else
    IRQn_Type intrSrc;
#endif
    cy_israddress userIsr;
    cy_stc_sysint_t *irq_cfg;
    const cy_stc_canfd_config_t *canfd_config;
};

struct ifx_can
{
    struct ifx_can_config *config;
    struct rt_can_device device;
    cy_stc_canfd_context_t context;
    rt_uint32_t irq_mask;
    rt_uint32_t tx_pending_mask;

    cy_stc_canfd_r0_t rx_r0;
    cy_stc_canfd_r1_t rx_r1;
    uint32_t rx_data[16];
    cy_stc_canfd_rx_buffer_t rx_buffer;

    cy_stc_canfd_t0_t tx_t0;
    cy_stc_canfd_t1_t tx_t1;
    uint32_t tx_data[16];
    cy_stc_canfd_tx_buffer_t tx_buffer;
};

int rt_hw_can_init(void);
rt_err_t ifx_can_direct_init(void);
rt_err_t ifx_can_direct_reinit_bitrate(rt_uint32_t bitrate);
rt_err_t ifx_can_direct_send(const struct rt_can_msg *msg);
rt_ssize_t ifx_can_direct_recv(struct rt_can_msg *msg);
void ifx_can_direct_set_raw_rx_pause(rt_bool_t pause);

#endif /* __DRV_CAN_H__ */
