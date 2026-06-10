#include "wifi_config_service.h"

#include <netdev_ipaddr.h>
#include <netdev.h>
#include <wlan_mgnt.h>
#include <string.h>
#include <stdio.h>

#define WIFI_CONFIG_FILE_PATH      "/flash/rehab_wifi.cfg"
#define WIFI_CONFIG_FILE_MAGIC     "rehab_wifi_v1"
#define WIFI_CONFIG_AUTO_DELAY_MS  3500U

void whd_wlan_get_diag(int *stage, int *result, rt_uint32_t *flags);

static struct
{
    struct rt_mutex lock;
    rt_bool_t initialized;
    rt_thread_t auto_thread;
    wifi_config_snapshot_t snapshot;
} g_wifi_config;

static void wifi_config_strip_newline(char *text)
{
    char *p;

    if (text == RT_NULL)
    {
        return;
    }

    p = text;
    while (*p != '\0')
    {
        if ((*p == '\r') || (*p == '\n'))
        {
            *p = '\0';
            return;
        }
        p++;
    }
}

static void wifi_config_refresh_locked(void)
{
    struct netdev *netdev = netdev_default;

    g_wifi_config.snapshot.wlan_connected = rt_wlan_is_connected() ? 1U : 0U;
    g_wifi_config.snapshot.wlan_ready = rt_wlan_is_ready() ? 1U : 0U;
    g_wifi_config.snapshot.wlan_rssi = rt_wlan_get_rssi();

    if (netdev == RT_NULL)
    {
        netdev = netdev_get_first_by_flags(NETDEV_FLAG_UP);
    }
    if (netdev == RT_NULL)
    {
        netdev = netdev_get_first_by_flags(NETDEV_FLAG_LINK_UP);
    }

    if (netdev == RT_NULL)
    {
        g_wifi_config.snapshot.netdev_flags = 0;
        g_wifi_config.snapshot.netdev_ip = 0;
        g_wifi_config.snapshot.netdev_gw = 0;
        g_wifi_config.snapshot.netdev_mask = 0;
        g_wifi_config.snapshot.netdev_dns0 = 0;
        g_wifi_config.snapshot.netdev_name[0] = '\0';
        return;
    }

    rt_memset(g_wifi_config.snapshot.netdev_name, 0, sizeof(g_wifi_config.snapshot.netdev_name));
    rt_strncpy(g_wifi_config.snapshot.netdev_name,
               netdev->name,
               sizeof(g_wifi_config.snapshot.netdev_name) - 1);
    g_wifi_config.snapshot.netdev_flags = netdev->flags;
    g_wifi_config.snapshot.netdev_ip = ip4_addr_get_u32(&netdev->ip_addr);
    g_wifi_config.snapshot.netdev_gw = ip4_addr_get_u32(&netdev->gw);
    g_wifi_config.snapshot.netdev_mask = ip4_addr_get_u32(&netdev->netmask);
    g_wifi_config.snapshot.netdev_dns0 = ip4_addr_get_u32(&netdev->dns_servers[0]);
}

rt_err_t wifi_config_service_init(void)
{
    if (g_wifi_config.initialized)
    {
        return RT_EOK;
    }

    if (rt_mutex_init(&g_wifi_config.lock, "wifi_cfg", RT_IPC_FLAG_PRIO) != RT_EOK)
    {
        return -RT_ERROR;
    }

    rt_memset(&g_wifi_config.snapshot, 0, sizeof(g_wifi_config.snapshot));
    g_wifi_config.snapshot.last_result = -RT_ERROR;
    g_wifi_config.snapshot.scan_count = -1;
    g_wifi_config.snapshot.storage_result = -RT_ERROR;
    g_wifi_config.snapshot.auto_connect = 1U;
    g_wifi_config.initialized = RT_TRUE;
    (void)wifi_config_load();
    return RT_EOK;
}

rt_err_t wifi_config_set_ssid(const char *ssid)
{
    if ((ssid == RT_NULL) || (ssid[0] == '\0') || (rt_strlen(ssid) > WIFI_CONFIG_SSID_MAX_LEN))
    {
        return -RT_EINVAL;
    }

    (void)wifi_config_service_init();
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    rt_memset(g_wifi_config.snapshot.ssid, 0, sizeof(g_wifi_config.snapshot.ssid));
    rt_strncpy(g_wifi_config.snapshot.ssid, ssid, sizeof(g_wifi_config.snapshot.ssid) - 1);
    rt_mutex_release(&g_wifi_config.lock);
    return RT_EOK;
}

