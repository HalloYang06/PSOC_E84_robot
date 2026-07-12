#include "http_server.h"
#include "openclaw_integration.h"

#include <string.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <netdb.h>
#include <arpa/inet.h>
#include <unistd.h>

#ifndef closesocket
#define closesocket close
#endif

#define DBG_TAG "http"
#define DBG_LVL DBG_INFO
#include <rtdbg.h>

#define HTTP_SERVER_THREAD_STACK 6144
#define HTTP_SERVER_BACKLOG      4
#define HTTP_REQUEST_MAX         2048
#define HTTP_RESPONSE_MAX        1536

static rt_thread_t g_http_thread = RT_NULL;
static int g_http_listen_fd = -1;

static const char *skip_spaces(const char *s)
{
    while (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n')
    {
        s++;
    }
    return s;
}

static const char *find_header(const char *req, const char *name)
{
    const char *cursor = req;
    rt_size_t name_len = rt_strlen(name);

    while (cursor && *cursor)
    {
        if (rt_strncmp(cursor, name, name_len) == 0)
        {
            return cursor + name_len;
        }
        cursor = rt_strstr(cursor, "\r\n");
        if (!cursor)
        {
            break;
        }
        cursor += 2;
    }
    return RT_NULL;
}

static int get_content_length(const char *request)
{
    const char *value = find_header(request, "Content-Length:");
    if (!value)
    {
        return 0;
    }
    value = skip_spaces(value);
    return atoi(value);
}

static const char *get_body(const char *request)
{
    const char *body = rt_strstr(request, "\r\n\r\n");
    return body ? body + 4 : RT_NULL;
}

static rt_bool_t parse_request_line(const char *request, char *method, rt_size_t method_size,
                                    char *path, rt_size_t path_size)
{
    const char *sp1;
    const char *sp2;
    rt_size_t method_len;
    rt_size_t path_len;

    sp1 = strchr(request, ' ');
    if (!sp1)
    {
        return RT_FALSE;
    }

    sp2 = strchr(sp1 + 1, ' ');
    if (!sp2)
    {
        return RT_FALSE;
    }

    method_len = (rt_size_t)(sp1 - request);
    path_len = (rt_size_t)(sp2 - (sp1 + 1));

    if (method_len >= method_size)
    {
        method_len = method_size - 1;
    }
    if (path_len >= path_size)
    {
        path_len = path_size - 1;
    }

    rt_memcpy(method, request, method_len);
    method[method_len] = '\0';
    rt_memcpy(path, sp1 + 1, path_len);
    path[path_len] = '\0';
    return RT_TRUE;
}

static rt_bool_t json_extract_tool(const char *body, char *tool, rt_size_t tool_size)
{
    const char *cursor;
    const char *start;
    const char *end;
    rt_size_t len;

    cursor = rt_strstr(body, "\"tool\"");
    if (!cursor)
    {
        return RT_FALSE;
    }

    cursor = strchr(cursor, ':');
    if (!cursor)
    {
        return RT_FALSE;
    }
    cursor = skip_spaces(cursor + 1);
    if (*cursor != '"')
    {
        return RT_FALSE;
    }

    start = ++cursor;
    end = strchr(start, '"');
    if (!end)
    {
        return RT_FALSE;
    }

    len = (rt_size_t)(end - start);
    if (len >= tool_size)
    {
        len = tool_size - 1;
    }
    rt_memcpy(tool, start, len);
    tool[len] = '\0';
    return RT_TRUE;
}

static int send_response(int fd, int code, const char *reason, const char *content_type, const char *body)
{
    char header[256];
    int body_len = body ? (int)rt_strlen(body) : 0;
    int header_len = rt_snprintf(header, sizeof(header),
                                 "HTTP/1.1 %d %s\r\n"
                                 "Content-Type: %s\r\n"
                                 "Content-Length: %d\r\n"
                                 "Connection: close\r\n\r\n",
                                 code, reason, content_type, body_len);

    if (send(fd, header, header_len, 0) < 0)
    {
        return -1;
    }
    if (body_len > 0 && send(fd, body, body_len, 0) < 0)
    {
        return -1;
    }
    return 0;
}

static void handle_status_request(int fd)
{
    char body[HTTP_RESPONSE_MAX];
    openclaw_build_status_json(body, sizeof(body));
    send_response(fd, 200, "OK", "application/json", body);
}

static void handle_sensor_request(int fd)
{
    char body[HTTP_RESPONSE_MAX];
    openclaw_build_sensors_json(body, sizeof(body));
    send_response(fd, 200, "OK", "application/json", body);
}

static void handle_command_request(int fd, const char *body)
{
    char tool[48];
    char response[HTTP_RESPONSE_MAX];
    rt_err_t ret;

    if (!body || !json_extract_tool(body, tool, sizeof(tool)))
    {
        send_response(fd, 400, "Bad Request", "application/json",
                      "{\"ok\":false,\"error\":\"missing_tool\"}");
        return;
    }

    ret = openclaw_execute_tool(tool, body, response, sizeof(response));
    if (ret == RT_EOK)
    {
        send_response(fd, 200, "OK", "application/json", response);
    }
    else if (ret == -RT_ENOSYS)
    {
        send_response(fd, 404, "Not Found", "application/json", response);
    }
    else
    {
        send_response(fd, 500, "Internal Server Error", "application/json", response);
    }
}

static void handle_client(int client_fd)
{
    char request[HTTP_REQUEST_MAX + 1];
    char method[8];
    char path[64];
    const char *body;
    int received;
    int content_length;

    received = recv(client_fd, request, HTTP_REQUEST_MAX, 0);
    if (received <= 0)
    {
        return;
    }

    request[received] = '\0';
    if (!parse_request_line(request, method, sizeof(method), path, sizeof(path)))
    {
        send_response(client_fd, 400, "Bad Request", "application/json",
                      "{\"ok\":false,\"error\":\"bad_request_line\"}");
        return;
    }

    content_length = get_content_length(request);
    body = get_body(request);
    if (body && content_length > 0)
    {
        int current_body_len = (int)rt_strlen(body);
        while (current_body_len < content_length && received < HTTP_REQUEST_MAX)
        {
            int chunk = recv(client_fd, request + received, HTTP_REQUEST_MAX - received, 0);
            if (chunk <= 0)
            {
                break;
            }
            received += chunk;
            request[received] = '\0';
            body = get_body(request);
            current_body_len = body ? (int)rt_strlen(body) : 0;
        }
    }

    LOG_I("HTTP %s %s", method, path);

    if (rt_strcmp(method, "GET") == 0 && rt_strcmp(path, "/api/status") == 0)
    {
        handle_status_request(client_fd);
    }
    else if (rt_strcmp(method, "GET") == 0 && rt_strcmp(path, "/api/sensors") == 0)
    {
        handle_sensor_request(client_fd);
    }
    else if (rt_strcmp(method, "POST") == 0 && rt_strcmp(path, "/api/command") == 0)
    {
        handle_command_request(client_fd, body);
    }
    else
    {
        send_response(client_fd, 404, "Not Found", "application/json",
                      "{\"ok\":false,\"error\":\"endpoint_not_found\"}");
    }
}

static void http_server_entry(void *parameter)
{
    struct sockaddr_in addr;
    rt_bool_t announced_wait = RT_FALSE;

    RT_UNUSED(parameter);

    while (1)
    {
        g_http_listen_fd = socket(AF_INET, SOCK_STREAM, 0);
        if (g_http_listen_fd < 0)
        {
            if (!announced_wait)
            {
                LOG_W("network not ready yet, waiting for WiFi before starting HTTP server");
                announced_wait = RT_TRUE;
            }
            rt_thread_mdelay(1000);
            continue;
        }

        {
            int opt = 1;
            setsockopt(g_http_listen_fd, SOL_SOCKET, SO_REUSEADDR, (const void *)&opt, sizeof(opt));
        }

        rt_memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port = htons(HTTP_SERVER_PORT);
        addr.sin_addr.s_addr = htonl(INADDR_ANY);

        if (bind(g_http_listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
        {
            LOG_W("bind %d failed, retrying", HTTP_SERVER_PORT);
            closesocket(g_http_listen_fd);
            g_http_listen_fd = -1;
            rt_thread_mdelay(1000);
            continue;
        }

        if (listen(g_http_listen_fd, HTTP_SERVER_BACKLOG) < 0)
        {
            LOG_W("listen failed, retrying");
            closesocket(g_http_listen_fd);
            g_http_listen_fd = -1;
            rt_thread_mdelay(1000);
            continue;
        }

        LOG_I("HTTP server listening on port %d", HTTP_SERVER_PORT);
        break;
    }

    while (1)
    {
        int client_fd;
        struct sockaddr_in client_addr;
        socklen_t addr_len = sizeof(client_addr);

        client_fd = accept(g_http_listen_fd, (struct sockaddr *)&client_addr, &addr_len);
        if (client_fd < 0)
        {
            rt_thread_mdelay(100);
            continue;
        }

        handle_client(client_fd);
        closesocket(client_fd);
    }
}

rt_err_t http_server_init(void)
{
    if (g_http_thread != RT_NULL)
    {
        return RT_EOK;
    }

    g_http_thread = rt_thread_create("httpd",
                                     http_server_entry,
                                     RT_NULL,
                                     HTTP_SERVER_THREAD_STACK,
                                     18,
                                     10);
    if (g_http_thread == RT_NULL)
    {
        return -RT_ENOMEM;
    }

    rt_thread_startup(g_http_thread);
    return RT_EOK;
}
