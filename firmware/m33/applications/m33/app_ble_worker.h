#ifndef APP_BLE_WORKER_H
#define APP_BLE_WORKER_H

#include <stddef.h>
#include <stdint.h>

#ifndef APP_BLE_WORKER_HOST_TEST
#include <rtthread.h>
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define APP_BLE_RX_FRAGMENT_MAX 244U
#define APP_BLE_RX_QUEUE_DEPTH 4U
#define APP_BLE_TX_PAYLOAD_MAX 244U
#define APP_BLE_TX_ACK_QUEUE_DEPTH 4U
#define APP_BLE_FRAME_MAX 256U
#define APP_BLE_PARTIAL_TIMEOUT_MS 500U
#define APP_BLE_WORKER_STACK_SIZE 2048U
#define APP_BLE_WORKER_PRIORITY 22U
#define APP_BLE_WORKER_TICK 10U

typedef struct
{
    uint8_t data[APP_BLE_FRAME_MAX];
    uint16_t length;
    uint32_t first_fragment_ms;
    uint32_t generation;
    uint8_t dropping_oversize;
} app_ble_reassembly_t;

typedef struct
{
    uint32_t generation;
    uint16_t conn_id;
    uint16_t length;
    uint8_t data[APP_BLE_RX_FRAGMENT_MAX];
} app_ble_rx_message_t;

typedef enum
{
    APP_BLE_TX_KIND_ACK = 0,
    APP_BLE_TX_KIND_TELEMETRY
} app_ble_tx_kind_t;

typedef struct
{
    uint32_t generation;
    uint16_t conn_id;
} app_ble_session_token_t;

typedef struct
{
    uint32_t generation;
    uint16_t conn_id;
    uint16_t length;
    app_ble_tx_kind_t kind;
    uint8_t data[APP_BLE_TX_PAYLOAD_MAX];
} app_ble_tx_message_t;

typedef void (*app_ble_frame_handler_t)(const uint8_t *frame,
                                        uint16_t length,
                                        void *context);

void app_ble_reassembly_init(app_ble_reassembly_t *state);
void app_ble_reassembly_reset(app_ble_reassembly_t *state);
void app_ble_reassembly_sync_generation(app_ble_reassembly_t *state,
                                        uint32_t generation);
int app_ble_reassembly_expire(app_ble_reassembly_t *state, uint32_t now_ms);
uint32_t app_ble_reassembly_feed(app_ble_reassembly_t *state,
                                 const uint8_t *data,
                                 uint16_t length,
                                 uint32_t now_ms,
                                 app_ble_frame_handler_t handler,
                                 void *context);

#ifdef APP_BLE_WORKER_HOST_TEST
typedef int app_ble_worker_result_t;
#else
typedef rt_err_t app_ble_worker_result_t;
#endif

app_ble_worker_result_t app_ble_worker_init(void);
app_ble_worker_result_t app_ble_worker_start(void);
app_ble_worker_result_t app_ble_worker_begin_session(uint16_t conn_id);
void app_ble_worker_reset_session(uint16_t conn_id);
app_ble_worker_result_t app_ble_worker_enqueue(uint16_t conn_id,
                                               const uint8_t *data,
                                               uint16_t length);
app_ble_worker_result_t app_ble_worker_get_session_token(app_ble_session_token_t *token);
app_ble_worker_result_t app_ble_worker_enqueue_ack(const app_ble_session_token_t *token,
                                                   const uint8_t *data,
                                                   uint16_t length);
app_ble_worker_result_t app_ble_worker_publish_telemetry(const app_ble_session_token_t *token,
                                                         const uint8_t *data,
                                                         uint16_t length);
int app_ble_worker_session_is_current(uint32_t generation, uint16_t conn_id);
int app_ble_worker_is_current_thread(void);
int app_ble_worker_notify_try_acquire(const app_ble_session_token_t *token);
void app_ble_worker_notify_buffer_returned(void);
void app_ble_worker_notify_operation_complete(uint16_t conn_id);
void app_ble_worker_notify_abort(const app_ble_session_token_t *token);
uint32_t app_ble_worker_drop_count(void);

#ifdef APP_BLE_WORKER_HOST_TEST
int app_ble_worker_host_dequeue(app_ble_rx_message_t *message);
int app_ble_worker_host_dequeue_tx(app_ble_tx_message_t *message);
#endif

#ifdef __cplusplus
}
#endif

#endif
