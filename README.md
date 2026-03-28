# VLA MVP

这个仓库现在已经包含一套可运行的规则版 VLA 子系统，职责边界固定为：

- VLA 负责任务理解、grounding、阶段判断、不确定性确认。
- ROS / MoveIt / 控制器负责规划、控制、安全和执行。

## 快速运行

运行内置示例：

```bash
python main.py
```

用 JSON 请求文件走离线桥接：

```bash
python -m vla_system.cli.resolve_task_cli --input vla_system/examples/clear_pick_and_place.json --pretty
```

运行测试：

```bash
python -m unittest discover -s vla_system/tests -p "test_*.py"
```

## 当前交付内容

- `vla_system/services/`：规则版四模块和统一 bridge
- `vla_system/utils/json_schema.py`：输入输出数据结构
- `vla_system/utils/validators.py`：协议校验
- `vla_system/configs/resolve_task_input.schema.json`：输入 contract
- `vla_system/configs/resolved_task.schema.json`：输出 contract
- `vla_system/examples/`：标准示例请求
- `vla_system/ros_bridge/`：ROS topic/msg/srv 模板

## 示例场景

- `vla_system/examples/clear_pick_and_place.json`：明确 pick-and-place
- `vla_system/examples/ambiguous_retrieve.json`：歧义取物，需要确认
- `vla_system/examples/handover_left.json`：相对方位 handover

## ROS 对接边界

建议保持这三个接口不变：

- 输入场景：`/scene/objects`、`/scene/regions`、`/scene/relations`
- 输入任务：`/speech/text`
- 输出结果：`/task/resolved`

`/task/resolved` 的字段定义见 `vla_system/ros_bridge/msg/ResolvedTask.msg`，离线 JSON 版定义见 `vla_system/configs/resolved_task.schema.json`。

## 下一步建议

- 用你们真实感知输出替换示例 JSON。
- 先接通 ROS2 topic，再做 10 到 20 个固定任务回归。
- 在 `grounding_service.py` 和 `confirm_service.py` 的位置逐步替换成小模型。