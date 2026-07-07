#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include <rtthread.h>

#include "bt_hci_uart_prm.h"
#include "cybt_platform_config.h"
#include "cybt_platform_hci.h"
#include "cybt_platform_util.h"
#include "wiced_bt_dev.h"
#include "wiced_bt_stack_platform.h"

#define HCI_VSC_UPDATE_BAUDRATE_CMD                (0xFC18)
#define HCI_VSC_UPDATE_BAUDRATE_LEN                (6u)
#ifndef HCI_UART_DEFAULT_BAUDRATE
#define HCI_UART_DEFAULT_BAUDRATE                  (115200u)
#endif

typedef enum
{
    BT_POST_RESET_STATE_IDLE = 0,
    BT_POST_RESET_STATE_UPDATE_BAUDRATE_FOR_FW_DL,
    BT_POST_RESET_STATE_FW_DOWNLOADING,
    BT_POST_RESET_STATE_FW_DOWNLOAD_COMPLETED,
    BT_POST_RESET_STATE_UPDATE_BAUDRATE_FOR_FEATURE,
    BT_POST_RESET_STATE_DONE,
    BT_POST_RESET_STATE_FAILED
} bt_post_reset_state_t;

typedef struct
{
    bt_post_reset_state_t state;
} bt_fw_download_cb_t;

extern const char brcm_patch_version[];
extern const uint8_t brcm_patchram_format;
extern const uint8_t brcm_patchram_buf[];
extern const int brcm_patch_ram_length;
extern bool bt_post_stack_init_seen(void);
extern void wiced_post_stack_init_cback(void);

static bt_fw_download_cb_t g_bt_fwdl_cb = { .state = BT_POST_RESET_STATE_IDLE };
static rt_tick_t g_bt_post_reset_resync_deadline = 0;

static void bt_baudrate_updated_cback(wiced_bt_dev_vendor_specific_command_complete_params_t *p);
static void bt_fw_download_complete_cback(cybt_prm_status_t status);

void bt_post_reset_arm_rx_resync_window(uint32_t duration_ms)
{
    g_bt_post_reset_resync_deadline = rt_tick_get() + rt_tick_from_millisecond(duration_ms);
}

bool bt_post_reset_rx_resync_active(void)
{
    rt_tick_t now = rt_tick_get();
    return (g_bt_post_reset_resync_deadline != 0) && ((rt_int32_t)(g_bt_post_reset_resync_deadline - now) > 0);
}

static void bt_start_fw_download(void)
{
    bool started;

    g_bt_fwdl_cb.state = BT_POST_RESET_STATE_FW_DOWNLOADING;

    rt_kprintf("[bt.hci] patch version=%s format=%u len=%d\n",
               brcm_patch_version,
               (unsigned int)brcm_patchram_format,
               brcm_patch_ram_length);

    started = cybt_prm_download(bt_fw_download_complete_cback,
                                brcm_patchram_buf,
                                (uint32_t)brcm_patch_ram_length,
                                0,
                                brcm_patchram_format);

    rt_kprintf("[bt.hci] patch download start=%d\n", started ? 1 : 0);
}

static void bt_update_platform_baudrate(uint32_t baudrate)
{
    uint32_t actual_baud = 0;
    cybt_result_t result;

    rt_thread_mdelay(100);
    result = cybt_platform_hci_set_baudrate(baudrate);
    rt_kprintf("[bt.hci] update platform baud result=%d baud=%lu\n",
               result,
               (unsigned long)baudrate);

    if (result == CYBT_SUCCESS)
    {
        actual_baud = baudrate;
    }

    rt_kprintf("[bt.hci] set baud req=%lu actual=%lu\n",
               (unsigned long)baudrate,
               (unsigned long)actual_baud);
    rt_thread_mdelay(100);
}

static void bt_update_controller_baudrate(uint32_t baudrate)
{
    uint8_t hci_data[HCI_VSC_UPDATE_BAUDRATE_LEN];
    wiced_result_t result;

    memset(hci_data, 0, sizeof(hci_data));
    hci_data[2] = (uint8_t)(baudrate & 0xFFu);
    hci_data[3] = (uint8_t)((baudrate >> 8) & 0xFFu);
    hci_data[4] = (uint8_t)((baudrate >> 16) & 0xFFu);
    hci_data[5] = (uint8_t)((baudrate >> 24) & 0xFFu);

    result = wiced_bt_dev_vendor_specific_command(HCI_VSC_UPDATE_BAUDRATE_CMD,
                                                  HCI_VSC_UPDATE_BAUDRATE_LEN,
                                                  hci_data,
                                                  bt_baudrate_updated_cback);
    rt_kprintf("[bt.hci] update controller baud req=%lu result=0x%08lx\n",
               (unsigned long)baudrate,
               (unsigned long)result);
}

