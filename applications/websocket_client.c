#include "websocket_client.h"

#include <rtdevice.h>
#include <sys/socket.h>
#include <netdb.h>
#include <stdlib.h>
#include <string.h>

#define WS_RX_BUFFER_SIZE 2048
#define WS_TX_BUFFER_SIZE 2048
#define WS_HEADER_BUFFER_SIZE 512

typedef struct
{
    rt_bool_t initialized;
    rt_bool_t connected;
    char server_url[128];
    char server_host[64];
    char server_path[64];
    char extra_headers[WS_HEADER_BUFFER_SIZE];
    int server_port;
    int sock;
    struct rt_mutex send_lock;
    rt_thread_t recv_thread;
    websocket_message_callback_t callback;
} websocket_client_t;

static websocket_client_t g_ws;

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

    rt_strncpy(g_ws.server_path, path_start ? path_start : "/", sizeof(g_ws.server_path) - 1);

    if (port_start && (!path_start || port_start < path_start))
    {
        host_len = (rt_size_t)(port_start - host_start);
        g_ws.server_port = atoi(port_start + 1);
    }
    else
    {
        host_len = path_start ? (rt_size_t)(path_start - host_start) : rt_strlen(host_start);
        g_ws.server_port = 80;
    }

    if ((host_len == 0) || (host_len >= sizeof(g_ws.server_host)))
    {
        return -RT_EINVAL;
    }

    rt_memcpy(g_ws.server_host, host_start, host_len);
    g_ws.server_host[host_len] = '\0';
    return RT_EOK;
}

static rt_err_t websocket_send_frame(uint8_t opcode, const uint8_t *payload, rt_size_t payload_len)
{
    uint8_t frame[WS_TX_BUFFER_SIZE];
    uint8_t mask_key[4];
    rt_size_t header_len = 0;
    rt_size_t i;
    rt_size_t frame_len;

    if (!g_ws.connected)
    {
        return -RT_ERROR;
    }

    if (payload_len > (WS_TX_BUFFER_SIZE - 14))
    {
        return -RT_EFULL;
    }

    frame[header_len++] = 0x80 | (opcode & 0x0F);

    if (payload_len < 126)
    {
        frame[header_len++] = 0x80 | (uint8_t)payload_len;
    }
    else
    {
        frame[header_len++] = 0x80 | 126;
        frame[header_len++] = (uint8_t)((payload_len >> 8) & 0xFF);
        frame[header_len++] = (uint8_t)(payload_len & 0xFF);
    }

    mask_key[0] = (uint8_t)(rt_tick_get() & 0xFF);
    mask_key[1] = (uint8_t)((rt_tick_get() >> 8) & 0xFF);
    mask_key[2] = 0x5A;
    mask_key[3] = 0xC3;

    for (i = 0; i < sizeof(mask_key); i++)
    {
        frame[header_len++] = mask_key[i];
    }

    for (i = 0; i < payload_len; i++)
    {
        frame[header_len + i] = payload[i] ^ mask_key[i % 4];
    }

    frame_len = header_len + payload_len;

    rt_mutex_take(&g_ws.send_lock, RT_WAITING_FOREVER);
    if (send(g_ws.sock, frame, frame_len, 0) < 0)
    {
        rt_mutex_release(&g_ws.send_lock);
        return -RT_ERROR;
    }
    rt_mutex_release(&g_ws.send_lock);
    return RT_EOK;
}

static void websocket_handle_frame(uint8_t opcode, const uint8_t *payload, rt_size_t payload_len)
{
    if ((opcode == 0x1 || opcode == 0x2) && g_ws.callback)
    {
        g_ws.callback(opcode == 0x1 ? WEBSOCKET_MESSAGE_TEXT : WEBSOCKET_MESSAGE_BINARY,
                      payload, payload_len);
        return;
    }

    if (opcode == 0x8)
    {
        rt_kprintf("[websocket] peer closed\n");
        g_ws.connected = RT_FALSE;
        return;
    }

    if (opcode == 0x9)
    {
        websocket_send_frame(0xA, payload, payload_len);
    }
}

static void websocket_recv_thread_entry(void *parameter)
{
    uint8_t buffer[WS_RX_BUFFER_SIZE];
    int buffered = 0;

    RT_UNUSED(parameter);

    while (g_ws.connected)
    {
        int received = recv(g_ws.sock, buffer + buffered, sizeof(buffer) - buffered, 0);
        int offset = 0;

        if (received <= 0)
        {
            g_ws.connected = RT_FALSE;
            break;
        }

        buffered += received;

        while ((buffered - offset) >= 2)
        {
            uint8_t opcode = buffer[offset] & 0x0F;
            uint8_t masked = (buffer[offset + 1] & 0x80U) != 0U;
            rt_size_t payload_len = buffer[offset + 1] & 0x7FU;
            rt_size_t header_len = 2;
            rt_size_t i;

            if (payload_len == 126)
            {
                if ((buffered - offset) < 4)
                {
                    break;
                }
                payload_len = ((rt_size_t)buffer[offset + 2] << 8) | buffer[offset + 3];
                header_len = 4;
            }
            else if (payload_len == 127)
            {
                rt_kprintf("[websocket] 64-bit frame not supported\n");
                g_ws.connected = RT_FALSE;
                break;
            }

            if (masked)
            {
                header_len += 4;
            }

            if ((buffered - offset) < (int)(header_len + payload_len))
            {
                break;
            }

            if (masked)
            {
                uint8_t *payload = buffer + offset + header_len;
                const uint8_t *mask = buffer + offset + header_len - 4;

                for (i = 0; i < payload_len; i++)
                {
                    payload[i] ^= mask[i % 4];
                }
            }

            websocket_handle_frame(opcode, buffer + offset + header_len, payload_len);
            offset += (int)(header_len + payload_len);
        }

        if (offset > 0)
        {
            if (offset < buffered)
            {
                rt_memmove(buffer, buffer + offset, buffered - offset);
            }
            buffered -= offset;
        }
    }

    if (g_ws.sock >= 0)
    {
        closesocket(g_ws.sock);
        g_ws.sock = -1;
    }

    rt_kprintf("[websocket] recv thread exit\n");
}

