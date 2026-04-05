/*
 * Copyright (c) 2006-2021, RT-Thread Development Team
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Change Logs:
 * Date           Author       Notes
 * 2026-03-19     ASUS       the first version
 */
#ifndef __CAN_CONFIG_H__
#define __CAN_CONFIG_H__

#include <stdbool.h>

#include "board.h"
#include "drv_can.h"
#include "cycfg_peripherals.h"
#include "cy_canfd.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifdef BSP_USING_CANFD0
#ifndef BSP_CANFD0_HW
#define BSP_CANFD0_HW CANFD0
#endif

#ifndef BSP_CANFD0_CHANNEL
#define BSP_CANFD0_CHANNEL 0U
#endif

#ifndef BSP_CANFD0_IRQN
#define BSP_CANFD0_IRQN canfd_0_interrupts0_0_IRQn
#endif

#ifndef IFX_CAN_FORCE_CLASSIC
#define IFX_CAN_FORCE_CLASSIC 1
#endif

#ifndef BSP_CANFD0_NOMINAL_PRESCALER
#define BSP_CANFD0_NOMINAL_PRESCALER 2U
#endif

#ifndef BSP_CANFD0_NOMINAL_TSEG1
#define BSP_CANFD0_NOMINAL_TSEG1 13U
#endif

#ifndef BSP_CANFD0_NOMINAL_TSEG2
#define BSP_CANFD0_NOMINAL_TSEG2 2U
#endif

#ifndef BSP_CANFD0_NOMINAL_SJW
#define BSP_CANFD0_NOMINAL_SJW 2U
#endif

#ifndef BSP_CANFD0_FAST_PRESCALER
#define BSP_CANFD0_FAST_PRESCALER BSP_CANFD0_NOMINAL_PRESCALER
#endif

#ifndef BSP_CANFD0_FAST_TSEG1
#define BSP_CANFD0_FAST_TSEG1 BSP_CANFD0_NOMINAL_TSEG1
#endif

#ifndef BSP_CANFD0_FAST_TSEG2
#define BSP_CANFD0_FAST_TSEG2 BSP_CANFD0_NOMINAL_TSEG2
#endif

#ifndef BSP_CANFD0_FAST_SJW
#define BSP_CANFD0_FAST_SJW BSP_CANFD0_NOMINAL_SJW
#endif

#ifndef BSP_CANFD0_MRAM_ADDR
#if defined(CY_CAN0MRAM_BASE)
#define BSP_CANFD0_MRAM_ADDR CY_CAN0MRAM_BASE
#elif defined(CY_CAN0MRAM_NS_CBUS_BASE)
#define BSP_CANFD0_MRAM_ADDR CY_CAN0MRAM_NS_CBUS_BASE
#else
#define BSP_CANFD0_MRAM_ADDR 0x42850000UL
#endif
#endif

#ifndef BSP_CANFD0_MRAM_SIZE
#if defined(CY_CAN0MRAM_SIZE)
#define BSP_CANFD0_MRAM_SIZE CY_CAN0MRAM_SIZE
#else
#define BSP_CANFD0_MRAM_SIZE 0x00010000UL
#endif
#endif

#ifndef BSP_CANFD0_RX_FIFO0_ELEMENTS
#define BSP_CANFD0_RX_FIFO0_ELEMENTS 16U
#endif

#ifndef BSP_CANFD0_RX_FIFO1_ELEMENTS
#define BSP_CANFD0_RX_FIFO1_ELEMENTS 0U
#endif

#ifndef BSP_CANFD0_TX_BUFFER_COUNT
#define BSP_CANFD0_TX_BUFFER_COUNT 16U
#endif

static const cy_stc_canfd_bitrate_t ifx_canfd0_nominal_bitrate =
{
    .prescaler = BSP_CANFD0_NOMINAL_PRESCALER,
    .timeSegment1 = BSP_CANFD0_NOMINAL_TSEG1,
    .timeSegment2 = BSP_CANFD0_NOMINAL_TSEG2,
    .syncJumpWidth = BSP_CANFD0_NOMINAL_SJW,
};

static const cy_stc_canfd_bitrate_t ifx_canfd0_fast_bitrate =
{
    .prescaler = BSP_CANFD0_FAST_PRESCALER,
    .timeSegment1 = BSP_CANFD0_FAST_TSEG1,
    .timeSegment2 = BSP_CANFD0_FAST_TSEG2,
    .syncJumpWidth = BSP_CANFD0_FAST_SJW,
};

