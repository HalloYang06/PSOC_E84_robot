/*******************************************************************************
#include <packages/lvgl_9.2.0/src/draw/sw/lv_draw_sw.h>
* File Name        : lv_port_disp.c
*
* Description      : This file provides implementation of low level display
*                    device driver for LVGL.
*
* Related Document : See README.md
*
******************************************************************************/

/*******************************************************************************
* Header Files
*******************************************************************************/
#include "lv_port_disp.h"
#include <stdbool.h>
#include <string.h>
#include "cy_graphics.h"
#include "vg_lite.h"

extern cy_stc_gfx_context_t *drv_lcd_get_gfx_context(void);
extern rt_int32_t drv_lcd_get_init_result(void);
extern rt_int32_t drv_lcd_get_vglite_status(void);

#define SMIF0_GPU_GATE_TIMEOUT_MS         (500U)
#define SMIF0_GPU_FINISH_TIMEOUT_MS       (5000U)
#define SMIF0_GPU_INIT_GATE_TIMEOUT_MS    (120000U)
#define SMIF0_GPU_RENDER_GATE_TIMEOUT_MS  (1000U)

typedef enum
{
    SMIF0_GPU_STATE_COLD = 0,
    SMIF0_GPU_STATE_HW_INITING,
    SMIF0_GPU_STATE_HW_READY,
    SMIF0_GPU_STATE_UI_INITING,
    SMIF0_GPU_STATE_READY,
    SMIF0_GPU_STATE_FAILED
} smif0_gpu_state_t;


/*******************************************************************************
* Global Variables
*******************************************************************************/
CY_SECTION(".cy_gpu_buf") LV_ATTRIBUTE_MEM_ALIGN uint8_t disp_buf1[MY_DISP_HOR_RES *
                                               MY_DISP_VER_RES * 2];
CY_SECTION(".cy_gpu_buf") LV_ATTRIBUTE_MEM_ALIGN uint8_t disp_buf2[MY_DISP_HOR_RES *
                                               MY_DISP_VER_RES * 2];
/* Frame buffers used by GFXSS to render UI */
void *frame_buffer1 = &disp_buf1;
void *frame_buffer2 = &disp_buf2;

cy_stc_gfx_context_t gfx_context;
static volatile rt_uint32_t g_lvgl_flush_count = 0;
static volatile rt_int32_t g_lvgl_last_flush_status = -1;
static struct rt_mutex g_smif0_gpu_gate;
static rt_bool_t g_smif0_gpu_gate_initialized = RT_FALSE;
static rt_bool_t g_smif0_gpu_transaction_held = RT_FALSE;
static smif0_gpu_state_t g_smif0_gpu_state = SMIF0_GPU_STATE_COLD;

static int lv_port_disp_smif0_gate_init(void)
{
    const rt_err_t status = rt_mutex_init(&g_smif0_gpu_gate,
                                          "gpu_gate",
                                          RT_IPC_FLAG_PRIO);

    if (status == RT_EOK)
    {
        g_smif0_gpu_gate_initialized = RT_TRUE;
    }
    return status;
}
INIT_PREV_EXPORT(lv_port_disp_smif0_gate_init);


/*******************************************************************************
* Function Name: disp_flush
********************************************************************************
* Summary:
*  Flush the content of the internal buffer the specific area on the display.
*  You can use DMA or any hardware acceleration to do this operation in the
*  background but 'lv_disp_flush_ready()' has to be called when finished.
*
* Parameters:
*  *disp_drv: Pointer to the display driver structure to be registered by HAL.
*  *area: Pointer to the area of the screen (not used).
*  *color_p: Pointer to the frame buffer address.
*
* Return:
*  void
*
*******************************************************************************/
static void LV_ATTRIBUTE_FAST_MEM disp_flush(lv_display_t *disp_drv, const lv_area_t *area,
        uint8_t *color_p)
{
    CY_UNUSED_PARAMETER(area);

    cy_en_gfx_status_t status;

    status = Cy_GFXSS_Set_FrameBuffer((GFXSS_Type*) GFXSS, (uint32_t*) color_p,
                                      drv_lcd_get_gfx_context());
    g_lvgl_last_flush_status = (rt_int32_t)status;
    if (status == CY_GFX_SUCCESS)
    {
        g_lvgl_flush_count++;
    }

    /* Inform the graphics library that you are ready with the flushing */
    lv_display_flush_ready(disp_drv);

}


