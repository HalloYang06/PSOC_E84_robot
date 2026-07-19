#include "wifi_config_service.h"

#include <netdev_ipaddr.h>
#include <netdev.h>
#include <wlan_mgnt.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>

#define WIFI_CONFIG_FILE_PATH      "/flash/rehab_wifi.cfg"
#define WIFI_CONFIG_FILE_MAGIC     "rehab_wifi_v1"
#define WIFI_CONFIG_FAL_PART       "wifi_cfg"
#define WIFI_CONFIG_USE_FAL_STORE  1
#define WIFI_CONFIG_FAL_MAGIC      0x57494649U
#define WIFI_CONFIG_FAL_VERSION    1U
#define WIFI_CONFIG_FAL_RECORD_MAGIC_EMPTY 0xFFFFFFFFU
#define WIFI_CONFIG_FAL_ERASE_SIZE (64U * 1024U)
#define WIFI_CONFIG_AUTO_DELAY_MS  3500U
#define WIFI_CONFIG_SAVE_RETRIES   8U
#define WIFI_CONFIG_SAVE_RETRY_MS  250U
#define WIFI_CONFIG_DRIVER_WAIT_MS 45000U
#define WIFI_CONFIG_CONNECT_RETRIES 3U
#define WIFI_CONFIG_CONNECT_RETRY_MS 5000U
#define WIFI_CONFIG_READY_WAIT_MS 30000U
#define WIFI_CONFIG_CONNECT_SCAN_WAIT_MS 25000U

#if defined(RT_USING_FAL) && WIFI_CONFIG_USE_FAL_STORE
#include <fal.h>
#endif

void whd_wlan_get_diag(int *stage, int *result, rt_uint32_t *flags);
void whd_wlan_get_diag_extra(rt_uint32_t *extra0, rt_uint32_t *extra1);
extern volatile rt_uint32_t g_mmcsd_diag_core_init;
extern volatile rt_uint32_t g_mmcsd_diag_thread_started;
extern volatile rt_uint32_t g_mmcsd_diag_change_sent;
extern volatile rt_uint32_t g_mmcsd_diag_change_err;
extern volatile rt_uint32_t g_mmcsd_diag_recv_count;
extern volatile rt_uint32_t g_mmcsd_diag_power_up_count;
extern volatile rt_uint32_t g_mmcsd_diag_cmd5_before_count;
extern volatile rt_uint32_t g_mmcsd_diag_cmd5_after_count;
extern volatile rt_int32_t  g_mmcsd_diag_cmd5_last_err;

static void wifi_config_scan_thread_entry(void *parameter);

static struct
{
    struct rt_mutex lock;
    rt_bool_t initialized;
    rt_thread_t auto_thread;
    rt_bool_t connect_running;
    rt_thread_t scan_thread;
    rt_bool_t scan_handler_registered;
    rt_bool_t scan_done_handler_registered;
    rt_sem_t scan_done_sem;
    wifi_config_ap_t scan_aps[WIFI_CONFIG_SCAN_MAX_APS];
    wifi_config_snapshot_t snapshot;
} g_wifi_config;

typedef struct
{
    rt_uint32_t magic;
    rt_uint32_t version;
    rt_uint32_t auto_connect;
    char ssid[WIFI_CONFIG_SSID_MAX_LEN + 1];
    char password[WIFI_CONFIG_PASSWORD_MAX_LEN + 1];
    rt_uint32_t checksum;
} wifi_config_fal_record_t;

static rt_uint32_t wifi_config_checksum(const void *data, rt_size_t size)
{
    const rt_uint8_t *p = (const rt_uint8_t *)data;
    rt_uint32_t hash = 2166136261UL;

    while (size-- > 0U)
    {
        hash ^= *p++;
        hash *= 16777619UL;
    }

    return hash;
}

static rt_uint32_t wifi_config_record_checksum(const wifi_config_fal_record_t *record)
{
    return wifi_config_checksum(record,
                                (rt_size_t)((const rt_uint8_t *)&record->checksum -
                                            (const rt_uint8_t *)record));
}

#if defined(RT_USING_FAL) && WIFI_CONFIG_USE_FAL_STORE
static rt_bool_t wifi_config_record_is_valid(wifi_config_fal_record_t *record)
{
    if (record == RT_NULL)
    {
        return RT_FALSE;
    }

    record->ssid[sizeof(record->ssid) - 1] = '\0';
    record->password[sizeof(record->password) - 1] = '\0';

    return ((record->magic == WIFI_CONFIG_FAL_MAGIC) &&
            (record->version == WIFI_CONFIG_FAL_VERSION) &&
            (record->checksum == wifi_config_record_checksum(record)) &&
            (record->ssid[0] != '\0') &&
            (rt_strnlen(record->ssid, sizeof(record->ssid)) <= WIFI_CONFIG_SSID_MAX_LEN) &&
            (rt_strnlen(record->password, sizeof(record->password)) <= WIFI_CONFIG_PASSWORD_MAX_LEN)) ?
           RT_TRUE :
           RT_FALSE;
}

