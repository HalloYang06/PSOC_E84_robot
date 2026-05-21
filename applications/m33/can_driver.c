#include "can_driver.h"
#include "control/control_layer.h"
#include "control/control_layer_cfg.h"
#include "CAN_config.h"
#include "cy_gpio.h"
#include "cy_sysclk.h"
#include "gpio_pse84_bga_220.h"
#include <finsh.h>
#include <stdlib.h>
#include <string.h>

static cy_stc_canfd_context_t s_can_min_ctx;
static rt_bool_t s_can_min_ready = RT_FALSE;
static rt_uint8_t s_can_min_tx_index = 0U;

static void can_min_dump_status(const char *tag)
{
#ifdef BSP_USING_CANFD0
    rt_uint32_t chan = BSP_CANFD0_CHANNEL;

    rt_kprintf("[can_min] %s cccr=0x%08lx nbtp=0x%08lx dbtp=0x%08lx ir=0x%08lx psr=0x%08lx\n",
               tag,
               (unsigned long)CANFD_CCCR(BSP_CANFD0_HW, chan),
               (unsigned long)CANFD_NBTP(BSP_CANFD0_HW, chan),
               (unsigned long)CANFD_DBTP(BSP_CANFD0_HW, chan),
               (unsigned long)CANFD_IR(BSP_CANFD0_HW, chan),
               (unsigned long)CANFD_PSR(BSP_CANFD0_HW, chan));
    rt_kprintf("[can_min] %s txbrp=0x%08lx txbto=0x%08lx txbcf=0x%08lx rxf0s=0x%08lx\n",
               tag,
               (unsigned long)CANFD_TXBRP(BSP_CANFD0_HW, chan),
               (unsigned long)CANFD_TXBTO(BSP_CANFD0_HW, chan),
               (unsigned long)CANFD_TXBCF(BSP_CANFD0_HW, chan),
               (unsigned long)CANFD_RXF0S(BSP_CANFD0_HW, chan));
#else
    (void)tag;
#endif
}

static void can_min_prepare_hw(void)
{
#ifdef BSP_USING_CANFD0
    cy_stc_gpio_pin_config_t rx_pin_cfg;
    cy_stc_gpio_pin_config_t tx_pin_cfg;

    Cy_SysClk_PeriGroupSlaveInit(
        CY_MMIO_HSIOM_PERI_NR,
        CY_MMIO_HSIOM_GROUP_NR,
        CY_MMIO_HSIOM_SLAVE_NR,
        CY_MMIO_HSIOM_CLK_HF_NR);
    Cy_SysClk_PeriGroupSlaveInit(
        CY_MMIO_GPIO_PERI_NR,
        CY_MMIO_GPIO_GROUP_NR,
        CY_MMIO_GPIO_SLAVE_NR,
        CY_MMIO_GPIO_CLK_HF_NR);
    Cy_SysClk_PeriGroupSlaveInit(
        CY_MMIO_CANFD0_PERI_NR,
        CY_MMIO_CANFD0_GROUP_NR,
        CY_MMIO_CANFD0_SLAVE_NR,
        CY_MMIO_CANFD0_CLK_HF_NR);

    Cy_SysClk_PeriPclkAssignDivider(PCLK_CANFD0_CLOCK_CAN_EN0, CY_SYSCLK_DIV_8_BIT, 4U);
    Cy_SysClk_PeriPclkAssignDivider(PCLK_CANFD0_CLOCK_CAN_EN1, CY_SYSCLK_DIV_8_BIT, 4U);
    Cy_SysClk_PeriPclkSetDivider(PCLK_CANFD0_CLOCK_CAN_EN0, CY_SYSCLK_DIV_8_BIT, 4U, 4U);
    Cy_SysClk_PeriPclkSetDivider(PCLK_CANFD0_CLOCK_CAN_EN1, CY_SYSCLK_DIV_8_BIT, 4U, 4U);
    Cy_SysClk_PeriPclkEnableDivider(PCLK_CANFD0_CLOCK_CAN_EN0, CY_SYSCLK_DIV_8_BIT, 4U);
    Cy_SysClk_PeriPclkEnableDivider(PCLK_CANFD0_CLOCK_CAN_EN1, CY_SYSCLK_DIV_8_BIT, 4U);

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
#endif
}

