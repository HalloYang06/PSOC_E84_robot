#include <rtthread.h>
#include <rtdevice.h>
#include <board.h>
#include <fal.h>
#include <finsh.h>

#include "whd.h"
#include "whd_resource_api.h"
#include "http_server.h"
#include "openclaw_integration.h"

#define LED_PIN_G               GET_PIN(16, 6)

extern whd_resource_source_t resource_ops;

static void dump_hex(const char *title, const rt_uint8_t *raw, rt_size_t size)
{
    rt_size_t i;

    rt_kprintf("%s\n", title);
    for (i = 0; i < size; i++)
    {
        rt_kprintf("%02x ", raw[i]);
        if ((i % 16) == 15)
        {
            rt_kprintf("\n");
        }
    }
    if ((size % 16) != 0)
    {
        rt_kprintf("\n");
    }
}

static void whd_dump_head(int argc, char **argv)
{
    const struct fal_partition *part;
    rt_uint8_t raw[32] = {0};

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    part = fal_partition_find("whd_firmware");
    if (!part)
    {
        rt_kprintf("whd_firmware partition not found\n");
        return;
    }

    if (fal_partition_read(part, 0, raw, sizeof(raw)) < 0)
    {
        rt_kprintf("read whd_firmware failed\n");
        return;
    }

    dump_hex("whd_firmware head:", raw, sizeof(raw));
}
MSH_CMD_EXPORT(whd_dump_head, Dump first 32 bytes of whd_firmware partition);

static void whd_dump_block0(int argc, char **argv)
{
    const rt_uint8_t *data = RT_NULL;
    rt_uint8_t copy[32] = {0};
    uint32_t size_out = 0;
    uint32_t result;
    uint32_t fw_size = 0;
    rt_size_t dump_size;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    result = resource_ops.whd_resource_size(RT_NULL, WHD_RESOURCE_WLAN_FIRMWARE, &fw_size);
    rt_kprintf("whd_resource_size result=%u size=%u\n", result, fw_size);
    if (result != 0)
    {
        return;
    }

    result = resource_ops.whd_get_resource_block(RT_NULL, WHD_RESOURCE_WLAN_FIRMWARE, 0, &data, &size_out);
    rt_kprintf("whd_get_resource_block result=%u block0_size=%u data=%p\n", result, size_out, data);
    if (result != 0 || data == RT_NULL)
    {
        return;
    }

    dump_size = size_out < sizeof(copy) ? size_out : sizeof(copy);
    rt_memcpy(copy, data, dump_size);
    dump_hex("whd firmware block0:", copy, dump_size);
}
MSH_CMD_EXPORT(whd_dump_block0, Dump first 32 bytes of WHD firmware block0);

static void openclaw_dump_status(int argc, char **argv)
{
    char json[OPENCLAW_JSON_MEDIUM];

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    openclaw_build_status_json(json, sizeof(json));
    rt_kprintf("%s\n", json);
}
MSH_CMD_EXPORT(openclaw_dump_status, Dump OpenClaw bridge status as JSON);

int main(void)
{
    rt_err_t ret;

    rt_kprintf("Hello RT-Thread\r\n");
    rt_kprintf("It's cortex-m55\r\n");

    rt_pin_mode(LED_PIN_G, PIN_MODE_OUTPUT);

    ret = openclaw_integration_init();
    if (ret != RT_EOK)
    {
        rt_kprintf("OpenClaw integration init failed: %d\n", ret);
    }

    ret = http_server_init();
    if (ret != RT_EOK)
    {
        rt_kprintf("HTTP server init failed: %d\n", ret);
    }

    while (1)
    {
        rt_pin_write(LED_PIN_G, PIN_LOW);
        rt_thread_mdelay(500);
        rt_pin_write(LED_PIN_G, PIN_HIGH);
        rt_thread_mdelay(500);
    }

    return 0;
}