static rt_err_t wifi_config_load_fal_record(wifi_config_fal_record_t *latest_record)
{
    const struct fal_partition *part;
    wifi_config_fal_record_t record;
    rt_bool_t found = RT_FALSE;
    rt_uint32_t offset;

    if (latest_record == RT_NULL)
    {
        return -RT_EINVAL;
    }

    (void)fal_init();
    part = fal_partition_find(WIFI_CONFIG_FAL_PART);
    if (part == RT_NULL)
    {
        return -RT_ERROR;
    }

    for (offset = 0U;
         offset + sizeof(record) <= part->len;
         offset += sizeof(record))
    {
        if (fal_partition_read(part, offset, (rt_uint8_t *)&record, sizeof(record)) != sizeof(record))
        {
            return -RT_ERROR;
        }

        if (record.magic == WIFI_CONFIG_FAL_RECORD_MAGIC_EMPTY)
        {
            break;
        }

        if (wifi_config_record_is_valid(&record))
        {
            *latest_record = record;
            found = RT_TRUE;
        }
    }

    return found ? RT_EOK : -RT_ERROR;
}

static rt_err_t wifi_config_save_fal_record(const wifi_config_fal_record_t *record)
{
    const struct fal_partition *part;
    wifi_config_fal_record_t existing;
    rt_uint32_t offset;
    rt_uint32_t write_offset = 0xFFFFFFFFU;

    if (record == RT_NULL)
    {
        return -RT_EINVAL;
    }

    (void)fal_init();
    part = fal_partition_find(WIFI_CONFIG_FAL_PART);
    if (part == RT_NULL)
    {
        rt_kprintf("[wifi_config] fal part not found: %s\n", WIFI_CONFIG_FAL_PART);
        return -RT_ERROR;
    }

    for (offset = 0U;
         offset + sizeof(existing) <= part->len;
         offset += sizeof(existing))
    {
        if (fal_partition_read(part, offset, (rt_uint8_t *)&existing, sizeof(existing)) != sizeof(existing))
        {
            return -RT_ERROR;
        }

        if (existing.magic == WIFI_CONFIG_FAL_RECORD_MAGIC_EMPTY)
        {
            write_offset = offset;
            break;
        }
    }

    if (write_offset == 0xFFFFFFFFU)
    {
        rt_kprintf("[wifi_config] fal log full part=%s len=%lu\n",
                   WIFI_CONFIG_FAL_PART,
                   (unsigned long)part->len);
        if (fal_partition_erase(part, 0, part->len) < 0)
        {
            return -RT_ERROR;
        }
        write_offset = 0U;
    }

    if (fal_partition_write(part, write_offset, (const rt_uint8_t *)record, sizeof(*record)) != sizeof(*record))
    {
        return -RT_ERROR;
    }

    rt_kprintf("[wifi_config] fal append offset=%lu size=%lu\n",
               (unsigned long)write_offset,
               (unsigned long)sizeof(*record));
    return RT_EOK;
}
#endif

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

    g_wifi_config.snapshot.mmcsd_core_init = g_mmcsd_diag_core_init;
    g_wifi_config.snapshot.mmcsd_thread_started = g_mmcsd_diag_thread_started;
    g_wifi_config.snapshot.mmcsd_change_sent = g_mmcsd_diag_change_sent;
    g_wifi_config.snapshot.mmcsd_change_err = g_mmcsd_diag_change_err;
    g_wifi_config.snapshot.mmcsd_recv_count = g_mmcsd_diag_recv_count;
    g_wifi_config.snapshot.mmcsd_power_up_count = g_mmcsd_diag_power_up_count;
    g_wifi_config.snapshot.mmcsd_cmd5_before_count = g_mmcsd_diag_cmd5_before_count;
    g_wifi_config.snapshot.mmcsd_cmd5_after_count = g_mmcsd_diag_cmd5_after_count;
    g_wifi_config.snapshot.mmcsd_cmd5_last_err = g_mmcsd_diag_cmd5_last_err;

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

static rt_bool_t wifi_config_bssid_equal(const rt_uint8_t *lhs, const rt_uint8_t *rhs)
{
    return (rt_memcmp(lhs, rhs, sizeof(((wifi_config_ap_t *)0)->bssid)) == 0) ? RT_TRUE : RT_FALSE;
}

