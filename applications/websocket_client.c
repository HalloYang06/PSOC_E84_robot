#include "websocket_client.h"

#include <ipc/completion.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <lwip/err.h>
#include <lwip/altcp.h>
#include <lwip/ip_addr.h>
#include <lwip/netif.h>
#include <lwip/opt.h>
#include <lwip/apps/websocket_client.h>
#include <lwip/tcpip.h>
#include <netdev.h>

#define WS_URL_BUFFER_SIZE 192
#define WS_HOST_BUFFER_SIZE 64
#define WS_PATH_BUFFER_SIZE 160
#define WS_HEADER_BUFFER_SIZE 1024
#define WS_CONNECT_WAIT_MS 8000
#define WS_DISCONNECT_WAIT_MS 1000

typedef enum
{
    WS_STAGE_IDLE = 0,
    WS_STAGE_PARSE_URL = 5,
    WS_STAGE_INIT = 10,
    WS_STAGE_CONNECT_START = 20,
    WS_STAGE_BIND_LOCAL = 25,
    WS_STAGE_WAIT_101 = 30,
    WS_STAGE_CONNECTED = 70,
    WS_STAGE_DISCONNECTED = 80
} websocket_stage_t;

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t connecting;
    rt_bool_t connected;
    char server_url[WS_URL_BUFFER_SIZE];
    char server_host[WS_HOST_BUFFER_SIZE];
    char server_path[WS_PATH_BUFFER_SIZE];
    char extra_headers[WS_HEADER_BUFFER_SIZE];
    int server_port;
    int last_stage;
    int last_errno;
    struct rt_mutex send_lock;
    struct rt_completion connect_done;
    websocket_message_callback_t callback;
    wsock_state_t wsock;
} websocket_client_t;

typedef struct
{
    err_t result;
    char header_fmt[WS_HEADER_BUFFER_SIZE];
} websocket_connect_job_t;

static websocket_client_t g_ws;

static void websocket_set_diag(int stage, int err)
{
    g_ws.last_stage = stage;
    g_ws.last_errno = err;
}

static rt_err_t websocket_parse_url(const char *server_url)
{
    const char *host_start;
    const char *path_start;
    const char *port_start;
    rt_size_t host_len;

    if ((server_url == RT_NULL) || (rt_strncmp(server_url, "ws://", 5) != 0))
    {
        return -RT_EINVAL;
    }

    host_start = server_url + 5;
    path_start = strchr(host_start, '/');
    port_start = strchr(host_start, ':');

    if ((path_start != RT_NULL) && (rt_strlen(path_start) >= sizeof(g_ws.server_path)))
    {
        return -RT_EINVAL;
    }

    rt_memset(g_ws.server_path, 0, sizeof(g_ws.server_path));
    rt_strncpy(g_ws.server_path, path_start ? path_start : "/", sizeof(g_ws.server_path) - 1);

    if ((port_start != RT_NULL) && ((path_start == RT_NULL) || (port_start < path_start)))
    {
        host_len = (rt_size_t)(port_start - host_start);
        g_ws.server_port = atoi(port_start + 1);
    }
    else
    {
        host_len = path_start ? (rt_size_t)(path_start - host_start) : rt_strlen(host_start);
        g_ws.server_port = 80;
    }

    if ((host_len == 0) || (host_len >= sizeof(g_ws.server_host)) || (g_ws.server_port <= 0))
    {
        return -RT_EINVAL;
    }

    rt_memset(g_ws.server_host, 0, sizeof(g_ws.server_host));
    rt_memcpy(g_ws.server_host, host_start, host_len);
    g_ws.server_host[host_len] = '\0';
    return RT_EOK;
}

