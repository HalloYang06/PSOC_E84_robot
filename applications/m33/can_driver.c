#include "can_driver.h"

rt_err_t can_driver_init(void)
{
    return RT_EOK;
}

rt_err_t can_send_joint_target(joint_id_t joint, float target)
{
    RT_UNUSED(joint);
    RT_UNUSED(target);
    return RT_EOK;
}

rt_err_t can_process_frame(const rehab_can_frame_t *frame, sensor_data_t *snapshot)
{
    if (frame == RT_NULL || snapshot == RT_NULL)
    {
        return -RT_ERROR;
    }

    switch (frame->id)
    {
    case CAN_ID_SENSOR_EMG:
        snapshot->emg_ch1 = frame->data[0] / 10.0f;
        snapshot->emg_ch2 = frame->data[1] / 10.0f;
        break;
    case CAN_ID_SENSOR_HEART:
        snapshot->heart_rate = frame->data[0];
        snapshot->spo2 = frame->data[1];
        break;
    default:
        break;
    }

    snapshot->timestamp = rt_tick_get();
    return RT_EOK;
}
