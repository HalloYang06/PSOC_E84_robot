#include "model_result_publisher.h"

#include "m33_m55_comm.h"

#define MODEL_RESULT_MOTION_CLASS_NONE      0U
#define MODEL_RESULT_MOTION_CLASS_DETECTED  1U
#define MODEL_RESULT_FLAG_FRESH             0x01U
#define MODEL_RESULT_FLAG_DETECTED          0x02U

static rt_uint32_t g_model_result_seq;

static float model_result_confidence_float(rt_uint16_t confidence_permille)
{
    if (confidence_permille > 1000U)
    {
        confidence_permille = 1000U;
    }
    return ((float)confidence_permille) / 1000.0f;
}

rt_err_t model_result_publish(rt_uint8_t model_code,
                              rt_uint8_t result_code,
                              rt_uint16_t confidence_permille,
                              rt_bool_t detected,
                              rt_bool_t fresh,
                              rt_uint16_t window_ms)
{
    m33_m55_message_t msg;

    if (confidence_permille > 1000U)
    {
        confidence_permille = 1000U;
    }

    rt_memset(&msg, 0, sizeof(msg));
    msg.type = MSG_TYPE_AI_INFERENCE_RESP;
    msg.seq = ++g_model_result_seq;
    msg.payload.ai_inference.motion_class = detected ? MODEL_RESULT_MOTION_CLASS_DETECTED
                                                     : MODEL_RESULT_MOTION_CLASS_NONE;
    msg.payload.ai_inference.model_code = model_code;
    msg.payload.ai_inference.result_code = result_code;
    msg.payload.ai_inference.result_flags = (fresh ? MODEL_RESULT_FLAG_FRESH : 0U) |
                                            (detected ? MODEL_RESULT_FLAG_DETECTED : 0U);
    msg.payload.ai_inference.confidence = model_result_confidence_float(confidence_permille);
    msg.payload.ai_inference.fatigue_score = fresh ? 0.0f : 1.0f;
    msg.payload.ai_inference.pain_risk = ((float)window_ms) / 1000.0f;

    return m33_m55_comm_publish(&msg);
}

rt_err_t model_result_publish_wake_word(rt_uint16_t confidence_permille,
                                         rt_bool_t detected,
                                         rt_bool_t fresh,
                                         rt_uint16_t window_ms)
{
    return model_result_publish(MODEL_CODE_WAKE_WORD,
                                detected ? MODEL_RESULT_CODE_WAKE_START_REQUEST
                                         : MODEL_RESULT_CODE_NONE,
                                confidence_permille,
                                detected,
                                fresh,
                                window_ms);
}