static int websocket_build_extra_header_format(char *out, rt_size_t out_len)
{
    const char *cursor = g_ws.extra_headers;
    rt_size_t used = 0;

    if ((out == RT_NULL) || (out_len == 0))
    {
        return -RT_EINVAL;
    }
    out[0] = '\0';

    while (*cursor != '\0')
    {
        const char *line_end = rt_strstr(cursor, "\r\n");
        rt_size_t line_len = line_end ? (rt_size_t)(line_end - cursor) : rt_strlen(cursor);
        const char *line_start = cursor;
        const char *value_start;
        const char *colon;
        rt_size_t name_len;
        rt_size_t value_len;

        if (line_len == 0)
        {
            break;
        }

        colon = memchr(cursor, ':', line_len);
        if (colon == RT_NULL)
        {
            return -RT_EINVAL;
        }

        name_len = (rt_size_t)(colon - cursor);
        value_len = line_len - name_len - 1;
        value_start = colon + 1;
        while ((value_len > 0) && (*value_start == ' '))
        {
            value_start++;
            value_len--;
        }

        if ((used + name_len + value_len + 5) >= out_len)
        {
            return -RT_EFULL;
        }

        rt_memcpy(out + used, line_start, name_len);
        used += name_len;
        out[used++] = ':';
        out[used++] = ' ';
        rt_memcpy(out + used, value_start, value_len);
        used += value_len;
        out[used++] = '\r';
        out[used++] = '\n';
        out[used] = '\0';

        cursor = line_end ? line_end + 2 : value_start + value_len;
    }

    return (int)used;
}

static err_t websocket_wsock_callback(int code, char *buf, size_t len)
{
    if (code == WS_CONNECT)
    {
        int status = (int)(uintptr_t)buf;

        g_ws.connecting = RT_FALSE;
        if (status == 101)
        {
            g_ws.connected = RT_TRUE;
            websocket_set_diag(WS_STAGE_CONNECTED, 0);
        }
        else
        {
            g_ws.connected = RT_FALSE;
            websocket_set_diag(WS_STAGE_WAIT_101, status > 0 ? -status : -RT_EPERM);
        }
        rt_completion_done(&g_ws.connect_done);
        return ERR_OK;
    }

    if (code == WS_DISCONNECT)
    {
        int err = (int)(uintptr_t)buf;

        g_ws.connecting = RT_FALSE;
        g_ws.connected = RT_FALSE;
        websocket_set_diag(WS_STAGE_DISCONNECTED, err);
        rt_completion_done(&g_ws.connect_done);
        return ERR_OK;
    }

    if (((code == WS_TEXT) || (code == WS_DATA)) && (g_ws.callback != RT_NULL))
    {
        g_ws.callback(code == WS_TEXT ? WEBSOCKET_MESSAGE_TEXT : WEBSOCKET_MESSAGE_BINARY,
                      (const rt_uint8_t *)buf,
                      (rt_size_t)len);
    }

    return ERR_OK;
}

static void websocket_start_connect_job(void *ctx)
{
    websocket_connect_job_t *job = (websocket_connect_job_t *)ctx;
    struct netdev *rt_netdev = netdev_default;
    const ip_addr_t *bind_ip = RT_NULL;
    err_t err;

    rt_memset(&g_ws.wsock, 0, sizeof(g_ws.wsock));
    err = wsock_init(&g_ws.wsock, 0, 1, websocket_wsock_callback);
    if (err != ERR_OK)
    {
        job->result = err;
        return;
    }

    if ((rt_netdev != RT_NULL) &&
        ((rt_netdev->flags & NETDEV_FLAG_UP) != 0U) &&
        ((rt_netdev->flags & NETDEV_FLAG_LINK_UP) != 0U) &&
        !ip_addr_isany(&rt_netdev->ip_addr))
    {
        bind_ip = &rt_netdev->ip_addr;
        rt_kprintf("[websocket] netdev default=%s flags=0x%04x ip=0x%08lx gw=0x%08lx\n",
                   rt_netdev->name,
                   rt_netdev->flags,
                   (unsigned long)ip4_addr_get_u32(ip_2_ip4(&rt_netdev->ip_addr)),
                   (unsigned long)ip4_addr_get_u32(ip_2_ip4(&rt_netdev->gw)));
    }
    else if ((netif_default != RT_NULL) &&
             netif_is_up(netif_default) &&
             netif_is_link_up(netif_default) &&
             !ip_addr_isany(netif_ip_addr4(netif_default)))
    {
        bind_ip = netif_ip_addr4(netif_default);
        rt_kprintf("[websocket] lwip default=%c%c%d flags=0x%02x ip=0x%08lx gw=0x%08lx\n",
                   netif_default->name[0],
                   netif_default->name[1],
                   netif_default->num,
                   netif_default->flags,
                   (unsigned long)ip4_addr_get_u32(netif_ip4_addr(netif_default)),
                   (unsigned long)ip4_addr_get_u32(netif_ip4_gw(netif_default)));
    }
    else
    {
        rt_kprintf("[websocket] no usable default netdev/netif for bind\n");
    }

    if (bind_ip != RT_NULL)
    {
        err = altcp_bind(g_ws.wsock.pcb, bind_ip, 0);
        if (err != ERR_OK)
        {
            job->result = err;
            websocket_set_diag(WS_STAGE_BIND_LOCAL, err);
            return;
        }
    }

    job->result = wsock_connect(&g_ws.wsock,
                                (uint16_t)(rt_strlen(g_ws.server_path) + rt_strlen(g_ws.server_host) +
                                           rt_strlen(job->header_fmt) + WSOCK_KEY_SIZE + 128 + 1),
                                g_ws.server_host,
                                g_ws.server_path,
                                (u16_t)g_ws.server_port,
                                RT_NULL,
                                RT_NULL,
                                "%s",
                                job->header_fmt);
}

