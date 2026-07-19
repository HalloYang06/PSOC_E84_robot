#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "app_ble_worker.h"

typedef struct
{
    uint32_t count;
    uint16_t length[4];
    uint8_t frame[4][APP_BLE_FRAME_MAX];
} capture_t;

static void capture_frame(const uint8_t *frame, uint16_t length, void *context)
{
    capture_t *capture = (capture_t *)context;

    assert(capture->count < 4u);
    assert(length <= APP_BLE_FRAME_MAX);
    capture->length[capture->count] = length;
    memcpy(capture->frame[capture->count], frame, length);
    capture->count++;
}

static void test_20_byte_fragments(void)
{
    static const uint8_t line[] =
        "{\"schema\":\"rehab_ble_v1\",\"type\":\"heartbeat\",\"request_id\":1}\n";
    app_ble_reassembly_t state;
    capture_t capture = {0};
    size_t offset = 0u;

    app_ble_reassembly_init(&state);
    while (offset < sizeof(line) - 1u)
    {
        size_t remaining = sizeof(line) - 1u - offset;
        uint16_t chunk = (uint16_t)(remaining > 20u ? 20u : remaining);
        app_ble_reassembly_feed(&state, line + offset, chunk, (uint32_t)offset,
                                capture_frame, &capture);
        offset += chunk;
    }

    assert(capture.count == 1u);
    assert(capture.length[0] == sizeof(line) - 2u);
    assert(memcmp(capture.frame[0], line, capture.length[0]) == 0);
}

static void test_244_byte_fragment(void)
{
    uint8_t fragment[244];
    app_ble_reassembly_t state;
    capture_t capture = {0};

    memset(fragment, 'a', sizeof(fragment));
    fragment[sizeof(fragment) - 1u] = '\n';
    app_ble_reassembly_init(&state);
    app_ble_reassembly_feed(&state, fragment, sizeof(fragment), 10u,
                            capture_frame, &capture);

    assert(capture.count == 1u);
    assert(capture.length[0] == 243u);
}

static void test_coalesced_frames(void)
{
    static const uint8_t frames[] = "heartbeat\nstatus\n";
    app_ble_reassembly_t state;
    capture_t capture = {0};

    app_ble_reassembly_init(&state);
    app_ble_reassembly_feed(&state, frames, sizeof(frames) - 1u, 20u,
                            capture_frame, &capture);

    assert(capture.count == 2u);
    assert(capture.length[0] == 9u);
    assert(capture.length[1] == 6u);
    assert(memcmp(capture.frame[0], "heartbeat", 9u) == 0);
    assert(memcmp(capture.frame[1], "status", 6u) == 0);
}

static void test_partial_frame_timeout(void)
{
    static const uint8_t partial[] = "heart";
    static const uint8_t suffix[] = "beat\n";
    app_ble_reassembly_t state;
    capture_t capture = {0};

    app_ble_reassembly_init(&state);
    app_ble_reassembly_feed(&state, partial, sizeof(partial) - 1u, 100u,
                            capture_frame, &capture);
    assert(capture.count == 0u);
    assert(state.length == 5u);
    assert(app_ble_reassembly_expire(&state, 599u) == 0);
    assert(state.length == 5u);
    assert(app_ble_reassembly_expire(&state, 600u) == 1);
    assert(state.length == 0u);

    app_ble_reassembly_feed(&state, suffix, sizeof(suffix) - 1u, 601u,
                            capture_frame, &capture);
    assert(capture.count == 1u);
    assert(capture.length[0] == 4u);
    assert(memcmp(capture.frame[0], "beat", 4u) == 0);
}

static void test_partial_deadline_does_not_slide(void)
{
    static const uint8_t first[] = "a";
    static const uint8_t later[] = "b";
    app_ble_reassembly_t state;
    capture_t capture = {0};

    app_ble_reassembly_init(&state);
    app_ble_reassembly_feed(&state, first, sizeof(first) - 1u, 100u,
                            capture_frame, &capture);
    app_ble_reassembly_feed(&state, later, sizeof(later) - 1u, 500u,
                            capture_frame, &capture);
    assert(state.first_fragment_ms == 100u);
    assert(app_ble_reassembly_expire(&state, 600u) == 1);
    assert(state.length == 0u);
}

static void test_disconnect_clears_partial_frame(void)
{
    static const uint8_t before[] = "old";
    static const uint8_t after[] = "new\n";
    app_ble_reassembly_t state;
    capture_t capture = {0};

    app_ble_reassembly_init(&state);
    app_ble_reassembly_feed(&state, before, sizeof(before) - 1u, 1u,
                            capture_frame, &capture);
    app_ble_reassembly_reset(&state);
    app_ble_reassembly_feed(&state, after, sizeof(after) - 1u, 2u,
                            capture_frame, &capture);

    assert(capture.count == 1u);
    assert(capture.length[0] == 3u);
    assert(memcmp(capture.frame[0], "new", 3u) == 0);
}

