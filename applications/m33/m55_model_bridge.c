#include "m55_model_bridge.h"

#include "control/control_layer.h"
#include "control/control_layer_cfg.h"

#define M55_MODEL_CODE_WAKE_WORD 1U
#define M55_RESULT_CODE_NONE 0U
#define M55_RESULT_CODE_WAKE_START_REQUEST 1U
#define M55_RESULT_FLAG_FRESH 0x01U
#define M55_RESULT_FLAG_DETECTED 0x02U

typedef struct
{
    rt_uint32_t seq;
    rt_uint8_t model_code;
    rt_uint8_t result_code;
    rt_uint16_t confidence_permille;
    rt_uint8_t flags;
    rt_uint16_t window_ms;
    rt_tick_t timestamp;
} m55_model_bridge_state_t;

typedef struct
{
    rt_uint32_t seq;
    rt_uint32_t cmd;
    rt_int32_t result;
    rt_uint32_t m55_tick;
    rt_tick_t timestamp;
} m55_voice_ack_state_t;

typedef struct
{
    rt_uint32_t seq;
    voice_status_msg_t status;
    rt_tick_t timestamp;
} m55_voice_status_state_t;

static m55_model_bridge_state_t g_m55_model_state;
static m55_voice_ack_state_t g_m55_voice_ack_state;
static m55_voice_status_state_t g_m55_voice_status_state;

static rt_uint16_t confidence_to_permille(float confidence)
{
    if (confidence <= 0.0f)
    {
        return 0U;
    }
    if (confidence >= 1.0f)
    {
        return 1000U;
    }
    return (rt_uint16_t)((confidence * 1000.0f) + 0.5f);
}

void m55_model_bridge_init(void)
{
    rt_memset(&g_m55_model_state, 0, sizeof(g_m55_model_state));
    rt_memset(&g_m55_voice_ack_state, 0, sizeof(g_m55_voice_ack_state));
    rt_memset(&g_m55_voice_status_state, 0, sizeof(g_m55_voice_status_state));
}

static void m55_model_bridge_handle_ai_result(const m33_m55_message_t *msg)
{
    const ai_inference_msg_t *ai;
    rt_err_t ret;
    rt_uint8_t flags = 0U;
    rt_uint8_t result_code = M55_RESULT_CODE_NONE;
    rt_uint8_t model_code = M55_MODEL_CODE_WAKE_WORD;
    rt_uint16_t confidence_permille;
    rt_uint16_t window_ms;

    ai = &msg->payload.ai_inference;
    confidence_permille = confidence_to_permille(ai->confidence);
    window_ms = (rt_uint16_t)(ai->pain_risk * 1000.0f);
    if (ai->model_code != 0U)
    {
        model_code = ai->model_code;
        result_code = ai->result_code;
        if ((ai->result_flags & M55_RESULT_FLAG_FRESH) != 0U)
        {
            flags |= CONTROL_M33_MODEL_STATUS_FLAG_FRESH;
        }
        if ((ai->result_flags & M55_RESULT_FLAG_DETECTED) != 0U)
        {
            flags |= CONTROL_M33_MODEL_STATUS_FLAG_DETECTED;
        }
    }

    if ((ai->model_code == 0U) && (ai->motion_class != 0U))
    {
        flags |= CONTROL_M33_MODEL_STATUS_FLAG_FRESH;
        flags |= CONTROL_M33_MODEL_STATUS_FLAG_DETECTED;
        result_code = M55_RESULT_CODE_WAKE_START_REQUEST;
    }

    g_m55_model_state.seq = msg->seq;
    g_m55_model_state.model_code = model_code;
    g_m55_model_state.result_code = result_code;
    g_m55_model_state.confidence_permille = confidence_permille;
    g_m55_model_state.flags = flags;
    g_m55_model_state.window_ms = window_ms;
    g_m55_model_state.timestamp = rt_tick_get();

    ret = control_publish_m55_model_result(g_m55_model_state.model_code,
                                           g_m55_model_state.result_code,
                                           g_m55_model_state.confidence_permille,
                                           g_m55_model_state.flags,
                                           g_m55_model_state.window_ms);
    rt_kprintf("[m55_model_bridge] ai seq=%lu model=%u result=%u conf=%u flags=0x%02x win=%u can_ret=%d\n",
               (unsigned long)g_m55_model_state.seq,
               g_m55_model_state.model_code,
               g_m55_model_state.result_code,
               g_m55_model_state.confidence_permille,
               g_m55_model_state.flags,
               g_m55_model_state.window_ms,
               ret);
}

