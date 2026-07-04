(function () {
  const PAGE_BY_LABEL = {
    "首页": "home.html",
    "训练": "training-library.html",
    "肌电": "emg.html",
    "设备": "device.html",
    "我的": "profile.html"
  };

  const DEFAULT_API_BASE = "http://106.55.62.122:8011";
  const API_BASE_KEY = "rehabArmMobileApiBase";
  const TOKEN_KEY = "rehabArmAccessToken";
  const STORE_KEY = "rehabArmMobileState";
  const DEFAULT_STATE = {
    profile: null,
    devices: [],
    plans: [],
    catalog: null,
    bootstrap: null,
    workflow: null,
    publicConfig: null,
    latestEmg: null,
    nativeSpp: null,
    lastSync: null,
    lastLegacySppSend: null,
    online: false,
    authenticated: false,
    statusText: "正在连接后端..."
  };

  function readJson(key, fallback) {
    try {
      return Object.assign({}, fallback, JSON.parse(localStorage.getItem(key) || "{}"));
    } catch (_error) {
      return Object.assign({}, fallback);
    }
  }

  function readState() {
    return readJson(STORE_KEY, DEFAULT_STATE);
  }

  function writeState(nextState) {
    localStorage.setItem(STORE_KEY, JSON.stringify(nextState));
  }

  function apiBase() {
    const stored = localStorage.getItem(API_BASE_KEY);
    if (stored) return stored;
    localStorage.setItem(API_BASE_KEY, DEFAULT_API_BASE);
    return DEFAULT_API_BASE;
  }

  function token() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function nativeSppPlugin() {
    return window.Capacitor && window.Capacitor.Plugins ? window.Capacitor.Plugins.RehabArmSpp : null;
  }

  async function readNativeSppStatus() {
    const plugin = nativeSppPlugin();
    if (!plugin || !plugin.status) {
      return { available: false, connected: false, permission: "web_unavailable", controlBoundary: "pwa_no_bluetooth_classic_spp" };
    }
    try {
      return await plugin.status();
    } catch (error) {
      return { available: true, connected: false, permission: "error", error: error.message || String(error), controlBoundary: "android_spp_transport_only_m33_final_authority" };
    }
  }

  function nativeDeviceSelector(device) {
    if (!device) return {};
    const id = device.m33_device_id || "";
    const looksLikeMac = /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(id);
    return {
      address: looksLikeMac ? id : "",
      name: device.ble_name || (looksLikeMac ? "" : id)
    };
  }

  async function api(path, options) {
    const headers = { "Content-Type": "application/json", ...(options && options.headers ? options.headers : {}) };
    const accessToken = token();
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    const response = await fetch(apiBase().replace(/\/$/, "") + path, { ...options, headers });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = body && body.error ? body.error.message || body.error.code : "API request failed";
      throw new Error(message);
    }
    return body.data;
  }

  function toast(message, tone) {
    let node = document.querySelector("[data-arm-toast]");
    if (!node) {
      node = document.createElement("div");
      node.setAttribute("data-arm-toast", "true");
      node.style.cssText = [
        "position:fixed",
        "left:16px",
        "right:16px",
        "bottom:92px",
        "z-index:9999",
        "max-width:398px",
        "margin:0 auto",
        "padding:12px 14px",
        "border-radius:8px",
        "font:600 13px/1.45 Inter,system-ui,sans-serif",
        "box-shadow:0 10px 28px rgba(15,23,42,.18)"
      ].join(";");
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.style.background = tone === "warn" ? "#fff7ed" : "#ecfdf5";
    node.style.color = tone === "warn" ? "#9a3412" : "#047857";
    node.style.border = tone === "warn" ? "1px solid #fed7aa" : "1px solid #a7f3d0";
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => node.remove(), 3200);
  }

  function pageName() {
    return location.pathname.split("/").pop() || "home.html";
  }

  function navigate(target) {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ type: "rehab-arm-mobile:navigate", target }, "*");
      return;
    }
    location.href = target;
  }

  function bindNav() {
    document.querySelectorAll("nav a, nav button, nav div").forEach((item) => {
      const label = (item.textContent || "").trim();
      const target = Object.keys(PAGE_BY_LABEL).find((key) => label.includes(key));
      if (!target) return;
      item.setAttribute("role", "button");
      item.setAttribute("tabindex", "0");
      item.addEventListener("click", (event) => {
        event.preventDefault();
        navigate(PAGE_BY_LABEL[target]);
      });
    });
  }

  function statusTone(state) {
    if (!state.online) return { bg: "#fff7ed", border: "#fed7aa", color: "#9a3412" };
    if (!state.authenticated) return { bg: "#eff6ff", border: "#bfdbfe", color: "#1d4ed8" };
    return { bg: "#ecfdf5", border: "#a7f3d0", color: "#047857" };
  }

  function upsertStatusStrip(state) {
    let strip = document.querySelector("[data-arm-status]");
    if (!strip) {
      strip = document.createElement("div");
      strip.setAttribute("data-arm-status", "true");
      strip.style.cssText = [
        "position:sticky",
        "top:0",
        "z-index:30",
        "margin:0 auto",
        "max-width:780px",
        "padding:8px 16px",
        "font:600 12px/1.4 Inter,system-ui,sans-serif",
        "backdrop-filter:blur(14px)"
      ].join(";");
      document.body.prepend(strip);
    }
    const tone = statusTone(state);
    strip.style.background = tone.bg;
    strip.style.borderBottom = `1px solid ${tone.border}`;
    strip.style.color = tone.color;
    strip.textContent = state.statusText || "灵动康复 ArmControl";
  }

  function createLoginPanel(state) {
    if (token() || document.querySelector("[data-arm-login]")) return;
    const panel = document.createElement("form");
    panel.setAttribute("data-arm-login", "true");
    panel.style.cssText = [
      "position:fixed",
      "left:14px",
      "right:14px",
      "bottom:16px",
      "z-index:9998",
      "max-width:398px",
      "margin:0 auto",
      "padding:12px",
      "background:#ffffff",
      "border:1px solid #cbd5e1",
      "border-radius:8px",
      "box-shadow:0 16px 40px rgba(15,23,42,.18)",
      "font:500 12px/1.35 Inter,system-ui,sans-serif"
    ].join(";");
    panel.innerHTML = [
      '<div style="font-weight:800;color:#0f172a;margin-bottom:8px">登录后查看真实后端数据</div>',
      '<input name="email" placeholder="账号/邮箱" autocomplete="username" style="box-sizing:border-box;width:100%;height:38px;margin-bottom:8px;border:1px solid #cbd5e1;border-radius:6px;padding:0 10px" />',
      '<input name="password" placeholder="密码" type="password" autocomplete="current-password" style="box-sizing:border-box;width:100%;height:38px;margin-bottom:8px;border:1px solid #cbd5e1;border-radius:6px;padding:0 10px" />',
      '<button type="submit" style="width:100%;height:38px;border:0;border-radius:6px;background:#0f766e;color:white;font-weight:800">连接后端</button>',
      `<div style="margin-top:8px;color:#64748b">API: ${apiBase()}；当前${state.online ? "已连 public-config" : "等待连接"}。</div>`
    ].join("");
    panel.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(panel);
      try {
        const session = await api("/api/auth/session", {
          method: "POST",
          body: JSON.stringify({ email: String(form.get("email") || ""), password: String(form.get("password") || "") })
        });
        if (!session || !session.access_token) throw new Error("登录响应缺少 access_token");
        localStorage.setItem(TOKEN_KEY, session.access_token);
        panel.remove();
        toast("已登录，正在读取 /me 闭环状态");
        await refreshFromBackend();
      } catch (error) {
        toast(error.message || "登录失败", "warn");
      }
    });
    document.body.appendChild(panel);
  }

  function replaceFirst(candidates, value) {
    if (value === undefined || value === null || value === "") return;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const text = node.nodeValue || "";
      const hit = candidates.find((candidate) => text.includes(candidate));
      if (hit) {
        node.nodeValue = text.replace(hit, String(value));
        return;
      }
    }
  }

  function replaceAll(candidates, value) {
    if (value === undefined || value === null || value === "") return;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      let text = node.nodeValue || "";
      candidates.forEach((candidate) => {
        text = text.split(candidate).join(String(value));
      });
      node.nodeValue = text;
    });
  }

  function removeBackendEvidencePanel() {
    document.querySelector("[data-arm-evidence]")?.remove();
  }

  function removeWorkflowPanel() {
    document.querySelector("[data-arm-workflow]")?.remove();
  }

  function removeTimelinePanel() {
    document.querySelector("[data-arm-timeline]")?.remove();
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .split("&").join("&amp;")
      .split("<").join("&lt;")
      .split(">").join("&gt;")
      .split('"').join("&quot;")
      .split("'").join("&#39;");
  }

  function actionLabel(action) {
    if (!action) return "等待后端下一步";
    return action.label || action.title || action.code || "等待后端下一步";
  }

  function canExecuteWorkflowAction(action) {
    const code = action && action.code;
    return [
      "READY_TO_START",
      "FINISH_SESSION",
      "RECORD_PROGRESS",
      "RESUME_SESSION",
      "CANCEL_SESSION",
      "RECORD_SAFETY_REVIEW",
      "GENERATE_TRAINING_REPORT",
      "RECORD_REPORT_REVIEW",
      "DRAFT_NEXT_PLAN_FROM_REPORT",
      "ACCEPT_AI_DRAFT",
      "REPLAY_OFFLINE_EVIDENCE",
      "REVIEW_FAILED_OFFLINE_ITEM",
      "SYNC_ACCEPTED_PLAN_TO_M33"
    ].includes(code);
  }

  function actionPayload(action) {
    const hint = (action && action.payload_hint) || {};
    if (action && action.code === "FINISH_SESSION") {
      return { completion_rate: 1, pain_after: null, user_note: "手机端完成训练记录" };
    }
    if (action && action.code === "RECORD_REPORT_REVIEW") {
      return {
        reviewer_role: "patient",
        review_status: "reviewed",
        reviewer_note: "手机端已复盘训练报告",
        next_step: "continue_current_plan",
        request_new_plan: false
      };
    }
    return hint;
  }

  function insertWorkflowPanel(state) {
    removeWorkflowPanel();
    const workflow = state.workflow || {};
    const phase = workflow.phase || {};
    const nextAction = workflow.next_action || {};
    const actions = (workflow.action_queue || []).slice(0, 4);
    const blockers = (workflow.blockers || []).slice(0, 3);
    const forbidden = (workflow.forbidden_actions || []).slice(0, 4);
    const panel = document.createElement("section");
    panel.setAttribute("data-arm-workflow", "true");
    panel.style.cssText = [
      "margin:10px 16px 12px",
      "padding:14px",
      "border:1px solid #bfdbfe",
      "border-radius:8px",
      "background:#eff6ff",
      "color:#0f172a",
      "font:600 12px/1.5 Inter,system-ui,sans-serif"
    ].join(";");
    panel.innerHTML = [
      '<div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start;margin-bottom:8px">',
      '<div style="font-size:13px;font-weight:900;color:#1d4ed8">康复工作流</div>',
      `<div style="font:700 11px/1.2 JetBrains Mono,monospace;color:#334155">${phase.status || "waiting"}</div>`,
      "</div>",
      `<div style="font-size:16px;font-weight:900;color:#0f172a">${phase.title || "等待后端工作流"}</div>`,
      `<div style="margin-top:4px;color:#334155">${phase.description || "登录后读取 /me/workflow，页面不再使用本地 demo 成功状态。"}</div>`,
      `<div style="margin-top:10px;padding:10px;border-radius:8px;background:#ffffff;border:1px solid #dbeafe"><span style="color:#1d4ed8">下一步：</span>${actionLabel(nextAction)}</div>`,
      canExecuteWorkflowAction(nextAction)
        ? `<button type="button" data-arm-workflow-action="${nextAction.code}" style="width:100%;margin-top:10px;padding:10px 12px;border:0;border-radius:8px;background:#1d4ed8;color:#fff;font:900 13px/1.2 Inter,system-ui,sans-serif">执行后端下一步</button>`
        : '<div style="margin-top:10px;color:#475569">当前下一步需要先进入对应页面补资料，或等待硬件协议/M33 决策。</div>',
      actions.length
        ? `<div style="margin-top:10px;color:#334155">动作队列：${actions.map(actionLabel).join(" / ")}</div>`
        : '<div style="margin-top:10px;color:#334155">动作队列：等待读取后端动作</div>',
      blockers.length
        ? `<div style="margin-top:8px;color:#92400e">阻塞：${blockers.map((item) => item.title || item.code).join(" / ")}</div>`
        : '<div style="margin-top:8px;color:#047857">阻塞：当前无后端阻塞记录</div>',
      forbidden.length
        ? `<div style="margin-top:8px;font:700 11px/1.35 JetBrains Mono,monospace;color:#991b1b">禁止：${forbidden.join(" / ")}</div>`
        : "",
      '<div style="margin-top:8px;color:#475569">App 只显示流程证据；真实运动许可仍由 M33 最终裁决。</div>'
    ].join("");
    const anchor = document.querySelector("[data-arm-evidence]") || document.querySelector("[data-arm-status]");
    if (anchor && anchor.nextSibling) {
      anchor.parentNode.insertBefore(panel, anchor.nextSibling);
    } else {
      document.body.prepend(panel);
    }
  }

  function insertTimelinePanel(state) {
    removeTimelinePanel();
    const bootstrap = state.bootstrap || {};
    const items = ((bootstrap.care_timeline || {}).items || []).slice(0, 4);
    const panel = document.createElement("section");
    panel.setAttribute("data-arm-timeline", "true");
    panel.style.cssText = [
      "margin:10px 16px 12px",
      "padding:14px",
      "border:1px solid #bbf7d0",
      "border-radius:8px",
      "background:#f0fdf4",
      "color:#052e16",
      "font:600 12px/1.5 Inter,system-ui,sans-serif"
    ].join(";");
    const rows = items.map((item) => {
      const display = item.display || {};
      const action = item.primary_action || {};
      const tone = display.tone || "neutral";
      const title = display.title || item.title || item.kind || "康复记录";
      const subtitle = display.subtitle || item.status || "";
      const actionText = action.label || action.code || "查看证据";
      return [
        `<div style="padding:10px 0;border-top:1px solid #bbf7d0" data-arm-timeline-item="${escapeHtml(item.kind || "")}">`,
        `<div style="display:flex;justify-content:space-between;gap:8px"><span style="font-weight:900;color:#166534">${escapeHtml(title)}</span><span style="font:800 10px/1.2 JetBrains Mono,monospace;color:#166534">${escapeHtml(tone)}</span></div>`,
        `<div style="margin-top:3px;color:#166534">${escapeHtml(subtitle)}</div>`,
        `<div style="margin-top:5px;color:#475569">动作：${escapeHtml(actionText)}</div>`,
        "</div>"
      ].join("");
    });
    panel.innerHTML = [
      '<div style="font-size:13px;font-weight:900;color:#166534;margin-bottom:6px">真实康复历史</div>',
      items.length ? rows.join("") : '<div style="color:#166534">暂无后端训练/报告/草稿/离线证据记录。</div>',
      '<div style="margin-top:8px;color:#166534">历史只来自后端持久化证据，不使用本地 demo 进度。</div>'
    ].join("");
    const anchor = document.querySelector("[data-arm-workflow]") || document.querySelector("[data-arm-evidence]") || document.querySelector("[data-arm-status]");
    if (anchor && anchor.nextSibling) {
      anchor.parentNode.insertBefore(panel, anchor.nextSibling);
    } else {
      document.body.prepend(panel);
    }
  }

  function insertBackendEvidencePanel(state) {
    removeBackendEvidencePanel();
    const bootstrap = state.bootstrap || {};
    const readiness = bootstrap.mobile_readiness_guide || {};
    const blockers = readiness.blockers || [];
    const primaryBlocker = blockers[0] || {};
    const devices = bootstrap.devices || [];
    const plans = bootstrap.training_plans || [];
    const panel = document.createElement("section");
    panel.setAttribute("data-arm-evidence", "true");
    panel.style.cssText = [
      "margin:10px 16px 12px",
      "padding:12px",
      "border:1px solid #f59e0b",
      "border-radius:8px",
      "background:#fffbeb",
      "color:#78350f",
      "font:600 12px/1.5 Inter,system-ui,sans-serif"
    ].join(";");
    panel.innerHTML = [
      '<div style="font-size:13px;font-weight:900;color:#92400e;margin-bottom:6px">真实后端状态</div>',
      `<div>账号：${state.authenticated ? "已登录" : "未登录"}；设备：${devices.length}；计划：${plans.length}</div>`,
      `<div>门禁：${readiness.status || "等待读取"}</div>`,
      `<div>蓝牙桥：${(state.nativeSpp && state.nativeSpp.connected) ? "SPP 已连接" : (state.nativeSpp && state.nativeSpp.available) ? "SPP 待连接/待权限" : "仅 Web，不支持 SPP"}</div>`,
      `<div>阻塞：${primaryBlocker.title || "等待完成康复档案、设备和硬件协议"}</div>`,
      '<div style="margin-top:6px;color:#9a3412">页面内训练/M33/AI 文案均为后端证据展示，不代表运动许可。</div>'
    ].join("");
    const anchor = document.querySelector("[data-arm-status]");
    if (anchor && anchor.nextSibling) {
      anchor.parentNode.insertBefore(panel, anchor.nextSibling);
    } else {
      document.body.prepend(panel);
    }
  }

  function annotatePage(state) {
    const current = pageName();
    const bootstrap = state.bootstrap || {};
    const profile = bootstrap.profile || state.profile;
    const devices = bootstrap.devices || state.devices || [];
    const plans = bootstrap.training_plans || state.plans || [];
    const catalog = state.catalog || {};
    const readiness = bootstrap.mobile_readiness_guide || {};
    const isBlocked = readiness.status === "blocked";
    if (state.authenticated) {
      insertBackendEvidencePanel(state);
      insertWorkflowPanel(state);
      insertTimelinePanel(state);
    } else {
      removeBackendEvidencePanel();
      removeWorkflowPanel();
      removeTimelinePanel();
    }
    const workflow = state.workflow || {};
    const phase = workflow.phase || {};
    const nextAction = workflow.next_action || {};
    if (isBlocked) {
      replaceAll(["M33 ACTIVE", "状态：M33 已允许执行", "M33 已允许执行"], "M33 待协议/待审核");
      replaceAll(["急停已就绪"], "急停状态待硬件上报");
      replaceAll(["已连接"], devices.length ? "已绑定" : "待绑定");
      replaceAll(["激活"], state.latestEmg ? "有记录" : "等待记录");
      replaceAll(["安全"], "等待协议");
      replaceAll(["已同步"], "已连接后端");
      replaceAll(["康复阶段：亚急性期"], profile && profile.rehab_stage ? `康复阶段：${profile.rehab_stage}` : "康复阶段：待完善档案");
      replaceAll(["患侧：左侧"], profile && profile.affected_side ? `患侧：${profile.affected_side}` : "患侧：待完善档案");
      replaceAll(["今日目标：30 分钟"], plans[0] ? `今日目标：${plans[0].duration_sec || 0} 秒` : "今日目标：待创建训练计划");
      replaceAll(["完成度\n95%", "95%"], "完成度\n无真实报告");
      replaceAll(["肌肉疲劳\n低", "低"], "等待肌电");
      replaceAll(["动作稳定性极佳，建议维持当前强度"], "等待真实训练报告和治疗师复核");
      replaceAll(["最近训练结果快照"], "后端训练证据快照");
      replaceAll(["开始训练"], nextAction.code === "READY_TO_START" ? "开始训练记录" : "查看下一步");
    }
    replaceAll(["执行中 - 由 M33 监控"], phase.title ? `工作流状态：${phase.title}` : "工作流状态：等待读取");
    replaceAll(["AI 建议"], "AI/报告建议待复核");
    replaceAll(["训练总结"], "训练报告闭环");
    if (current === "profile.html" && profile) {
      replaceFirst(["Sarah Chen", "康复用户"], profile.name || "康复用户");
      replaceFirst(["RoboRehab Controller"], "灵动康复 ArmControl");
    }
    if (current === "device.html") {
      const device = devices[0];
      replaceFirst(["M33-Cortex", "ArmControl"], device ? device.ble_name || device.m33_device_id : "等待绑定 M33");
      replaceFirst(["已连接"], device && device.trust_status === "trusted" ? "已绑定" : "待绑定");
    }
    if (current === "training-library.html" || current === "ai-plan.html") {
      const movement = catalog.training_movements && catalog.training_movements[0];
      replaceFirst(["屈肘训练"], movement ? movement.label : "目录加载中");
      replaceFirst(["AI 规划"], readiness.status === "blocked" ? "后端门禁待完成" : "AI 规划");
      replaceAll(["智能方案生成"], "AI 草稿待审核");
      replaceAll(["生成方案"], "生成 AI 草稿");
      replaceAll(["开始计划"], "查看计划工作流");
    }
    if (current === "emg.html") {
      replaceFirst(["肱二头肌", "biceps"], state.latestEmg ? state.latestEmg.muscle_name : "等待肌电记录");
    }
    if (current === "home.html") {
      replaceFirst(["今日训练"], readiness.status === "blocked" ? "真实后端已连接：仍有门禁" : "今日训练");
    }
    if (plans[0]) {
      replaceFirst(["3组", "3 组"], `${plans[0].sets || 0}组`);
      replaceFirst(["8次", "8 次"], `${plans[0].reps || 0}次`);
    }
  }

  async function refreshFromBackend() {
    const state = readState();
    try {
      const publicConfig = await api("/api/rehab-arm/app/v1/public-config");
      const catalog = await api(publicConfig.rehab_app.catalog_endpoint || "/api/rehab-arm/app/v1/catalog");
      if (!token()) {
        const nextState = {
          ...state,
          publicConfig,
          catalog,
          online: true,
          authenticated: false,
          statusText: `已连接后端配置：${publicConfig.app_name}；请登录读取 /me。`
        };
        writeState(nextState);
        upsertStatusStrip(nextState);
        createLoginPanel(nextState);
        annotatePage(nextState);
        return nextState;
      }
      const bootstrap = await api("/api/rehab-arm/app/v1/me");
      const workflowEndpoint = (publicConfig.rehab_app && publicConfig.rehab_app.workflow_endpoint) || "/api/rehab-arm/app/v1/me/workflow";
      const workflow = await api(workflowEndpoint);
      const latestEmg = await api("/api/rehab-arm/app/v1/emg/latest").catch(() => null);
      const nativeSpp = await readNativeSppStatus();
      const nextState = {
        ...state,
        publicConfig,
        catalog,
        bootstrap,
        workflow,
        nativeSpp,
        profile: bootstrap.profile,
        devices: bootstrap.devices || [],
        plans: bootstrap.training_plans || [],
        latestEmg,
        online: true,
        authenticated: true,
        statusText: `已连接后端：${workflow.phase ? workflow.phase.title : bootstrap.mobile_readiness_guide ? bootstrap.mobile_readiness_guide.summary : "读取成功"}`
      };
      writeState(nextState);
      upsertStatusStrip(nextState);
      annotatePage(nextState);
      return nextState;
    } catch (error) {
      const nextState = {
        ...state,
        online: false,
        authenticated: Boolean(token()),
        statusText: `后端连接失败：${error.message || "请检查网络"}`
      };
      writeState(nextState);
      upsertStatusStrip(nextState);
      createLoginPanel(nextState);
      annotatePage(nextState);
      return nextState;
    }
  }

  async function executeWorkflowAction(actionCode) {
    const state = readState();
    const workflow = state.workflow || {};
    const action = [workflow.next_action, ...(workflow.action_queue || [])].find((item) => item && item.code === actionCode);
    if (!token() || !action) {
      toast("请先登录并刷新后端工作流。", "warn");
      return;
    }
    const result = await api("/api/rehab-arm/app/v1/me/workflow/actions", {
      method: "POST",
      body: JSON.stringify({ action_code: actionCode, payload: actionPayload(action) })
    });
    writeState({ ...state, workflow: result.workflow, lastWorkflowAction: result });
    toast("后端工作流已推进；真实运动许可仍由 M33 裁决。");
    await refreshFromBackend();
  }

  async function connectNativeSpp(device, profile) {
    const plugin = nativeSppPlugin();
    if (!plugin || !plugin.connect) {
      throw new Error("当前运行环境不是 Android 原生包，不能打开 Bluetooth Classic SPP。");
    }
    if (plugin.requestPermissions) {
      await plugin.requestPermissions().catch(() => null);
    }
    const selector = nativeDeviceSelector(device);
    return plugin.connect({
      ...selector,
      uuid: (profile && profile.standard_uuid) || "00001101-0000-1000-8000-00805F9B34FB"
    });
  }

  async function sendLegacyFrameToNative(device, frame, profile) {
    if (!frame || !frame.sendable || !frame.wire_text) {
      return { sent: false, reason: "legacy_frame_not_sendable" };
    }
    const plugin = nativeSppPlugin();
    if (!plugin || !plugin.sendLegacyFrame) {
      return { sent: false, reason: "android_native_spp_plugin_unavailable" };
    }
    let status = await readNativeSppStatus();
    if (!status.connected) {
      status = await connectNativeSpp(device, profile);
    }
    return plugin.sendLegacyFrame({
      sendable: true,
      wireText: frame.wire_text,
      messageType: frame.json && frame.json.type,
      controlBoundary: "android_spp_transport_only_m33_final_authority"
    });
  }

  async function handlePrimaryAction(label) {
    const state = readState();
    if (label.includes("同步")) {
      const plan = state.plans && state.plans[0];
      const device = state.devices && state.devices[0];
      if (!token() || !plan || !device) {
        toast("请先登录并完成设备/计划；App 不使用本地 demo 同步。", "warn");
        return;
      }
      const sync = await api(`/api/rehab-arm/app/v1/training-plans/${plan.id}/sync-to-device`, {
        method: "POST",
        body: JSON.stringify({ device_id: device.id })
      });
      const bleMessage = await api(`/api/rehab-arm/app/v1/devices/${device.id}/ble/messages`, {
        method: "POST",
        body: JSON.stringify({ message_type: "training_plan_push", plan_id: plan.id })
      });
      const profile = (state.publicConfig && state.publicConfig.m33_legacy_spp_profile) || (state.catalog && state.catalog.m33_legacy_spp_profile);
      const frame = bleMessage && bleMessage.payload ? bleMessage.payload.legacy_transport_frame : null;
      const sendResult = await sendLegacyFrameToNative(device, frame, profile).catch((error) => ({ sent: false, reason: error.message || String(error) }));
      writeState({ ...state, lastSync: sync, lastBleMessage: bleMessage, lastLegacySppSend: sendResult, nativeSpp: await readNativeSppStatus() });
      toast(sendResult.sent ? "训练计划已通过旧 SPP 帧写入手机蓝牙桥；M33 仍需确认。" : `已创建后端蓝牙帧，但手机未发送：${sendResult.reason}`, sendResult.sent ? undefined : "warn");
      return;
    }
    if (label.includes("开始训练") || label.includes("play_arrow")) {
      navigate("training-session.html");
      toast("进入训练记录页；真实运动仍由 M33 最终决定。", "warn");
      return;
    }
    if (label.includes("退出") || label.includes("注销")) {
      localStorage.removeItem(TOKEN_KEY);
      toast("已退出登录");
      await refreshFromBackend();
      return;
    }
    if (label.includes("急停") || label.includes("停止") || label.includes("block")) {
      toast("App 只能记录停止请求，不能释放急停或绕过 M33。", "warn");
      return;
    }
    if (label.includes("校准")) {
      toast("校准结果会作为证据记录，不直接驱动电机。");
    }
  }

  function bindActions() {
    document.addEventListener("click", (event) => {
      const button = event.target && event.target.closest ? event.target.closest("[data-arm-workflow-action]") : null;
      if (!button) return;
      event.preventDefault();
      executeWorkflowAction(button.getAttribute("data-arm-workflow-action")).catch((error) => toast(error.message, "warn"));
    });
    document.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        const label = (button.textContent || button.innerText || "").trim();
        handlePrimaryAction(label).catch((error) => toast(error.message, "warn"));
      });
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    bindNav();
    bindActions();
    upsertStatusStrip(readState());
    await refreshFromBackend();
  });
})();