static void test_generation_change_clears_old_partial_before_new_feed(void)
{
    static const uint8_t old_partial[] = "old";
    static const uint8_t new_frame[] = "new\n";
    app_ble_reassembly_t state;
    capture_t capture = {0};

    app_ble_reassembly_init(&state);
    app_ble_reassembly_sync_generation(&state, 10u);
    app_ble_reassembly_feed(&state, old_partial, sizeof(old_partial) - 1u, 1u,
                            capture_frame, &capture);
    app_ble_reassembly_sync_generation(&state, 11u);
    app_ble_reassembly_feed(&state, new_frame, sizeof(new_frame) - 1u, 2u,
                            capture_frame, &capture);

    assert(capture.count == 1u);
    assert(capture.length[0] == 3u);
    assert(memcmp(capture.frame[0], "new", 3u) == 0);
}

static void test_oversize_frame_is_dropped_without_poisoning_next_frame(void)
{
    uint8_t input[APP_BLE_FRAME_MAX + 1u + 1u + 3u];
    app_ble_reassembly_t state;
    capture_t capture = {0};

    memset(input, 'x', APP_BLE_FRAME_MAX + 1u);
    input[APP_BLE_FRAME_MAX + 1u] = '\n';
    memcpy(input + APP_BLE_FRAME_MAX + 2u, "ok\n", 3u);
    app_ble_reassembly_init(&state);
    app_ble_reassembly_feed(&state, input, sizeof(input), 10u,
                            capture_frame, &capture);

    assert(capture.count == 1u);
    assert(capture.length[0] == 2u);
    assert(memcmp(capture.frame[0], "ok", 2u) == 0);
    assert(state.dropping_oversize == 0u);
}

static void test_queue_full_does_not_overwrite_and_generation_invalidates_old(void)
{
    static const uint8_t values[5] = {1u, 2u, 3u, 4u, 5u};
    app_ble_rx_message_t message;
    uint32_t old_generation;
    unsigned int i;

    assert(app_ble_worker_init() == 0);
    assert(app_ble_worker_begin_session(7u) == 0);
    for (i = 0u; i < APP_BLE_RX_QUEUE_DEPTH; ++i)
    {
        assert(app_ble_worker_enqueue(7u, &values[i], 1u) == 0);
    }
    assert(app_ble_worker_enqueue(7u, &values[4], 1u) != 0);
    assert(app_ble_worker_drop_count() == 1u);
    for (i = 0u; i < APP_BLE_RX_QUEUE_DEPTH; ++i)
    {
        assert(app_ble_worker_host_dequeue(&message) == (int)sizeof(message));
        assert(message.data[0] == values[i]);
    }
    assert(app_ble_worker_host_dequeue(&message) == 0);

    assert(app_ble_worker_enqueue(7u, values, 1u) == 0);
    assert(app_ble_worker_host_dequeue(&message) == (int)sizeof(message));
    old_generation = message.generation;
    app_ble_worker_reset_session(7u);
    assert(!app_ble_worker_session_is_current(old_generation, 7u));
    assert(app_ble_worker_host_dequeue(&message) == 0);
    assert(app_ble_worker_begin_session(8u) == 0);
    assert(app_ble_worker_enqueue(7u, values, 1u) != 0);
    assert(app_ble_worker_enqueue(8u, values, 1u) == 0);
}

static void test_tx_ack_queue_is_bounded_and_precedes_coalesced_telemetry(void)
{
    static const uint8_t ack_values[5] = {'1', '2', '3', '4', '5'};
    static const uint8_t telemetry_old[] = "old\n";
    static const uint8_t telemetry_new[] = "new\n";
    app_ble_tx_message_t message;
    app_ble_session_token_t token;
    unsigned int i;

    assert(app_ble_worker_init() == 0);
    assert(app_ble_worker_begin_session(9u) == 0);
    assert(app_ble_worker_get_session_token(&token) == 0);
    assert(app_ble_worker_publish_telemetry(&token,
                                            telemetry_old,
                                            sizeof(telemetry_old) - 1u) == 0);
    assert(app_ble_worker_publish_telemetry(&token,
                                            telemetry_new,
                                            sizeof(telemetry_new) - 1u) == 0);
    for (i = 0u; i < APP_BLE_TX_ACK_QUEUE_DEPTH; ++i)
    {
        assert(app_ble_worker_enqueue_ack(&token, &ack_values[i], 1u) == 0);
    }
    assert(app_ble_worker_enqueue_ack(&token, &ack_values[4], 1u) != 0);

    for (i = 0u; i < APP_BLE_TX_ACK_QUEUE_DEPTH; ++i)
    {
        assert(app_ble_worker_host_dequeue_tx(&message) == (int)sizeof(message));
        assert(message.kind == APP_BLE_TX_KIND_ACK);
        assert(message.length == 1u);
        assert(message.data[0] == ack_values[i]);
    }
    assert(app_ble_worker_host_dequeue_tx(&message) == (int)sizeof(message));
    assert(message.kind == APP_BLE_TX_KIND_TELEMETRY);
    assert(message.length == sizeof(telemetry_new) - 1u);
    assert(memcmp(message.data, telemetry_new, message.length) == 0);
    assert(app_ble_worker_host_dequeue_tx(&message) == 0);
}

