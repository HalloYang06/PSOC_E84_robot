# AI协作平台 SuperTokens 接入方案

## 目标

把当前“自制注册/登录”逐步迁移到正式的开源认证体系，优先落地下面 4 步：

1. 邮箱密码注册
2. 邮箱验证
3. 登录建立会话
4. 登录后进入“创建项目”首页

注册时不分配角色。角色和项目分工仍然在项目协作阶段决定。

## 当前代码状态

后端已经补入可选的 SuperTokens 运行时骨架：

- `apps/api/app/supertokens_runtime.py`
- `apps/api/app/settings.py`
- `apps/api/requirements.txt`
- `.env.example`

默认仍然是：

- `AUTH_PROVIDER=legacy`

只有在下面两个条件同时满足时才会启用 SuperTokens：

1. `AUTH_PROVIDER=supertokens`
2. `SUPERTOKENS_CONNECTION_URI` 非空

## 默认接入路径

为了不和当前 `/api/auth/*` 冲突，SuperTokens 先走独立路径：

- API 基础路径：`/api/st-auth`
- 前端基础路径：`/auth`

这样我们可以先把新认证跑通，再平滑替换旧登录页。

## 推荐本地配置

```env
AUTH_PROVIDER=supertokens
SUPERTOKENS_CONNECTION_URI=你的 SuperTokens Core 地址
SUPERTOKENS_API_DOMAIN=http://127.0.0.1:8000
SUPERTOKENS_WEBSITE_DOMAIN=http://lvh.me:3001
SUPERTOKENS_API_BASE_PATH=/api/st-auth
SUPERTOKENS_WEBSITE_BASE_PATH=/auth
SUPERTOKENS_EMAIL_VERIFICATION_MODE=REQUIRED
```

如果要真的发验证邮件，再补 SMTP：

```env
SUPERTOKENS_SMTP_HOST=smtp.example.com
SUPERTOKENS_SMTP_PORT=587
SUPERTOKENS_SMTP_USERNAME=your-user
SUPERTOKENS_SMTP_PASSWORD=your-password
SUPERTOKENS_SMTP_FROM_NAME=AI协作平台
SUPERTOKENS_SMTP_FROM_EMAIL=no-reply@example.com
SUPERTOKENS_SMTP_SECURE=false
```

## 下一步建议

1. 在前端新增 `/auth` 页面，接 SuperTokens 的注册/登录/验证 UI。
2. 登录成功后统一跳到 `/projects`。
3. 把当前手写 `/login` 页面逐步下线。
4. 最后再决定是否把 `/api/auth/*` 旧接口整体迁移或保留兼容层。