static rt_uint32_t can_min_motor_private_ext_id(rt_uint8_t comm_type, rt_uint16_t data2, rt_uint8_t data1)
{
    return (((rt_uint32_t)comm_type & 0x1FU) << 24) |
           (((rt_uint32_t)data2 & 0xFFFFU) << 8) |
           ((rt_uint32_t)data1 & 0xFFU);
}

rt_err_t can_driver_init(void)
{
    rt_err_t ret;

    rt_kprintf("[can_driver] start control layer on %s\n", CONTROL_CAN_DEV_DEFAULT);
    ret = control_layer_init(CONTROL_CAN_DEV_DEFAULT);
    rt_kprintf("[can_driver] control layer ret=%d\n", ret);

    return ret;
}

rt_err_t can_send_joint_target(joint_id_t joint, float target)
{
    return control_motor_position_control((rt_uint8_t)joint, target, 2.0f, RT_TRUE);
}

rt_err_t can_process_frame(const rehab_can_frame_t *frame, sensor_data_t *snapshot)
{
    if (frame == RT_NULL || snapshot == RT_NULL)
    {
        return -RT_ERROR;
    }

    switch (frame->id)
    {
    case CAN_ID_SENSOR_EMG:
        snapshot->emg_ch1 = frame->data[0] / 10.0f;
        snapshot->emg_ch2 = frame->data[1] / 10.0f;
        break;
    case CAN_ID_SENSOR_HEART:
        snapshot->heart_rate = frame->data[0];
        snapshot->spo2 = frame->data[1];
        break;
    default:
        break;
    }

    snapshot->timestamp = rt_tick_get();
    return RT_EOK;
}

static void cmd_can_reg_probe(void)
{
#ifdef BSP_USING_CANFD0
    CANFD_Type *base = BSP_CANFD0_HW;

    rt_kprintf("[can_probe] base=0x%08lx mram=0x%08lx ch=%lu irq=%lu\n",
               (unsigned long)base,
               (unsigned long)BSP_CANFD0_MRAM_ADDR,
               (unsigned long)BSP_CANFD0_CHANNEL,
               (unsigned long)BSP_CANFD0_IRQN);

    rt_kprintf("[can_probe] init hsiom mmio\n");
    Cy_SysClk_PeriGroupSlaveInit(
        CY_MMIO_HSIOM_PERI_NR,
        CY_MMIO_HSIOM_GROUP_NR,
        CY_MMIO_HSIOM_SLAVE_NR,
        CY_MMIO_HSIOM_CLK_HF_NR);

    rt_kprintf("[can_probe] init gpio mmio\n");
    Cy_SysClk_PeriGroupSlaveInit(
        CY_MMIO_GPIO_PERI_NR,
        CY_MMIO_GPIO_GROUP_NR,
        CY_MMIO_GPIO_SLAVE_NR,
        CY_MMIO_GPIO_CLK_HF_NR);

    rt_kprintf("[can_probe] init canfd0 mmio\n");
    Cy_SysClk_PeriGroupSlaveInit(
        CY_MMIO_CANFD0_PERI_NR,
        CY_MMIO_CANFD0_GROUP_NR,
        CY_MMIO_CANFD0_SLAVE_NR,
        CY_MMIO_CANFD0_CLK_HF_NR);

    rt_kprintf("[can_probe] about to read CTL\n");
    rt_kprintf("[can_probe] ctl=0x%08lx\n", (unsigned long)CANFD_CTL(base));

    rt_kprintf("[can_probe] about to read STATUS\n");
    rt_kprintf("[can_probe] status=0x%08lx\n", (unsigned long)CANFD_STATUS(base));

    rt_kprintf("[can_probe] about to read IR\n");
    rt_kprintf("[can_probe] ir=0x%08lx\n",
               (unsigned long)CANFD_IR(base, BSP_CANFD0_CHANNEL));
#else
    rt_kprintf("[can_probe] BSP_USING_CANFD0 is not enabled\n");
#endif
}
MSH_CMD_EXPORT(cmd_can_reg_probe, probe raw CANFD0 registers);

