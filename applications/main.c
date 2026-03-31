#include <rtthread.h>
#include <rtdevice.h>
#include <board.h>
#include <fal.h>
#include <finsh.h>

#include "whd.h"
#include "whd_resource_api.h"
#include "http_server.h"
#include "openclaw_integration.h"
#include "voice_service.h"

#define LED_PIN_G GET_PIN(16, 6)
#define M55_AUDIO_SAMPLE_RATE 16000
#define M55_AUDIO_CHANNELS 1
#define M55_AUDIO_BITS_PER_SAMPLE 16
#define M55_AUDIO_FRAME_BYTES 2048
#define M55_VOICE_BOOT_DELAY_MS 5000

static struct
{
    rt_device_t dev;
    rt_thread_t thread;
    rt_bool_t running;
    rt_uint8_t buffer[M55_AUDIO_FRAME_BYTES];
} g_m55_mic = {0};
static rt_thread_t g_voice_boot_thread = RT_NULL;

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

static void m55_mic_thread_entry(void *parameter)
{
    rt_size_t read_len;
    rt_uint32_t frame_count = 0;
    rt_uint32_t peak = 0;

    RT_UNUSED(parameter);

    while (g_m55_mic.running)
    {
        read_len = rt_device_read(g_m55_mic.dev, 0, g_m55_mic.buffer, sizeof(g_m55_mic.buffer));
        if (read_len > 0)
        {
            rt_size_t i;
            rt_uint32_t local_peak = 0;
            rt_int16_t *samples = (rt_int16_t *)g_m55_mic.buffer;
            rt_size_t sample_count = read_len / sizeof(rt_int16_t);

            for (i = 0; i < sample_count; i++)
            {
                rt_uint32_t mag = (samples[i] < 0) ? (rt_uint32_t)(-samples[i]) : (rt_uint32_t)samples[i];
                if (mag > local_peak)
                {
                    local_peak = mag;
                }
            }

            if (local_peak > peak)
            {
                peak = local_peak;
            }

            frame_count++;
            if ((frame_count % 10U) == 0U)
            {
                rt_kprintf("[m55_mic] read ok len=%u peak=%u frames=%u\n",
                           (unsigned)read_len,
                           (unsigned)peak,
                           (unsigned)frame_count);
                peak = 0;
            }
        }
        else
        {
            rt_thread_mdelay(10);
        }
    }
}

static rt_err_t m55_mic_start_internal(void)
{
    struct rt_audio_caps caps;

    if (g_m55_mic.running)
    {
        return -RT_EBUSY;
    }

    if (g_m55_mic.dev == RT_NULL)
    {
        g_m55_mic.dev = rt_device_find("mic0");
        if (g_m55_mic.dev == RT_NULL)
        {
            rt_kprintf("[m55_mic] mic0 not found\n");
            return -RT_ERROR;
        }

        if (rt_device_open(g_m55_mic.dev, RT_DEVICE_OFLAG_RDONLY) != RT_EOK)
        {
            rt_kprintf("[m55_mic] open mic0 failed\n");
            g_m55_mic.dev = RT_NULL;
            return -RT_ERROR;
        }

        rt_memset(&caps, 0, sizeof(caps));
        caps.main_type = AUDIO_TYPE_INPUT;
        caps.sub_type = AUDIO_DSP_PARAM;
        caps.udata.config.samplerate = M55_AUDIO_SAMPLE_RATE;
        caps.udata.config.channels = M55_AUDIO_CHANNELS;
        caps.udata.config.samplebits = M55_AUDIO_BITS_PER_SAMPLE;
        if (rt_device_control(g_m55_mic.dev, AUDIO_CTL_CONFIGURE, &caps) == RT_EOK)
        {
            rt_kprintf("[m55_mic] configured mic0 sr=%d ch=%d bits=%d\n",
                       M55_AUDIO_SAMPLE_RATE,
                       M55_AUDIO_CHANNELS,
                       M55_AUDIO_BITS_PER_SAMPLE);
        }
        else
        {
            rt_kprintf("[m55_mic] configure mic0 failed\n");
        }
    }

    g_m55_mic.running = RT_TRUE;
    g_m55_mic.thread = rt_thread_create("m55_mic",
                                        m55_mic_thread_entry,
                                        RT_NULL,
                                        4096,
                                        18,
                                        10);
    if (g_m55_mic.thread == RT_NULL)
    {
        g_m55_mic.running = RT_FALSE;
        rt_kprintf("[m55_mic] create thread failed\n");
        return -RT_ERROR;
    }

    rt_thread_startup(g_m55_mic.thread);
    rt_kprintf("[m55_mic] started\n");
    return RT_EOK;
}

static rt_err_t m55_mic_stop_internal(void)
{
    if (!g_m55_mic.running)
    {
        return RT_EOK;
    }

    g_m55_mic.running = RT_FALSE;
    rt_thread_mdelay(50);
    g_m55_mic.thread = RT_NULL;
    rt_kprintf("[m55_mic] stopped\n");
    return RT_EOK;
}

static void m55_mic_test(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55_mic_start_internal();
    rt_kprintf("m55_mic_test ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55_mic_test, Start local CM55 mic0 capture test);

static void m55_mic_stop(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = m55_mic_stop_internal();
    rt_kprintf("m55_mic_stop ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55_mic_stop, Stop local CM55 mic0 capture test);

static void voice_test(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = voice_service_request_capture_start();
    rt_kprintf("voice_test ret=%d\n", ret);
}
MSH_CMD_EXPORT(voice_test, Trigger M33 voice capture from M55);

static void voice_stop(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = voice_service_request_capture_stop();
    rt_kprintf("voice_stop ret=%d\n", ret);
}
MSH_CMD_EXPORT(voice_stop, Stop M33 voice capture from M55);

static void wake_on(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = voice_service_request_listen_start();
    rt_kprintf("wake_on ret=%d\n", ret);
}
MSH_CMD_EXPORT(wake_on, Start continuous wake listening on M33->CM55);

static void wake_off(int argc, char **argv)
{
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    ret = voice_service_request_listen_stop();
    rt_kprintf("wake_off ret=%d\n", ret);
}
MSH_CMD_EXPORT(wake_off, Stop continuous wake listening on M33->CM55);

static void voice_boot_thread_entry(void *parameter)
{
    rt_err_t ret;
    const char *api_key = "YOUR_BAIDU_API_KEY";
    const char *secret_key = "YOUR_BAIDU_SECRET_KEY";

    RT_UNUSED(parameter);

    rt_thread_mdelay(M55_VOICE_BOOT_DELAY_MS);
    rt_kprintf("[m55] starting voice service\n");

    ret = voice_service_init(api_key, secret_key);
    if (ret != RT_EOK)
    {
        rt_kprintf("Voice service init failed: %d\n", ret);
        g_voice_boot_thread = RT_NULL;
        return;
    }

    rt_kprintf("[m55] voice service initialized\n");
    ret = voice_service_start();
    if (ret != RT_EOK)
    {
        rt_kprintf("Voice service start failed: %d\n", ret);
    }

    g_voice_boot_thread = RT_NULL;
}

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

    g_voice_boot_thread = rt_thread_create("voice_bt",
                                           voice_boot_thread_entry,
                                           RT_NULL,
                                           4096,
                                           16,
                                           10);
    if (g_voice_boot_thread)
    {
        rt_thread_startup(g_voice_boot_thread);
        rt_kprintf("[m55] voice boot scheduled\n");
    }
    else
    {
        rt_kprintf("[m55] voice boot thread create failed\n");
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
