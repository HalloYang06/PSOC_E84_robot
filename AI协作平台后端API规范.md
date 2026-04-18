# AI 协作平台后端 API 规范

版本：v0.1  
用途：统一后端 API 设计、错误格式、权限检查和数据返回规则

---

## 1. API 设计原则

1. REST API 优先。
2. 路径使用复数名词。
3. 请求和响应使用 JSON。
4. 所有写操作必须有权限检查。
5. 所有关键操作写入审计日志。
6. 后端不返回明文 token。
7. 错误格式统一。
8. 分页、筛选、排序规则统一。

---

## 2. 路径规范

示例：

```text
GET    /api/projects
POST   /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}

GET    /api/tasks
POST   /api/tasks
GET    /api/tasks/{task_id}
PATCH  /api/tasks/{task_id}
POST   /api/tasks/{task_id}/run
POST   /api/tasks/{task_id}/cancel
```

动作类接口使用动词作为子路径：

```text
POST /api/tasks/{task_id}/create-handoff
POST /api/tasks/{task_id}/approve
POST /api/projects/{project_id}/sync-github
```

---

## 3. 响应格式

成功：

```json
{
  "data": {},
  "meta": {
    "request_id": "req_xxx"
  }
}
```

列表：

```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100
  },
  "meta": {
    "request_id": "req_xxx"
  }
}
```

错误：

```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "没有权限执行该操作",
    "details": {}
  },
  "meta": {
    "request_id": "req_xxx"
  }
}
```

---

## 4. 错误码

```text
VALIDATION_ERROR
UNAUTHORIZED
PERMISSION_DENIED
NOT_FOUND
CONFLICT
RATE_LIMITED
TOKEN_BUDGET_EXCEEDED
CONTEXT_TOO_LARGE
HUMAN_APPROVAL_REQUIRED
HARDWARE_OPERATION_BLOCKED
RUNNER_OFFLINE
AGENT_FAILED
GIT_OPERATION_FAILED
INTERNAL_ERROR
```

---

## 5. 权限检查

每个写接口必须检查：

```text
用户角色
项目权限
AI 权限等级
目录权限
任务状态
是否需要人工确认
是否涉及硬件
```

涉及以下操作必须额外审计：

```text
修改权限
修改密钥
创建/删除 token
合并分支
回滚版本
触发 Runner 执行
访问硬件
烧录固件
```

---

## 6. 分页和筛选

统一参数：

```text
page
page_size
sort
order
status
project_id
agent_id
created_from
created_to
keyword
```

---

## 7. API 文档要求

新增 API 必须写明：

```text
路径
方法
权限
请求参数
响应字段
错误码
审计日志
是否需要人工确认
测试用例
```

