#include "mtb_wwd.h"

#include MTB_WWD_NLU_CONFIG_HEADER(PROJECT_PREFIX)

static mtb_wwd_t g_wwd;
static int g_ready;

int ifx_deepcraft_wake_init(void)
{
    cy_rslt_t result;

    if (g_ready)
    {
        return 0;
    }

    result = mtb_wwd_init(&g_wwd, MTB_WWD_NLU_CONFIG_STRUCT(PROJECT_PREFIX)[0]);
    if (result != MTB_VA_RSLT_SUCCESS)
    {
        return (int)result;
    }

    g_ready = 1;
    return 0;
}

int ifx_deepcraft_wake_process(int16_t *pcm, int *detected)
{
    mtb_wwd_state_t state = CY_WWD_NOT_DETECTED;
    cy_rslt_t result;

    if ((pcm == 0) || (detected == 0))
    {
        return MTB_VA_RSLT_INVALID_PARAM;
    }

    if (!g_ready)
    {
        result = ifx_deepcraft_wake_init();
        if (result != 0)
        {
            return (int)result;
        }
    }

    result = mtb_wwd_process(&g_wwd, pcm, &state);
    *detected = (state == CY_WWD_DETECTED) ? 1 : 0;
    return (int)result;
}