rt_err_t wifi_config_set_password(const char *password)
{
    if ((password == RT_NULL) || (rt_strlen(password) > WIFI_CONFIG_PASSWORD_MAX_LEN))
    {
        return -RT_EINVAL;
    }

    (void)wifi_config_service_init();
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    rt_memset(g_wifi_config.snapshot.password, 0, sizeof(g_wifi_config.snapshot.password));
    rt_strncpy(g_wifi_config.snapshot.password,
               password,
               sizeof(g_wifi_config.snapshot.password) - 1);
    rt_mutex_release(&g_wifi_config.lock);
    return RT_EOK;
}

rt_err_t wifi_config_set_auto_connect(rt_bool_t enable)
{
    (void)wifi_config_service_init();
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.auto_connect = enable ? 1U : 0U;
    rt_mutex_release(&g_wifi_config.lock);
    return RT_EOK;
}

rt_err_t wifi_config_load(void)
{
#ifdef RT_USING_DFS
    FILE *file;
    char magic[32];
    char auto_line[16];
    char ssid[WIFI_CONFIG_SSID_MAX_LEN + 4];
    char password[WIFI_CONFIG_PASSWORD_MAX_LEN + 4];
    rt_err_t ret = RT_EOK;

    (void)wifi_config_service_init();

    file = fopen(WIFI_CONFIG_FILE_PATH, "r");
    if (file == RT_NULL)
    {
        rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
        g_wifi_config.snapshot.saved = 0U;
        g_wifi_config.snapshot.storage_result = -RT_ERROR;
        rt_mutex_release(&g_wifi_config.lock);
        return -RT_ERROR;
    }

    rt_memset(magic, 0, sizeof(magic));
    rt_memset(auto_line, 0, sizeof(auto_line));
    rt_memset(ssid, 0, sizeof(ssid));
    rt_memset(password, 0, sizeof(password));

    if ((fgets(magic, sizeof(magic), file) == RT_NULL) ||
        (fgets(auto_line, sizeof(auto_line), file) == RT_NULL) ||
        (fgets(ssid, sizeof(ssid), file) == RT_NULL) ||
        (fgets(password, sizeof(password), file) == RT_NULL))
    {
        ret = -RT_ERROR;
    }
    fclose(file);

    wifi_config_strip_newline(magic);
    wifi_config_strip_newline(auto_line);
    wifi_config_strip_newline(ssid);
    wifi_config_strip_newline(password);

    if ((ret != RT_EOK) || (rt_strcmp(magic, WIFI_CONFIG_FILE_MAGIC) != 0) ||
        (ssid[0] == '\0') || (rt_strlen(ssid) > WIFI_CONFIG_SSID_MAX_LEN) ||
        (rt_strlen(password) > WIFI_CONFIG_PASSWORD_MAX_LEN))
    {
        rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
        g_wifi_config.snapshot.saved = 0U;
        g_wifi_config.snapshot.storage_result = -RT_ERROR;
        rt_mutex_release(&g_wifi_config.lock);
        return -RT_ERROR;
    }

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    rt_memset(g_wifi_config.snapshot.ssid, 0, sizeof(g_wifi_config.snapshot.ssid));
    rt_memset(g_wifi_config.snapshot.password, 0, sizeof(g_wifi_config.snapshot.password));
    rt_strncpy(g_wifi_config.snapshot.ssid, ssid, sizeof(g_wifi_config.snapshot.ssid) - 1);
    rt_strncpy(g_wifi_config.snapshot.password, password, sizeof(g_wifi_config.snapshot.password) - 1);
    g_wifi_config.snapshot.auto_connect = (auto_line[0] == '0') ? 0U : 1U;
    g_wifi_config.snapshot.saved = 1U;
    g_wifi_config.snapshot.storage_result = RT_EOK;
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] loaded saved ssid=%s auto=%lu\n",
               ssid,
               (unsigned long)((auto_line[0] == '0') ? 0U : 1U));
    return RT_EOK;
#else
    return -RT_ENOSYS;
#endif
}

