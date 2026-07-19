#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "app_ble_protocol.h"

static app_ble_request_t parse_ok(const char *json)
{
    app_ble_request_t request;

    memset(&request, 0xA5, sizeof(request));
    assert(app_ble_protocol_parse((const uint8_t *)json, strlen(json), &request) ==
           APP_BLE_PROTOCOL_OK);
    return request;
}

static void parse_rejected(const uint8_t *frame, size_t length)
{
    app_ble_request_t request;
    app_ble_request_t zero = {0};

    memset(&request, 0xA5, sizeof(request));
    assert(app_ble_protocol_parse(frame, length, &request) != APP_BLE_PROTOCOL_OK);
    assert(memcmp(&request, &zero, sizeof(request)) == 0);
}

static void reject_text(const char *json)
{
    parse_rejected((const uint8_t *)json, strlen(json));
}

static void test_valid_requests(void)
{
    app_ble_request_t request = parse_ok(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\",\"request_id\":101}");
    assert(request.type == APP_BLE_REQUEST_HEARTBEAT);
    assert(request.mode == APP_BLE_MODE_NONE);
    assert(request.request_id == 101u);
    assert(request.joint_mask == 0u);
    assert(request.ttl_ms == 0u);

    request = parse_ok(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"stop_request\",\"request_id\":103}");
    assert(request.type == APP_BLE_REQUEST_STOP);
    assert(request.request_id == 103u);

    request = parse_ok(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\"," 
        "\"request_id\":104,\"profile\":\"single_joint_curl_j5_v1\"," 
        "\"joint_mask\":16,\"ttl_ms\":1000}");
    assert(request.type == APP_BLE_REQUEST_TRAINING);
    assert(request.training == APP_BLE_TRAINING_CURL_J5);
    assert(request.request_id == 104u);
    assert(request.joint_mask == APP_BLE_PROTOCOL_CURL_J5_MASK);
    assert(request.ttl_ms == 1000u);

    request = parse_ok(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"mode_request\","
        "\"request_id\":102,\"mode\":\"assist\",\"joint_mask\":56,"
        "\"ttl_ms\":1000}");
    assert(request.type == APP_BLE_REQUEST_MODE);
    assert(request.mode == APP_BLE_MODE_ASSIST);
    assert(request.request_id == 102u);
    assert(request.joint_mask == APP_BLE_PROTOCOL_REHAB_MASK);
    assert(request.ttl_ms == 1000u);

    request = parse_ok(
        " \t{\"ttl_ms\":200,\"joint_mask\":56,\"mode\":\"active\","
        "\"request_id\":7,\"type\":\"mode_request\","
        "\"schema\":\"rehab_ble_v1\"}\r\n");
    assert(request.mode == APP_BLE_MODE_ACTIVE);
    assert(request.ttl_ms == APP_BLE_PROTOCOL_MIN_TTL_MS);

    request = parse_ok(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"mode_request\","
        "\"request_id\":4294967295,\"mode\":\"resist\","
        "\"joint_mask\":56,\"ttl_ms\":2000}");
    assert(request.mode == APP_BLE_MODE_RESIST);
    assert(request.request_id == UINT32_MAX);
    assert(request.ttl_ms == APP_BLE_PROTOCOL_MAX_TTL_MS);
}

static void test_strict_schema(void)
{
    reject_text("{\"schema\":\"rehab_ble_v2\",\"type\":\"heartbeat\",\"request_id\":1}");
    reject_text("{\"schema\":\"rehab_ble_v1\",\"type\":\"unknown\",\"request_id\":1}");
    reject_text("{\"schema\":\"rehab_ble_v1\",\"request_id\":1}");
    reject_text("{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\"}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\","
        "\"request_id\":1,\"extra\":0}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"schema\":\"rehab_ble_v1\","
        "\"type\":\"heartbeat\",\"request_id\":1}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\","
        "\"request_id\":1,\"request_id\":2}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"stop_request\","
        "\"request_id\":1,\"mode\":\"active\"}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"mode_request\","
        "\"request_id\":1,\"mode\":\"assist\",\"joint_mask\":56}");
}

static void test_mode_bounds(void)
{
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"mode_request\","
        "\"request_id\":1,\"mode\":\"passive\",\"joint_mask\":56,"
        "\"ttl_ms\":1000}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"mode_request\","
        "\"request_id\":1,\"mode\":\"assist\",\"joint_mask\":55,"
        "\"ttl_ms\":1000}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"mode_request\","
        "\"request_id\":1,\"mode\":\"assist\",\"joint_mask\":56,"
        "\"ttl_ms\":199}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"mode_request\","
        "\"request_id\":1,\"mode\":\"assist\",\"joint_mask\":56,"
        "\"ttl_ms\":2001}");
}

