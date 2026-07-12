#ifndef CONTROL_CAN_METRICS_H
#define CONTROL_CAN_METRICS_H

#include <rtthread.h>
#include <rtdevice.h>
#include <drivers/can.h>

void can_metrics_reset(void);
void can_metrics_set_bitrate(rt_uint32_t bitrate);
void can_metrics_record_tx(const struct rt_can_msg *msg, rt_err_t result);
void can_metrics_record_rx(const struct rt_can_msg *msg);
void can_metrics_record_rx_drain_limit(void);

#endif /* CONTROL_CAN_METRICS_H */