/*******************************************************************************
* Function Name: lv_port_disp_init
********************************************************************************
* Summary:
*  Initialization function for display devices supported by LittelvGL.
*   LVGL requires a buffer where it internally draws the widgets.
*   Later this buffer will passed to your display driver's `flush_cb` to copy
*   its content to your display.
*   The buffer has to be greater than 1 display row
*
*   There are 3 buffering configurations:
*   1. Create ONE buffer:
*      LVGL will draw the display's content here and writes it to your display
*
*   2. Create TWO buffer:
*      LVGL will draw the display's content to a buffer and writes it your
*      display.
*      You should use DMA to write the buffer's content to the display.
*      It will enable LVGL to draw the next part of the screen to the other
*      buffer while the data is being sent form the first buffer.
*      It makes rendering and flushing parallel.
*
*   3. Double buffering
*      Set 2 screens sized buffers and set disp_drv.full_refresh = 1.
*      This way LVGL will always provide the whole rendered screen in `flush_cb`
*      and you only need to change the frame buffer's address.
*
*
* Parameters:
*  void
*
* Return:
*  void
*
*******************************************************************************/
rt_err_t lv_port_disp_init(void)
{
    lv_display_t *disp;

    if ((drv_lcd_get_init_result() != RT_EOK) ||
        (drv_lcd_get_vglite_status() != VG_LITE_SUCCESS))
    {
        return -RT_ERROR;
    }

    memset(disp_buf1, 0, sizeof(disp_buf1));
    memset(disp_buf2, 0, sizeof(disp_buf2));

    disp = lv_display_create(MY_DISP_HOR_RES, MY_DISP_VER_RES);
    if (disp == RT_NULL)
    {
        return -RT_ENOMEM;
    }

    lv_display_set_flush_cb(disp, disp_flush);

    lv_tick_set_cb(&rt_tick_get_millisecond);

    lv_display_set_buffers(disp, disp_buf1, disp_buf2, sizeof(disp_buf1),
                           LV_DISPLAY_RENDER_MODE_FULL);//

    // lv_display_set_rotation(disp, LV_DISPLAY_ROTATION_270);

    Cy_GFXSS_Clear_DC_Interrupt((GFXSS_Type*) GFXSS, drv_lcd_get_gfx_context());
    return RT_EOK;
}

rt_err_t lv_port_disp_smif0_init_begin(void)
{
    rt_err_t status;

    if (!g_smif0_gpu_gate_initialized)
    {
        return -RT_ERROR;
    }

    status = rt_mutex_take(&g_smif0_gpu_gate,
                           rt_tick_from_millisecond(SMIF0_GPU_INIT_GATE_TIMEOUT_MS));
    if (status != RT_EOK)
    {
        return status;
    }

    if (g_smif0_gpu_state != SMIF0_GPU_STATE_HW_READY)
    {
        (void)rt_mutex_release(&g_smif0_gpu_gate);
        return -RT_EBUSY;
    }

    g_smif0_gpu_state = SMIF0_GPU_STATE_UI_INITING;
    return RT_EOK;
}

void lv_port_disp_smif0_init_end(rt_bool_t success)
{
    if (!g_smif0_gpu_gate_initialized ||
        (g_smif0_gpu_state != SMIF0_GPU_STATE_UI_INITING))
    {
        return;
    }

    g_smif0_gpu_state = success ? SMIF0_GPU_STATE_READY : SMIF0_GPU_STATE_FAILED;
    (void)rt_mutex_release(&g_smif0_gpu_gate);
}

rt_err_t lv_port_disp_smif0_hw_init_begin(void)
{
    rt_err_t status;

    if (!g_smif0_gpu_gate_initialized)
    {
        return -RT_ERROR;
    }

    status = rt_mutex_take(&g_smif0_gpu_gate,
                           rt_tick_from_millisecond(SMIF0_GPU_INIT_GATE_TIMEOUT_MS));
    if (status != RT_EOK)
    {
        return status;
    }

    if (g_smif0_gpu_state != SMIF0_GPU_STATE_COLD)
    {
        (void)rt_mutex_release(&g_smif0_gpu_gate);
        return -RT_EBUSY;
    }

    g_smif0_gpu_state = SMIF0_GPU_STATE_HW_INITING;
    return RT_EOK;
}