static void test_tx_rejects_oversize_and_disconnect_invalidates_pending(void)
{
    uint8_t oversize[APP_BLE_TX_PAYLOAD_MAX + 1u] = {0};
    static const uint8_t payload[] = "pending\n";
    app_ble_tx_message_t message;
    app_ble_session_token_t old_token;
    app_ble_session_token_t new_token;

    assert(app_ble_worker_init() == 0);
    assert(app_ble_worker_begin_session(10u) == 0);
    assert(app_ble_worker_get_session_token(&old_token) == 0);
    assert(app_ble_worker_enqueue_ack(&old_token, oversize, sizeof(oversize)) != 0);
    assert(app_ble_worker_publish_telemetry(&old_token, oversize, sizeof(oversize)) != 0);
    assert(app_ble_worker_enqueue_ack(&old_token, payload, sizeof(payload) - 1u) == 0);
    assert(app_ble_worker_publish_telemetry(&old_token, payload, sizeof(payload) - 1u) == 0);

    app_ble_worker_reset_session(10u);
    assert(app_ble_worker_host_dequeue_tx(&message) == 0);
    assert(app_ble_worker_begin_session(10u) == 0);
    assert(app_ble_worker_get_session_token(&new_token) == 0);
    assert(app_ble_worker_enqueue_ack(&old_token, payload, sizeof(payload) - 1u) != 0);
    assert(app_ble_worker_publish_telemetry(&old_token, payload, sizeof(payload) - 1u) != 0);
    assert(app_ble_worker_enqueue_ack(&new_token, payload, sizeof(payload) - 1u) == 0);
}

static void test_notify_gate_requires_buffer_return_and_operation_completion(void)
{
    app_ble_session_token_t token;

    assert(app_ble_worker_init() == 0);
    assert(app_ble_worker_begin_session(12u) == 0);
    assert(app_ble_worker_get_session_token(&token) == 0);
    assert(app_ble_worker_notify_try_acquire(&token));
    assert(!app_ble_worker_notify_try_acquire(&token));

    app_ble_worker_reset_session(12u);
    assert(app_ble_worker_begin_session(13u) != 0);
    app_ble_worker_notify_buffer_returned();
    assert(app_ble_worker_begin_session(13u) != 0);
    app_ble_worker_notify_operation_complete(token.conn_id);
    assert(app_ble_worker_begin_session(13u) == 0);

    assert(app_ble_worker_get_session_token(&token) == 0);
    assert(app_ble_worker_notify_try_acquire(&token));
    app_ble_worker_notify_operation_complete((uint16_t)(token.conn_id + 1u));
    app_ble_worker_notify_buffer_returned();
    assert(app_ble_worker_begin_session(14u) != 0);
    app_ble_worker_notify_operation_complete(token.conn_id);
    assert(app_ble_worker_begin_session(14u) == 0);

    assert(app_ble_worker_get_session_token(&token) == 0);
    assert(app_ble_worker_notify_try_acquire(&token));
    app_ble_worker_notify_operation_complete(token.conn_id);
    assert(app_ble_worker_begin_session(15u) != 0);
    app_ble_worker_notify_buffer_returned();
    assert(app_ble_worker_begin_session(15u) == 0);
}

int main(void)
{
    test_20_byte_fragments();
    test_244_byte_fragment();
    test_coalesced_frames();
    test_partial_frame_timeout();
    test_partial_deadline_does_not_slide();
    test_disconnect_clears_partial_frame();
    test_generation_change_clears_old_partial_before_new_feed();
    test_oversize_frame_is_dropped_without_poisoning_next_frame();
    test_queue_full_does_not_overwrite_and_generation_invalidates_old();
    test_tx_ack_queue_is_bounded_and_precedes_coalesced_telemetry();
    test_tx_rejects_oversize_and_disconnect_invalidates_pending();
    test_notify_gate_requires_buffer_return_and_operation_completion();
    puts("app_ble_reassembly_test: PASS");
    return 0;
}