static void m55_model_bridge_handle_voice_ack(const m33_m55_message_t *msg)
{
    const voice_control_msg_t *ack = &msg->payload.voice_control;

    g_m55_voice_ack_state.seq = msg->seq;
    g_m55_voice_ack_state.cmd = ack->cmd;
    g_m55_voice_ack_state.result = (rt_int32_t)ack->arg0;
    g_m55_voice_ack_state.m55_tick = ack->arg1;
    g_m55_voice_ack_state.timestamp = rt_tick_get();

    rt_kprintf("[m55_model_bridge] voice_ack seq=%lu cmd=%lu result=%ld m55_tick=%lu\n",
               (unsigned long)g_m55_voice_ack_state.seq,
               (unsigned long)g_m55_voice_ack_state.cmd,
               (long)g_m55_voice_ack_state.result,
               (unsigned long)g_m55_voice_ack_state.m55_tick);
}

static void m55_model_bridge_handle_voice_status(const m33_m55_message_t *msg)
{
    g_m55_voice_status_state.seq = msg->seq;
    g_m55_voice_status_state.status = msg->payload.voice_status;
    g_m55_voice_status_state.timestamp = rt_tick_get();
}

void m55_model_bridge_handle_message(const m33_m55_message_t *msg)
{
    if (msg == RT_NULL)
    {
        return;
    }

    switch (msg->type)
    {
    case MSG_TYPE_AI_INFERENCE_RESP:
        m55_model_bridge_handle_ai_result(msg);
        break;
    case MSG_TYPE_ASR_TEXT:
        rt_kprintf("[m55_model_bridge] asr text: %.64s\n", msg->payload.text.text);
        break;
    case MSG_TYPE_VOICE_CONTROL_ACK:
        m55_model_bridge_handle_voice_ack(msg);
        break;
    case MSG_TYPE_VOICE_STATUS:
        m55_model_bridge_handle_voice_status(msg);
        break;
    default:
        break;
    }
}

rt_bool_t m55_model_bridge_get_snapshot(rt_uint32_t *seq,
                                        rt_uint8_t *model_code,
                                        rt_uint8_t *result_code,
                                        rt_uint16_t *confidence_permille,
                                        rt_uint8_t *flags,
                                        rt_uint16_t *window_ms,
                                        rt_tick_t *timestamp)
{
    if (g_m55_model_state.timestamp == 0U)
    {
        return RT_FALSE;
    }

    if (seq != RT_NULL)
    {
        *seq = g_m55_model_state.seq;
    }
    if (model_code != RT_NULL)
    {
        *model_code = g_m55_model_state.model_code;
    }
    if (result_code != RT_NULL)
    {
        *result_code = g_m55_model_state.result_code;
    }
    if (confidence_permille != RT_NULL)
    {
        *confidence_permille = g_m55_model_state.confidence_permille;
    }
    if (flags != RT_NULL)
    {
        *flags = g_m55_model_state.flags;
    }
    if (window_ms != RT_NULL)
    {
        *window_ms = g_m55_model_state.window_ms;
    }
    if (timestamp != RT_NULL)
    {
        *timestamp = g_m55_model_state.timestamp;
    }
    return RT_TRUE;
}

rt_bool_t m55_model_bridge_get_voice_status(voice_status_msg_t *status,
                                            rt_uint32_t *seq,
                                            rt_tick_t *timestamp)
{
    if (g_m55_voice_status_state.timestamp == 0U)
    {
        return RT_FALSE;
    }

    if (status != RT_NULL)
    {
        *status = g_m55_voice_status_state.status;
    }
    if (seq != RT_NULL)
    {
        *seq = g_m55_voice_status_state.seq;
    }
    if (timestamp != RT_NULL)
    {
        *timestamp = g_m55_voice_status_state.timestamp;
    }
    return RT_TRUE;
}

rt_bool_t m55_model_bridge_get_voice_ack(rt_uint32_t *seq,
                                         rt_uint32_t *cmd,
                                         rt_int32_t *result,
                                         rt_uint32_t *m55_tick,
                                         rt_tick_t *timestamp)
{
    if (g_m55_voice_ack_state.timestamp == 0U)
    {
        return RT_FALSE;
    }

    if (seq != RT_NULL)
    {
        *seq = g_m55_voice_ack_state.seq;
    }
    if (cmd != RT_NULL)
    {
        *cmd = g_m55_voice_ack_state.cmd;
    }
    if (result != RT_NULL)
    {
        *result = g_m55_voice_ack_state.result;
    }
    if (m55_tick != RT_NULL)
    {
        *m55_tick = g_m55_voice_ack_state.m55_tick;
    }
    if (timestamp != RT_NULL)
    {
        *timestamp = g_m55_voice_ack_state.timestamp;
    }
    return RT_TRUE;
}