static const cy_stc_canfd_transceiver_delay_compensation_t ifx_canfd0_tdc =
{
    .tdcEnabled = false,
    .tdcOffset = 0U,
    .tdcFilterWindow = 0U,
};

static const cy_stc_canfd_sid_filter_config_t ifx_canfd0_sid_filter_cfg =
{
    .numberOfSIDFilters = 0U,
    .sidFilter = RT_NULL,
};

static const cy_stc_canfd_extid_filter_config_t ifx_canfd0_extid_filter_cfg =
{
    .numberOfEXTIDFilters = 0U,
    .extidFilter = RT_NULL,
    .extIDANDMask = 0x1FFFFFFFUL,
};

static const cy_stc_canfd_global_filter_config_t ifx_canfd0_global_filter_cfg =
{
    .nonMatchingFramesStandard = CY_CANFD_ACCEPT_IN_RXFIFO_0,
    .nonMatchingFramesExtended = CY_CANFD_ACCEPT_IN_RXFIFO_0,
    .rejectRemoteFramesStandard = true,
    .rejectRemoteFramesExtended = true,
};

static const cy_en_canfd_fifo_config_t ifx_canfd0_rx_fifo0_cfg =
{
    .mode = CY_CANFD_FIFO_MODE_OVERWRITE,
    .watermark = 0U,
    .numberOfFIFOElements = BSP_CANFD0_RX_FIFO0_ELEMENTS,
    .topPointerLogicEnabled = false,
};

static const cy_en_canfd_fifo_config_t ifx_canfd0_rx_fifo1_cfg =
{
    .mode = CY_CANFD_FIFO_MODE_BLOCKING,
    .watermark = 0U,
    .numberOfFIFOElements = BSP_CANFD0_RX_FIFO1_ELEMENTS,
    .topPointerLogicEnabled = false,
};

static const cy_stc_canfd_config_t ifx_canfd0_default_config =
{
    .txCallback = NULL,
    .rxCallback = NULL,
    .errorCallback = NULL,
    .canFDMode = (IFX_CAN_FORCE_CLASSIC ? false : true),
    .bitrate = &ifx_canfd0_nominal_bitrate,
    .fastBitrate = &ifx_canfd0_fast_bitrate,
    .tdcConfig = &ifx_canfd0_tdc,
    .sidFilterConfig = &ifx_canfd0_sid_filter_cfg,
    .extidFilterConfig = &ifx_canfd0_extid_filter_cfg,
    .globalFilterConfig = &ifx_canfd0_global_filter_cfg,
    .rxBufferDataSize = CY_CANFD_BUFFER_DATA_SIZE_8,
    .rxFIFO1DataSize = CY_CANFD_BUFFER_DATA_SIZE_8,
    .rxFIFO0DataSize = CY_CANFD_BUFFER_DATA_SIZE_8,
    .txBufferDataSize = CY_CANFD_BUFFER_DATA_SIZE_8,
    .rxFIFO0Config = &ifx_canfd0_rx_fifo0_cfg,
    .rxFIFO1Config = &ifx_canfd0_rx_fifo1_cfg,
    .noOfRxBuffers = 0U,
    .noOfTxBuffers = BSP_CANFD0_TX_BUFFER_COUNT,
    .messageRAMaddress = BSP_CANFD0_MRAM_ADDR,
    .messageRAMsize = BSP_CANFD0_MRAM_SIZE,
};

#ifndef BSP_CANFD0_CONFIG
#define BSP_CANFD0_CONFIG ifx_canfd0_default_config
#endif

static cy_stc_sysint_t CANFD0_IRQ_cfg =
{
    .intrSrc = (IRQn_Type)BSP_CANFD0_IRQN,
    .intrPriority = 7u,
};

#ifndef CANFD0_CONFIG
#define CANFD0_CONFIG                            \
    {                                            \
        .name = "can0",                          \
        .can_x = BSP_CANFD0_HW,                  \
        .channel = BSP_CANFD0_CHANNEL,           \
        .intrSrc = (IRQn_Type)BSP_CANFD0_IRQN,   \
        .userIsr = canfd_isr_callback(canfd0),   \
        .irq_cfg = &CANFD0_IRQ_cfg,              \
        .canfd_config = (const cy_stc_canfd_config_t *)&BSP_CANFD0_CONFIG, \
    }
#endif

void canfd0_isr_callback(void);
#endif /* BSP_USING_CANFD0 */

#ifdef __cplusplus
}
#endif

#endif /* __CAN_CONFIG_H__ */
