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
    publicConfig: null,
    latestEmg: null,
    lastSync: null,
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
    } else {
      removeBackendEvidencePanel();
    }
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
      replaceAll(["开始训练"], "查看训练门禁");
    }
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
      const latestEmg = await api("/api/rehab-arm/app/v1/emg/latest").catch(() => null);
      const nextState = {
        ...state,
        publicConfig,
        catalog,
        bootstrap,
        profile: bootstrap.profile,
        devices: bootstrap.devices || [],
        plans: bootstrap.training_plans || [],
        latestEmg,
        online: true,
        authenticated: true,
        statusText: `已连接后端：${bootstrap.mobile_readiness_guide ? bootstrap.mobile_readiness_guide.summary : "读取成功"}`
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
      writeState({ ...state, lastSync: sync });
      toast("训练计划已提交给 M33 审核，不是运动许可。");
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
