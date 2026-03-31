/*
 * Copyright (c) 2006-2021, RT-Thread Development Team
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Change Logs:
 * Date           Author       Notes
 * 2026-03-19     ASUS         the first version
 */

#include <rtthread.h>

#include "drv_can.h"
#include "CAN_config.h"

#ifdef BSP_USING_CAN

#ifndef IFX_CAN_FORCE_CLASSIC
#define IFX_CAN_FORCE_CLASSIC 1
#endif

enum
{
#ifdef BSP_USING_CANFD0
    CANFD0_INDEX,
#endif
};

static struct ifx_can_config can_config[] =
{
#ifdef BSP_USING_CANFD0
    CANFD0_CONFIG,
#endif
};

#if !defined(BSP_USING_CANFD0)
#error "BSP_USING_CAN is enabled, but no CANFD instance is selected."
#endif

static struct ifx_can can_obj[sizeof(can_config) / sizeof(can_config[0])] = {0};

static const rt_uint8_t can_dlc_to_len_table[16] =
{
    0, 1, 2, 3, 4, 5, 6, 7,
    8, 12, 16, 20, 24, 32, 48, 64,
};

static rt_uint8_t can_len_to_dlc(rt_uint8_t len, rt_bool_t fd_frame)
{
    if (!fd_frame)
    {
        return (len > 8U) ? 8U : len;
    }

    if (len <= 8U)
    {
        return len;
    }
    if (len <= 12U)
    {
        return 9U;
    }
    if (len <= 16U)
    {
        return 10U;
    }
    if (len <= 20U)
    {
        return 11U;
    }
    if (len <= 24U)
    {
        return 12U;
    }
    if (len <= 32U)
    {
        return 13U;
    }
    if (len <= 48U)
    {
        return 14U;
    }

    return 15U;
}

static rt_uint8_t can_dlc_to_len(rt_uint8_t dlc)
{
    return can_dlc_to_len_table[(dlc < 16U) ? dlc : 15U];
}

static void can_apply_mode(struct ifx_can *can, rt_uint32_t mode)
{
    cy_stc_canfd_test_mode_t test_mode = CY_CANFD_TEST_MODE_DISABLE;

    if (mode == RT_CAN_MODE_LISTEN)
    {
        test_mode = CY_CANFD_TEST_MODE_BUS_MONITORING;
    }
    else if ((mode == RT_CAN_MODE_LOOPBACK) || (mode == RT_CAN_MODE_LOOPBACKANLISTEN))
    {
        test_mode = CY_CANFD_TEST_MODE_INTERNAL_LOOP_BACK;
    }

    if (Cy_CANFD_ConfigChangesEnable(can->config->can_x, can->config->channel) == CY_CANFD_SUCCESS)
    {
        Cy_CANFD_TestModeConfig(can->config->can_x, can->config->channel, test_mode);
        (void)Cy_CANFD_ConfigChangesDisable(can->config->can_x, can->config->channel);
    }
}

static void can_report_tx_done(struct ifx_can *can)
{
    rt_uint32_t idx;

    for (idx = 0; idx < 32U; idx++)
    {
        rt_uint32_t mask = (1UL << idx);

        if ((can->tx_pending_mask & mask) == 0U)
        {
            continue;
        }

        switch (Cy_CANFD_GetTxBufferStatus(can->config->can_x, can->config->channel, (uint8_t)idx))
        {
        case CY_CANFD_TX_BUFFER_PENDING:
            break;

        case CY_CANFD_TX_BUFFER_CANCEL_FINISHED:
            can->tx_pending_mask &= ~mask;
            rt_hw_can_isr(&can->device, RT_CAN_EVENT_TX_FAIL | (idx << 8));
            break;

        default:
            can->tx_pending_mask &= ~mask;
            rt_hw_can_isr(&can->device, RT_CAN_EVENT_TX_DONE | (idx << 8));
            break;
        }
    }
}