void lv_port_disp_smif0_hw_init_end(rt_bool_t success)
{
    if (!g_smif0_gpu_gate_initialized ||
        (g_smif0_gpu_state != SMIF0_GPU_STATE_HW_INITING))
    {
        return;
    }

    g_smif0_gpu_state = success ? SMIF0_GPU_STATE_HW_READY : SMIF0_GPU_STATE_FAILED;
    (void)rt_mutex_release(&g_smif0_gpu_gate);
}

rt_err_t lv_port_disp_smif0_render_begin(void)
{
    rt_err_t status;

    if (!g_smif0_gpu_gate_initialized)
    {
        return -RT_ERROR;
    }

    status = rt_mutex_take(&g_smif0_gpu_gate,
                           rt_tick_from_millisecond(SMIF0_GPU_RENDER_GATE_TIMEOUT_MS));
    if (status != RT_EOK)
    {
        return status;
    }

    if (g_smif0_gpu_state != SMIF0_GPU_STATE_READY)
    {
        (void)rt_mutex_release(&g_smif0_gpu_gate);
        return -RT_ERROR;
    }
    return RT_EOK;
}

void lv_port_disp_smif0_render_end(void)
{
    if (g_smif0_gpu_gate_initialized)
    {
        (void)rt_mutex_release(&g_smif0_gpu_gate);
    }
}

void lv_port_disp_smif0_gpu_fault(void)
{
    if (!g_smif0_gpu_gate_initialized)
    {
        return;
    }

    if (rt_mutex_take(&g_smif0_gpu_gate,
                      rt_tick_from_millisecond(SMIF0_GPU_GATE_TIMEOUT_MS)) == RT_EOK)
    {
        g_smif0_gpu_state = SMIF0_GPU_STATE_FAILED;
        (void)rt_mutex_release(&g_smif0_gpu_gate);
    }
}

rt_err_t lv_port_disp_smif0_quiesce(void)
{
#if LV_USE_DRAW_VG_LITE
    vg_lite_uint32_t gpu_idle = 0U;
#endif
    rt_err_t status;

    if (!g_smif0_gpu_gate_initialized)
    {
        return -RT_ERROR;
    }

    status = rt_mutex_take(&g_smif0_gpu_gate,
                           rt_tick_from_millisecond(SMIF0_GPU_GATE_TIMEOUT_MS));
    if (status != RT_EOK)
    {
        return status;
    }

    if (g_smif0_gpu_transaction_held)
    {
        (void)rt_mutex_release(&g_smif0_gpu_gate);
        return -RT_EBUSY;
    }

    g_smif0_gpu_transaction_held = RT_TRUE;
    if (g_smif0_gpu_state == SMIF0_GPU_STATE_COLD)
    {
        /* Hold the lifecycle gate so GPU initialization cannot cross this transaction. */
        return RT_EOK;
    }
    if ((g_smif0_gpu_state != SMIF0_GPU_STATE_HW_READY) &&
        (g_smif0_gpu_state != SMIF0_GPU_STATE_READY))
    {
        g_smif0_gpu_transaction_held = RT_FALSE;
        (void)rt_mutex_release(&g_smif0_gpu_gate);
        return -RT_ERROR;
    }

#if LV_USE_DRAW_VG_LITE
    if ((vg_lite_finish_timeout(SMIF0_GPU_FINISH_TIMEOUT_MS) != VG_LITE_SUCCESS) ||
        (vg_lite_get_parameter(VG_LITE_GPU_IDLE_STATE, 1, &gpu_idle) != VG_LITE_SUCCESS) ||
        (gpu_idle == 0U))
    {
        g_smif0_gpu_state = SMIF0_GPU_STATE_FAILED;
        g_smif0_gpu_transaction_held = RT_FALSE;
        (void)rt_mutex_release(&g_smif0_gpu_gate);
        return -RT_ERROR;
    }
#endif

    return RT_EOK;
}

void lv_port_disp_smif0_resume(void)
{
    if (g_smif0_gpu_gate_initialized && g_smif0_gpu_transaction_held)
    {
        g_smif0_gpu_transaction_held = RT_FALSE;
        (void)rt_mutex_release(&g_smif0_gpu_gate);
    }
}

rt_uint32_t lv_port_disp_get_flush_count(void)
{
    return g_lvgl_flush_count;
}

rt_int32_t lv_port_disp_get_last_flush_status(void)
{
    return g_lvgl_last_flush_status;
}



/* [] END OF FILE */