rt_err_t wifi_config_save(void)
{
#ifdef RT_USING_DFS
    FILE *file;
    char ssid[sizeof(g_wifi_config.snapshot.ssid)];
    char password[sizeof(g_wifi_config.snapshot.password)];
    rt_uint32_t auto_connect;
    rt_err_t ret = RT_EOK;

    (void)wifi_config_service_init();

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    rt_strncpy(ssid, g_wifi_config.snapshot.ssid, sizeof(ssid) - 1);
    ssid[sizeof(ssid) - 1] = '\0';
    rt_strncpy(password, g_wifi_config.snapshot.password, sizeof(password) - 1);
    password[sizeof(password) - 1] = '\0';
    auto_connect = g_wifi_config.snapshot.auto_connect;
    rt_mutex_release(&g_wifi_config.lock);

    if (ssid[0] == '\0')
    {
        return -RT_EINVAL;
    }

    file = fopen(WIFI_CONFIG_FILE_PATH, "w");
    if (file == RT_NULL)
    {
        ret = -RT_ERROR;
    }
    else
    {
        if (fprintf(file, "%s\n%lu\n%s\n%s\n",
                    WIFI_CONFIG_FILE_MAGIC,
                    (unsigned long)(auto_connect ? 1U : 0U),
                    ssid,
                    password) < 0)
        {
            ret = -RT_ERROR;
        }
        fclose(file);
    }

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.saved = (ret == RT_EOK) ? 1U : 0U;
    g_wifi_config.snapshot.storage_result = ret;
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] save ret=%d path=%s ssid=%s auto=%lu\n",
               ret,
               WIFI_CONFIG_FILE_PATH,
               ssid,
               (unsigned long)(auto_connect ? 1U : 0U));
    return ret;
#else
    return -RT_ENOSYS;
#endif
}

rt_err_t wifi_config_forget(void)
{
    rt_err_t ret = RT_EOK;

    (void)wifi_config_service_init();

#ifdef RT_USING_DFS
    if (remove(WIFI_CONFIG_FILE_PATH) != 0)
    {
        ret = -RT_ERROR;
    }
#else
    ret = -RT_ENOSYS;
#endif

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    rt_memset(g_wifi_config.snapshot.ssid, 0, sizeof(g_wifi_config.snapshot.ssid));
    rt_memset(g_wifi_config.snapshot.password, 0, sizeof(g_wifi_config.snapshot.password));
    g_wifi_config.snapshot.saved = 0U;
    g_wifi_config.snapshot.storage_result = ret;
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] forget ret=%d\n", ret);
    return ret;
}

static void wifi_config_auto_thread_entry(void *parameter)
{
    rt_uint32_t delay_ms = (rt_uint32_t)(rt_ubase_t)parameter;
    wifi_config_snapshot_t snapshot;

    if (delay_ms == 0U)
    {
        delay_ms = WIFI_CONFIG_AUTO_DELAY_MS;
    }

    rt_thread_mdelay(delay_ms);
    wifi_config_get_snapshot(&snapshot);
    if ((snapshot.saved == 0U) || (snapshot.auto_connect == 0U) || (snapshot.ssid[0] == '\0'))
    {
        rt_kprintf("[wifi_config] auto connect skipped saved=%lu auto=%lu ssid=%s\n",
                   (unsigned long)snapshot.saved,
                   (unsigned long)snapshot.auto_connect,
                   snapshot.ssid[0] ? snapshot.ssid : "(empty)");
        g_wifi_config.auto_thread = RT_NULL;
        return;
    }

    rt_kprintf("[wifi_config] auto connect ssid=%s\n", snapshot.ssid);
    (void)wifi_config_connect();
    (void)wifi_config_whd_diag();
    g_wifi_config.auto_thread = RT_NULL;
}

rt_err_t wifi_config_start_auto_connect(rt_uint32_t delay_ms)
{
    (void)wifi_config_service_init();

    if (g_wifi_config.auto_thread != RT_NULL)
    {
        return -RT_EBUSY;
    }

    g_wifi_config.auto_thread = rt_thread_create("wifi_auto",
                                                 wifi_config_auto_thread_entry,
                                                 (void *)(rt_ubase_t)delay_ms,
                                                 4096,
                                                 17,
                                                 10);
    if (g_wifi_config.auto_thread == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_thread_startup(g_wifi_config.auto_thread);
    return RT_EOK;
}

rt_err_t wifi_config_connect(void)
{
    char ssid[sizeof(g_wifi_config.snapshot.ssid)];
    char password[sizeof(g_wifi_config.snapshot.password)];
    rt_err_t ret;

    (void)wifi_config_service_init();
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    rt_strncpy(ssid, g_wifi_config.snapshot.ssid, sizeof(ssid) - 1);
    ssid[sizeof(ssid) - 1] = '\0';
    rt_strncpy(password, g_wifi_config.snapshot.password, sizeof(password) - 1);
    password[sizeof(password) - 1] = '\0';
    rt_mutex_release(&g_wifi_config.lock);

    if (ssid[0] == '\0')
    {
        rt_kprintf("[wifi_config] ssid is empty\n");
        return -RT_EINVAL;
    }

    rt_wlan_config_autoreconnect(RT_TRUE);
    ret = rt_wlan_connect(ssid, password);

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.last_result = ret;
    wifi_config_refresh_locked();
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] connect ssid=%s ret=%d connected=%d ready=%d rssi=%d\n",
               ssid,
               ret,
               rt_wlan_is_connected() ? 1 : 0,
               rt_wlan_is_ready() ? 1 : 0,
               rt_wlan_get_rssi());
    return ret;
}