static void can_irq_handler(struct ifx_can *can)
{
    rt_uint32_t status;

    status = Cy_CANFD_GetInterruptStatus(can->config->can_x, can->config->channel);
    if (status == 0U)
    {
        return;
    }

    Cy_CANFD_ClearInterrupt(can->config->can_x, can->config->channel, status);

    if ((status & CY_CANFD_RX_FIFO_0_NEW_MESSAGE) != 0U)
    {
        rt_hw_can_isr(&can->device, RT_CAN_EVENT_RX_IND | (CY_CANFD_RX_FIFO0 << 8));
    }

    if ((status & CY_CANFD_RX_FIFO_1_NEW_MESSAGE) != 0U)
    {
        rt_hw_can_isr(&can->device, RT_CAN_EVENT_RX_IND | (CY_CANFD_RX_FIFO1 << 8));
    }

    if ((status & (CY_CANFD_RX_FIFO_0_MSG_LOST | CY_CANFD_RX_FIFO_1_MSG_LOST)) != 0U)
    {
        rt_hw_can_isr(&can->device, RT_CAN_EVENT_RXOF_IND);
    }

    if ((status & (CY_CANFD_TRANSMISSION_COMPLETE | CY_CANFD_TRANSMISSION_CANCEL_FINISHED)) != 0U)
    {
        can_report_tx_done(can);
    }
}

#ifdef BSP_USING_CANFD0
void canfd0_isr_callback(void)
{
    rt_interrupt_enter();
    can_irq_handler(&can_obj[CANFD0_INDEX]);
    rt_interrupt_leave();
}
#endif

static rt_err_t ifx_can_configure(struct rt_can_device *device, struct can_configure *cfg)
{
    cy_en_canfd_status_t result;
    struct ifx_can *can;

    RT_ASSERT(device != RT_NULL);
    RT_ASSERT(cfg != RT_NULL);

    can = (struct ifx_can *)device->parent.user_data;
    RT_ASSERT(can != RT_NULL);

    Cy_CANFD_Enable(can->config->can_x, (1UL << can->config->channel));
    result = Cy_CANFD_Init(can->config->can_x, can->config->channel, can->config->canfd_config, &can->context);
    if (result != CY_CANFD_SUCCESS)
    {
        return -RT_ERROR;
    }

    can_apply_mode(can, cfg->mode);
    can->irq_mask = 0U;
    can->tx_pending_mask = 0U;

    return RT_EOK;
}

static rt_err_t ifx_can_control(struct rt_can_device *device, int cmd, void *arg)
{
    struct ifx_can *can;
    rt_ubase_t flag;

    RT_ASSERT(device != RT_NULL);

    can = (struct ifx_can *)device->parent.user_data;
    RT_ASSERT(can != RT_NULL);

    switch (cmd)
    {
    case RT_DEVICE_CTRL_SET_INT:
        flag = (rt_ubase_t)arg;

        if ((flag & RT_DEVICE_FLAG_INT_RX) != 0U)
        {
            can->irq_mask |= (CY_CANFD_RX_FIFO_0_NEW_MESSAGE | CY_CANFD_RX_FIFO_1_NEW_MESSAGE |
                              CY_CANFD_RX_FIFO_0_MSG_LOST | CY_CANFD_RX_FIFO_1_MSG_LOST);
        }

        if ((flag & RT_DEVICE_FLAG_INT_TX) != 0U)
        {
            can->irq_mask |= (CY_CANFD_TRANSMISSION_COMPLETE | CY_CANFD_TRANSMISSION_CANCEL_FINISHED);
        }

        if ((flag & RT_DEVICE_CAN_INT_ERR) != 0U)
        {
            can->irq_mask |= (CY_CANFD_WARNING_STATUS | CY_CANFD_ERROR_PASSIVE | CY_CANFD_BUS_OFF_STATUS);
        }

        Cy_CANFD_SetInterruptMask(can->config->can_x, can->config->channel, can->irq_mask);
        Cy_CANFD_EnableInterruptLine(can->config->can_x, can->config->channel, CY_CANFD_INTERRUPT_LINE_0_EN);
        Cy_SysInt_Init(can->config->irq_cfg, can->config->userIsr);
        NVIC_EnableIRQ(can->config->intrSrc);
        return RT_EOK;

    case RT_DEVICE_CTRL_CLR_INT:
        flag = (rt_ubase_t)arg;

        if ((flag & RT_DEVICE_FLAG_INT_RX) != 0U)
        {
            can->irq_mask &= ~(CY_CANFD_RX_FIFO_0_NEW_MESSAGE | CY_CANFD_RX_FIFO_1_NEW_MESSAGE |
                               CY_CANFD_RX_FIFO_0_MSG_LOST | CY_CANFD_RX_FIFO_1_MSG_LOST);
        }

        if ((flag & RT_DEVICE_FLAG_INT_TX) != 0U)
        {
            can->irq_mask &= ~(CY_CANFD_TRANSMISSION_COMPLETE | CY_CANFD_TRANSMISSION_CANCEL_FINISHED);
        }

        if ((flag & RT_DEVICE_CAN_INT_ERR) != 0U)
        {
            can->irq_mask &= ~(CY_CANFD_WARNING_STATUS | CY_CANFD_ERROR_PASSIVE | CY_CANFD_BUS_OFF_STATUS);
        }

        Cy_CANFD_SetInterruptMask(can->config->can_x, can->config->channel, can->irq_mask);
        if (can->irq_mask == 0U)
        {
            NVIC_DisableIRQ(can->config->intrSrc);
        }
        return RT_EOK;

    case RT_CAN_CMD_SET_FILTER:
        return RT_EOK;

    default:
        return RT_EOK;
    }
}

