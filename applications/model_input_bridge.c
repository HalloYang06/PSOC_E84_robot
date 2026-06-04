#include "model_input_bridge.h"

#include "motor7_model_runner.h"
#include "model_result_publisher.h"

#define SNAPSHOT_DETECT_THRESHOLD 0.25f
#define SNAPSHOT_WINDOW_MS        200U

static void model_input_bridge_handle_snapshot(const m33_m55_message_t *msg)
{
    const sensor_snapshot_msg_t *snapshot;
    float emg_abs_1;
    float emg_abs_2;
    float score;
    rt_bool_t detected;
    rt_uint16_t confidence_permille;
    rt_err_t ret;

    snapshot = &msg->payload.sensor_snapshot;
    if (snapshot->source == MODEL_INPUT_SRC_MOTOR_FEEDBACK)
    {
        ret = motor7_model_runner_run_snapshot(snapshot);
        rt_kprintf("[model_input] motor feedback snapshot ret=%d\n", ret);
        return;
    }

    emg_abs_1 = snapshot->emg_ch1 >= 0.0f ? snapshot->emg_ch1 : -snapshot->emg_ch1;
    emg_abs_2 = snapshot->emg_ch2 >= 0.0f ? snapshot->emg_ch2 : -snapshot->emg_ch2;
    score = emg_abs_1 > emg_abs_2 ? emg_abs_1 : emg_abs_2;
    if (score > 1.0f)
    {
        score = 1.0f;
    }

    detected = score >= SNAPSHOT_DETECT_THRESHOLD ? RT_TRUE : RT_FALSE;
    confidence_permille = (rt_uint16_t)((score * 1000.0f) + 0.5f);

    rt_kprintf("[model_input] snapshot seq=%lu emg=(%d,%d) hr=%u spo2=%u score=%u detected=%d\n",
               (unsigned long)msg->seq,
               (int)(snapshot->emg_ch1 * 1000.0f),
               (int)(snapshot->emg_ch2 * 1000.0f),
               snapshot->heart_rate,
               snapshot->spo2,
               confidence_permille,
               detected ? 1 : 0);

    ret = model_result_publish_wake_word(confidence_permille,
                                         detected,
                                         RT_TRUE,
                                         SNAPSHOT_WINDOW_MS);
    rt_kprintf("[model_input] snapshot publish ret=%d\n", ret);
}

static void model_input_bridge_handle_stream(const m33_m55_message_t *msg)
{
    const sensor_stream_msg_t *stream = &msg->payload.sensor_stream;

    if (stream->source == MODEL_INPUT_SRC_AUDIO_PCM)
    {
        return;
    }

    rt_kprintf("[model_input] stream seq=%lu source=%u fmt=%u channels=%u len=%lu chunk=%lu\n",
               (unsigned long)msg->seq,
               stream->source,
               stream->format,
               stream->channels,
               (unsigned long)stream->total_len,
               (unsigned long)stream->chunk_len);
}

void model_input_bridge_handle_message(const m33_m55_message_t *msg)
{
    if (msg == RT_NULL)
    {
        return;
    }

    switch (msg->type)
    {
    case MSG_TYPE_SENSOR_SNAPSHOT:
        model_input_bridge_handle_snapshot(msg);
        break;
    case MSG_TYPE_SENSOR_STREAM:
        model_input_bridge_handle_stream(msg);
        break;
    default:
        break;
    }
}

static void model_input_request_m33_snapshot(int argc, char **argv)
{
    m33_m55_message_t msg;
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_VOICE_CONTROL;
    msg.payload.voice_control.cmd = VOICE_CTRL_PUBLISH_TEST_SNAPSHOT;
    ret = m33_m55_comm_publish(&msg);
    rt_kprintf("model_input_request_m33_snapshot ret=%d\n", ret);
}
MSH_CMD_EXPORT(model_input_request_m33_snapshot, Request M33 to publish one test sensor snapshot);
MSH_CMD_EXPORT_ALIAS(model_input_request_m33_snapshot, req_snap, Request M33 to publish one test sensor snapshot);

static void model_input_request_m33_motor7(int argc, char **argv)
{
    m33_m55_message_t msg;
    rt_err_t ret;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_VOICE_CONTROL;
    msg.payload.voice_control.cmd = VOICE_CTRL_PUBLISH_MOTOR7_SNAPSHOT;
    ret = m33_m55_comm_publish(&msg);
    rt_kprintf("model_input_request_m33_motor7 ret=%d\n", ret);
}
MSH_CMD_EXPORT(model_input_request_m33_motor7, Request M33 motor7 feedback and run TFLM model);
MSH_CMD_EXPORT_ALIAS(model_input_request_m33_motor7, req_m7, Request M33 motor7 feedback and run TFLM model);
