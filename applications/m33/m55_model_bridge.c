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

static m55_model_bridge_state_t g_m55_model_state;

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
    default:
        break;
    }
}
