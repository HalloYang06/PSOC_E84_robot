from pathlib import Path


SOURCE = Path(__file__).parents[1] / "libraries/HAL_Drivers/drv_lcd.c"


def test_lcd_init_hands_backlight_from_unstarted_pwm_to_gpio():
    source = SOURCE.read_text(encoding="utf-8")
    panel_init = source.index("mipi_status = mtb_display_tl043wvv02_init")
    init_done = source.index('LOG_I("init screen success")', panel_init)
    handoff = source.find(
        "Cy_GPIO_Pin_FastInit(CYBSP_DISP_BACKLIGHT_PWM_PORT", panel_init
    )

    assert handoff != -1, "LCD init leaves P20.6 routed to an unstarted PWM"
    assert panel_init < handoff < init_done
    assert "HSIOM_SEL_GPIO" in source[handoff:init_done]
