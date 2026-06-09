#ifndef WEBSOCKET_CLIENT_H
#define WEBSOCKET_CLIENT_H

#include <rtthread.h>

typedef enum
{
    WEBSOCKET_MESSAGE_TEXT = 1,
    WEBSOCKET_MESSAGE_BINARY = 2
} websocket_message_type_t;

typedef void (*websocket_message_callback_t)(websocket_message_type_t type,
                                             const uint8_t *payload,
                                             rt_size_t payload_len);

rt_err_t websocket_client_init(const char *server_url);
rt_err_t websocket_client_configure(const char *server_url, const char *extra_headers);
rt_err_t websocket_client_connect(void);
rt_err_t websocket_client_send_text(const char *message);
rt_err_t websocket_client_send_binary(const uint8_t *data, rt_size_t len);
rt_err_t websocket_client_disconnect(void);
rt_bool_t websocket_client_is_connected(void);
void websocket_client_set_callback(websocket_message_callback_t callback);

#endif