rt_err_t wifi_config_disconnect(void)
{
    rt_err_t ret;

    (void)wifi_config_service_init();
    ret = rt_wlan_disconnect();

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.last_result = ret;
    wifi_config_refresh_locked();
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] disconnect ret=%d\n", ret);
    return ret;
}

rt_err_t wifi_config_scan(void)
{
    rt_err_t ret;
    rt_int32_t count = -2;

    (void)wifi_config_service_init();
    ret = rt_wlan_scan();

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.last_result = ret;
    g_wifi_config.snapshot.scan_count = count;
    wifi_config_refresh_locked();
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] scan ret=%d count=%ld netdev=%s flags=0x%lx\n",
               ret,
               (long)count,
               g_wifi_config.snapshot.netdev_name[0] ? g_wifi_config.snapshot.netdev_name : "(none)",
               (unsigned long)g_wifi_config.snapshot.netdev_flags);
    return ret;
}

rt_err_t wifi_config_diag(void)
{
    rt_err_t ret;

    (void)wifi_config_service_init();
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    wifi_config_refresh_locked();
    ret = (g_wifi_config.snapshot.netdev_name[0] != '\0') ? RT_EOK : -RT_ERROR;
    g_wifi_config.snapshot.last_result = ret;
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] diag ret=%d netdev=%s flags=0x%lx connected=%d ready=%d rssi=%d\n",
               ret,
               g_wifi_config.snapshot.netdev_name[0] ? g_wifi_config.snapshot.netdev_name : "(none)",
               (unsigned long)g_wifi_config.snapshot.netdev_flags,
               rt_wlan_is_connected() ? 1 : 0,
               rt_wlan_is_ready() ? 1 : 0,
               rt_wlan_get_rssi());
    return ret;
}

rt_err_t wifi_config_whd_diag(void)
{
    int stage = 0;
    int result = 0;
    rt_uint32_t flags = 0;
    rt_err_t ret;

    (void)wifi_config_service_init();
    whd_wlan_get_diag(&stage, &result, &flags);

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.whd_stage = stage;
    g_wifi_config.snapshot.whd_result = result;
    g_wifi_config.snapshot.whd_flags = flags;
    wifi_config_refresh_locked();
    ret = (stage > 0 && result == 0) ? RT_EOK : -RT_ERROR;
    g_wifi_config.snapshot.last_result = ret;
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] whd stage=%d result=%d flags=0x%lx netdev=%s ready=%d\n",
               stage,
               result,
               (unsigned long)flags,
               g_wifi_config.snapshot.netdev_name[0] ? g_wifi_config.snapshot.netdev_name : "(none)",
               rt_wlan_is_ready() ? 1 : 0);
    return ret;
}

void wifi_config_get_snapshot(wifi_config_snapshot_t *snapshot)
{
    if (snapshot == RT_NULL)
    {
        return;
    }

    (void)wifi_config_service_init();
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    wifi_config_refresh_locked();
    *snapshot = g_wifi_config.snapshot;
    rt_mutex_release(&g_wifi_config.lock);
}

void wifi_config_fill_voice_status(voice_status_msg_t *status)
{
    wifi_config_snapshot_t snapshot;

    if (status == RT_NULL)
    {
        return;
    }

    wifi_config_get_snapshot(&snapshot);
    status->netdev_flags = snapshot.netdev_flags;
    status->netdev_ip = snapshot.netdev_ip;
    status->netdev_gw = snapshot.netdev_gw;
    status->netdev_mask = snapshot.netdev_mask;
    status->netdev_dns0 = snapshot.netdev_dns0;
    status->wlan_connected = snapshot.wlan_connected;
    status->wlan_ready = snapshot.wlan_ready;
    status->wlan_rssi = snapshot.wlan_rssi;
    status->wifi_diag_result = snapshot.last_result;
    status->wifi_scan_count = snapshot.scan_count;
    status->whd_stage = snapshot.whd_stage;
    status->whd_result = snapshot.whd_result;
    status->whd_flags = snapshot.whd_flags;
    status->wifi_saved = snapshot.saved;
    status->wifi_auto_connect = snapshot.auto_connect;
    status->wifi_storage_result = snapshot.storage_result;
    rt_memset(status->netdev_name, 0, sizeof(status->netdev_name));
    rt_strncpy(status->netdev_name, snapshot.netdev_name, sizeof(status->netdev_name) - 1);
}