static void wifi_config_cache_ap_locked(const struct rt_wlan_info *info)
{
    rt_int32_t i;
    rt_int32_t target = -1;
    char ssid[WIFI_CONFIG_SSID_MAX_LEN + 1];
    rt_uint8_t ssid_len;

    if ((info == RT_NULL) || (info->ssid.len == 0U))
    {
        return;
    }

    ssid_len = info->ssid.len;
    if (ssid_len > WIFI_CONFIG_SSID_MAX_LEN)
    {
        ssid_len = WIFI_CONFIG_SSID_MAX_LEN;
    }

    rt_memset(ssid, 0, sizeof(ssid));
    rt_memcpy(ssid, info->ssid.val, ssid_len);

    for (i = 0; i < g_wifi_config.snapshot.scan_count; i++)
    {
        if ((rt_strcmp(g_wifi_config.scan_aps[i].ssid, ssid) == 0) &&
            wifi_config_bssid_equal(g_wifi_config.scan_aps[i].bssid, info->bssid))
        {
            target = i;
            break;
        }
    }

    if (target < 0)
    {
        if (g_wifi_config.snapshot.scan_count >= WIFI_CONFIG_SCAN_MAX_APS)
        {
            target = 0;
            for (i = 1; i < WIFI_CONFIG_SCAN_MAX_APS; i++)
            {
                if (g_wifi_config.scan_aps[i].rssi < g_wifi_config.scan_aps[target].rssi)
                {
                    target = i;
                }
            }

            if (info->rssi <= g_wifi_config.scan_aps[target].rssi)
            {
                return;
            }
        }
        else
        {
            target = g_wifi_config.snapshot.scan_count++;
        }
    }

    rt_memset(&g_wifi_config.scan_aps[target], 0, sizeof(g_wifi_config.scan_aps[target]));
    rt_strncpy(g_wifi_config.scan_aps[target].ssid, ssid, sizeof(g_wifi_config.scan_aps[target].ssid) - 1);
    g_wifi_config.scan_aps[target].rssi = info->rssi;
    g_wifi_config.scan_aps[target].channel = info->channel;
    g_wifi_config.scan_aps[target].security = (rt_uint32_t)info->security;
    rt_memcpy(g_wifi_config.scan_aps[target].bssid, info->bssid, sizeof(g_wifi_config.scan_aps[target].bssid));
}

static void wifi_config_scan_report_cb(int event, struct rt_wlan_buff *buff, void *parameter)
{
    struct rt_wlan_info *info;

    RT_UNUSED(parameter);

    if ((event != RT_WLAN_EVT_SCAN_REPORT) || (buff == RT_NULL) || (buff->data == RT_NULL))
    {
        return;
    }

    info = (struct rt_wlan_info *)buff->data;
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.scan_callback_count++;
    wifi_config_cache_ap_locked(info);
    rt_mutex_release(&g_wifi_config.lock);
}

static void wifi_config_scan_done_cb(int event, struct rt_wlan_buff *buff, void *parameter)
{
    RT_UNUSED(buff);
    RT_UNUSED(parameter);

    if (event != RT_WLAN_EVT_SCAN_DONE)
    {
        return;
    }

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.scan_done_count++;
    rt_mutex_release(&g_wifi_config.lock);

    if (g_wifi_config.scan_done_sem != RT_NULL)
    {
        rt_sem_release(g_wifi_config.scan_done_sem);
    }
}

static rt_bool_t wifi_config_find_cached_info_locked(const char *ssid, struct rt_wlan_info *info)
{
    rt_int32_t best = -1;

    if ((ssid == RT_NULL) || (info == RT_NULL))
    {
        return RT_FALSE;
    }

    for (rt_int32_t i = 0; i < g_wifi_config.snapshot.scan_count; i++)
    {
        if (rt_strcmp(g_wifi_config.scan_aps[i].ssid, ssid) != 0)
        {
            continue;
        }

        if ((best < 0) || (g_wifi_config.scan_aps[i].rssi > g_wifi_config.scan_aps[best].rssi))
        {
            best = i;
        }
    }

    if (best < 0)
    {
        return RT_FALSE;
    }

    rt_memset(info, 0, sizeof(*info));
    info->security = (rt_wlan_security_t)g_wifi_config.scan_aps[best].security;
    info->channel = g_wifi_config.scan_aps[best].channel;
    info->rssi = g_wifi_config.scan_aps[best].rssi;
    rt_strncpy((char *)info->ssid.val, g_wifi_config.scan_aps[best].ssid, sizeof(info->ssid.val) - 1);
    info->ssid.len = (rt_uint8_t)rt_strlen(g_wifi_config.scan_aps[best].ssid);
    rt_memcpy(info->bssid, g_wifi_config.scan_aps[best].bssid, sizeof(info->bssid));
    return RT_TRUE;
}

