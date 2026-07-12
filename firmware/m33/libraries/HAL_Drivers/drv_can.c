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
#include "cy_gpio.h"
#include "cy_sysclk.h"
#include "cycfg_peripheral_clocks.h"
#include "cycfg_system.h"
#include "gpio_pse84_bga_220.h"

#ifdef BSP_USING_CAN

#ifndef CANFD_ECR
#define CANFD_ECR(base, chan) (((CANFD_Type *)(base))->CH[chan].M_TTCAN.ECR)
#endif

#ifndef IFX_CAN_FORCE_CLASSIC
#define IFX_CAN_FORCE_CLASSIC 1
#endif

#ifndef IFX_CAN_TX_WAIT_MS
#define IFX_CAN_TX_WAIT_MS 20U
#endif

#ifndef IFX_CAN_RX_DRAIN_LIMIT
#define IFX_CAN_RX_DRAIN_LIMIT 16U
#endif

#ifndef IFX_CAN_ENABLE_NVIC
#define IFX_CAN_ENABLE_NVIC 0
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
static rt_bool_t g_canfd0_hw_prepared = RT_FALSE;
static rt_bool_t g_canfd0_mmio_prepared = RT_FALSE;
static rt_bool_t g_can_direct_ready = RT_FALSE;
static volatile rt_bool_t g_can_direct_raw_rx_pause = RT_FALSE;
static volatile rt_bool_t g_can_direct_tx_verbose = RT_FALSE;
static rt_uint32_t g_can_direct_tx_pending_suppressed = 0;
static rt_uint8_t g_can_direct_tx_index = 0U;
static rt_uint32_t g_can_direct_tx_timeout_count = 0U;
static rt_uint32_t g_can_direct_tx_send_fail_count = 0U;
static rt_uint32_t g_can_direct_rx_extract_fail_count = 0U;
static rt_uint32_t g_can_direct_rx_fifo0_lost_count = 0U;
static rt_uint32_t g_can_direct_rx_fifo0_full_count = 0U;
static rt_bool_t g_can_direct_rx_fifo0_lost_latched = RT_FALSE;
static rt_bool_t g_can_direct_rx_fifo0_full_latched = RT_FALSE;
#ifdef BSP_USING_CANFD0
static rt_uint32_t g_can_direct_bitrate = 1000000U;
static cy_stc_canfd_bitrate_t g_can_direct_nominal_bitrate;
static cy_stc_canfd_bitrate_t g_can_direct_fast_bitrate;
static cy_stc_canfd_config_t g_can_direct_canfd_config;
#endif

void ifx_can_direct_set_raw_rx_pause(rt_bool_t pause)
{
    g_can_direct_raw_rx_pause = pause ? RT_TRUE : RT_FALSE;
}

void ifx_can_direct_set_tx_verbose(rt_bool_t verbose)
{
    g_can_direct_tx_verbose = verbose ? RT_TRUE : RT_FALSE;
}

static int cmd_can_tx_log(int argc, char **argv)
{
    rt_bool_t verbose;

    if (argc < 2)
    {
        rt_kprintf("usage: cmd_can_tx_log <0|1>\n");
        rt_kprintf("current verbose=%d suppressed=%lu\n",
                   g_can_direct_tx_verbose ? 1 : 0,
                   (unsigned long)g_can_direct_tx_pending_suppressed);
        return 0;
    }

    verbose = (argv[1][0] != '0') ? RT_TRUE : RT_FALSE;
    ifx_can_direct_set_tx_verbose(verbose);
    rt_kprintf("[drv_can] tx verbose=%d\n", verbose ? 1 : 0);
    return 0;
}
MSH_CMD_EXPORT(cmd_can_tx_log, enable verbose CAN TX timeout register logging);

#ifdef BSP_USING_CANFD0
static rt_uint32_t ifx_can_direct_prescaler_for_bitrate(rt_uint32_t bitrate)
{
    switch (bitrate)
    {
    case 1000000U:
        return 0U;

    case 500000U:
        return 1U;

    case 250000U:
        return 3U;

    case 125000U:
        return 7U;

    default:
        return 0xFFFFFFFFUL;
    }
}