static void bt_baudrate_updated_cback(wiced_bt_dev_vendor_specific_command_complete_params_t *p)
{
    const cybt_platform_config_t *cfg = cybt_platform_get_config();

    if ((p == RT_NULL) || (cfg == RT_NULL) || (p->p_param_buf == RT_NULL))
    {
        rt_kprintf("[bt.hci] baud update callback invalid args\n");
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_FAILED;
        return;
    }

    rt_kprintf("[bt.hci] update controller baud status=0x%02X opcode=0x%04X state=%d\n",
               p->p_param_buf[0],
               p->opcode,
               g_bt_fwdl_cb.state);

    if (p->p_param_buf[0] != 0u)
    {
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_FAILED;
        return;
    }

    switch (g_bt_fwdl_cb.state)
    {
    case BT_POST_RESET_STATE_UPDATE_BAUDRATE_FOR_FW_DL:
        bt_update_platform_baudrate(cfg->hci_config.hci.hci_uart.baud_rate_for_fw_download);
        bt_start_fw_download();
        break;
    case BT_POST_RESET_STATE_UPDATE_BAUDRATE_FOR_FEATURE:
        bt_update_platform_baudrate(cfg->hci_config.hci.hci_uart.baud_rate_for_feature);
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_DONE;
        bt_post_reset_arm_rx_resync_window(500);
        rt_kprintf("[bt.hci] post reset done\n");
        wiced_bt_continue_reset();
        break;
    default:
        rt_kprintf("[bt.hci] baud update callback unexpected state=%d\n", g_bt_fwdl_cb.state);
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_FAILED;
        break;
    }
}

static void bt_fw_download_complete_cback(cybt_prm_status_t status)
{
    const cybt_platform_config_t *cfg = cybt_platform_get_config();

    switch (status)
    {
    case CYBT_PRM_STS_CONTINUE:
        rt_kprintf("[bt.hci] patch download continue\n");
        return;
    case CYBT_PRM_STS_COMPLETE:
        rt_kprintf("[bt.hci] patch download complete\n");
        break;
    case CYBT_PRM_STS_ABORT:
    default:
        rt_kprintf("[bt.hci] patch download abort\n");
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_FAILED;
        return;
    }

    if (cfg == RT_NULL)
    {
        rt_kprintf("[bt.hci] patch complete missing cfg\n");
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_FAILED;
        return;
    }

    g_bt_fwdl_cb.state = BT_POST_RESET_STATE_FW_DOWNLOAD_COMPLETED;

    if (cfg->hci_config.hci.hci_uart.baud_rate_for_fw_download != HCI_UART_DEFAULT_BAUDRATE)
    {
        rt_kprintf("[bt.hci] patch complete reset platform baud to default\n");
        bt_update_platform_baudrate(HCI_UART_DEFAULT_BAUDRATE);
    }

    if (cfg->hci_config.hci.hci_uart.baud_rate_for_feature != HCI_UART_DEFAULT_BAUDRATE)
    {
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_UPDATE_BAUDRATE_FOR_FEATURE;
        bt_update_controller_baudrate(cfg->hci_config.hci.hci_uart.baud_rate_for_feature);
    }
    else
    {
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_DONE;
        bt_post_reset_arm_rx_resync_window(500);
        rt_kprintf("[bt.hci] post reset done\n");
        wiced_bt_continue_reset();
    }
}

void bt_post_reset_cback(void)
{
    const cybt_platform_config_t *cfg = cybt_platform_get_config();

    rt_kprintf("[bt.hci] post reset callback\n");

    g_bt_fwdl_cb.state = BT_POST_RESET_STATE_IDLE;

    if (cfg == RT_NULL)
    {
        rt_kprintf("[bt.hci] post reset missing cfg\n");
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_FAILED;
        return;
    }

    if ((brcm_patch_ram_length <= 0) || (brcm_patchram_buf == RT_NULL))
    {
        rt_kprintf("[bt.hci] patch image invalid\n");
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_DONE;
        wiced_bt_continue_reset();
        return;
    }

#ifndef COMPONENT_55500
    if (cfg->hci_config.hci.hci_uart.baud_rate_for_fw_download != HCI_UART_DEFAULT_BAUDRATE)
    {
        g_bt_fwdl_cb.state = BT_POST_RESET_STATE_UPDATE_BAUDRATE_FOR_FW_DL;
        bt_update_controller_baudrate(cfg->hci_config.hci.hci_uart.baud_rate_for_fw_download);
        return;
    }
#endif

    bt_start_fw_download();
}