static rt_err_t wifi_config_wait_scan_done(rt_uint32_t timeout_ms)
{
    rt_uint32_t waited_ms = 0U;
    wifi_config_snapshot_t snapshot;

    while (waited_ms < timeout_ms)
    {
        wifi_config_get_snapshot(&snapshot);
        if (snapshot.scan_running == 0U)
        {
            return snapshot.scan_result;
        }
        rt_thread_mdelay(250);
        waited_ms += 250U;
    }

    return -RT_ETIMEOUT;
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
    g_wifi_config.snapshot.connect_result = -RT_ERROR;
    g_wifi_config.snapshot.connect_ready = 0U;
    g_wifi_config.snapshot.scan_count = -1;
    g_wifi_config.snapshot.scan_result = -RT_ERROR;
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
    rt_err_t ret = -RT_ERROR;

    (void)wifi_config_service_init();

#if defined(RT_USING_FAL) && WIFI_CONFIG_USE_FAL_STORE
    {
        wifi_config_fal_record_t record;

        if (wifi_config_load_fal_record(&record) == RT_EOK)
        {
            rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
            rt_memset(g_wifi_config.snapshot.ssid, 0, sizeof(g_wifi_config.snapshot.ssid));
            rt_memset(g_wifi_config.snapshot.password, 0, sizeof(g_wifi_config.snapshot.password));
            rt_strncpy(g_wifi_config.snapshot.ssid, record.ssid, sizeof(g_wifi_config.snapshot.ssid) - 1);
            rt_strncpy(g_wifi_config.snapshot.password, record.password, sizeof(g_wifi_config.snapshot.password) - 1);
            g_wifi_config.snapshot.auto_connect = record.auto_connect ? 1U : 0U;
            g_wifi_config.snapshot.saved = 1U;
            g_wifi_config.snapshot.storage_result = RT_EOK;
            rt_mutex_release(&g_wifi_config.lock);

            rt_kprintf("[wifi_config] loaded fal ssid=%s auto=%lu\n",
                       record.ssid,
                       (unsigned long)(record.auto_connect ? 1U : 0U));
            return RT_EOK;
        }
    }
#endif

#ifdef RT_USING_DFS
    {
        FILE *file;
        char magic[32];
        char auto_line[16];
        char ssid[WIFI_CONFIG_SSID_MAX_LEN + 4];
        char password[WIFI_CONFIG_PASSWORD_MAX_LEN + 4];

        ret = RT_EOK;
        file = fopen(WIFI_CONFIG_FILE_PATH, "r");
        if (file != RT_NULL)
        {
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

            if ((ret == RT_EOK) && (rt_strcmp(magic, WIFI_CONFIG_FILE_MAGIC) == 0) &&
                (ssid[0] != '\0') && (rt_strlen(ssid) <= WIFI_CONFIG_SSID_MAX_LEN) &&
                (rt_strlen(password) <= WIFI_CONFIG_PASSWORD_MAX_LEN))
            {
                rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
                rt_memset(g_wifi_config.snapshot.ssid, 0, sizeof(g_wifi_config.snapshot.ssid));
                rt_memset(g_wifi_config.snapshot.password, 0, sizeof(g_wifi_config.snapshot.password));
                rt_strncpy(g_wifi_config.snapshot.ssid, ssid, sizeof(g_wifi_config.snapshot.ssid) - 1);
                rt_strncpy(g_wifi_config.snapshot.password, password, sizeof(g_wifi_config.snapshot.password) - 1);
                g_wifi_config.snapshot.auto_connect = (auto_line[0] == '0') ? 0U : 1U;
                g_wifi_config.snapshot.saved = 1U;
                g_wifi_config.snapshot.storage_result = RT_EOK;
                rt_mutex_release(&g_wifi_config.lock);

                rt_kprintf("[wifi_config] loaded file ssid=%s auto=%lu\n",
                           ssid,
                           (unsigned long)((auto_line[0] == '0') ? 0U : 1U));
                return RT_EOK;
            }
        }
    }
#endif

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.saved = 0U;
    g_wifi_config.snapshot.storage_result = ret;
    rt_mutex_release(&g_wifi_config.lock);
    return ret;
}