static rt_ssize_t ifx_can_sendmsg(struct rt_can_device *device, const void *buf, rt_uint32_t boxno)
{
    cy_en_canfd_status_t result;
    const struct rt_can_msg *msg;
    struct ifx_can *can;
    rt_uint8_t dlc;
    rt_uint8_t len;
    rt_bool_t is_fd;

    RT_ASSERT(device != RT_NULL);
    RT_ASSERT(buf != RT_NULL);

    msg = (const struct rt_can_msg *)buf;
    can = (struct ifx_can *)device->parent.user_data;
    RT_ASSERT(can != RT_NULL);

#if defined(RT_CAN_USING_CANFD)
    is_fd = IFX_CAN_FORCE_CLASSIC ? RT_FALSE : ((msg->fd_frame != 0U) ? RT_TRUE : RT_FALSE);
#else
    is_fd = RT_FALSE;
#endif

    dlc = can_len_to_dlc((rt_uint8_t)msg->len, is_fd);
    len = can_dlc_to_len(dlc);

    can->tx_t0.id = msg->id;
    can->tx_t0.rtr = (msg->rtr != 0U) ? CY_CANFD_RTR_REMOTE_FRAME : CY_CANFD_RTR_DATA_FRAME;
    can->tx_t0.xtd = (msg->ide != 0U) ? CY_CANFD_XTD_EXTENDED_ID : CY_CANFD_XTD_STANDARD_ID;
    can->tx_t0.esi = CY_CANFD_ESI_ERROR_ACTIVE;

    can->tx_t1.dlc = dlc;
#if IFX_CAN_FORCE_CLASSIC
    can->tx_t1.brs = false;
    can->tx_t1.fdf = CY_CANFD_FDF_STANDARD_FRAME;
#elif defined(RT_CAN_USING_CANFD)
    can->tx_t1.brs = (msg->brs != 0U) ? true : false;
    can->tx_t1.fdf = is_fd ? CY_CANFD_FDF_CAN_FD_FRAME : CY_CANFD_FDF_STANDARD_FRAME;
#else
    can->tx_t1.brs = false;
    can->tx_t1.fdf = CY_CANFD_FDF_STANDARD_FRAME;
#endif
    can->tx_t1.efc = false;
    can->tx_t1.mm = 0U;

    rt_memset(can->tx_data, 0, sizeof(can->tx_data));
    if ((msg->rtr == RT_CAN_DTR) && (len > 0U))
    {
        rt_memcpy(can->tx_data, msg->data, len);
    }

    can->tx_buffer.t0_f = &can->tx_t0;
    can->tx_buffer.t1_f = &can->tx_t1;
    can->tx_buffer.data_area_f = can->tx_data;

    result = Cy_CANFD_UpdateAndTransmitMsgBuffer(can->config->can_x,
                                                  can->config->channel,
                                                  &can->tx_buffer,
                                                  (uint8_t)boxno,
                                                  &can->context);
    if (result != CY_CANFD_SUCCESS)
    {
        return -RT_ERROR;
    }

    if (boxno < 32U)
    {
        can->tx_pending_mask |= (1UL << boxno);
    }

    return RT_EOK;
}