static void cmd_can_init_min(void)
{
#ifdef BSP_USING_CANFD0
    cy_en_canfd_status_t ret;

    can_min_prepare_hw();

    rt_kprintf("[can_min] enable\n");
    Cy_CANFD_Enable(BSP_CANFD0_HW, (1UL << BSP_CANFD0_CHANNEL));

    rt_kprintf("[can_min] init\n");
    ret = Cy_CANFD_Init(BSP_CANFD0_HW,
                        BSP_CANFD0_CHANNEL,
                        &ifx_canfd0_default_config,
                        &s_can_min_ctx);
    rt_kprintf("[can_min] init ret=%d\n", ret);
    rt_kprintf("[can_min] pclk0=%lu pclk1=%lu div=%lu en=%d\n",
               (unsigned long)Cy_SysClk_PeriPclkGetFrequency(PCLK_CANFD0_CLOCK_CAN_EN0, CY_SYSCLK_DIV_8_BIT, 4U),
               (unsigned long)Cy_SysClk_PeriPclkGetFrequency(PCLK_CANFD0_CLOCK_CAN_EN1, CY_SYSCLK_DIV_8_BIT, 4U),
               (unsigned long)Cy_SysClk_PeriPclkGetDivider(PCLK_CANFD0_CLOCK_CAN_EN0, CY_SYSCLK_DIV_8_BIT, 4U),
               (int)Cy_SysClk_PeriPclkGetDividerEnabled(PCLK_CANFD0_CLOCK_CAN_EN0, CY_SYSCLK_DIV_8_BIT, 4U));

    s_can_min_ready = (ret == CY_CANFD_SUCCESS) ? RT_TRUE : RT_FALSE;
    s_can_min_tx_index = 0U;
    can_min_dump_status("after_init");
#else
    rt_kprintf("[can_min] BSP_USING_CANFD0 is not enabled\n");
#endif
}
MSH_CMD_EXPORT(cmd_can_init_min, minimal canfd init without rtdevice);

static void cmd_can_send_probe(int argc, char **argv)
{
#ifdef BSP_USING_CANFD0
    cy_stc_canfd_tx_buffer_t tx_buffer;
    cy_stc_canfd_t0_t tx_r0;
    cy_stc_canfd_t1_t tx_r1;
    rt_uint32_t tx_data[16];
    cy_en_canfd_status_t ret;
    rt_uint8_t motor_id = 0x7FU;
    rt_uint8_t tx_index;
    rt_uint32_t ext_id;

    if ((argc > 1) && (argv[1] != RT_NULL))
    {
        motor_id = (rt_uint8_t)strtoul(argv[1], RT_NULL, 0);
    }

    if (!s_can_min_ready)
    {
        rt_kprintf("[can_min] not ready, run cmd_can_init_min first\n");
        return;
    }

    rt_memset(&tx_buffer, 0, sizeof(tx_buffer));
    rt_memset(&tx_r0, 0, sizeof(tx_r0));
    rt_memset(&tx_r1, 0, sizeof(tx_r1));
    rt_memset(tx_data, 0, sizeof(tx_data));

    ext_id = can_min_motor_private_ext_id(0x00U, 0x00FDU, motor_id);

    tx_r0.id = ext_id;
    tx_r0.rtr = CY_CANFD_RTR_DATA_FRAME;
    tx_r0.xtd = CY_CANFD_XTD_EXTENDED_ID;
    tx_r0.esi = CY_CANFD_ESI_ERROR_ACTIVE;

    tx_r1.dlc = 8U;
    tx_r1.brs = false;
    tx_r1.fdf = CY_CANFD_FDF_STANDARD_FRAME;
    tx_r1.efc = false;
    tx_r1.mm = 0U;

    tx_buffer.t0_f = &tx_r0;
    tx_buffer.t1_f = &tx_r1;
    tx_buffer.data_area_f = tx_data;

    tx_index = s_can_min_tx_index++ % BSP_CANFD0_TX_BUFFER_COUNT;
    can_min_dump_status("before_send");
    ret = Cy_CANFD_UpdateAndTransmitMsgBuffer(BSP_CANFD0_HW,
                                              BSP_CANFD0_CHANNEL,
                                              &tx_buffer,
                                              tx_index,
                                              &s_can_min_ctx);
    rt_kprintf("[can_min] send probe motor=0x%02X ext=0x%08lx buf=%u ret=%d\n",
               (unsigned int)motor_id,
               (unsigned long)ext_id,
               (unsigned int)tx_index,
               ret);
    can_min_dump_status("after_send");
#else
    rt_kprintf("[can_min] BSP_USING_CANFD0 is not enabled\n");
#endif
}
MSH_CMD_EXPORT(cmd_can_send_probe, send private get-id frame by raw canfd);