static void test_training_is_fixed_profile(void)
{
    app_ble_request_t request;

    request = parse_ok(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\","
        "\"request_id\":201,\"profile\":\"fixed_elbow_flex_extend_v1\","
        "\"joint_mask\":16,\"ttl_ms\":1000}");
    assert(request.training == APP_BLE_TRAINING_FIXED_ELBOW_FLEX_EXTEND);
    assert(request.joint_mask == APP_BLE_PROTOCOL_FIXED_ELBOW_MASK);

    request = parse_ok(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\","
        "\"request_id\":202,\"profile\":\"fixed_shoulder_planar_v1\","
        "\"joint_mask\":32,\"ttl_ms\":1000}");
    assert(request.training == APP_BLE_TRAINING_FIXED_SHOULDER_PLANAR);
    assert(request.joint_mask == APP_BLE_PROTOCOL_FIXED_SHOULDER_PLANAR_MASK);

    request = parse_ok(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\","
        "\"request_id\":203,\"profile\":\"fixed_coordinated_elbow_shoulder_v1\","
        "\"joint_mask\":48,\"ttl_ms\":1000}");
    assert(request.training == APP_BLE_TRAINING_FIXED_COORDINATED);
    assert(request.joint_mask == APP_BLE_PROTOCOL_FIXED_COORDINATED_MASK);

    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\"," 
        "\"request_id\":1,\"profile\":\"single_joint_curl_j6_v1\"," 
        "\"joint_mask\":16,\"ttl_ms\":1000}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\","
        "\"request_id\":1,\"profile\":\"fixed_shoulder_fore_aft_v1\","
        "\"joint_mask\":8,\"ttl_ms\":1000}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\"," 
        "\"request_id\":1,\"profile\":\"single_joint_curl_j5_v1\"," 
        "\"joint_mask\":56,\"ttl_ms\":1000}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\"," 
        "\"request_id\":1,\"profile\":\"single_joint_curl_j5_v1\"," 
        "\"joint_mask\":16,\"ttl_ms\":1000,\"top_mrad\":6238}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\","
        "\"request_id\":1,\"profile\":\"fixed_elbow_flex_extend_v1\","
        "\"joint_mask\":16,\"ttl_ms\":1000,\"velocity\":0.12}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\","
        "\"request_id\":1,\"profile\":\"fixed_elbow_flex_extend_v1\","
        "\"joint_mask\":16,\"ttl_ms\":1000,\"current\":1.0}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"training_request\","
        "\"request_id\":1,\"profile\":\"fixed_elbow_flex_extend_v1\","
        "\"joint_mask\":16,\"ttl_ms\":1000,\"points\":[1,2]}");
}

static void test_strict_numbers(void)
{
    reject_text("{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\",\"request_id\":0}");
    reject_text("{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\",\"request_id\":-1}");
    reject_text("{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\",\"request_id\":+1}");
    reject_text("{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\",\"request_id\":01}");
    reject_text("{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\",\"request_id\":1.0}");
    reject_text("{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\",\"request_id\":1e1}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\","
        "\"request_id\":4294967296}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\","
        "\"request_id\":\"1\"}");
}

static void test_json_and_utf8_boundaries(void)
{
    uint8_t oversized[APP_BLE_PROTOCOL_MAX_FRAME_BYTES + 1u];
    static const uint8_t invalid_utf8[] = {
        '{', '"', 's', 'c', 'h', 'e', 'm', 'a', '"', ':', '"',
        'r', 'e', 'h', 'a', 'b', '_', 'b', 'l', 'e', '_', 'v', '1',
        0xC0u, 0xAFu, '"', ',', '"', 't', 'y', 'p', 'e', '"', ':',
        '"', 'h', 'e', 'a', 'r', 't', 'b', 'e', 'a', 't', '"', ',',
        '"', 'r', 'e', 'q', 'u', 'e', 's', 't', '_', 'i', 'd', '"',
        ':', '1', '}'
    };

    memset(oversized, ' ', sizeof(oversized));
    parse_rejected(oversized, sizeof(oversized));
    parse_rejected(invalid_utf8, sizeof(invalid_utf8));
    reject_text("");
    reject_text("[]");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\","
        "\"request_id\":1}x");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\","
        "\"request_id\":{\"nested\":1}}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\","
        "\"request_id\":[1]}");
    reject_text(
        "{\"sch\\u0065ma\":\"rehab_ble_v1\",\"type\":\"heartbeat\","
        "\"request_id\":1}");
    reject_text(
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"heart\\nbeat\","
        "\"request_id\":1}");
}

static void test_invalid_arguments(void)
{
    app_ble_request_t request = {0};

    assert(app_ble_protocol_parse(NULL, 1u, &request) != APP_BLE_PROTOCOL_OK);
    assert(app_ble_protocol_parse((const uint8_t *)"{}", 2u, NULL) !=
           APP_BLE_PROTOCOL_OK);
}

int main(void)
{
    test_valid_requests();
    test_strict_schema();
    test_mode_bounds();
    test_training_is_fixed_profile();
    test_strict_numbers();
    test_json_and_utf8_boundaries();
    test_invalid_arguments();
    puts("app_ble_protocol_test: PASS");
    return 0;
}