rt_err_t websocket_client_init(const char *server_url)
{
    rt_err_t ret;

    if (g_ws.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_ws, 0, sizeof(g_ws));
    websocket_set_diag(WS_STAGE_PARSE_URL, 0);
    ret = websocket_parse_url(server_url);
    if (ret != RT_EOK)
    {
        websocket_set_diag(WS_STAGE_PARSE_URL, ret);
        return ret;
    }

    rt_strncpy(g_ws.server_url, server_url, sizeof(g_ws.server_url) - 1);
    rt_mutex_init(&g_ws.send_lock, "wslock", RT_IPC_FLAG_PRIO);
    rt_completion_init(&g_ws.connect_done);
    g_ws.initialized = RT_TRUE;
    websocket_set_diag(WS_STAGE_IDLE, 0);
    rt_kprintf("[websocket] init %s:%d%s\n", g_ws.server_host, g_ws.server_port, g_ws.server_path);
    return RT_EOK;
}

rt_err_t websocket_client_configure(const char *server_url, const char *extra_headers)
{
    rt_err_t ret;

    if ((server_url == RT_NULL) || (rt_strlen(server_url) >= sizeof(g_ws.server_url)))
    {
        return -RT_EINVAL;
    }

    if ((extra_headers != RT_NULL) && (rt_strlen(extra_headers) >= sizeof(g_ws.extra_headers)))
    {
        return -RT_EINVAL;
    }

    if (!g_ws.initialized)
    {
        ret = websocket_client_init(server_url);
        if (ret != RT_EOK)
        {
            return ret;
        }
    }
    else if (g_ws.connected || g_ws.connecting)
    {
        websocket_client_disconnect();
    }

    websocket_set_diag(WS_STAGE_PARSE_URL, 0);
    ret = websocket_parse_url(server_url);
    if (ret != RT_EOK)
    {
        websocket_set_diag(WS_STAGE_PARSE_URL, ret);
        return ret;
    }

    rt_memset(g_ws.server_url, 0, sizeof(g_ws.server_url));
    rt_strncpy(g_ws.server_url, server_url, sizeof(g_ws.server_url) - 1);
    rt_memset(g_ws.extra_headers, 0, sizeof(g_ws.extra_headers));
    if (extra_headers != RT_NULL)
    {
        rt_strncpy(g_ws.extra_headers, extra_headers, sizeof(g_ws.extra_headers) - 1);
    }
    rt_kprintf("[websocket] configured %s:%d%s\n", g_ws.server_host, g_ws.server_port, g_ws.server_path);
    return RT_EOK;
}