rt_err_t wifi_config_save(void)
{
    char ssid[sizeof(g_wifi_config.snapshot.ssid)];
    char password[sizeof(g_wifi_config.snapshot.password)];
    rt_uint32_t auto_connect;
    rt_err_t ret = -RT_ERROR;

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

#if defined(RT_USING_FAL) && WIFI_CONFIG_USE_FAL_STORE
    {
        wifi_config_fal_record_t record;

        rt_memset(&record, 0, sizeof(record));
        record.magic = WIFI_CONFIG_FAL_MAGIC;
        record.version = WIFI_CONFIG_FAL_VERSION;
        record.auto_connect = auto_connect ? 1U : 0U;
        rt_strncpy(record.ssid, ssid, sizeof(record.ssid) - 1);
        rt_strncpy(record.password, password, sizeof(record.password) - 1);
        record.checksum = wifi_config_record_checksum(&record);

        ret = wifi_config_save_fal_record(&record);
    }
#endif

#ifdef RT_USING_DFS
    if (ret != RT_EOK)
    {
        FILE *file = RT_NULL;

    for (rt_uint32_t attempt = 0; attempt < WIFI_CONFIG_SAVE_RETRIES; attempt++)
    {
        file = fopen(WIFI_CONFIG_FILE_PATH, "w");
        if (file != RT_NULL)
        {
            break;
        }
        rt_thread_mdelay(WIFI_CONFIG_SAVE_RETRY_MS);
    }

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
    }
#endif

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.saved = (ret == RT_EOK) ? 1U : 0U;
    g_wifi_config.snapshot.storage_result = ret;
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] save ret=%d part=%s path=%s ssid=%s auto=%lu\n",
               ret,
               WIFI_CONFIG_FAL_PART,
               WIFI_CONFIG_FILE_PATH,
               ssid,
               (unsigned long)(auto_connect ? 1U : 0U));
    return ret;
}

