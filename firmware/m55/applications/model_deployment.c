#include "model_deployment.h"

#include "model_manager.h"
#include "model_result_publisher.h"
#include "wake_word_model_data.h"

#include <stdlib.h>

#define WAKE_DEFAULT_ARENA_KB       1536U
#define WAKE_DEFAULT_THRESHOLD      750U
#define WAKE_TEST_SAMPLE_RATE       16000U
#define WAKE_TEST_SAMPLE_COUNT      16000U
#define WAKE_TEST_WINDOW_MS         1000U

static rt_bool_t g_wake_slot_loaded = RT_FALSE;

static rt_uint32_t parse_u32_arg(int argc,
                                 char **argv,
                                 int index,
                                 rt_uint32_t fallback)
{
    if ((argc <= index) || (argv[index] == RT_NULL))
    {
        return fallback;
    }
    return (rt_uint32_t)strtoul(argv[index], RT_NULL, 0);
}

rt_err_t model_deployment_load_wake_word(rt_uint32_t arena_kb,
                                         rt_uint16_t threshold_permille)
{
    model_slot_config_t cfg;
    model_slot_info_t info;
    rt_err_t ret;

    if (arena_kb == 0U)
    {
        arena_kb = WAKE_DEFAULT_ARENA_KB;
    }
    if (threshold_permille == 0U)
    {
        threshold_permille = WAKE_DEFAULT_THRESHOLD;
    }
    if (threshold_permille > 1000U)
    {
        threshold_permille = 1000U;
    }

    ret = model_manager_init();
    if (ret != RT_EOK)
    {
        rt_kprintf("[model_deploy] manager init failed ret=%d\n", ret);
        return ret;
    }

    rt_memset(&cfg, 0, sizeof(cfg));
    cfg.arena_bytes = arena_kb * 1024U;
    cfg.input_kind = MODEL_INPUT_PCM_S16;
    cfg.sample_rate = WAKE_TEST_SAMPLE_RATE;
    cfg.channels = 1U;
    cfg.threshold_permille = threshold_permille;

    ret = model_manager_configure_slot(MODEL_SLOT_WAKE_WORD, &cfg);
    if (ret != RT_EOK)
    {
        rt_kprintf("[model_deploy] configure wake slot failed ret=%d\n", ret);
        return ret;
    }

    ret = model_manager_load_tflm_model(MODEL_SLOT_WAKE_WORD,
                                        wake_word_model,
                                        wake_word_model_len);
    if (ret != RT_EOK)
    {
        rt_kprintf("[model_deploy] load wake model failed ret=%d model=%u arena=%lu\n",
                   ret,
                   (unsigned int)wake_word_model_len,
                   (unsigned long)cfg.arena_bytes);
        return ret;
    }

    g_wake_slot_loaded = RT_TRUE;
    rt_memset(&info, 0, sizeof(info));
    model_manager_get_info(MODEL_SLOT_WAKE_WORD, &info);
    rt_kprintf("[model_deploy] wake slot ready=%d model=%u arena=%lu input_bytes=%lu output_bytes=%lu in_type=%lu out_type=%lu threshold=%lu\n",
               info.ready ? 1 : 0,
               (unsigned int)wake_word_model_len,
               (unsigned long)info.arena_bytes,
               (unsigned long)info.input_bytes,
               (unsigned long)info.output_bytes,
               (unsigned long)info.input_type,
               (unsigned long)info.output_type,
               (unsigned long)info.threshold_permille);
    return RT_EOK;
}

rt_err_t model_deployment_run_silence(rt_bool_t publish_result)
{
    int16_t *samples;
    float score = 0.0f;
    int detected = 0;
    long score_permille;
    rt_err_t ret;

    if (!g_wake_slot_loaded)
    {
        ret = model_deployment_load_wake_word(WAKE_DEFAULT_ARENA_KB,
                                              WAKE_DEFAULT_THRESHOLD);
        if (ret != RT_EOK)
        {
            return ret;
        }
    }

    samples = (int16_t *)rt_malloc_align(sizeof(int16_t) * WAKE_TEST_SAMPLE_COUNT, 16);
    if (samples == RT_NULL)
    {
        rt_kprintf("[model_deploy] alloc silence buffer failed\n");
        return -RT_ENOMEM;
    }

    rt_memset(samples, 0, sizeof(int16_t) * WAKE_TEST_SAMPLE_COUNT);
    ret = model_manager_run_pcm16(MODEL_SLOT_WAKE_WORD,
                                  samples,
                                  WAKE_TEST_SAMPLE_COUNT,
                                  &score,
                                  &detected);
    rt_free_align(samples);
    if (ret != RT_EOK)
    {
        rt_kprintf("[model_deploy] silence inference failed ret=%d\n", ret);
        return ret;
    }

    if (score < 0.0f)
    {
        score = 0.0f;
    }
    if (score > 1.0f)
    {
        score = 1.0f;
    }
    score_permille = (long)(score * 1000.0f);
    rt_kprintf("[model_deploy] silence score=%ld detected=%d publish=%d\n",
               score_permille,
               detected,
               publish_result ? 1 : 0);

    if (publish_result)
    {
        ret = model_result_publish_wake_word((rt_uint16_t)score_permille,
                                             detected ? RT_TRUE : RT_FALSE,
                                             RT_TRUE,
                                             WAKE_TEST_WINDOW_MS);
        rt_kprintf("[model_deploy] publish ret=%d\n", ret);
        return ret;
    }

    return RT_EOK;
}

static void m55_model_load_wake(int argc, char **argv)
{
    rt_uint32_t arena_kb = parse_u32_arg(argc, argv, 1, WAKE_DEFAULT_ARENA_KB);
    rt_uint32_t threshold = parse_u32_arg(argc, argv, 2, WAKE_DEFAULT_THRESHOLD);
    rt_err_t ret;

    ret = model_deployment_load_wake_word(arena_kb, (rt_uint16_t)threshold);
    rt_kprintf("m55_model_load_wake ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55_model_load_wake, Load bundled wake-word TFLM model into model_manager slot0);
MSH_CMD_EXPORT_ALIAS(m55_model_load_wake, mdl_load, Load bundled wake-word TFLM model into model_manager slot0);

static void m55_model_run_silence(int argc, char **argv)
{
    rt_bool_t publish_result = RT_FALSE;
    rt_err_t ret;

    if ((argc >= 2) && (argv[1] != RT_NULL) &&
        ((argv[1][0] == '1') || (argv[1][0] == 'p')))
    {
        publish_result = RT_TRUE;
    }

    ret = model_deployment_run_silence(publish_result);
    rt_kprintf("m55_model_run_silence ret=%d\n", ret);
}
MSH_CMD_EXPORT(m55_model_run_silence, Run bundled wake-word model on silence; arg 1/p publishes result);
MSH_CMD_EXPORT_ALIAS(m55_model_run_silence, mdl_sil, Run bundled wake-word model on silence; arg 1/p publishes result);