static void cmd_can_status(void)
{
    can_min_dump_status("manual");
}
MSH_CMD_EXPORT(cmd_can_status, dump raw canfd tx rx status);

static void cmd_can_poll_once(void)
{
#ifdef BSP_USING_CANFD0
    cy_stc_canfd_rx_buffer_t rx_buffer;
    cy_stc_canfd_r0_t rx_r0;
    cy_stc_canfd_r1_t rx_r1;
    rt_uint32_t rx_data[16];
    cy_en_canfd_status_t ret;
    rt_uint32_t f0s;
    rt_uint32_t fill;
    int i;

    if (!s_can_min_ready)
    {
        rt_kprintf("[can_min] not ready, run cmd_can_init_min first\n");
        return;
    }

    f0s = CANFD_RXF0S(BSP_CANFD0_HW, BSP_CANFD0_CHANNEL);
    fill = _FLD2VAL(CANFD_CH_M_TTCAN_RXF0S_F0FL, f0s);
    rt_kprintf("[can_min] fifo0 status=0x%08lx fill=%lu\n",
               (unsigned long)f0s,
               (unsigned long)fill);
    if (fill == 0U)
    {
        return;
    }

    rt_memset(&rx_buffer, 0, sizeof(rx_buffer));
    rt_memset(&rx_r0, 0, sizeof(rx_r0));
    rt_memset(&rx_r1, 0, sizeof(rx_r1));
    rt_memset(rx_data, 0, sizeof(rx_data));
    rx_buffer.r0_f = &rx_r0;
    rx_buffer.r1_f = &rx_r1;
    rx_buffer.data_area_f = rx_data;

    ret = Cy_CANFD_ExtractMsgFromRXBuffer(BSP_CANFD0_HW,
                                          BSP_CANFD0_CHANNEL,
                                          true,
                                          0U,
                                          &rx_buffer,
                                          &s_can_min_ctx);
    rt_kprintf("[can_min] poll ret=%d id=0x%08lx dlc=%lu xtd=%lu\n",
               ret,
               (unsigned long)rx_r0.id,
               (unsigned long)rx_r1.dlc,
               (unsigned long)rx_r0.xtd);

    for (i = 0; i < 8; i++)
    {
        rt_kprintf("%02X%s", ((rt_uint8_t *)rx_data)[i], (i == 7) ? "\n" : " ");
    }
#else
    rt_kprintf("[can_min] BSP_USING_CANFD0 is not enabled\n");
#endif
}
MSH_CMD_EXPORT(cmd_can_poll_once, poll rx fifo0 once by raw canfd);