rt_err_t wifi_config_forget(void)
{
    rt_err_t ret = RT_EOK;

    (void)wifi_config_service_init();

#if defined(RT_USING_FAL) && WIFI_CONFIG_USE_FAL_STORE
    {
        const struct fal_partition *part;

        (void)fal_init();
        part = fal_partition_find(WIFI_CONFIG_FAL_PART);
        if ((part == RT_NULL) ||
            (fal_partition_erase(part, 0, WIFI_CONFIG_FAL_ERASE_SIZE) < 0))
        {
            ret = -RT_ERROR;
        }
    }
#endif

#ifdef RT_USING_DFS
    if (remove(WIFI_CONFIG_FILE_PATH) != 0)
    {
        const int remove_errno = errno;

        /* RT-Thread's DFS POSIX wrapper may expose errno with either sign. */
        if ((remove_errno != ENOENT) && (remove_errno != -ENOENT))
        {
            ret = -RT_ERROR;
        }
    }
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
    rt_err_t ret = -RT_ERROR;

    if (delay_ms == 0U)
    {
        delay_ms = WIFI_CONFIG_AUTO_DELAY_MS;
    }

    rt_thread_mdelay(delay_ms);
    (void)wifi_config_load();
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
    for (rt_uint32_t attempt = 0; attempt < WIFI_CONFIG_CONNECT_RETRIES; attempt++)
    {
        ret = wifi_config_connect();
        (void)wifi_config_whd_diag();
        wifi_config_get_snapshot(&snapshot);
        if ((ret == RT_EOK) || ((snapshot.wlan_ready != 0U) && (snapshot.netdev_ip != 0U)))
        {
            break;
        }
        rt_kprintf("[wifi_config] auto connect retry %lu/%lu ret=%d ready=%lu ip=0x%08lx\n",
                   (unsigned long)(attempt + 1U),
                   (unsigned long)WIFI_CONFIG_CONNECT_RETRIES,
                   ret,
                   (unsigned long)snapshot.wlan_ready,
                   (unsigned long)snapshot.netdev_ip);
        rt_thread_mdelay(WIFI_CONFIG_CONNECT_RETRY_MS);
    }
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
    rt_uint32_t waited_ms = 0U;
    rt_uint32_t ready_waited_ms = 0U;
    rt_bool_t ready = RT_FALSE;
    struct rt_wlan_info info;
    rt_bool_t scanned_before_connect = RT_FALSE;

    (void)wifi_config_service_init();
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    if (g_wifi_config.connect_running)
    {
        rt_mutex_release(&g_wifi_config.lock);
        rt_kprintf("[wifi_config] connect already running\n");
        return -RT_EBUSY;
    }
    g_wifi_config.connect_running = RT_TRUE;
    rt_strncpy(ssid, g_wifi_config.snapshot.ssid, sizeof(ssid) - 1);
    ssid[sizeof(ssid) - 1] = '\0';
    rt_strncpy(password, g_wifi_config.snapshot.password, sizeof(password) - 1);
    password[sizeof(password) - 1] = '\0';

retry_find_ap:
    wifi_config_refresh_locked();
    if ((g_wifi_config.snapshot.wlan_ready != 0U) &&
        (g_wifi_config.snapshot.netdev_ip != 0U))
    {
        g_wifi_config.snapshot.connect_result = RT_EOK;
        g_wifi_config.snapshot.connect_ready = 1U;
        g_wifi_config.snapshot.last_result = RT_EOK;
        g_wifi_config.connect_running = RT_FALSE;
        rt_mutex_release(&g_wifi_config.lock);
        rt_kprintf("[wifi_config] connect skipped: already ready ip=0x%08lx\n",
                   (unsigned long)g_wifi_config.snapshot.netdev_ip);
        return RT_EOK;
    }

    if (!wifi_config_find_cached_info_locked(ssid, &info))
    {
        if (scanned_before_connect)
        {
            rt_mutex_release(&g_wifi_config.lock);
            rt_kprintf("[wifi_config] no cached AP for ssid=%s after scan\n", ssid);
            rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
            g_wifi_config.connect_running = RT_FALSE;
            g_wifi_config.snapshot.connect_result = -RT_ERROR;
            g_wifi_config.snapshot.connect_ready = 0U;
            g_wifi_config.snapshot.last_result = -RT_ERROR;
            wifi_config_refresh_locked();
            rt_mutex_release(&g_wifi_config.lock);
            return -RT_ERROR;
        }
        rt_mutex_release(&g_wifi_config.lock);
        rt_kprintf("[wifi_config] no cached AP for ssid=%s; scan before connect\n", ssid);
        ret = wifi_config_scan();
        if (ret == RT_EOK)
        {
            ret = wifi_config_wait_scan_done(WIFI_CONFIG_CONNECT_SCAN_WAIT_MS);
            rt_kprintf("[wifi_config] pre-connect scan ret=%d\n", ret);
            if (ret == RT_EOK)
            {
                scanned_before_connect = RT_TRUE;
                goto retry_find_ap;
            }
        }
        rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
        g_wifi_config.connect_running = RT_FALSE;
        g_wifi_config.snapshot.connect_result = ret;
        g_wifi_config.snapshot.connect_ready = 0U;
        g_wifi_config.snapshot.last_result = ret;
        wifi_config_refresh_locked();
        rt_mutex_release(&g_wifi_config.lock);
        return ret;
    }
    rt_mutex_release(&g_wifi_config.lock);

    if (ssid[0] == '\0')
    {
        rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
        g_wifi_config.connect_running = RT_FALSE;
        g_wifi_config.snapshot.connect_result = -RT_EINVAL;
        g_wifi_config.snapshot.connect_ready = 0U;
        rt_mutex_release(&g_wifi_config.lock);
        rt_kprintf("[wifi_config] ssid is empty\n");
        return -RT_EINVAL;
    }

    while (waited_ms < WIFI_CONFIG_DRIVER_WAIT_MS)
    {
        wifi_config_snapshot_t snapshot;

        (void)wifi_config_whd_diag();
        wifi_config_get_snapshot(&snapshot);
        if ((snapshot.whd_result == 0) &&
            (snapshot.netdev_name[0] != '\0') &&
            ((snapshot.netdev_flags & NETDEV_FLAG_UP) != 0U))
        {
            break;
        }

        rt_thread_mdelay(1000);
        waited_ms += 1000U;
    }

    rt_wlan_config_autoreconnect(RT_TRUE);
    ret = rt_wlan_connect_adv(&info, password);
    while ((ret == RT_EOK) && (ready_waited_ms < WIFI_CONFIG_READY_WAIT_MS))
    {
        wifi_config_snapshot_t snapshot;

        (void)wifi_config_whd_diag();
        wifi_config_get_snapshot(&snapshot);
        if ((snapshot.wlan_ready != 0U) && (snapshot.netdev_ip != 0U))
        {
            ready = RT_TRUE;
            break;
        }

        rt_thread_mdelay(1000);
        ready_waited_ms += 1000U;
    }

    if (!ready)
    {
        rt_kprintf("[wifi_config] connect_adv did not become ready ret=%d; fallback simple connect\n", ret);
        (void)rt_wlan_disconnect();
        rt_thread_mdelay(1000);
        ready_waited_ms = 0U;
        ret = rt_wlan_connect(ssid, password);
        while ((ret == RT_EOK) && (ready_waited_ms < WIFI_CONFIG_READY_WAIT_MS))
        {
            wifi_config_snapshot_t snapshot;

            (void)wifi_config_whd_diag();
            wifi_config_get_snapshot(&snapshot);
            if ((snapshot.wlan_ready != 0U) && (snapshot.netdev_ip != 0U))
            {
                ready = RT_TRUE;
                break;
            }

            rt_thread_mdelay(1000);
            ready_waited_ms += 1000U;
        }
    }

    if ((ret == RT_EOK) && !ready)
    {
        ret = -RT_ETIMEOUT;
    }

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.connect_result = ret;
    g_wifi_config.snapshot.connect_ready = ready ? 1U : 0U;
    g_wifi_config.snapshot.last_result = ret;
    wifi_config_refresh_locked();
    g_wifi_config.connect_running = RT_FALSE;
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] connect ssid=%s ret=%d connected=%d ready=%d rssi=%d waited=%lu ready_wait=%lu\n",
               ssid,
               ret,
               rt_wlan_is_connected() ? 1 : 0,
               rt_wlan_is_ready() ? 1 : 0,
               rt_wlan_get_rssi(),
               (unsigned long)waited_ms,
               (unsigned long)ready_waited_ms);
    return ret;
}