static void ifx_can_direct_apply_bitrate_config(rt_uint32_t bitrate)
{
    rt_uint32_t prescaler = ifx_can_direct_prescaler_for_bitrate(bitrate);

    if (prescaler == 0xFFFFFFFFUL)
    {
        prescaler = 0U;
        bitrate = 1000000U;
    }

    g_can_direct_nominal_bitrate = ifx_canfd0_nominal_bitrate;
    g_can_direct_nominal_bitrate.prescaler = prescaler;
    g_can_direct_fast_bitrate = ifx_canfd0_fast_bitrate;
    g_can_direct_fast_bitrate.prescaler = prescaler;

    g_can_direct_canfd_config = ifx_canfd0_default_config;
    g_can_direct_canfd_config.bitrate = &g_can_direct_nominal_bitrate;
    g_can_direct_canfd_config.fastBitrate = &g_can_direct_fast_bitrate;

    can_config[CANFD0_INDEX].canfd_config = &g_can_direct_canfd_config;
    g_can_direct_bitrate = bitrate;
}
#endif

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

static void ifx_canfd0_cancel_tx_buffer(struct ifx_can *can, rt_uint8_t tx_index)
{
#ifdef BSP_USING_CANFD0
    rt_uint32_t mask = 1UL << tx_index;
    rt_uint32_t waited_ms;

    if (can == RT_NULL)
    {
        return;
    }

    if ((CANFD_TXBRP(can->config->can_x, can->config->channel) & mask) == 0U)
    {
        return;
    }

    CANFD_TXBCR(can->config->can_x, can->config->channel) = mask;
    for (waited_ms = 0U; waited_ms < IFX_CAN_TX_WAIT_MS; waited_ms++)
    {
        if ((CANFD_TXBRP(can->config->can_x, can->config->channel) & mask) == 0U)
        {
            return;
        }
        rt_thread_mdelay(1);
    }
#else
    RT_UNUSED(can);
    RT_UNUSED(tx_index);
#endif
}

