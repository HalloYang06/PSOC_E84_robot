#ifndef __CONTROL_SENSOR_H__
#define __CONTROL_SENSOR_H__

#include <rtthread.h>
#include <drivers/can.h>

#include "control_layer.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * 传感器模块内部接口。
 *
 * 对外兼容 API 仍声明在 control_layer.h：
 * - control_sensor_report_enable(): 配置/启动/停止 F103 传感节点上报。
 * - control_get_emg_report(): 读取最近一次肌电兼容缓存。
 * - control_get_heart_report(): 读取最近一次心率兼容缓存。
 * - control_get_sensor_node_sample(): 读取 F103/C8T6 综合节点缓存。
 *
 * control_layer.c 只通过本头文件做两件事：
 * 1. 初始化传感器模块，注册 CAN 发送函数和 TX 序号函数。
 * 2. 收到对应 CAN ID 后，把原始 rt_can_msg 转交给传感器模块解析。
 */

/* CAN 发送回调类型。
 * 传感器模块不直接持有 CAN 设备句柄，而是通过 control_layer.c 的 ctrl_can_send() 发帧。
 * 这样可以保持所有 CAN 发送仍走同一个底层出口。
 */
typedef rt_err_t (*control_sensor_can_send_fn)(rt_uint32_t id,
                                               rt_uint8_t ide,
                                               const rt_uint8_t *data,
                                               rt_uint8_t len);
/* TX 序号回调类型。
 * F103 控制帧和旧传感控制帧都沿用 control_layer.c 的 s_tx_seq++。
 */
typedef rt_uint8_t (*control_sensor_next_seq_fn)(void);

/* 初始化传感器模块。
 * 参数 send_fn: control_layer.c 提供的 CAN 发送函数。
 * 参数 next_seq_fn: control_layer.c 提供的递增序号函数。
 */
rt_err_t control_sensor_module_init(control_sensor_can_send_fn send_fn,
                                    control_sensor_next_seq_fn next_seq_fn);

/* 解析旧版 EMG CAN 帧 CONTROL_CAN_ID_EMG_REPORT，并更新 control_emg_report_t 缓存。 */
void control_sensor_update_emg_report(const struct rt_can_msg *msg);
/* 解析旧版心率 CAN 帧 CONTROL_CAN_ID_HEART_REPORT，并更新 control_heart_report_t 缓存。 */
void control_sensor_update_heart_report(const struct rt_can_msg *msg);
/* 解析 F103 0x7C2 传感帧，并同时更新 F103 综合缓存、EMG 兼容缓存、心率兼容缓存。 */
void control_sensor_update_f103_sensor_report(const struct rt_can_msg *msg);
/* 解析 F103 0x7C3 健康帧，并更新节点状态/错误计数/队列状态。 */
void control_sensor_update_f103_health_report(const struct rt_can_msg *msg);
/* 解析 F103 0x7C1 ACK 帧，并记录最近一次命令 ACK。 */
void control_sensor_update_f103_ack_report(const struct rt_can_msg *msg);

#ifdef __cplusplus
}
#endif

#endif /* __CONTROL_SENSOR_H__ */