rt_err_t wifi_config_disconnect(void)
{
    rt_err_t ret;

    (void)wifi_config_service_init();
    ret = rt_wlan_disconnect();

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.last_result = ret;
    g_wifi_config.snapshot.connect_result = ret;
    g_wifi_config.snapshot.connect_ready = 0U;
    wifi_config_refresh_locked();
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] disconnect ret=%d\n", ret);
    return ret;
}

rt_err_t wifi_config_scan(void)
{
    rt_err_t ret = RT_EOK;

    (void)wifi_config_service_init();

    if (g_wifi_config.scan_thread != RT_NULL)
    {
        rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
        g_wifi_config.snapshot.last_result = -RT_EBUSY;
        g_wifi_config.snapshot.scan_request_count++;
        wifi_config_refresh_locked();
        rt_mutex_release(&g_wifi_config.lock);
        return -RT_EBUSY;
    }

    g_wifi_config.scan_thread = rt_thread_create("wifi_scan",
                                                 wifi_config_scan_thread_entry,
                                                 RT_NULL,
                                                 4096,
                                                 18,
                                                 10);
    if (g_wifi_config.scan_thread == RT_NULL)
    {
        ret = -RT_ENOMEM;
    }
    else
    {
        rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
        g_wifi_config.snapshot.scan_running = 1U;
        g_wifi_config.snapshot.scan_result = RT_EOK;
        g_wifi_config.snapshot.scan_count = 0;
        g_wifi_config.snapshot.scan_request_count++;
        g_wifi_config.snapshot.scan_callback_count = 0U;
        g_wifi_config.snapshot.scan_done_count = 0U;
        rt_memset(g_wifi_config.scan_aps, 0, sizeof(g_wifi_config.scan_aps));
        wifi_config_refresh_locked();
        rt_mutex_release(&g_wifi_config.lock);
        rt_thread_startup(g_wifi_config.scan_thread);
    }

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.last_result = ret;
    if (ret != RT_EOK)
    {
        g_wifi_config.snapshot.scan_running = 0U;
        g_wifi_config.snapshot.scan_result = ret;
    }
    wifi_config_refresh_locked();
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] scan start ret=%d count=%ld netdev=%s flags=0x%lx\n",
               ret,
               (long)g_wifi_config.snapshot.scan_count,
               g_wifi_config.snapshot.netdev_name[0] ? g_wifi_config.snapshot.netdev_name : "(none)",
               (unsigned long)g_wifi_config.snapshot.netdev_flags);
    return ret;
}

