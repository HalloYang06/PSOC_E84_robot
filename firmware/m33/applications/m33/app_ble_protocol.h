#ifndef APP_BLE_PROTOCOL_H
#define APP_BLE_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define APP_BLE_PROTOCOL_MAX_FRAME_BYTES 256u
#define APP_BLE_PROTOCOL_TOKEN_LIMIT 32u
#define APP_BLE_PROTOCOL_REHAB_MASK 0x38u
#define APP_BLE_PROTOCOL_CURL_J5_MASK 0x10u
#define APP_BLE_PROTOCOL_FIXED_ELBOW_MASK 0x10u
#define APP_BLE_PROTOCOL_FIXED_SHOULDER_PLANAR_MASK 0x20u
#define APP_BLE_PROTOCOL_FIXED_COORDINATED_MASK 0x30u
#define APP_BLE_PROTOCOL_MIN_TTL_MS 200u
#define APP_BLE_PROTOCOL_MAX_TTL_MS 2000u

typedef enum
{
    APP_BLE_PROTOCOL_OK = 0,
    APP_BLE_PROTOCOL_INVALID = -1
} app_ble_protocol_result_t;

typedef enum
{
    APP_BLE_REQUEST_NONE = 0,
    APP_BLE_REQUEST_HEARTBEAT,
    APP_BLE_REQUEST_MODE,
    APP_BLE_REQUEST_TRAINING,
    APP_BLE_REQUEST_STOP
} app_ble_request_type_t;

typedef enum
{
    APP_BLE_MODE_NONE = 0,
    APP_BLE_MODE_ACTIVE,
    APP_BLE_MODE_ASSIST,
    APP_BLE_MODE_RESIST
} app_ble_mode_t;

typedef enum
{
    APP_BLE_TRAINING_NONE = 0,
    APP_BLE_TRAINING_CURL_J5,
    APP_BLE_TRAINING_FIXED_ELBOW_FLEX_EXTEND,
    APP_BLE_TRAINING_FIXED_SHOULDER_PLANAR,
    APP_BLE_TRAINING_FIXED_COORDINATED,
    APP_BLE_TRAINING_FIXED_SHOULDER_FORE_AFT
} app_ble_training_t;

typedef struct
{
    app_ble_request_type_t type;
    app_ble_mode_t mode;
    app_ble_training_t training;
    uint32_t request_id;
    uint32_t ttl_ms;
    uint8_t joint_mask;
} app_ble_request_t;

app_ble_protocol_result_t app_ble_protocol_parse(const uint8_t *frame,
                                                 size_t length,
                                                 app_ble_request_t *out_request);

#ifdef __cplusplus
}
#endif

#endif