rt_err_t websocket_client_connect(void)
{
    websocket_connect_job_t job;
    rt_err_t wait_ret;
    err_t err;
    int header_len;

    if (!g_ws.initialized)
    {
        return -RT_ERROR;
    }

    if (g_ws.connected)
    {
        return RT_EOK;
    }

    rt_memset(&job, 0, sizeof(job));
    rt_completion_init(&g_ws.connect_done);

    header_len = websocket_build_extra_header_format(job.header_fmt, sizeof(job.header_fmt));
    if (header_len < 0)
    {
        websocket_set_diag(WS_STAGE_INIT, header_len);
        return (rt_err_t)header_len;
    }

    g_ws.connecting = RT_TRUE;
    g_ws.connected = RT_FALSE;
    websocket_set_diag(WS_STAGE_CONNECT_START, 0);
    rt_kprintf("[websocket] wsock connect %s:%d%s\n", g_ws.server_host, g_ws.server_port, g_ws.server_path);
    err = tcpip_callback_with_block(websocket_start_connect_job, &job, 1);
    if (err != ERR_OK)
    {
        g_ws.connecting = RT_FALSE;
        websocket_set_diag(WS_STAGE_CONNECT_START, err);
        return -RT_ERROR;
    }
    err = job.result;
    if (err != ERR_OK)
    {
        g_ws.connecting = RT_FALSE;
        websocket_set_diag(WS_STAGE_CONNECT_START, err);
        return -RT_ERROR;
    }

    websocket_set_diag(WS_STAGE_WAIT_101, 0);
    wait_ret = rt_completion_wait(&g_ws.connect_done, rt_tick_from_millisecond(WS_CONNECT_WAIT_MS));
    if (wait_ret != RT_EOK)
    {
        g_ws.connecting = RT_FALSE;
        g_ws.connected = RT_FALSE;
        websocket_set_diag(WS_STAGE_WAIT_101, -RT_ETIMEOUT);
        wsock_close(&g_ws.wsock, WSOCK_RESULT_ERR_TIMEOUT, ERR_TIMEOUT);
        return -RT_ETIMEOUT;
    }

    if (!g_ws.connected)
    {
        return -RT_ERROR;
    }

    rt_kprintf("[websocket] connected\n");
    return RT_EOK;
}

rt_err_t websocket_client_send_text(const char *message)
{
    err_t err;

    if (message == RT_NULL)
    {
        return -RT_EINVAL;
    }
    if (!g_ws.connected)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_ws.send_lock, RT_WAITING_FOREVER);
    err = wsock_write(&g_ws.wsock, message, (u16_t)rt_strlen(message), OPCODE_TEXT);
    rt_mutex_release(&g_ws.send_lock);
    return err == ERR_OK ? RT_EOK : -RT_ERROR;
}

rt_err_t websocket_client_send_binary(const uint8_t *data, rt_size_t len)
{
    err_t err;

    if (((data == RT_NULL) && (len != 0)) || (len > WSMSG_MAXSIZE))
    {
        return -RT_EINVAL;
    }
    if (!g_ws.connected)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_ws.send_lock, RT_WAITING_FOREVER);
    err = wsock_write(&g_ws.wsock, (const char *)data, (u16_t)len, OPCODE_BINARY);
    rt_mutex_release(&g_ws.send_lock);
    return err == ERR_OK ? RT_EOK : -RT_ERROR;
}

rt_err_t websocket_client_disconnect(void)
{
    if (!g_ws.initialized)
    {
        return RT_EOK;
    }

    if (g_ws.connected || g_ws.connecting)
    {
        wsock_close(&g_ws.wsock, WSOCK_RESULT_LOCAL_ABORT, ERR_ABRT);
        rt_thread_mdelay(WS_DISCONNECT_WAIT_MS);
    }

    g_ws.connected = RT_FALSE;
    g_ws.connecting = RT_FALSE;
    websocket_set_diag(WS_STAGE_DISCONNECTED, 0);
    return RT_EOK;
}

rt_bool_t websocket_client_is_connected(void)
{
    return g_ws.connected;
}

void websocket_client_set_callback(websocket_message_callback_t callback)
{
    g_ws.callback = callback;
}

int websocket_client_last_stage(void)
{
    return g_ws.last_stage;
}

int websocket_client_last_errno(void)
{
    return g_ws.last_errno;
}