static rt_ssize_t ifx_can_recvmsg(struct rt_can_device *device, void *buf, rt_uint32_t boxno)
{
    cy_en_canfd_status_t result;
    struct rt_can_msg *msg;
    struct ifx_can *can;
    rt_uint8_t dlc;
    rt_uint8_t len;

    RT_ASSERT(device != RT_NULL);
    RT_ASSERT(buf != RT_NULL);

    msg = (struct rt_can_msg *)buf;
    can = (struct ifx_can *)device->parent.user_data;
    RT_ASSERT(can != RT_NULL);

    can->rx_buffer.r0_f = &can->rx_r0;
    can->rx_buffer.r1_f = &can->rx_r1;
    can->rx_buffer.data_area_f = can->rx_data;
    rt_memset(can->rx_data, 0, sizeof(can->rx_data));

    result = Cy_CANFD_ExtractMsgFromRXBuffer(can->config->can_x,
                                             can->config->channel,
                                             true,
                                             (uint8_t)boxno,
                                             &can->rx_buffer,
                                             &can->context);
    if (result != CY_CANFD_SUCCESS)
    {
        return -RT_ERROR;
    }

    msg->id = can->rx_r0.id;
    msg->ide = (can->rx_r0.xtd == CY_CANFD_XTD_EXTENDED_ID) ? 1U : 0U;
    msg->rtr = (can->rx_r0.rtr == CY_CANFD_RTR_REMOTE_FRAME) ? 1U : 0U;
    msg->hdr_index = (rt_int8_t)can->rx_r1.fidx;

    dlc = (rt_uint8_t)can->rx_r1.dlc;
    len = can_dlc_to_len(dlc);
    msg->len = len;
    msg->rxfifo = boxno;
#if defined(RT_CAN_USING_CANFD)
#if IFX_CAN_FORCE_CLASSIC
    msg->fd_frame = 0U;
    msg->brs = 0U;
#else
    msg->fd_frame = (can->rx_r1.fdf == CY_CANFD_FDF_CAN_FD_FRAME) ? 1U : 0U;
    msg->brs = can->rx_r1.brs ? 1U : 0U;
#endif
#endif

    if (len > 0U)
    {
        rt_memcpy(msg->data, can->rx_data, len);
    }

    Cy_CANFD_AckRxFifo(can->config->can_x, can->config->channel, boxno);

    return RT_EOK;
}

static const struct rt_can_ops ifx_can_ops =
{
    .configure = ifx_can_configure,
    .control = ifx_can_control,
    .sendmsg = ifx_can_sendmsg,
    .recvmsg = ifx_can_recvmsg,
};

int rt_hw_can_init(void)
{
    rt_err_t result;
    rt_size_t i;
    struct can_configure config = CANDEFAULTCONFIG;

#if defined(RT_CAN_USING_CANFD)
#if IFX_CAN_FORCE_CLASSIC
    config.enable_canfd = 0;
#else
    config.enable_canfd = 1;
#endif
    config.baud_rate_fd = CAN1MBaud;
#endif
    config.baud_rate = CAN1MBaud;
#ifdef RT_CAN_USING_HDR
    config.maxhdr = 14;
#endif

    for (i = 0; i < (sizeof(can_obj) / sizeof(can_obj[0])); i++)
    {
        can_obj[i].config = &can_config[i];
        can_obj[i].device.config = config;

        result = rt_hw_can_register(&can_obj[i].device,
                                    can_obj[i].config->name,
                                    &ifx_can_ops,
                                    &can_obj[i]);
        if (result != RT_EOK)
        {
            return result;
        }
    }

    return RT_EOK;
}
INIT_BOARD_EXPORT(rt_hw_can_init);

#endif /* BSP_USING_CAN */