rt_err_t websocket_client_init(const char *server_url)
{
    if (g_ws.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_ws, 0, sizeof(g_ws));
    g_ws.sock = -1;
    rt_mutex_init(&g_ws.send_lock, "wslock", RT_IPC_FLAG_PRIO);

    if (websocket_parse_url(server_url) != RT_EOK)
    {
        return -RT_EINVAL;
    }

    rt_strncpy(g_ws.server_url, server_url, sizeof(g_ws.server_url) - 1);
    g_ws.initialized = RT_TRUE;
    rt_kprintf("[websocket] init %s:%d%s\n", g_ws.server_host, g_ws.server_port, g_ws.server_path);
    return RT_EOK;
}

rt_err_t websocket_client_configure(const char *server_url, const char *extra_headers)
{
    if ((server_url == RT_NULL) || (rt_strlen(server_url) >= sizeof(g_ws.server_url)))
    {
        return -RT_EINVAL;
    }

    if ((extra_headers != RT_NULL) && (rt_strlen(extra_headers) >= sizeof(g_ws.extra_headers)))
    {
        return -RT_EINVAL;
    }

    if (g_ws.connected)
    {
        websocket_client_disconnect();
    }

    if (!g_ws.initialized)
    {
        rt_err_t ret = websocket_client_init(server_url);
        if (ret != RT_EOK)
        {
            return ret;
        }
        if (extra_headers != RT_NULL)
        {
            rt_strncpy(g_ws.extra_headers, extra_headers, sizeof(g_ws.extra_headers) - 1);
        }
        return RT_EOK;
    }

    if (websocket_parse_url(server_url) != RT_EOK)
    {
        return -RT_EINVAL;
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
    struct hostent *host;
    struct sockaddr_in server_addr;
    char request[512];
    char response[512];
    int ret;

    if (!g_ws.initialized)
    {
        return -RT_ERROR;
    }

    if (g_ws.connected)
    {
        return RT_EOK;
    }

    host = gethostbyname(g_ws.server_host);
    if (!host)
    {
        return -RT_ERROR;
    }

    g_ws.sock = socket(AF_INET, SOCK_STREAM, 0);
    if (g_ws.sock < 0)
    {
        return -RT_ERROR;
    }

    rt_memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(g_ws.server_port);
    server_addr.sin_addr = *((struct in_addr *)host->h_addr);

    if (connect(g_ws.sock, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0)
    {
        closesocket(g_ws.sock);
        g_ws.sock = -1;
        return -RT_ERROR;
    }

    rt_snprintf(request, sizeof(request),
                "GET %s HTTP/1.1\r\n"
                "Host: %s:%d\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Key: c29tZS1vcGVuY2xhdy1rZXk=\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "%s"
                "\r\n",
                g_ws.server_path, g_ws.server_host, g_ws.server_port,
                g_ws.extra_headers);

    if (send(g_ws.sock, request, rt_strlen(request), 0) < 0)
    {
        closesocket(g_ws.sock);
        g_ws.sock = -1;
        return -RT_ERROR;
    }

    rt_memset(response, 0, sizeof(response));
    ret = recv(g_ws.sock, response, sizeof(response) - 1, 0);
    if ((ret <= 0) || (rt_strstr(response, " 101 ") == RT_NULL))
    {
        rt_kprintf("[websocket] handshake failed: %s\n", response);
        closesocket(g_ws.sock);
        g_ws.sock = -1;
        return -RT_ERROR;
    }

    g_ws.connected = RT_TRUE;
    g_ws.recv_thread = rt_thread_create("ws_recv", websocket_recv_thread_entry, RT_NULL, 4096, 12, 10);
    if (!g_ws.recv_thread)
    {
        closesocket(g_ws.sock);
        g_ws.sock = -1;
        g_ws.connected = RT_FALSE;
        return -RT_ENOMEM;
    }

    rt_thread_startup(g_ws.recv_thread);
    rt_kprintf("[websocket] connected\n");
    return RT_EOK;
}

rt_err_t websocket_client_send_text(const char *message)
{
    if (!message)
    {
        return -RT_EINVAL;
    }

    return websocket_send_frame(0x1, (const uint8_t *)message, rt_strlen(message));
}

rt_err_t websocket_client_send_binary(const uint8_t *data, rt_size_t len)
{
    if ((!data && len != 0) || (len > 0xFFFF))
    {
        return -RT_EINVAL;
    }

    return websocket_send_frame(0x2, data, len);
}

rt_err_t websocket_client_disconnect(void)
{
    if (!g_ws.connected)
    {
        return RT_EOK;
    }

    websocket_send_frame(0x8, RT_NULL, 0);
    g_ws.connected = RT_FALSE;

    if (g_ws.sock >= 0)
    {
        closesocket(g_ws.sock);
        g_ws.sock = -1;
    }

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
