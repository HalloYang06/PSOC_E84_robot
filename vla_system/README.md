# VLA System

这是项目中的 VLA 子系统实现，目标不是直接控制机械臂，而是输出结构化决策结果。

## 子模块

- `task_parser_service.py`：把文本解析成任务草稿
- `grounding_service.py`：给目标物体和区域排序
- `phase_service.py`：根据状态和历史判断当前 phase
- `confirm_service.py`：判断是否要追问确认
- `vla_bridge_service.py`：聚合上面四个模块，输出 `ResolvedTask`

## 契约文件

- 输入 schema：`configs/resolve_task_input.schema.json`
- 输出 schema：`configs/resolved_task.schema.json`
- 枚举与别名：`configs/task_schema.yaml`
- 阈值：`configs/thresholds.yaml`

## 离线调试

```bash
python -m vla_system.cli.resolve_task_cli --input vla_system/examples/clear_pick_and_place.json --pretty
```

## 替换为模型时的落点

- `task_parser_service.py` -> 小文本分类器
- `grounding_service.py` -> 候选排序模型
- `phase_service.py` -> 阶段分类模型
- `confirm_service.py` -> 二分类确认模型