static void wifi_config_scan_thread_entry(void *parameter)
{
    rt_err_t ret;
    rt_int32_t count;

    RT_UNUSED(parameter);

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    rt_memset(g_wifi_config.scan_aps, 0, sizeof(g_wifi_config.scan_aps));
    g_wifi_config.snapshot.scan_count = 0;
    g_wifi_config.snapshot.scan_running = 1U;
    g_wifi_config.snapshot.scan_result = RT_EOK;
    g_wifi_config.snapshot.scan_callback_count = 0U;
    g_wifi_config.snapshot.scan_done_count = 0U;
    rt_mutex_release(&g_wifi_config.lock);

    if (g_wifi_config.scan_done_sem == RT_NULL)
    {
        g_wifi_config.scan_done_sem = rt_sem_create("wifi_done", 0, RT_IPC_FLAG_PRIO);
    }
    if (g_wifi_config.scan_done_sem == RT_NULL)
    {
        ret = -RT_ENOMEM;
        goto finish_scan;
    }

    ret = rt_wlan_register_event_handler(RT_WLAN_EVT_SCAN_REPORT,
                                         wifi_config_scan_report_cb,
                                         RT_NULL);
    if (ret == RT_EOK)
    {
        g_wifi_config.scan_handler_registered = RT_TRUE;
    }

    if (ret == RT_EOK)
    {
        ret = rt_wlan_register_event_handler(RT_WLAN_EVT_SCAN_DONE,
                                             wifi_config_scan_done_cb,
                                             RT_NULL);
        if (ret == RT_EOK)
        {
            g_wifi_config.scan_done_handler_registered = RT_TRUE;
        }
    }

    if (ret == RT_EOK)
    {
        ret = rt_wlan_scan();
    }

    if (ret == RT_EOK)
    {
        if (rt_sem_take(g_wifi_config.scan_done_sem, rt_tick_from_millisecond(20000)) != RT_EOK)
        {
            rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
            g_wifi_config.snapshot.scan_timeout_count++;
            rt_mutex_release(&g_wifi_config.lock);
            ret = -RT_ETIMEOUT;
        }
    }

finish_scan:
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.last_result = ret;
    g_wifi_config.snapshot.scan_result = ret;
    g_wifi_config.snapshot.scan_running = 0U;
    count = g_wifi_config.snapshot.scan_count;
    wifi_config_refresh_locked();
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] scan done ret=%d count=%ld\n", ret, (long)count);
    if (g_wifi_config.scan_done_handler_registered)
    {
        (void)rt_wlan_unregister_event_handler(RT_WLAN_EVT_SCAN_DONE);
        g_wifi_config.scan_done_handler_registered = RT_FALSE;
    }
    if (g_wifi_config.scan_handler_registered)
    {
        (void)rt_wlan_unregister_event_handler(RT_WLAN_EVT_SCAN_REPORT);
        g_wifi_config.scan_handler_registered = RT_FALSE;
    }
    if (g_wifi_config.scan_done_sem != RT_NULL)
    {
        rt_sem_delete(g_wifi_config.scan_done_sem);
        g_wifi_config.scan_done_sem = RT_NULL;
    }
    g_wifi_config.scan_thread = RT_NULL;
}

rt_int32_t wifi_config_get_scan_count(void)
{
    rt_int32_t count;

    (void)wifi_config_service_init();
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    count = g_wifi_config.snapshot.scan_count;
    rt_mutex_release(&g_wifi_config.lock);
    return count;
}

rt_err_t wifi_config_get_scan_ap(rt_int32_t index, wifi_config_ap_t *ap)
{
    if (ap == RT_NULL)
    {
        return -RT_EINVAL;
    }

    (void)wifi_config_service_init();
    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    if ((index < 0) || (index >= g_wifi_config.snapshot.scan_count) ||
        (index >= WIFI_CONFIG_SCAN_MAX_APS))
    {
        rt_mutex_release(&g_wifi_config.lock);
        return -RT_EINVAL;
    }

    *ap = g_wifi_config.scan_aps[index];
    rt_mutex_release(&g_wifi_config.lock);
    return RT_EOK;
}

const char *wifi_config_security_name(rt_uint32_t security)
{
    switch (security)
    {
    case SECURITY_OPEN:
        return "OPEN";
    case SECURITY_WEP_PSK:
        return "WEP";
    case SECURITY_WEP_SHARED:
        return "WEP";
    case SECURITY_WPA_TKIP_PSK:
        return "WPA";
    case SECURITY_WPA_AES_PSK:
        return "WPA";
    case SECURITY_WPA2_AES_PSK:
        return "WPA2";
    case SECURITY_WPA2_TKIP_PSK:
        return "WPA2";
    case SECURITY_WPA2_MIXED_PSK:
        return "WPA2";
    case SECURITY_WPS_OPEN:
        return "WPS";
    case SECURITY_WPS_SECURE:
        return "WPS";
    default:
        return "SEC";
    }
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
    rt_uint32_t extra0 = 0;
    rt_uint32_t extra1 = 0;
    rt_err_t ret;

    (void)wifi_config_service_init();
    whd_wlan_get_diag(&stage, &result, &flags);
    whd_wlan_get_diag_extra(&extra0, &extra1);

    rt_mutex_take(&g_wifi_config.lock, RT_WAITING_FOREVER);
    g_wifi_config.snapshot.whd_stage = stage;
    g_wifi_config.snapshot.whd_result = result;
    g_wifi_config.snapshot.whd_flags = flags;
    g_wifi_config.snapshot.whd_extra0 = extra0;
    g_wifi_config.snapshot.whd_extra1 = extra1;
    wifi_config_refresh_locked();
    ret = (stage > 0 && result == 0) ? RT_EOK : -RT_ERROR;
    g_wifi_config.snapshot.last_result = ret;
    rt_mutex_release(&g_wifi_config.lock);

    rt_kprintf("[wifi_config] whd stage=%d result=%d flags=0x%lx extra=%lx/%lx netdev=%s ready=%d\n",
               stage,
               result,
               (unsigned long)flags,
               (unsigned long)extra0,
               (unsigned long)extra1,
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
    status->cloud_tcp_result = snapshot.connect_result;
    status->cloud_tcp_errno = (rt_int32_t)snapshot.connect_ready;
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
