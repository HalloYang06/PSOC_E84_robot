#include "m55_voice_mode_bridge.h"

#include "control_manager.h"

#include <rtthread.h>
#include <string.h>

typedef struct
{
    const char *keyword;
    control_mode_t mode;
    const char *name;
} voice_mode_keyword_t;

static const voice_mode_keyword_t kModeKeywords[] = {
    {"被动", CONTROL_MODE_PASSIVE, "passive"},
    {"停止", CONTROL_MODE_PASSIVE, "passive"},
    {"退出", CONTROL_MODE_PASSIVE, "passive"},
    {"停下", CONTROL_MODE_PASSIVE, "passive"},
    {"passive", CONTROL_MODE_PASSIVE, "passive"},
    {"stop", CONTROL_MODE_PASSIVE, "passive"},
    {"主动", CONTROL_MODE_ACTIVE, "active"},
    {"active", CONTROL_MODE_ACTIVE, "active"},
    {"记忆", CONTROL_MODE_MEMORY, "memory"},
    {"memory", CONTROL_MODE_MEMORY, "memory"},
    {"助力", CONTROL_MODE_AI_ASSIST, "assist"},
    {"辅助", CONTROL_MODE_AI_ASSIST, "assist"},
    {"assist", CONTROL_MODE_AI_ASSIST, "assist"},
    {"ai assist", CONTROL_MODE_AI_ASSIST, "assist"},
};

static const char *const kCommandHints[] = {
    "切换",
    "进入",
    "启动",
    "开启",
    "打开",
    "设置",
    "设为",
    "换到",
    "模式",
    "switch",
    "set ",
    "start",
};

static const char *const kQuestionHints[] = {
    "什么",
    "怎么",
    "如何",
    "吗",
    "是不是",
    "?",
};

static rt_bool_t text_contains_any(const char *text,
                                   const char *const *words,
                                   rt_size_t word_count)
{
    if (text == RT_NULL)
    {
        return RT_FALSE;
    }

    for (rt_size_t i = 0U; i < word_count; i++)
    {
        if ((words[i] != RT_NULL) && (strstr(text, words[i]) != RT_NULL))
        {
            return RT_TRUE;
        }
    }
    return RT_FALSE;
}

static const voice_mode_keyword_t *find_mode_keyword(const char *text)
{
    if (text == RT_NULL)
    {
        return RT_NULL;
    }

    for (rt_size_t i = 0U; i < (sizeof(kModeKeywords) / sizeof(kModeKeywords[0])); i++)
    {
        if (strstr(text, kModeKeywords[i].keyword) != RT_NULL)
        {
            return &kModeKeywords[i];
        }
    }
    return RT_NULL;
}

rt_bool_t m55_voice_mode_bridge_parse(const char *text, control_mode_t *mode)
{
    const voice_mode_keyword_t *keyword;
    rt_bool_t has_command_hint;
    rt_bool_t has_question_hint;

    if ((text == RT_NULL) || (mode == RT_NULL) || (text[0] == '\0'))
    {
        return RT_FALSE;
    }

    has_question_hint = text_contains_any(text,
                                          kQuestionHints,
                                          sizeof(kQuestionHints) / sizeof(kQuestionHints[0]));
    if (has_question_hint)
    {
        return RT_FALSE;
    }

    keyword = find_mode_keyword(text);
    if (keyword == RT_NULL)
    {
        return RT_FALSE;
    }

    has_command_hint = text_contains_any(text,
                                         kCommandHints,
                                         sizeof(kCommandHints) / sizeof(kCommandHints[0]));
    if (!has_command_hint && (keyword->mode != CONTROL_MODE_PASSIVE))
    {
        return RT_FALSE;
    }

    *mode = keyword->mode;
    return RT_TRUE;
}

rt_err_t m55_voice_mode_bridge_handle_text(const char *text)
{
    control_mode_t mode;
    rt_err_t ret;

    if (!m55_voice_mode_bridge_parse(text, &mode))
    {
        rt_kprintf("[voice_mode] ignore text: %.64s\n", text ? text : "(null)");
        return -RT_EINVAL;
    }

    ret = control_set_mode(mode);
    rt_kprintf("[voice_mode] set mode=%d ret=%d text=%.64s\n",
               (int)mode,
               ret,
               text);
    return ret;
}
