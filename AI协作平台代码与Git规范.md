# AI 协作平台代码与 Git 规范

版本：v0.1  
用途：统一代码风格、分支、提交、PR、审查和回滚规则

---

## 1. 分支规范

固定分支：

```text
main       稳定分支，只接受确认后的合并
develop    日常集成分支
```

任务分支：

```text
ai/<身份>/<任务号>-<简短描述>
human/<姓名>/<任务号>-<简短描述>
hotfix/<问题>
release/<版本号>
```

示例：

```text
ai/fe-game/TASK-012-dashboard-base
ai/be-task/TASK-021-task-api
ai/runner/TASK-030-heartbeat
```

规则：

1. AI 不允许直接提交 `main`。
2. 每个任务必须单独分支。
3. 一个分支只解决一个清晰任务。
4. 跨模块修改必须在任务说明中写明。
5. 合并必须经过测试和审查。

---

## 2. Commit 规范

格式：

```text
<type>(<scope>): <summary>
```

type：

```text
feat      新功能
fix       修复
docs      文档
style     格式和样式，不影响逻辑
refactor  重构
test      测试
chore     工程配置
security  安全相关
infra     部署和基础设施
```

示例：

```text
feat(tasks): add task status transition api
fix(runner): handle heartbeat timeout
docs(rules): add AI identity claim rules
security(secrets): prevent token from frontend response
```

---

## 3. 代码风格

通用规则：

1. 优先清晰，不追求炫技。
2. 函数只做一件事。
3. 变量名表达业务含义。
4. 不写无意义注释。
5. 复杂逻辑必须写简短说明。
6. 不复制大段重复代码。
7. 不引入无必要依赖。
8. 错误处理必须明确。
9. 日志不能包含 token、密码、私钥。
10. 所有高风险操作必须走权限检查。

---

## 4. TypeScript/前端规则

1. 使用 TypeScript。
2. 禁止 `any` 泛滥，确实需要时写原因。
3. API 类型应从共享类型或 OpenAPI 生成。
4. 组件 props 必须有明确类型。
5. 页面状态要区分 loading、empty、error、ready。
6. 用户操作必须有反馈。
7. 危险操作必须二次确认。

---

## 5. Python/后端规则

1. 使用类型标注。
2. API 入参和出参使用 Pydantic model。
3. 数据库访问放在 repository 或 service 层。
4. 业务逻辑不要写在路由函数里。
5. 错误响应格式统一。
6. 数据库 migration 必须可回滚或说明不可回滚原因。
7. 后端不得返回明文 token。

---

## 6. PR/MR 规范

每个 PR/MR 必须包含：

```text
任务编号:
修改摘要:
修改文件:
测试命令:
测试结果:
风险说明:
是否涉及权限:
是否涉及密钥:
是否涉及硬件:
是否需要人类确认:
回滚方式:
```

禁止合并：

1. 无任务编号。
2. 无测试说明。
3. 涉及权限但没有安全审查。
4. 涉及硬件但没有人工确认点。
5. 包含明文 token。
6. 大范围重构但没有架构确认。

---

## 7. 回滚规范

回滚前必须记录：

```text
回滚原因
影响范围
目标 commit/tag
是否影响数据库
是否影响部署配置
是否需要通知其他 AI
```

回滚后必须创建复盘任务。