static void ifx_canfd0_prepare_hw(void)
{
#ifdef BSP_USING_CANFD0
    cy_stc_gpio_pin_config_t rx_pin_cfg;
    cy_stc_gpio_pin_config_t tx_pin_cfg;

    if (g_canfd0_hw_prepared)
    {
        return;
    }

    if (!g_canfd0_mmio_prepared)
    {
        rt_kprintf("[drv_can] mmio step1 init hsiom\n");
        Cy_SysClk_PeriGroupSlaveInit(
            CY_MMIO_HSIOM_PERI_NR,
            CY_MMIO_HSIOM_GROUP_NR,
            CY_MMIO_HSIOM_SLAVE_NR,
            CY_MMIO_HSIOM_CLK_HF_NR);

        rt_kprintf("[drv_can] mmio step2 init gpio\n");
        Cy_SysClk_PeriGroupSlaveInit(
            CY_MMIO_GPIO_PERI_NR,
            CY_MMIO_GPIO_GROUP_NR,
            CY_MMIO_GPIO_SLAVE_NR,
            CY_MMIO_GPIO_CLK_HF_NR);

        rt_kprintf("[drv_can] mmio step3 init canfd0\n");
        Cy_SysClk_PeriGroupSlaveInit(
            CY_MMIO_CANFD0_PERI_NR,
            CY_MMIO_CANFD0_GROUP_NR,
            CY_MMIO_CANFD0_SLAVE_NR,
            CY_MMIO_CANFD0_CLK_HF_NR);

        g_canfd0_mmio_prepared = RT_TRUE;
        rt_kprintf("[drv_can] mmio step4 done\n");
    }

    rt_kprintf("[drv_can] hw prep step1 assign pclk\n");
    Cy_SysClk_PeriPclkAssignDivider(PCLK_CANFD0_CLOCK_CAN_EN0, CY_SYSCLK_DIV_8_BIT, 4U);
    Cy_SysClk_PeriPclkAssignDivider(PCLK_CANFD0_CLOCK_CAN_EN1, CY_SYSCLK_DIV_8_BIT, 4U);
    Cy_SysClk_PeriPclkSetDivider(PCLK_CANFD0_CLOCK_CAN_EN0, CY_SYSCLK_DIV_8_BIT, 4U, 4U);
    Cy_SysClk_PeriPclkSetDivider(PCLK_CANFD0_CLOCK_CAN_EN1, CY_SYSCLK_DIV_8_BIT, 4U, 4U);
    Cy_SysClk_PeriPclkEnableDivider(PCLK_CANFD0_CLOCK_CAN_EN0, CY_SYSCLK_DIV_8_BIT, 4U);
    Cy_SysClk_PeriPclkEnableDivider(PCLK_CANFD0_CLOCK_CAN_EN1, CY_SYSCLK_DIV_8_BIT, 4U);

    rt_kprintf("[drv_can] hw prep step2 config p16.0 rx\n");
    rx_pin_cfg.outVal = 1U;
    rx_pin_cfg.driveMode = CY_GPIO_DM_HIGHZ;
    rx_pin_cfg.hsiom = P16_0_CANFD0_TTCAN_RX0;
    rx_pin_cfg.intEdge = CY_GPIO_INTR_DISABLE;
    rx_pin_cfg.intMask = 0UL;
    rx_pin_cfg.vtrip = CY_GPIO_VTRIP_CMOS;
    rx_pin_cfg.slewRate = CY_GPIO_SLEW_FAST;
    rx_pin_cfg.driveSel = CY_GPIO_DRIVE_1_2;
    rx_pin_cfg.vregEn = 0UL;
    rx_pin_cfg.ibufMode = 0UL;
    rx_pin_cfg.vtripSel = 0UL;
    rx_pin_cfg.vrefSel = 0UL;
    rx_pin_cfg.vohSel = 0UL;
    rx_pin_cfg.pullUpRes = CY_GPIO_PULLUP_RES_DISABLE;
    rx_pin_cfg.nonSec = 1UL;
    Cy_GPIO_Pin_Init(P16_0_PORT, P16_0_PIN, &rx_pin_cfg);

    rt_kprintf("[drv_can] hw prep step3 config p16.1 tx\n");
    tx_pin_cfg.outVal = 1U;
    tx_pin_cfg.driveMode = CY_GPIO_DM_STRONG_IN_OFF;
    tx_pin_cfg.hsiom = P16_1_CANFD0_TTCAN_TX0;
    tx_pin_cfg.intEdge = CY_GPIO_INTR_DISABLE;
    tx_pin_cfg.intMask = 0UL;
    tx_pin_cfg.vtrip = CY_GPIO_VTRIP_CMOS;
    tx_pin_cfg.slewRate = CY_GPIO_SLEW_FAST;
    tx_pin_cfg.driveSel = CY_GPIO_DRIVE_1_2;
    tx_pin_cfg.vregEn = 0UL;
    tx_pin_cfg.ibufMode = 0UL;
    tx_pin_cfg.vtripSel = 0UL;
    tx_pin_cfg.vrefSel = 0UL;
    tx_pin_cfg.vohSel = 0UL;
    tx_pin_cfg.pullUpRes = CY_GPIO_PULLUP_RES_DISABLE;
    tx_pin_cfg.nonSec = 1UL;
    Cy_GPIO_Pin_Init(P16_1_PORT, P16_1_PIN, &tx_pin_cfg);

    g_canfd0_hw_prepared = RT_TRUE;
    rt_kprintf("[drv_can] hw prep step4 done\n");
#endif
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

static void can_wait_tx_done_or_fail(struct ifx_can *can, rt_uint8_t idx)
{
    rt_uint32_t mask = (1UL << idx);
    rt_uint32_t waited_ms;

    for (waited_ms = 0U; waited_ms <= IFX_CAN_TX_WAIT_MS; waited_ms++)
    {
        can_report_tx_done(can);
        if ((can->tx_pending_mask & mask) == 0U)
        {
            return;
        }

        if (waited_ms < IFX_CAN_TX_WAIT_MS)
        {
            rt_thread_mdelay(1);
        }
    }

    can->tx_pending_mask &= ~mask;
    rt_kprintf("[drv_can] tx timeout box=%u\n", (unsigned int)idx);
    rt_hw_can_isr(&can->device, RT_CAN_EVENT_TX_FAIL | ((rt_uint32_t)idx << 8));
}

static void can_report_rx_fifo(struct ifx_can *can, rt_uint32_t fifo)
{
    rt_uint32_t count;

    for (count = 0U; count < IFX_CAN_RX_DRAIN_LIMIT; count++)
    {
        rt_uint32_t fill;

        if (fifo == CY_CANFD_RX_FIFO0)
        {
            fill = _FLD2VAL(CANFD_CH_M_TTCAN_RXF0S_F0FL,
                            CANFD_RXF0S(can->config->can_x, can->config->channel));
        }
        else
        {
            fill = _FLD2VAL(CANFD_CH_M_TTCAN_RXF1S_F1FL,
                            CANFD_RXF1S(can->config->can_x, can->config->channel));
        }

        if (fill == 0U)
        {
            break;
        }

        rt_hw_can_isr(&can->device, RT_CAN_EVENT_RX_IND | (fifo << 8));
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
        can_report_rx_fifo(can, CY_CANFD_RX_FIFO0);
    }

    if ((status & CY_CANFD_RX_FIFO_1_NEW_MESSAGE) != 0U)
    {
        can_report_rx_fifo(can, CY_CANFD_RX_FIFO1);
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

    ifx_canfd0_prepare_hw();
    rt_kprintf("[drv_can] configure step1 base=0x%08lx ch=%lu mram=0x%08lx\n",
               (unsigned long)can->config->can_x,
               (unsigned long)can->config->channel,
               (unsigned long)can->config->canfd_config->messageRAMaddress);
    rt_kprintf("[drv_can] configure step1.1 ctl=0x%08lx status=0x%08lx\n",
               (unsigned long)CANFD_CTL(can->config->can_x),
               (unsigned long)CANFD_STATUS(can->config->can_x));
    rt_kprintf("[drv_can] configure step2 enable\n");
    Cy_CANFD_Enable(can->config->can_x, (1UL << can->config->channel));
    rt_kprintf("[drv_can] configure step3 init\n");
    result = Cy_CANFD_Init(can->config->can_x, can->config->channel, can->config->canfd_config, &can->context);
    rt_kprintf("[drv_can] configure step4 init ret=%d\n", result);
    if (result != CY_CANFD_SUCCESS)
    {
        return -RT_ERROR;
    }

    can_apply_mode(can, cfg->mode);
    rt_kprintf("[drv_can] configure step5 mode=%lu\n", (unsigned long)cfg->mode);
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
        rt_kprintf("[drv_can] set_int step1 flag=0x%08lx\n", (unsigned long)flag);

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
            rt_kprintf("[drv_can] set_int skip err mask during bring-up\n");
        }

        rt_kprintf("[drv_can] set_int step2 mask=0x%08lx\n", (unsigned long)can->irq_mask);
        Cy_CANFD_ClearInterrupt(can->config->can_x,
                                can->config->channel,
                                0xFFFFFFFFUL);
        NVIC_ClearPendingIRQ(can->config->intrSrc);
#if IFX_CAN_ENABLE_NVIC
        Cy_CANFD_SetInterruptMask(can->config->can_x, can->config->channel, can->irq_mask);
        rt_kprintf("[drv_can] set_int step3 line enable\n");
        Cy_CANFD_EnableInterruptLine(can->config->can_x, can->config->channel, CY_CANFD_INTERRUPT_LINE_0_EN);
        rt_kprintf("[drv_can] set_int step4 sysint init irqn=%ld\n", (long)can->config->intrSrc);
        Cy_SysInt_Init(can->config->irq_cfg, can->config->userIsr);
        rt_kprintf("[drv_can] set_int step5 nvic enable\n");
        NVIC_EnableIRQ(can->config->intrSrc);
        rt_kprintf("[drv_can] set_int step6 done\n");
#else
        Cy_CANFD_SetInterruptMask(can->config->can_x, can->config->channel, 0U);
        Cy_CANFD_EnableInterruptLine(can->config->can_x, can->config->channel, 0U);
        NVIC_DisableIRQ(can->config->intrSrc);
        rt_kprintf("[drv_can] set_int polling mode nvic disabled\n");
#endif
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

    case IFX_CAN_CMD_POLL_RX:
        can_report_rx_fifo(can, CY_CANFD_RX_FIFO0);
        can_report_rx_fifo(can, CY_CANFD_RX_FIFO1);
        can_report_tx_done(can);
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
        can_wait_tx_done_or_fail(can, (rt_uint8_t)boxno);
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

    return RT_EOK;
}

rt_err_t ifx_can_direct_init(void)
{
#ifdef BSP_USING_CANFD0
    cy_en_canfd_status_t result;
    struct ifx_can *can = &can_obj[CANFD0_INDEX];

    ifx_can_direct_apply_bitrate_config(g_can_direct_bitrate);
    can->config = &can_config[CANFD0_INDEX];

    ifx_canfd0_prepare_hw();
    Cy_CANFD_Enable(can->config->can_x, (1UL << can->config->channel));
    result = Cy_CANFD_Init(can->config->can_x,
                           can->config->channel,
                           can->config->canfd_config,
                           &can->context);
    if (result != CY_CANFD_SUCCESS)
    {
        rt_kprintf("[drv_can] direct init failed ret=%d\n", result);
        g_can_direct_ready = RT_FALSE;
        return -RT_ERROR;
    }

    (void)Cy_CANFD_ClearInterrupt(can->config->can_x, can->config->channel, 0xFFFFFFFFUL);
    Cy_CANFD_SetInterruptMask(can->config->can_x, can->config->channel, 0U);
    Cy_CANFD_EnableInterruptLine(can->config->can_x, can->config->channel, 0U);
    NVIC_ClearPendingIRQ(can->config->intrSrc);
    NVIC_DisableIRQ(can->config->intrSrc);

    can_apply_mode(can, RT_CAN_MODE_NORMAL);
    can->irq_mask = 0U;
    can->tx_pending_mask = 0U;
    g_can_direct_tx_index = 0U;
    g_can_direct_tx_pending_suppressed = 0U;
    g_can_direct_tx_timeout_count = 0U;
    g_can_direct_tx_send_fail_count = 0U;
    g_can_direct_rx_extract_fail_count = 0U;
    g_can_direct_rx_fifo0_lost_count = 0U;
    g_can_direct_rx_fifo0_full_count = 0U;
    g_can_direct_rx_fifo0_lost_latched = RT_FALSE;
    g_can_direct_rx_fifo0_full_latched = RT_FALSE;
    g_can_direct_ready = RT_TRUE;

    rt_kprintf("[drv_can] direct ready bitrate=%lu pclk=%lu nbtp=0x%08lx rxf0s=0x%08lx\n",
               (unsigned long)g_can_direct_bitrate,
               (unsigned long)Cy_SysClk_PeriPclkGetFrequency(PCLK_CANFD0_CLOCK_CAN_EN0,
                                                              CY_SYSCLK_DIV_8_BIT,
                                                              4U),
               (unsigned long)CANFD_NBTP(can->config->can_x, can->config->channel),
               (unsigned long)CANFD_RXF0S(can->config->can_x, can->config->channel));
    return RT_EOK;
#else
    return -RT_ERROR;
#endif
}

rt_err_t ifx_can_direct_reinit_bitrate(rt_uint32_t bitrate)
{
#ifdef BSP_USING_CANFD0
    cy_en_canfd_status_t result;
    struct ifx_can *can = &can_obj[CANFD0_INDEX];

    if (ifx_can_direct_prescaler_for_bitrate(bitrate) == 0xFFFFFFFFUL)
    {
        return -RT_EINVAL;
    }

    can->config = &can_config[CANFD0_INDEX];
    g_can_direct_ready = RT_FALSE;
    (void)Cy_CANFD_DeInit(can->config->can_x, can->config->channel, &can->context);
    (void)Cy_CANFD_ClearInterrupt(can->config->can_x, can->config->channel, 0xFFFFFFFFUL);

    g_can_direct_bitrate = bitrate;
    ifx_can_direct_apply_bitrate_config(g_can_direct_bitrate);

    Cy_CANFD_Enable(can->config->can_x, (1UL << can->config->channel));
    result = Cy_CANFD_Init(can->config->can_x,
                           can->config->channel,
                           can->config->canfd_config,
                           &can->context);
    if (result != CY_CANFD_SUCCESS)
    {
        rt_kprintf("[drv_can] direct bitrate reinit failed bitrate=%lu ret=%d\n",
                   (unsigned long)bitrate,
                   result);
        return -RT_ERROR;
    }

    Cy_CANFD_SetInterruptMask(can->config->can_x, can->config->channel, 0U);
    Cy_CANFD_EnableInterruptLine(can->config->can_x, can->config->channel, 0U);
    NVIC_ClearPendingIRQ(can->config->intrSrc);
    NVIC_DisableIRQ(can->config->intrSrc);
    can_apply_mode(can, RT_CAN_MODE_NORMAL);

    can->irq_mask = 0U;
    can->tx_pending_mask = 0U;
    g_can_direct_tx_index = 0U;
    g_can_direct_ready = RT_TRUE;

    rt_kprintf("[drv_can] direct bitrate=%lu pclk=%lu nbtp=0x%08lx\n",
               (unsigned long)g_can_direct_bitrate,
               (unsigned long)Cy_SysClk_PeriPclkGetFrequency(PCLK_CANFD0_CLOCK_CAN_EN0,
                                                              CY_SYSCLK_DIV_8_BIT,
                                                              4U),
               (unsigned long)CANFD_NBTP(can->config->can_x, can->config->channel));
    return RT_EOK;
#else
    RT_UNUSED(bitrate);
    return -RT_ERROR;
#endif
}

rt_err_t ifx_can_direct_send(const struct rt_can_msg *msg)
{
#ifdef BSP_USING_CANFD0
    cy_en_canfd_status_t result;
    struct ifx_can *can = &can_obj[CANFD0_INDEX];
    rt_uint8_t dlc;
    rt_uint8_t len;
    rt_uint8_t tx_index;
    rt_uint32_t waited_ms;
    rt_bool_t is_fd;

    if ((msg == RT_NULL) || (!g_can_direct_ready))
    {
        return -RT_ERROR;
    }

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

    tx_index = g_can_direct_tx_index++ % BSP_CANFD0_TX_BUFFER_COUNT;
    ifx_canfd0_cancel_tx_buffer(can, tx_index);
    result = Cy_CANFD_UpdateAndTransmitMsgBuffer(can->config->can_x,
                                                 can->config->channel,
                                                 &can->tx_buffer,
                                                 tx_index,
                                                 &can->context);
    if (result != CY_CANFD_SUCCESS)
    {
        g_can_direct_tx_send_fail_count++;
        rt_kprintf("[drv_can] direct send failed box=%u ret=%d\n",
                   (unsigned int)tx_index,
                   result);
        return -RT_ERROR;
    }

    for (waited_ms = 0U; waited_ms <= IFX_CAN_TX_WAIT_MS; waited_ms++)
    {
        if (Cy_CANFD_GetTxBufferStatus(can->config->can_x,
                                       can->config->channel,
                                       tx_index) != CY_CANFD_TX_BUFFER_PENDING)
        {
            return RT_EOK;
        }

        if (waited_ms < IFX_CAN_TX_WAIT_MS)
        {
            rt_thread_mdelay(1);
        }
    }

    if (g_can_direct_tx_verbose)
    {
        rt_kprintf("[drv_can] direct tx pending box=%u cccr=0x%08lx psr=0x%08lx txbrp=0x%08lx txbto=0x%08lx txbcf=0x%08lx\n",
                   (unsigned int)tx_index,
                   (unsigned long)CANFD_CCCR(can->config->can_x, can->config->channel),
                   (unsigned long)CANFD_PSR(can->config->can_x, can->config->channel),
                   (unsigned long)CANFD_TXBRP(can->config->can_x, can->config->channel),
                   (unsigned long)CANFD_TXBTO(can->config->can_x, can->config->channel),
                   (unsigned long)CANFD_TXBCF(can->config->can_x, can->config->channel));
    }
    else
    {
        g_can_direct_tx_pending_suppressed++;
    }
    g_can_direct_tx_timeout_count++;
    ifx_canfd0_cancel_tx_buffer(can, tx_index);
    return -RT_ETIMEOUT;
#else
    return -RT_ERROR;
#endif
}

rt_ssize_t ifx_can_direct_recv(struct rt_can_msg *msg)
{
#ifdef BSP_USING_CANFD0
    cy_en_canfd_status_t result;
    struct ifx_can *can = &can_obj[CANFD0_INDEX];
    rt_uint32_t f0s;
    rt_uint32_t fill;
    rt_uint8_t dlc;
    rt_uint8_t len;

    if ((msg == RT_NULL) || (!g_can_direct_ready) || g_can_direct_raw_rx_pause)
    {
        return -RT_ERROR;
    }

    f0s = CANFD_RXF0S(can->config->can_x, can->config->channel);
    if ((f0s & CANFD_CH_M_TTCAN_RXF0S_RF0L_Msk) != 0U)
    {
        if (!g_can_direct_rx_fifo0_lost_latched)
        {
            g_can_direct_rx_fifo0_lost_count++;
        }
        g_can_direct_rx_fifo0_lost_latched = RT_TRUE;
    }
    else
    {
        g_can_direct_rx_fifo0_lost_latched = RT_FALSE;
    }

    if ((f0s & CANFD_CH_M_TTCAN_RXF0S_F0F_Msk) != 0U)
    {
        if (!g_can_direct_rx_fifo0_full_latched)
        {
            g_can_direct_rx_fifo0_full_count++;
        }
        g_can_direct_rx_fifo0_full_latched = RT_TRUE;
    }
    else
    {
        g_can_direct_rx_fifo0_full_latched = RT_FALSE;
    }

    fill = _FLD2VAL(CANFD_CH_M_TTCAN_RXF0S_F0FL, f0s);
    if (fill == 0U)
    {
        return 0;
    }

    can->rx_buffer.r0_f = &can->rx_r0;
    can->rx_buffer.r1_f = &can->rx_r1;
    can->rx_buffer.data_area_f = can->rx_data;
    rt_memset(can->rx_data, 0, sizeof(can->rx_data));
    rt_memset(msg, 0, sizeof(*msg));

    result = Cy_CANFD_ExtractMsgFromRXBuffer(can->config->can_x,
                                             can->config->channel,
                                             true,
                                             CY_CANFD_RX_FIFO0,
                                             &can->rx_buffer,
                                             &can->context);
    if (result != CY_CANFD_SUCCESS)
    {
        g_can_direct_rx_extract_fail_count++;
        rt_kprintf("[drv_can] direct recv failed ret=%d f0s=0x%08lx\n",
                   result,
                   (unsigned long)f0s);
        return -RT_ERROR;
    }

    msg->id = can->rx_r0.id;
    msg->ide = (can->rx_r0.xtd == CY_CANFD_XTD_EXTENDED_ID) ? 1U : 0U;
    msg->rtr = (can->rx_r0.rtr == CY_CANFD_RTR_REMOTE_FRAME) ? 1U : 0U;
    msg->hdr_index = (rt_int8_t)can->rx_r1.fidx;
    msg->rxfifo = CY_CANFD_RX_FIFO0;

    dlc = (rt_uint8_t)can->rx_r1.dlc;
    len = can_dlc_to_len(dlc);
    msg->len = len;
#if defined(RT_CAN_USING_CANFD)
    msg->fd_frame = 0U;
    msg->brs = 0U;
#endif
    if (len > 0U)
    {
        rt_memcpy(msg->data, can->rx_data, len);
    }

    return (rt_ssize_t)sizeof(*msg);
#else
    return -RT_ERROR;
#endif
}

rt_err_t ifx_can_direct_get_diag(ifx_can_direct_diag_t *out)
{
#ifdef BSP_USING_CANFD0
    struct ifx_can *can = &can_obj[CANFD0_INDEX];

    if (out == RT_NULL)
    {
        return -RT_EINVAL;
    }

    rt_memset(out, 0, sizeof(*out));
    out->ready = g_can_direct_ready;
    out->bitrate = g_can_direct_bitrate;
    out->tx_timeout_count = g_can_direct_tx_timeout_count;
    out->tx_send_fail_count = g_can_direct_tx_send_fail_count;
    out->rx_extract_fail_count = g_can_direct_rx_extract_fail_count;
    out->rx_fifo0_lost_count = g_can_direct_rx_fifo0_lost_count;
    out->rx_fifo0_full_count = g_can_direct_rx_fifo0_full_count;
    out->tx_pending_suppressed_count = g_can_direct_tx_pending_suppressed;

    if (!g_can_direct_ready)
    {
        return -RT_ERROR;
    }

    can->config = &can_config[CANFD0_INDEX];
    out->pclk_hz = Cy_SysClk_PeriPclkGetFrequency(PCLK_CANFD0_CLOCK_CAN_EN0,
                                                  CY_SYSCLK_DIV_8_BIT,
                                                  4U);
    out->cccr = CANFD_CCCR(can->config->can_x, can->config->channel);
    out->psr = CANFD_PSR(can->config->can_x, can->config->channel);
    out->ecr = CANFD_ECR(can->config->can_x, can->config->channel);
    out->ir = CANFD_IR(can->config->can_x, can->config->channel);
    out->rxf0s = CANFD_RXF0S(can->config->can_x, can->config->channel);
    out->txbrp = CANFD_TXBRP(can->config->can_x, can->config->channel);
    out->txbto = CANFD_TXBTO(can->config->can_x, can->config->channel);
    out->txbcf = CANFD_TXBCF(can->config->can_x, can->config->channel);

    return RT_EOK;
#else
    RT_UNUSED(out);
    return -RT_ERROR;
#endif
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
    config.ticks = rt_tick_from_millisecond(50);
    if (config.ticks == 0U)
    {
        config.ticks = 1U;
    }
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

