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
    lastAiDraft: null,
    lastAcceptedAiPlan: null,
    lastAcceptedAiDraftId: "",
    nativeSpp: null,
    lastSync: null,
    lastLegacySppSend: null,
    lastLegacySppInbound: null,
    legacySppLogs: [],
    selectedSppDevice: null,
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

  async function listNativeSppDevices() {
    const plugin = nativeSppPlugin();
    if (!plugin || !plugin.listBondedDevices) {
      throw new Error("当前运行环境不是 Android 原生包，不能读取 Classic SPP 已配对设备。");
    }
    if (plugin.requestPermissions) {
      await plugin.requestPermissions().catch(() => null);
    }
    return plugin.listBondedDevices();
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

  function appendLegacySppLog(direction, detail) {
    const state = readState();
    const logs = Array.isArray(state.legacySppLogs) ? state.legacySppLogs.slice(0, 39) : [];
    logs.unshift({
      at: new Date().toISOString(),
      direction,
      detail: typeof detail === "string" ? detail : JSON.stringify(detail || {})
    });
    const nextState = { ...state, legacySppLogs: logs };
    writeState(nextState);
    renderBluetoothDebugPage(nextState);
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

  function isBridgeNode(node) {
    const parent = node && node.parentElement;
    return Boolean(parent && parent.closest("[data-arm-status], [data-arm-toast], [data-arm-login], [data-arm-workflow], [data-arm-evidence]"));
  }

  function statusTone(state) {
    if (!state.online) return { bg: "#fff7ed", border: "#fed7aa", color: "#9a3412" };
    if (!state.authenticated) return { bg: "#eff6ff", border: "#bfdbfe", color: "#1d4ed8" };
    return { bg: "#ecfdf5", border: "#a7f3d0", color: "#047857" };
  }

  function userNextAction(state) {
    const bootstrap = state.bootstrap || {};
    const workflow = state.workflow || {};
    const guide = bootstrap.daily_action_guide || {};
    const action = workflow.next_action || guide.next_action || {};
    const label = action.label || action.title || "";
    if (label) return label;
    const readiness = bootstrap.mobile_readiness_guide || {};
    if (!state.authenticated) return "登录账号";
    if ((bootstrap.devices || []).length === 0) return "绑定康复设备";
    if ((bootstrap.training_plans || []).length === 0) return "创建训练计划";
    if (readiness.status === "ready") return "可以进入训练前检查";
    return "完成首次设置";
  }

  function userStatusText(state) {
    if (!state.online) return "网络未连接，请检查后端服务";
    if (!state.authenticated) return "请登录后同步康复数据";
    const prefix = (state.devices || []).length ? "已连接后端" : "已连接后端，待绑定设备";
    return `${prefix}｜下一步：${userNextAction(state)}`;
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
    strip.textContent = userStatusText(state);
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
      '<div style="font-weight:800;color:#0f172a;margin-bottom:8px">登录后同步康复数据</div>',
      '<input name="email" placeholder="账号/邮箱" autocomplete="username" style="box-sizing:border-box;width:100%;height:48px;margin-bottom:8px;border:1px solid #cbd5e1;border-radius:6px;padding:0 10px" />',
      '<input name="password" placeholder="密码" type="password" autocomplete="current-password" style="box-sizing:border-box;width:100%;height:48px;margin-bottom:8px;border:1px solid #cbd5e1;border-radius:6px;padding:0 10px" />',
      '<button type="submit" style="width:100%;height:48px;border:0;border-radius:6px;background:#0f766e;color:white;font-weight:800">登录并同步</button>',
      `<div style="margin-top:8px;color:#64748b">训练计划、报告和设备状态会从云端同步。</div>`
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
      if (isBridgeNode(node)) continue;
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
      if (isBridgeNode(node)) return;
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

  function parseEventDate(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function dateKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function startOfWeek(date) {
    const copy = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const day = copy.getDay() || 7;
    copy.setDate(copy.getDate() - day + 1);
    return copy;
  }

  function profileTimelineItems(state) {
    const bootstrap = state.bootstrap || {};
    return (((bootstrap.care_timeline || {}).items) || [])
      .map((item) => ({ ...item, _date: parseEventDate(item.event_at) }))
      .filter((item) => item._date)
      .sort((a, b) => b._date.getTime() - a._date.getTime());
  }

  function timelineKindLabel(kind) {
    return {
      training_plan: "训练计划",
      training_session: "训练记录",
      training_report: "训练报告",
      ai_training_draft: "AI 草稿",
      offline_queue_item: "离线证据"
    }[kind] || "康复证据";
  }

  function timelineTarget(item) {
    const action = item.primary_action || {};
    const code = action.code || "";
    if (code.includes("AI_DRAFT") || item.kind === "ai_training_draft") return "ai-plan.html";
    if (code.includes("REPORT") || item.kind === "training_report") return "report.html";
    if (code.includes("SESSION") || item.kind === "training_session") return "report.html";
    if (code.includes("PLAN") || item.kind === "training_plan") return "training-library.html";
    if (item.kind === "offline_queue_item") return "device.html";
    return "training-library.html";
  }

  function timelineBadge(item) {
    return {
      training_plan: "计",
      training_session: "训",
      training_report: "报",
      ai_training_draft: "AI",
      offline_queue_item: "离"
    }[item.kind] || "证";
  }

  function formatAngleRange(range) {
    if (!range) return "待同步";
    const min = range.min_deg == null ? null : Number(range.min_deg);
    const max = range.max_deg == null ? null : Number(range.max_deg);
    if (Number.isFinite(min) && Number.isFinite(max)) return `${min}-${max}°`;
    if (Number.isFinite(max)) return `${max}°`;
    return "待同步";
  }

  function formatAssistLevel(value) {
    if (value == null || value === "") return "待审核";
    const number = Number(value);
    return Number.isFinite(number) ? `${Math.round(number * 100)}%` : String(value);
  }

  function planStatusLabel(plan) {
    if (!plan) return "待创建";
    if (plan.m33_status === "m33_accepted" || plan.device_sync_status === "accepted") return "M33 已接受";
    if (plan.device_sync_status === "synced" || plan.status === "synced") return "已同步待审核";
    if (plan.status === "draft") return "待同步";
    return plan.status || "待同步";
  }

  function movementLabel(plan, catalog) {
    const movementType = plan && plan.movement_type;
    const movement = ((catalog && catalog.training_movements) || []).find((item) => item.code === movementType || item.id === movementType);
    return movement ? movement.label : "";
  }

  function renderTrainingLibraryPage(state) {
    if (pageName() !== "training-library.html") return;
    const bootstrap = state.bootstrap || {};
    const catalog = state.catalog || {};
    const plans = bootstrap.training_plans || state.plans || [];
    const cards = Array.from(document.querySelectorAll("section"))
      .find((section) => (section.textContent || "").includes("今日计划"))
      ?.querySelectorAll(".glass-panel.rounded-xl");
    if (!cards || !cards.length) return;
    cards.forEach((card, index) => {
      const plan = plans[index];
      const titleNode = card.querySelector("h4");
      const statusNode = card.querySelector("h4 + span");
      const valueNodes = card.querySelectorAll(".grid p.text-body-md");
      const badgeText = card.querySelector(".border-t span.text-data-viz");
      const actionIcon = card.querySelector(".border-t button span");
      const actionButton = card.querySelector(".border-t button");
      if (!plan) {
        if (index === 0) {
          if (titleNode) titleNode.textContent = "还没有训练计划";
          if (statusNode) statusNode.textContent = "待生成";
          if (valueNodes[0]) valueNodes[0].textContent = "待同步";
          if (valueNodes[1]) valueNodes[1].textContent = "待审核";
          if (valueNodes[2]) valueNodes[2].textContent = "暂无真实记录";
          if (badgeText) badgeText.textContent = "去 AI 生成";
          if (actionIcon) actionIcon.textContent = "auto_awesome";
          card.addEventListener("click", () => navigate("ai-plan.html"), { once: true });
        } else {
          if (titleNode) titleNode.textContent = "等待更多计划";
          if (statusNode) statusNode.textContent = "待评估";
          if (valueNodes[0]) valueNodes[0].textContent = "待同步";
          if (valueNodes[1]) valueNodes[1].textContent = "待审核";
          if (valueNodes[2]) valueNodes[2].textContent = "暂无真实记录";
          if (badgeText) badgeText.textContent = "待同步";
          if (actionIcon) actionIcon.textContent = "lock";
        }
        return;
      }
      if (titleNode) titleNode.textContent = plan.title || movementLabel(plan, catalog) || "后端训练计划";
      if (statusNode) statusNode.textContent = planStatusLabel(plan);
      if (valueNodes[0]) valueNodes[0].textContent = formatAngleRange(plan.target_angle_range);
      if (valueNodes[1]) valueNodes[1].textContent = formatAssistLevel(plan.assist_level);
      if (valueNodes[2]) valueNodes[2].textContent = "等待真实训练记录";
      if (badgeText) badgeText.textContent = planStatusLabel(plan);
      if (actionIcon) actionIcon.textContent = planStatusLabel(plan).includes("接受") ? "play_arrow" : "sync";
      if (actionButton) {
        actionButton.setAttribute("aria-label", planStatusLabel(plan).includes("接受") ? "进入训练记录" : "去设备页同步计划");
      }
      card.addEventListener("click", () => navigate(planStatusLabel(plan).includes("接受") ? "training-session.html" : "device.html"), { once: true });
    });
  }

  function timelineDayTitle(dayItems) {
    if (!dayItems.length) return "无康复活动";
    const counts = dayItems.reduce((acc, item) => {
      const label = timelineKindLabel(item.kind);
      acc[label] = (acc[label] || 0) + 1;
      return acc;
    }, {});
    return Object.keys(counts).map((label) => `${label} ${counts[label]} 条`).join(" / ");
  }

  function renderProfileTrainingActivity(state) {
    if (pageName() !== "profile.html") return;
    const grid = document.querySelector("[data-role='profile-calendar-grid']");
    if (!grid) return;
    const monthNode = document.querySelector("[data-role='profile-calendar-month']");
    const countNode = document.querySelector("[data-role='profile-weekly-count']");
    const logNode = document.querySelector("[data-role='profile-log-list']");
    const logButton = document.querySelector("[data-role='profile-view-log']");
    const today = new Date();
    const weekStart = startOfWeek(today);
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 7);
    const items = profileTimelineItems(state);
    const currentWeekItems = items.filter((item) => item._date >= weekStart && item._date < weekEnd);
    const currentWeekSessions = items.filter((item) => item.kind === "training_session" && item._date >= weekStart && item._date < weekEnd);
    const byDay = new Map();
    items.forEach((item) => {
      const key = dateKey(item._date);
      const list = byDay.get(key) || [];
      list.push(item);
      byDay.set(key, list);
    });
    if (monthNode) monthNode.textContent = today.toLocaleDateString("zh-CN", { year: "numeric", month: "long" });
    if (countNode) {
      countNode.textContent = currentWeekItems.length
        ? `${currentWeekItems.length} 条本周康复活动，其中 ${currentWeekSessions.length} 次训练记录`
        : "暂无本周康复活动";
    }
    const days = [];
    const first = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    first.setDate(first.getDate() - 13);
    for (let index = 0; index < 14; index += 1) {
      const day = new Date(first);
      day.setDate(first.getDate() + index);
      days.push(day);
    }
    const headers = ["一", "二", "三", "四", "五", "六", "日"];
    const headerHtml = headers.map((label) => `<div class="text-center text-data-viz font-data-viz text-outline mb-2">${label}</div>`).join("");
    const dayHtml = days.map((day) => {
      const key = dateKey(day);
      const dayItems = byDay.get(key) || [];
      const isToday = key === dateKey(today);
      const activeClass = dayItems.length
        ? "bg-primary-container text-on-primary-container border border-primary shadow-sm"
        : "bg-surface-container-low text-on-surface-variant border border-outline-variant/20";
      const todayClass = isToday ? " ring-2 ring-primary ring-offset-1 ring-offset-surface-container-lowest" : "";
      const title = timelineDayTitle(dayItems);
      const target = dayItems.length ? timelineTarget(dayItems[0]) : "training-library.html";
      const badges = dayItems.slice(0, 2).map((item) => `<span class="text-[9px] leading-none font-bold">${escapeHtml(timelineBadge(item))}</span>`).join("");
      return [
        `<button type="button" data-arm-timeline-target="${target}" class="aspect-square rounded-md flex flex-col items-center justify-center gap-1 text-data-viz font-data-viz ${activeClass}${todayClass}" title="${escapeHtml(title)}">`,
        `<span>${day.getDate()}</span>`,
        dayItems.length ? `<span class="flex items-center gap-0.5">${badges}</span>` : "",
        "</button>"
      ].join("");
    }).join("");
    grid.innerHTML = headerHtml + dayHtml;
    if (logNode) {
      const recent = items.slice(0, 4);
      logNode.innerHTML = recent.length
        ? recent.map((item) => {
            const display = item.display || {};
            const title = display.title || item.title || timelineKindLabel(item.kind);
            const subtitle = display.subtitle || item.status || "";
            const dateText = item._date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
            return [
              `<button type="button" data-arm-timeline-target="${timelineTarget(item)}" class="w-full text-left rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 hover:border-primary/40 transition-colors">`,
              `<div class="flex items-center justify-between gap-2"><span class="text-label-md font-label-md text-on-surface">${escapeHtml(title)}</span><span class="text-data-viz font-data-viz text-on-surface-variant">${escapeHtml(dateText)}</span></div>`,
              `<div class="mt-1 text-data-viz font-data-viz text-on-surface-variant">${escapeHtml(timelineKindLabel(item.kind))} · ${escapeHtml(subtitle)}</div>`,
              "</button>"
            ].join("");
          }).join("")
        : '<div class="rounded-lg border border-outline-variant/30 bg-surface-container-low p-3 text-body-md font-body-md text-on-surface-variant">还没有真实训练日志。先去“训练”创建计划，或去“AI 规划”生成草稿。</div>';
    }
    if (logButton) {
      logButton.textContent = items.length ? "查看最近记录" : "去创建计划";
      logButton.setAttribute("data-arm-timeline-target", items.length ? timelineTarget(items[0]) : "training-library.html");
    }
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
    if (!state) return;
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
    if (!state) return;
    if (pageName() !== "training-library.html") return;
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
    const devices = bootstrap.devices || [];
    const plans = bootstrap.training_plans || [];
    const nextAction = userNextAction(state);
    const needsDevice = devices.length === 0;
    const panel = document.createElement("section");
    panel.setAttribute("data-arm-evidence", "true");
    panel.style.cssText = [
      "margin:8px 14px 10px",
      "padding:12px 14px",
      "border:1px solid #dbeafe",
      "border-radius:8px",
      "background:#ffffff",
      "color:#0f172a",
      "box-shadow:0 6px 18px rgba(15,23,42,.06)",
      "font:600 12px/1.5 Inter,system-ui,sans-serif"
    ].join(";");
    panel.innerHTML = [
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px">',
      '<div>',
      '<div style="font-size:12px;color:#64748b">今日康复进度</div>',
      `<div style="font-size:16px;font-weight:900;color:#0f172a;margin-top:2px">${escapeHtml(nextAction)}</div>`,
      `<div style="margin-top:4px;color:#475569">${needsDevice ? "还没有绑定设备；可以先规划训练，正式训练前再连接设备。" : "训练前仍会做设备同步和安全检查。"}</div>`,
      "</div>",
      `<div style="flex:0 0 auto;text-align:right;color:#2563eb;font-weight:900">${plans.length}<div style="font-size:11px;color:#64748b;font-weight:700">训练计划</div></div>`,
      "</div>"
    ].join("");
    const anchor = document.querySelector("[data-arm-status]");
    if (anchor && anchor.nextSibling) {
      anchor.parentNode.insertBefore(panel, anchor.nextSibling);
    } else {
      document.body.prepend(panel);
    }
  }

  function numberOr(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function latestEmgChannels(latestEmg) {
    const defaults = [
      { channel: "ch1", muscle: "biceps" },
      { channel: "ch2", muscle: "triceps" },
      { channel: "ch3", muscle: "forearm_flexors" },
      { channel: "ch4", muscle: "reserved" }
    ];
    const sourceChannels = latestEmg && Array.isArray(latestEmg.channels) ? latestEmg.channels : [];
    return defaults.map((fallback, index) => {
      const source = sourceChannels[index] || {};
      const rawAdc = Math.round(numberOr(source.raw_adc, 0));
      const voltage = numberOr(source.voltage_v, rawAdc * 3.3 / 4095);
      const normalized = numberOr(source.normalized, rawAdc ? rawAdc / 4095 : 0);
      return {
        channel: String(source.channel || fallback.channel).toUpperCase(),
        muscle: source.muscle || source.muscle_name || fallback.muscle,
        rawAdc,
        voltage,
        normalized,
        connected: Boolean(source.connected || rawAdc > 0)
      };
    });
  }

  function latestEmgModel(latestEmg) {
    const intent = latestEmg && latestEmg.intent_prediction ? latestEmg.intent_prediction : {};
    const model = latestEmg && latestEmg.model_outputs ? latestEmg.model_outputs : {};
    const candidates = Array.isArray(model.candidates) ? model.candidates : [];
    const firstCandidate = candidates[0] || {};
    const label = intent.predicted_action || model.summary || firstCandidate.label || "等待 M55 推理";
    const confidence = intent.confidence != null ? intent.confidence : firstCandidate.confidence;
    return { label, confidence: confidence == null ? null : numberOr(confidence, null) };
  }

  function removeLiveEmgPanel() {
    const panel = document.querySelector("[data-arm-live-emg]");
    if (panel) panel.remove();
  }

  function renderLiveEmgPanel(state) {
    if (pageName() !== "emg.html") {
      removeLiveEmgPanel();
      return;
    }
    const latestEmg = state.latestEmg || null;
    const channels = latestEmgChannels(latestEmg);
    const model = latestEmgModel(latestEmg);
    const hasLiveChannels = Boolean(latestEmg && Array.isArray(latestEmg.channels));
    const deviceId = latestEmg && (latestEmg.platform_device_id || latestEmg.m33_device_id || latestEmg.app_device_id);
    const source = latestEmg && latestEmg.source ? latestEmg.source : "waiting";
    const confidenceText = model.confidence == null ? "等待同步" : `${Math.round(model.confidence * 100)}%`;
    const freshness = latestEmg && latestEmg.freshness_ms != null ? `${Math.round(numberOr(latestEmg.freshness_ms, 0))} ms` : "--";
    const panel = document.querySelector("[data-arm-live-emg]") || document.createElement("section");
    panel.setAttribute("data-arm-live-emg", "true");
    panel.style.cssText = [
      "grid-column:1 / -1",
      "padding:14px",
      "border:1px solid #99f6e4",
      "border-radius:8px",
      "background:#f8fafc",
      "box-shadow:0 10px 24px rgba(15,23,42,.08)",
      "font:600 12px/1.5 Inter,system-ui,sans-serif",
      "color:#0f172a"
    ].join(";");
    panel.innerHTML = [
      '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px;flex-wrap:wrap">',
      '<div>',
      '<div style="font-size:12px;color:#0f766e;font-weight:900;letter-spacing:.04em">SERVER EMG LIVE</div>',
      `<div style="font-size:17px;font-weight:900;margin-top:2px">${hasLiveChannels ? "四路肌电服务器下发" : "等待服务器肌电"}</div>`,
      `<div style="color:#475569;margin-top:2px">来源 ${escapeHtml(source)} · 设备 ${escapeHtml(deviceId || "--")} · fresh ${escapeHtml(freshness)}</div>`,
      "</div>",
      `<div style="border:1px solid #bae6fd;border-radius:8px;padding:8px 10px;background:#ecfeff;min-width:132px"><div style="color:#0369a1">M55 推理</div><div style="font-size:16px;font-weight:900;color:#0f172a">${escapeHtml(model.label)}</div><div style="color:#475569">置信度 ${escapeHtml(confidenceText)}</div></div>`,
      "</div>",
      '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:8px">',
      ...channels.map((channel) => [
        `<div style="border:1px solid ${channel.connected ? "#67e8f9" : "#e2e8f0"};border-radius:8px;padding:10px;background:${channel.connected ? "#ecfeff" : "#ffffff"}">`,
        `<div style="display:flex;justify-content:space-between;gap:8px"><span style="font-weight:900">${escapeHtml(channel.channel)}</span><span style="color:${channel.connected ? "#0891b2" : "#94a3b8"}">${channel.connected ? "active" : "0"}</span></div>`,
        `<div style="color:#475569;margin-top:2px">${escapeHtml(channel.muscle)}</div>`,
        `<div style="font-size:18px;font-weight:900;margin-top:6px">${channel.rawAdc}</div>`,
        `<div style="color:#64748b">ADC · ${channel.voltage.toFixed(3)} V · ${Math.round(channel.normalized * 100)}%</div>`,
        "</div>"
      ].join("")),
      "</div>"
    ].join("");
    const main = document.querySelector("main") || document.body;
    if (!panel.parentNode) main.prepend(panel);
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
    replaceAll(["RoboRehab Controller", "RoboRehab 控制器", "RoboRehab"], "灵动康复 ArmControl");
    replaceAll(["M33 ACTIVE", "状态：M33 已允许执行", "M33 已允许执行"], "M33 待协议/待审核");
    replaceAll(["M33 状态：准备就绪，允许安全训练"], "设备状态：等待绑定与审核");
    replaceAll(["已扫描蓝牙"], devices.length ? "已绑定设备" : "等待绑定设备");
    replaceAll(["M33 康复机械臂"], devices[0] ? devices[0].ble_name || devices[0].m33_device_id : "等待绑定康复设备");
    replaceAll(["急停已就绪"], "急停状态待硬件上报");
    replaceAll(["动作稳定性极佳，建议维持当前强度"], "等待真实训练报告和治疗师复核");
    replaceAll(["2小时前"], "暂无真实记录");
    if (isBlocked) {
      replaceAll(["M33 ACTIVE", "状态：M33 已允许执行", "M33 已允许执行"], "M33 待协议/待审核");
      replaceAll(["M33 状态：准备就绪，允许安全训练"], "设备状态：等待绑定与审核");
      replaceAll(["需 M33 审核：计划必须先同步并经由 M33 审核后方可执行。"], "训练前需要先同步到设备，并完成设备审核与训练前检查。");
      replaceAll(["急停已就绪"], "急停状态待硬件上报");
      replaceAll(["设备已连接", "蓝牙已连接"], devices.length ? "已绑定" : "待绑定");
      replaceAll(["已扫描蓝牙"], devices.length ? "已绑定设备" : "等待绑定设备");
      replaceAll(["M33 康复机械臂"], devices[0] ? devices[0].ble_name || devices[0].m33_device_id : "等待绑定康复设备");
      replaceAll(["准备就绪"], "等待设备审核");
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
      replaceAll(["目标角度\n\n120°", "120°"], plans[0] && plans[0].target_angle_range ? `${plans[0].target_angle_range.min_deg || 0}-${plans[0].target_angle_range.max_deg || 0}°` : "待同步");
      replaceAll(["最近完成\n\n2小时前", "2小时前"], "暂无真实记录");
    }
    replaceAll(["执行中 - 由 M33 监控"], phase.title ? `工作流状态：${phase.title}` : "工作流状态：等待读取");
    replaceAll(["AI 建议"], "AI/报告建议待复核");
    replaceAll(["训练总结"], "训练报告闭环");
    if (current === "profile.html") {
      replaceFirst(["Sarah Chen", "康复用户"], (profile && profile.name) || "康复用户");
      replaceFirst(["RoboRehab Controller"], "灵动康复 ArmControl");
      replaceAll(["患者 A"], (profile && profile.name) || "康复用户");
      replaceAll(["ID: 8829"], profile && profile.id ? `ID: ${String(profile.id).slice(0, 8)}` : "ID: 待同步");
      replaceAll(["第二阶段康复中"], profile && profile.rehab_stage ? `康复阶段：${profile.rehab_stage}` : "康复阶段待完善");
      replaceAll(["避免过度伸展 > 120°"], profile && (profile.medical_constraints || []).length ? (profile.medical_constraints || []).join("；") : "暂无后端医疗约束记录");
      replaceAll(["System OK", "待登录"], state.authenticated ? "已同步" : "待登录");
      replaceAll(["M33 康复机械臂"], devices[0] ? devices[0].ble_name || devices[0].m33_device_id : "等待绑定康复设备");
      replaceAll(["M55 肌电传感器"], state.latestEmg ? "M55 肌电最近记录" : "等待肌电记录");
      replaceAll(["EXO-L-01"], devices[0] ? devices[0].m33_device_id || devices[0].id : "未绑定设备");
      replaceAll(["EMG-PATCH"], state.latestEmg ? "已同步肌电" : "暂无肌电");
      replaceAll(["激活"], devices.length || state.latestEmg ? "有记录" : "待同步");
      replaceAll(["云端平台"], "云端同步");
      replaceAll(["同步中"], state.authenticated ? "已同步" : "待登录");
      replaceAll(["小智语音"], "语音入口");
      replaceAll(["已开启"], "由平台配置");
      replaceAll(["权限管理"], "照护协作");
      replaceAll(["康复师/家属"], "待邀请");
    }
    renderProfileTrainingActivity(state);
    if (current === "device.html") {
      const device = devices[0];
      replaceFirst(["M33-Cortex", "ArmControl-Alpha", "ArmControl-Session", "ArmControl-Workflow"], device ? device.ble_name || device.m33_device_id : "等待绑定 M33");
      replaceFirst(["已连接"], device && device.trust_status === "trusted" ? "已绑定" : "待绑定");
      replaceAll(["安全门控 (Gatekeeper)"], "等待协议门控 (Gatekeeper)");
      replaceAll(["120ms", "45ms"], "待上报");
      replaceAll(["机械臂电量:\n85%", "85%"], "机械臂电量:\n待上报");
      replaceAll(["电源状态"], "电源状态待上报");
      replaceAll(["心跳状态"], "心跳状态待上报");
    }
    if (current === "bluetooth-debug.html") {
      renderBluetoothDebugPage(state);
    }
    if (current === "ai-plan.html") {
      renderAiPlanPage(state);
    }
    if (current === "training-library.html" || current === "ai-plan.html") {
      const movement = catalog.training_movements && catalog.training_movements[0];
      replaceFirst(["屈肘训练"], movement ? movement.label : "目录加载中");
      replaceFirst(["AI 规划"], readiness.status === "blocked" ? "后端门禁待完成" : "AI 规划");
      replaceAll(["智能方案生成"], "AI 草稿待审核");
      replaceAll(["生成方案"], "生成 AI 草稿");
      replaceAll(["开始计划"], "查看计划工作流");
      if (current === "training-library.html") {
        replaceAll(["M33 已接收"], "等待设备审核");
        replaceAll(["肩部旋转"], "待创建计划");
        replaceAll(["中风险"], "待评估");
        replaceAll(["45°"], "待同步");
        replaceAll(["50%"], "待审核");
        replaceAll(["昨天"], "暂无真实记录");
        replaceAll(["康复师方案"], "照护方案");
        replaceAll(["由陈医生开具 • 3 组 x 15 次", "由陈医生开具 • 2组 x 15 次"], "等待康复师或照护协作记录");
        replaceAll(["基于昨天的表现指标，AI/报告建议待复核增加 5% 的阻力以进一步刺激神经调控。"], "等待真实训练报告后再生成调整建议。");
        replaceAll(["基于昨天的表现指标，AI 建议增加 5% 的阻力以进一步刺激神经调控。"], "等待真实训练报告后再生成调整建议。");
        replaceAll(["基于暂无真实记录的表现指标，AI/报告建议待复核增加 5% 的阻力以进一步刺激神经调控。"], "等待真实训练报告后再生成调整建议。");
        replaceAll(["生成蓝图"], "生成 AI 草稿");
      }
    }
    renderTrainingLibraryPage(state);
    if (current === "emg.html") {
      renderLiveEmgPanel(state);
      replaceFirst(["肱二头肌", "biceps"], state.latestEmg ? state.latestEmg.muscle_name : "等待肌电记录");
      replaceAll(["Exoskeleton: Connected"], "设备待绑定");
      replaceAll(["实时肌肉等待记录与动作意图推断。M55 医疗审批生效中。"], "肌电和动作意图只显示后端记录；未连接 M55 时保持等待。");
      replaceAll(["实时肌肉激活与动作意图推断。M55 医疗审批生效中。"], "肌电和动作意图只显示后端记录；未连接 M55 时保持等待。");
      replaceAll(["接触良好"], state.latestEmg ? "有记录" : "等待记录");
      replaceAll(["14.2 µV", "28.5 µV", "42%", "5.1 µV", "12.0 µV", "15%", "32.4 µV", "65.2 µV", "88%", "8.3 µV", "18.1 µV", "22%"], state.latestEmg ? "已同步" : "待同步");
      replaceAll(["建议降等待肌电助力"], "等待真实肌电趋势");
      replaceAll(["建议降低助力"], "等待真实肌电趋势");
      replaceAll(["持续监测 CH3 屈肌 (近 15 分钟)"], "等待 M55 上传肌电趋势");
      replaceAll(["预测动作\n屈曲"], "预测动作\n等待意图记录");
      replaceAll(["屈曲"], "等待意图记录");
      replaceAll(["置信度: 98%"], "置信度：待同步");
      replaceAll(["CH3 88%", "CH1 42%"], "等待记录");
    } else {
      removeLiveEmgPanel();
    }
    if (current === "report.html") {
      const report = bootstrap.latest_report || {};
      const summary = report.summary || {};
      const hasReport = Boolean(report.id);
      replaceAll(["训练总结"], hasReport ? "训练报告闭环" : "暂无训练报告");
      replaceAll(["92"], hasReport && summary.score != null ? summary.score : "--");
      replaceAll(["/ 100"], hasReport ? "/ 100" : "待生成");
      replaceAll(["表现评分"], hasReport ? "表现评分" : "报告生成后显示");
      replaceAll(["100%"], hasReport && summary.completion_rate != null ? `${Math.round(Number(summary.completion_rate) * 100)}%` : "待报告");
      replaceAll(["15m"], hasReport && summary.duration_sec ? `${Math.round(Number(summary.duration_sec) / 60)}m` : "待报告");
      replaceAll(["中断次数"], "中断记录");
      replaceAll(["质量指标"], "质量指标待报告");
      replaceAll(["稳定性"], "稳定性待报告");
      replaceAll(["高"], "待报告");
      replaceAll(["路径偏差"], "路径偏差待报告");
      replaceAll(["低"], "待报告");
      replaceAll(["代偿情况"], "代偿情况待报告");
      replaceAll(["无"], "待报告");
      replaceAll(["稳定性\n高"], "稳定性\n待报告");
      replaceAll(["路径偏差\n低"], "路径偏差\n待报告");
      replaceAll(["代偿情况\n无"], "代偿情况\n待报告");
      replaceAll(["肌肉洞察"], "肌肉洞察待报告");
      replaceAll(["峰值疲劳 (第 3 组)", "峰值疲劳 (第 2组)"], "峰值疲劳待肌电报告");
      replaceAll(["70%"], "待同步");
      replaceAll(["峰值疲劳 (第 3 组)"], "峰值疲劳待肌电报告");
      replaceAll(["左右平衡"], "左右平衡待报告");
      replaceAll(["48 / 52"], "待报告");
      replaceAll(["48", "52"], "待报告");
      replaceAll(["L: 48%", "R: 52%", "L: 待报告%", "R: 待报告%"], "待报告");
      replaceAll(["M33 系统日志"], "设备审核记录");
      replaceAll(["自动裁决"], "设备通过");
      replaceAll(["人工干预"], "人工复核");
      replaceAll(["12"], "0");
      replaceAll(["AI 洞察"], "报告建议");
      replaceAll(['"动作一致性极佳。准备好在下次训练中增加强度了吗？"'], hasReport ? "请根据报告复盘结果决定是否生成下一次训练草稿。" : "完成真实训练记录并生成报告后，这里会显示复盘建议。");
      replaceAll(["同步至云端"], "刷新报告");
      replaceAll(["分享给康复师"], "等待照护协作");
    }
    if (current === "training-session.html") {
      replaceAll(["Exoskeleton: Connected"], "设备待绑定");
      replaceAll(["执行中 - 由 M33 等待协议门控监控", "执行中 - 由 M33 监控", "执行中 - 由 M33 安全门控监控"], "等待设备审核，暂不能开始训练");
      replaceAll(["训练编号: TRN-8842-X"], "训练记录：待创建");
      replaceAll(["疲劳度上升"], "等待真实训练数据");
      replaceAll(["M33 正在动态调整助力等级以确保患者等待协议。"], "当前没有可执行训练；需要设备审核和训练前检查后才能记录。");
      replaceAll(["M33 正在动态调整助力等级以确保患者安全。"], "当前没有可执行训练；需要设备审核和训练前检查后才能记录。");
      replaceAll(["Sets 2/3"], "Sets --/--");
      replaceAll(["8/12"], "--/--");
      replaceAll(["08:45"], "--:--");
      replaceAll(["实时角度"], "角度记录待同步");
      replaceAll(["偏差: -8°"], "偏差：待同步");
      replaceAll(["90°", "82°"], "--°");
      replaceAll(["助力状态"], "助力状态待设备审核");
      replaceAll(["比例\n30%"], "比例\n待审核");
      replaceAll(["方向\n向上"], "方向\n待同步");
      replaceAll(["30%"], "待审核");
      replaceAll(["向上"], "待同步");
      replaceAll(["68%", "24%", "45%", "32%"], "待同步");
      replaceAll(["暂停"], "查看流程");
      replaceAll(["紧急停止"], "记录停止请求");
    }
    if (current === "home.html") {
      replaceFirst(["今日训练"], readiness.status === "blocked" ? "真实后端已连接：仍有门禁" : "今日训练");
      replaceAll(["晚上好，今天适合做轻量屈肘训练"], userNextAction(state));
      replaceAll(["20 mins"], plans[0] && plans[0].duration_sec ? `${Math.round(Number(plans[0].duration_sec) / 60)} 分钟` : "待计划");
      replaceAll(["45%"], "待记录");
      replaceAll(["进度"], "训练记录");
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
        lastAiDraft: state.lastAcceptedAiPlan ? null : (state.lastAiDraft || bootstrap.latest_open_ai_draft || null),
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

  function aiDraftPlan(draft) {
    return draft && (draft.generated_plan || draft.training_plan || draft.plan) ? (draft.generated_plan || draft.training_plan || draft.plan) : {};
  }

  function aiPlannerStatus(draft) {
    const context = (draft && draft.context_snapshot) || {};
    const planner = context.ai_planner || {};
    if (planner.status === "external_used") return `模型已调用：${planner.model || "configured relay"}`;
    if (planner.status === "external_rejected_fallback_rule_based") return "模型响应被安全过滤，已使用规则草稿";
    if (planner.status === "fallback_rule_based") return `规则草稿：${planner.error || "模型未配置/未启用"}`;
    return "等待生成";
  }

  function renderAiPlanPage(state) {
    if (pageName() !== "ai-plan.html") return;
    const acceptedPlan = state.lastAcceptedAiPlan || null;
    const draft = acceptedPlan ? null : (state.lastAiDraft || ((state.bootstrap || {}).latest_open_ai_draft) || null);
    if (acceptedPlan) {
      const sets = acceptedPlan.sets == null ? "-" : acceptedPlan.sets;
      const reps = acceptedPlan.reps == null ? "-" : acceptedPlan.reps;
      const assist = acceptedPlan.assist_level == null ? "-" : `${Math.round(Number(acceptedPlan.assist_level) * 100)}%`;
      const speed = acceptedPlan.speed_level || "-";
      setText("[data-role='ai-draft-title']", acceptedPlan.title || "已接受的训练计划");
      setText("[data-role='ai-draft-sets-reps']", `${sets} 组 x ${reps} 次`);
      setText("[data-role='ai-draft-assist']", `${assist} / ${speed}`);
      setText(
        "[data-role='ai-draft-explain']",
        "已接受为普通训练计划。下一步请同步到设备，等待 M33 accepted，并通过 preflight 后再开始训练记录。"
      );
      document.querySelectorAll("[data-arm-ai-accept]").forEach((button) => {
        button.disabled = true;
      });
      return;
    }
    const plan = aiDraftPlan(draft);
    const sets = plan.sets == null ? "-" : plan.sets;
    const reps = plan.reps == null ? "-" : plan.reps;
    const assist = plan.assist_level == null ? "-" : `${Math.round(Number(plan.assist_level) * 100)}%`;
    const speed = plan.speed_level || "-";
    const riskNotes = Array.isArray(draft && draft.risk_notes) ? draft.risk_notes : [];
    setText("[data-role='ai-draft-title']", plan.title || (draft ? "AI 训练草稿" : "等待生成训练草稿"));
    setText("[data-role='ai-draft-sets-reps']", draft ? `${sets} 组 x ${reps} 次` : (state.authenticated ? "点击生成草稿" : "登录后生成"));
    setText("[data-role='ai-draft-assist']", draft ? `${assist} / ${speed}` : "-");
    setText(
      "[data-role='ai-draft-explain']",
      draft
        ? `${aiPlannerStatus(draft)}。${plan.goal || "草稿只用于生成训练计划。"} ${riskNotes[0] || "接受后仍需设备同步、M33 接受和训练前检查。"}`
        : "AI 规划会调用后端 /ai-training-drafts/generate。模型未配置时会明确显示规则回退，不再伪装真实 AI 调用。"
    );
    document.querySelectorAll("[data-arm-ai-accept]").forEach((button) => {
      button.disabled = !(draft && draft.id && !draft.accepted_plan_id);
    });
  }

  function selectedAiFatigue() {
    const node = document.querySelector("[data-arm-ai-fatigue]");
    return node ? node.value || node.options[node.selectedIndex]?.text || "" : "";
  }

  function composeAiDraftContext(state) {
    const painNode = document.querySelector("[data-arm-ai-pain]");
    const profile = (state.bootstrap && state.bootstrap.profile) || state.profile || {};
    const plan = (state.plans || [])[0] || {};
    return {
      source: "app_ai_plan_page",
      movement_type: plan.movement_type || "elbow_flexion",
      pain_level: painNode ? Number(painNode.value || 0) : null,
      fatigue_level: selectedAiFatigue(),
      latest_emg: state.latestEmg || null,
      current_plan: plan && plan.id ? {
        id: plan.id,
        movement_type: plan.movement_type,
        sets: plan.sets,
        reps: plan.reps,
        assist_level: plan.assist_level,
        speed_level: plan.speed_level,
        target_angle_range: plan.target_angle_range
      } : null,
      profile_snapshot: {
        rehab_stage: profile.rehab_stage || "",
        affected_side: profile.affected_side || "",
        medical_constraints: profile.medical_constraints || []
      },
      control_boundary: "app_ai_context_only_not_motion_permission"
    };
  }

  async function generateAiTrainingDraft() {
    if (!token()) {
      toast("请先登录后端，再生成 AI 训练草稿。", "warn");
      return null;
    }
    const input = document.querySelector("[data-arm-ai-input]");
    const inputText = (input && input.value ? input.value.trim() : "") || "根据当前康复档案、疼痛、疲劳和最近肌电生成下一次轻量训练草稿。";
    const state = readState();
    const loadingState = { ...state, lastAiDraft: null, lastAcceptedAiPlan: null, lastAcceptedAiDraftId: "" };
    writeState(loadingState);
    setText("[data-role='ai-draft-title']", "正在生成 AI 训练草稿");
    setText("[data-role='ai-draft-sets-reps']", "请稍候");
    setText("[data-role='ai-draft-assist']", "-");
    setText("[data-role='ai-draft-explain']", "正在调用后端 AI 训练规划链路；生成期间不能接受旧草稿。");
    document.querySelectorAll("[data-arm-ai-generate]").forEach((button) => { button.disabled = true; });
    document.querySelectorAll("[data-arm-ai-accept]").forEach((button) => { button.disabled = true; });
    try {
      const draft = await api("/api/rehab-arm/app/v1/ai-training-drafts/generate", {
        method: "POST",
        body: JSON.stringify({ input_text: inputText, context_snapshot: composeAiDraftContext(state) })
      });
      const nextState = { ...readState(), lastAiDraft: draft, lastAcceptedAiPlan: null, lastAcceptedAiDraftId: "" };
      writeState(nextState);
      renderAiPlanPage(nextState);
      toast(aiPlannerStatus(draft));
      await refreshFromBackend();
      return draft;
    } finally {
      document.querySelectorAll("[data-arm-ai-generate]").forEach((button) => { button.disabled = false; });
    }
  }

  async function acceptAiTrainingDraft() {
    const state = readState();
    const draft = state.lastAiDraft || ((state.bootstrap || {}).latest_open_ai_draft) || null;
    if (!token() || !draft || !draft.id) {
      toast("没有可接受的后端 AI 草稿。请先生成或刷新。", "warn");
      return null;
    }
    const plan = await api(`/api/rehab-arm/app/v1/ai-training-drafts/${draft.id}/accept`, { method: "POST", body: JSON.stringify({}) });
    writeState({ ...readState(), lastAiDraft: null, lastAcceptedAiPlan: plan, lastAcceptedAiDraftId: draft.id, plans: [plan, ...((state.plans || []).filter((item) => item.id !== plan.id))] });
    toast("AI 草稿已接受为训练计划；仍需同步设备、M33 accepted 和 preflight。");
    await refreshFromBackend();
    return plan;
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

  async function connectSelectedNativeSpp(device) {
    const plugin = nativeSppPlugin();
    if (!plugin || !plugin.connect) {
      throw new Error("当前运行环境不是 Android 原生包，不能打开 Bluetooth Classic SPP。");
    }
    if (plugin.requestPermissions) {
      await plugin.requestPermissions().catch(() => null);
    }
    const profile = (readState().publicConfig && readState().publicConfig.m33_legacy_spp_profile) || (readState().catalog && readState().catalog.m33_legacy_spp_profile) || {};
    const result = await plugin.connect({
      address: device.address || "",
      name: device.name || "",
      uuid: profile.standard_uuid || "00001101-0000-1000-8000-00805F9B34FB"
    });
    const nextState = { ...readState(), nativeSpp: result, selectedSppDevice: device };
    writeState(nextState);
    appendLegacySppLog("CONNECT", `${device.name || "SPP"} ${device.address || ""}`);
    renderBluetoothDebugPage(nextState);
    return result;
  }

  async function bindSelectedSppDeviceToBackend(device) {
    if (!token()) {
      throw new Error("请先登录后端，再绑定可信 M33 设备。");
    }
    const m33DeviceId = device.address || device.name || "";
    if (!m33DeviceId) {
      throw new Error("已配对设备缺少 MAC/名称，不能绑定到后端。");
    }
    const result = await api("/api/rehab-arm/app/v1/devices/bind", {
      method: "POST",
      body: JSON.stringify({
        m33_device_id: m33DeviceId,
        ble_name: device.name || m33DeviceId,
        trust_status: "trusted"
      })
    });
    const nextState = {
      ...readState(),
      selectedSppDevice: device,
      devices: [result, ...((readState().devices || []).filter((item) => item.id !== result.id))]
    };
    writeState(nextState);
    appendLegacySppLog("BIND", `${result.ble_name || result.m33_device_id} -> backend trusted device`);
    await refreshFromBackend();
    return result;
  }

  async function disconnectNativeSpp() {
    const plugin = nativeSppPlugin();
    if (!plugin || !plugin.disconnect) {
      throw new Error("当前运行环境不是 Android 原生包，不能断开 SPP。");
    }
    const result = await plugin.disconnect();
    const nextState = { ...readState(), nativeSpp: result };
    writeState(nextState);
    appendLegacySppLog("DISCONNECT", "SPP socket closed");
    renderBluetoothDebugPage(nextState);
    return result;
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

  async function sendDebugLegacyFrame() {
    const state = readState();
    const frame = state.lastBleMessage && state.lastBleMessage.payload ? state.lastBleMessage.payload.legacy_transport_frame : null;
    if (!frame || !frame.sendable || !frame.wire_text) {
      throw new Error("还没有可发送的后端 legacy_transport_frame。请先在设备页同步训练计划。");
    }
    const plugin = nativeSppPlugin();
    if (!plugin || !plugin.sendLegacyFrame) {
      throw new Error("当前运行环境不是 Android 原生包，不能发送 SPP 帧。");
    }
    let status = await readNativeSppStatus();
    if (!status.connected) {
      const selected = state.selectedSppDevice;
      if (selected && (selected.address || selected.name)) {
        status = await connectSelectedNativeSpp(selected);
      } else {
        const profile = (state.publicConfig && state.publicConfig.m33_legacy_spp_profile) || (state.catalog && state.catalog.m33_legacy_spp_profile);
        const backendDevice = state.devices && state.devices[0];
        status = await connectNativeSpp(backendDevice, profile);
      }
    }
    const result = await plugin.sendLegacyFrame({
      sendable: true,
      wireText: frame.wire_text,
      messageType: frame.json && frame.json.type,
      controlBoundary: "android_spp_transport_only_m33_final_authority"
    });
    const nextState = { ...readState(), nativeSpp: status, lastLegacySppSend: result };
    writeState(nextState);
    appendLegacySppLog("TX", frame.wire_text.trim());
    renderBluetoothDebugPage(nextState);
    return result;
  }

  async function uploadLegacySppInbound(event) {
    const state = readState();
    const device = state.devices && state.devices[0];
    const wireText = event && event.wireText;
    if (!token() || !device || !wireText) return null;
    const related = state.lastBleMessage && state.lastBleMessage.id ? state.lastBleMessage.id : "";
    const result = await api(`/api/rehab-arm/app/v1/devices/${device.id}/legacy-spp/inbound`, {
      method: "POST",
      body: JSON.stringify({
        raw_text: wireText,
        related_message_id: related,
        transport_event: {
          deviceName: event.deviceName || "",
          deviceAddress: event.deviceAddress || "",
          connected: Boolean(event.connected),
          controlBoundary: "android_spp_transport_only_m33_final_authority"
        }
      })
    });
    writeState({ ...readState(), lastLegacySppInbound: result, nativeSpp: await readNativeSppStatus() });
    appendLegacySppLog("API", result.status || "inbound_uploaded");
    return result;
  }

  function renderBluetoothDebugPage(state) {
    if (pageName() !== "bluetooth-debug.html") return;
    const nativeSpp = state.nativeSpp || {};
    const connected = Boolean(nativeSpp.connected);
    const frame = state.lastBleMessage && state.lastBleMessage.payload ? state.lastBleMessage.payload.legacy_transport_frame : null;
    const inbound = state.lastLegacySppInbound || {};
    const lastSend = state.lastLegacySppSend || {};
    const logs = Array.isArray(state.legacySppLogs) ? state.legacySppLogs : [];
    renderStatusPill(connected ? "SPP 已连接" : nativeSpp.available ? "SPP 待连接" : "仅 Web/无权限", connected);
    setText("[data-role='spp-device-name']", nativeSpp.deviceName || (state.selectedSppDevice && state.selectedSppDevice.name) || "未连接");
    setText("[data-role='spp-device-address']", nativeSpp.deviceAddress || (state.selectedSppDevice && state.selectedSppDevice.address) || "-");
    setText("[data-role='spp-uuid']", nativeSpp.uuid || "00001101-0000-1000-8000-00805F9B34FB");
    setText("[data-role='spp-permission']", nativeSpp.permission || "等待读取");
    const primaryDevice = (state.devices || []).find((item) => item.trust_status !== "revoked");
    setText("[data-role='spp-backend-binding']", primaryDevice ? `${primaryDevice.ble_name || primaryDevice.m33_device_id} / ${primaryDevice.trust_status}` : (state.authenticated ? "未绑定" : "等待登录"));
    setText("[data-role='spp-frame-state']", frame && frame.sendable ? "sendable=true" : "等待后端批准帧");
    setText("[data-role='spp-frame-preview']", frame && frame.wire_text ? frame.wire_text.trim() : "只有后端生成并标记 sendable=true 的 legacy_transport_frame 会出现在这里。");
    setText("[data-role='spp-last-send']", lastSend.sent ? `sent ${lastSend.byteLength || 0} bytes` : (lastSend.reason || "-"));
    setText("[data-role='spp-last-inbound']", inbound.raw_text || inbound.message_type || inbound.status || "-");
    setText("[data-role='spp-last-api']", inbound.status || "-");
    setText("[data-role='spp-sensor-snapshot']", sensorSnapshot(inbound));
    const sendButton = document.querySelector("[data-arm-spp-send-frame]");
    if (sendButton) sendButton.disabled = !(frame && frame.sendable && frame.wire_text);
    const logNode = document.querySelector("[data-role='spp-log-stream']");
    if (logNode) {
      logNode.innerHTML = logs.length
        ? logs.map((item) => `<div class="log-line"><span class="text-primary">${escapeHtml(item.direction)}</span> ${escapeHtml(item.at)}<br/>${escapeHtml(item.detail)}</div>`).join("")
        : '<div class="log-line">等待真实蓝牙事件。</div>';
    }
  }

  function setText(selector, value) {
    const node = document.querySelector(selector);
    if (node) node.textContent = value == null || value === "" ? "-" : String(value);
  }

  function renderStatusPill(label, connected) {
    const node = document.querySelector("[data-role='spp-status-pill']");
    if (!node) return;
    node.setAttribute("class", connected ? "px-2 py-1 bg-green-100 text-green-800 text-data-viz font-data-viz rounded flex items-center gap-1" : "px-2 py-1 bg-surface-container-high text-on-surface-variant text-data-viz font-data-viz rounded flex items-center gap-1");
    node.innerHTML = `<span class="${connected ? "w-2 h-2 rounded-full bg-green-500 animate-pulse" : "w-2 h-2 rounded-full bg-outline"}" data-role="spp-status-dot"></span>${escapeHtml(label)}`;
  }

  function setClass(selector, value) {
    const node = document.querySelector(selector);
    if (node) node.setAttribute("class", value);
  }

  function sensorSnapshot(inbound) {
    const payload = inbound && (inbound.parsed || inbound.payload || inbound.legacy_payload);
    if (!payload || typeof payload !== "object") return "等待 sensor JSON";
    if (payload.type && payload.type !== "sensor") return payload.type;
    const parts = [];
    ["position", "angle", "emg", "battery", "status"].forEach((key) => {
      if (payload[key] !== undefined) parts.push(`${key}=${JSON.stringify(payload[key])}`);
    });
    return parts.length ? parts.join(" / ") : JSON.stringify(payload).slice(0, 120);
  }

  async function refreshBluetoothDebugStatus() {
    const nativeSpp = await readNativeSppStatus();
    const nextState = { ...readState(), nativeSpp };
    writeState(nextState);
    renderBluetoothDebugPage(nextState);
    return nextState;
  }

  async function refreshBluetoothDebugDevices() {
    const result = await listNativeSppDevices();
    const devices = result.devices || [];
    const nextState = { ...readState(), nativeSpp: result, nativeSppBondedDevices: devices };
    writeState(nextState);
    setText("[data-role='spp-device-count']", `${devices.length} 台已配对`);
    const list = document.querySelector("[data-role='spp-device-list']");
    if (list) {
      list.innerHTML = devices.length
        ? devices.map((device) => [
            '<div class="flex justify-between items-center border border-outline-variant rounded-lg p-3 bg-surface-container-lowest">',
            '<div>',
            `<div class="font-label-md text-label-md">${escapeHtml(device.name || "未命名 SPP 设备")}</div>`,
            `<div class="text-data-viz text-on-surface-variant">${escapeHtml(device.address || "")}</div>`,
            "</div>",
            '<div class="flex gap-2">',
            `<button class="bg-surface-container-high text-on-surface px-3 py-2 rounded text-label-md font-label-md hover:opacity-90 transition-opacity" data-arm-spp-bind-device="${escapeHtml(device.address || device.name || "")}" type="button">绑定</button>`,
            `<button class="bg-primary text-on-primary px-4 py-2 rounded text-label-md font-label-md hover:opacity-90 transition-opacity" data-arm-spp-connect="${escapeHtml(device.address || device.name || "")}" type="button">连接</button>`,
            "</div>",
            "</div>"
          ].join(""))
        : '<div class="border border-outline-variant rounded-lg p-3 bg-surface-container-lowest text-data-viz text-on-surface-variant">没有读取到已配对设备，请先去 Android 系统蓝牙设置配对 M33/PSoC SPP。</div>';
    }
    renderBluetoothDebugPage(nextState);
    return devices;
  }

  function setupNativeSppInboundListener() {
    if (window.__rehabArmSppInboundBound) return;
    const plugin = nativeSppPlugin();
    if (!plugin || !plugin.addListener) return;
    window.__rehabArmSppInboundBound = true;
    plugin.addListener("legacySppData", (event) => {
      appendLegacySppLog("RX", event && event.wireText ? event.wireText.trim() : event);
      uploadLegacySppInbound(event)
        .then((result) => {
          if (result && result.status === "matched") toast("已收到 M33 SPP 回包并记录为后端证据。");
        })
        .catch((error) => toast(`M33 回包上传失败：${error.message || String(error)}`, "warn"));
    });
    plugin.addListener("legacySppDisconnected", (event) => {
      writeState({ ...readState(), nativeSpp: event || { connected: false } });
      appendLegacySppLog("DISCONNECT", "Native SPP disconnected");
    });
  }

  async function handlePrimaryAction(label) {
    const state = readState();
    if (label.includes("配对新设备") || label.includes("蓝牙调试") || label.includes("实机验证")) {
      navigate("bluetooth-debug.html");
      toast("进入蓝牙调试；请先在 Android 系统蓝牙里配对 M33/PSoC，再由 App 读取已配对设备。");
      return;
    }
    if (label.includes("云端同步")) {
      await refreshFromBackend();
      toast("已刷新云端康复数据。");
      return;
    }
    if (label.includes("新建计划") || label.includes("生成 AI 草稿") || label.includes("AI 生成")) {
      if (pageName() !== "ai-plan.html") {
        navigate("ai-plan.html");
        return;
      }
      await generateAiTrainingDraft();
      return;
    }
    if (label.includes("查看下一步") || label.includes("查看流程")) {
      if (state.workflow && state.workflow.phase) {
        insertWorkflowPanel(state);
        toast(`当前步骤：${actionLabel(state.workflow.next_action || {})}`);
      } else {
        toast("正在读取后端工作流，请稍后重试。", "warn");
        await refreshFromBackend();
      }
      return;
    }
    if (label.includes("刷新报告")) {
      const refreshed = await refreshFromBackend();
      const reports = (refreshed.bootstrap && refreshed.bootstrap.training_reports) || [];
      toast(reports.length ? "报告已刷新。" : "还没有真实训练报告；完成训练记录后再刷新。", reports.length ? undefined : "warn");
      return;
    }
    if (label.includes("同步")) {
      const plan = state.plans && state.plans[0];
      const device = state.devices && state.devices[0];
      if (!token()) {
        toast("请先登录；App 不使用本地 demo 同步。", "warn");
        return;
      }
      if (!plan) {
        toast("还没有训练计划；请先在 AI 规划或训练库生成/创建计划。", "warn");
        return;
      }
      if (!device) {
        toast("还没有可信康复设备；请进入蓝牙调试绑定 M33/PSoC 后再同步计划。", "warn");
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
      const sppRefresh = event.target && event.target.closest ? event.target.closest("[data-arm-spp-refresh]") : null;
      const timelineTarget = event.target && event.target.closest ? event.target.closest("[data-arm-timeline-target]") : null;
      if (timelineTarget) {
        event.preventDefault();
        navigate(timelineTarget.getAttribute("data-arm-timeline-target") || "training-library.html");
        return;
      }
      const profileLog = event.target && event.target.closest ? event.target.closest("[data-role='profile-view-log']") : null;
      if (profileLog) {
        event.preventDefault();
        const target = profileLog.getAttribute("data-arm-timeline-target") || "training-library.html";
        navigate(target);
        return;
      }
      if (sppRefresh) {
        event.preventDefault();
        refreshBluetoothDebugStatus().then(() => toast("SPP 状态已刷新")).catch((error) => toast(error.message, "warn"));
        return;
      }
      const sppList = event.target && event.target.closest ? event.target.closest("[data-arm-spp-list-devices]") : null;
      if (sppList) {
        event.preventDefault();
        refreshBluetoothDebugDevices().catch((error) => toast(error.message, "warn"));
        return;
      }
      const sppConnect = event.target && event.target.closest ? event.target.closest("[data-arm-spp-connect]") : null;
      if (sppConnect) {
        event.preventDefault();
        const key = sppConnect.getAttribute("data-arm-spp-connect") || "";
        const device = ((readState().nativeSppBondedDevices || []).find((item) => item.address === key || item.name === key)) || { address: key };
        connectSelectedNativeSpp(device).then(() => toast("SPP 已连接，等待 M33 回包。")).catch((error) => toast(error.message, "warn"));
        return;
      }
      const sppBindDevice = event.target && event.target.closest ? event.target.closest("[data-arm-spp-bind-device]") : null;
      if (sppBindDevice) {
        event.preventDefault();
        const key = sppBindDevice.getAttribute("data-arm-spp-bind-device") || "";
        const device = ((readState().nativeSppBondedDevices || []).find((item) => item.address === key || item.name === key)) || { address: key };
        bindSelectedSppDeviceToBackend(device).then(() => toast("已绑定为后端可信设备；仍需 M33 决策后才能训练。")).catch((error) => toast(error.message, "warn"));
        return;
      }
      const sppDisconnect = event.target && event.target.closest ? event.target.closest("[data-arm-spp-disconnect]") : null;
      if (sppDisconnect) {
        event.preventDefault();
        disconnectNativeSpp().then(() => toast("SPP 已断开")).catch((error) => toast(error.message, "warn"));
        return;
      }
      const sppSendFrame = event.target && event.target.closest ? event.target.closest("[data-arm-spp-send-frame]") : null;
      if (sppSendFrame) {
        event.preventDefault();
        sendDebugLegacyFrame().then(() => toast("已发送后端批准帧，等待 M33 ACK。")).catch((error) => toast(error.message, "warn"));
        return;
      }
      const aiGenerate = event.target && event.target.closest ? event.target.closest("[data-arm-ai-generate]") : null;
      if (aiGenerate) {
        event.preventDefault();
        generateAiTrainingDraft().catch((error) => toast(error.message, "warn"));
        return;
      }
      const aiAccept = event.target && event.target.closest ? event.target.closest("[data-arm-ai-accept]") : null;
      if (aiAccept) {
        event.preventDefault();
        acceptAiTrainingDraft().catch((error) => toast(error.message, "warn"));
        return;
      }
      const button = event.target && event.target.closest ? event.target.closest("[data-arm-workflow-action]") : null;
      if (!button) return;
      event.preventDefault();
      executeWorkflowAction(button.getAttribute("data-arm-workflow-action")).catch((error) => toast(error.message, "warn"));
    });
    document.querySelectorAll("button").forEach((button) => {
      if (button.matches("[data-arm-spp-refresh], [data-arm-spp-list-devices], [data-arm-spp-connect], [data-arm-spp-bind-device], [data-arm-spp-disconnect], [data-arm-spp-send-frame], [data-arm-ai-generate], [data-arm-ai-accept]")) return;
      button.addEventListener("click", () => {
        const label = (button.textContent || button.innerText || "").trim();
        handlePrimaryAction(label).catch((error) => toast(error.message, "warn"));
      });
    });
  }

  let liveEmgRefreshTimer = null;

  function startLiveEmgRefreshLoop() {
    if (pageName() !== "emg.html" || liveEmgRefreshTimer) return;
    liveEmgRefreshTimer = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      refreshFromBackend().catch(() => null);
    }, 2000);
  }

  document.addEventListener("DOMContentLoaded", async () => {
    bindNav();
    bindActions();
    setupNativeSppInboundListener();
    upsertStatusStrip(readState());
    await refreshFromBackend();
    startLiveEmgRefreshLoop();
  });
})();
