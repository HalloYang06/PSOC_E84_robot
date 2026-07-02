(function () {
  const PAGE_BY_LABEL = {
    "首页": "home.html",
    "训练": "training-library.html",
    "肌电": "emg.html",
    "设备": "device.html",
    "我的": "profile.html"
  };

  const API_BASE_KEY = "rehabArmMobileApiBase";
  const STORE_KEY = "rehabArmMobileState";
  const DEFAULT_STATE = {
    profile: {
      name: "康复用户",
      role: "patient",
      affected_side: "left",
      rehab_stage: "early_active",
      medical_constraints: ["M33 审核后执行"],
      pain_baseline: 2
    },
    devices: [
      {
        id: "local-m33",
        m33_device_id: "m33-rehab-arm-local",
        ble_name: "ArmControl-Local",
        firmware_version: "m33-preview",
        trust_status: "unverified",
        latest_sync: null,
        control_boundary: "device_binding_only_not_motion_permission"
      }
    ],
    plans: [
      {
        id: "local-plan-elbow",
        title: "屈肘训练",
        movement_type: "elbow_flexion",
        sets: 3,
        reps: 8,
        duration_sec: 600,
        assist_level: 0.25,
        status: "active",
        control_boundary: "training_plan_only_not_motor_command"
      }
    ],
    latestEmg: {
      session_id: "local-session",
      channel: "ch1",
      muscle_name: "biceps",
      rms_avg: 0.42,
      peak: 0.7,
      activation_avg: 0.55,
      fatigue_index: 0.18,
      contact_quality: "preview",
      control_boundary: "emg_summary_only_not_motion_permission"
    },
    lastSync: null,
    lastSession: null,
    offline: true
  };

  function readState() {
    try {
      return Object.assign({}, DEFAULT_STATE, JSON.parse(localStorage.getItem(STORE_KEY) || "{}"));
    } catch (_error) {
      return Object.assign({}, DEFAULT_STATE);
    }
  }

  function writeState(nextState) {
    localStorage.setItem(STORE_KEY, JSON.stringify(nextState));
  }

  function apiBase() {
    return localStorage.getItem(API_BASE_KEY) || "";
  }

  async function api(path, options) {
    const base = apiBase();
    if (!base) {
      throw new Error("API base is not configured");
    }
    const response = await fetch(base.replace(/\/$/, "") + path, {
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      ...options
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body && body.error ? body.error.message : "API request failed");
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
        "border-radius:12px",
        "font:600 13px/1.45 Inter,system-ui,sans-serif",
        "box-shadow:0 10px 28px rgba(15,23,42,.18)",
        "transition:opacity .2s ease, transform .2s ease"
      ].join(";");
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.style.background = tone === "warn" ? "#fff7ed" : "#eff6ff";
    node.style.color = tone === "warn" ? "#9a3412" : "#1d4ed8";
    node.style.border = tone === "warn" ? "1px solid #fed7aa" : "1px solid #bfdbfe";
    node.style.opacity = "1";
    node.style.transform = "translateY(0)";
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => {
      node.style.opacity = "0";
      node.style.transform = "translateY(8px)";
    }, 2600);
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
      item.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          navigate(PAGE_BY_LABEL[target]);
        }
      });
    });
  }

  function addStatusStrip(state) {
    if (document.querySelector("[data-arm-status]")) return;
    const strip = document.createElement("div");
    strip.setAttribute("data-arm-status", "true");
    strip.style.cssText = [
      "position:sticky",
      "top:0",
      "z-index:30",
      "margin:0 auto",
      "max-width:780px",
      "padding:8px 16px",
      "background:rgba(239,246,255,.94)",
      "border-bottom:1px solid #bfdbfe",
      "color:#1e3a8a",
      "font:600 12px/1.4 Inter,system-ui,sans-serif",
      "backdrop-filter:blur(14px)"
    ].join(";");
    strip.textContent = state.offline
      ? "PWA 预览模式：使用本地缓存数据；训练计划同步只代表提交给 M33 审核。"
      : "已连接 App 后端：当前页面只处理档案、设备绑定、计划和证据记录，不发送电机命令。";
    document.body.prepend(strip);
  }

  function annotatePage(state) {
    const current = pageName();
    if (current === "device.html") {
      const device = state.devices && state.devices[0];
      if (device) {
        replaceFirst(["M33-Cortex", "ArmControl"], device.ble_name || device.m33_device_id);
        replaceFirst(["已连接"], device.trust_status === "trusted" ? "已绑定" : "待验证");
      }
    }
    if (current === "profile.html" && state.profile) {
      replaceFirst(["RoboRehab Controller"], "灵动康复 ArmControl");
      replaceFirst(["Sarah Chen", "康复用户"], state.profile.name || "康复用户");
    }
    if (current === "emg.html" && state.latestEmg) {
      replaceFirst(["肱二头肌", "biceps"], state.latestEmg.muscle_name || "biceps");
    }
  }

  function replaceFirst(candidates, value) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const text = node.nodeValue || "";
      const hit = candidates.find((candidate) => text.includes(candidate));
      if (hit) {
        node.nodeValue = text.replace(hit, value);
        return;
      }
    }
  }

  async function refreshFromBackend() {
    const state = readState();
    try {
      const [profile, devices, plans, latestEmg] = await Promise.all([
        api("/api/rehab-arm/app/v1/me/profile"),
        api("/api/rehab-arm/app/v1/devices"),
        api("/api/rehab-arm/app/v1/training-plans"),
        api("/api/rehab-arm/app/v1/emg/latest")
      ]);
      const nextState = {
        ...state,
        profile: profile || state.profile,
        devices: devices && devices.length ? devices : state.devices,
        plans: plans && plans.length ? plans : state.plans,
        latestEmg: latestEmg || state.latestEmg,
        offline: false
      };
      writeState(nextState);
      return nextState;
    } catch (_error) {
      writeState({ ...state, offline: true });
      return { ...state, offline: true };
    }
  }

  async function handlePrimaryAction(label) {
    const state = readState();
    if (label.includes("同步")) {
      const plan = state.plans && state.plans[0];
      const device = state.devices && state.devices[0];
      if (!plan || !device || plan.id.startsWith("local-") || device.id.startsWith("local-")) {
        toast("已记录本地同步意图；真实动作仍需后端登录和 M33 审核。", "warn");
        return;
      }
      const sync = await api(`/api/rehab-arm/app/v1/training-plans/${plan.id}/sync-to-device`, {
        method: "POST",
        body: JSON.stringify({ device_id: device.id })
      });
      writeState({ ...state, lastSync: sync, offline: false });
      toast("训练计划已提交给 M33 审核，不是运动许可。");
      return;
    }
    if (label.includes("开始训练") || label.includes("play_arrow")) {
      navigate("training-session.html");
      toast("进入训练监控页；启动真实运动仍由 M33 安全系统决定。", "warn");
      return;
    }
    if (label.includes("配对") || label.includes("绑定")) {
      toast("手机端设备绑定入口已就绪；后续接 BLE/登录后写入后端。");
      return;
    }
    if (label.includes("急停") || label.includes("停止") || label.includes("block")) {
      toast("App 只能记录/请求停止状态，不能释放急停或绕过 M33。", "warn");
      return;
    }
    if (label.includes("校准")) {
      toast("校准结果会作为肌电证据记录，不直接驱动电机。");
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
    const state = await refreshFromBackend();
    addStatusStrip(state);
    annotatePage(state);
  });
})();
