(function () {
  const apiBase = "http://106.55.62.122:8011";
  const sessionEndpoint = "/api/auth/session";
  const bootstrapEndpoint = "/api/rehab-arm/app/v1/me";
  const phoneVerificationEndpoint = "/api/rehab-arm/app/v1/account/phone-verifications";
  const deviceBindEndpoint = "/api/rehab-arm/app/v1/devices/bind";
  const agentMessageEndpoint = "/api/rehab-arm/app/v1/agent/messages";

  let verificationId = "";
  let resendCooldown = 0;
  let resendTimer = null;
  let selectedDevice = null;
  let isAuthenticated = false;
  const discoveredDevices = new Map();

  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }

  function qsa(selector, root) {
    return Array.from((root || document).querySelectorAll(selector));
  }

  function getToken() {
    return localStorage.getItem("access_token") || "";
  }

  function apiUrl(path) {
    if (/^https?:\/\//i.test(path)) return path;
    return `${apiBase}${path.startsWith("/") ? path : `/${path}`}`;
  }

  function authHeaders(extra) {
    const token = getToken();
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(extra || {}),
    };
  }

  async function parseJson(response) {
    const text = await response.text();
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch {
      return { error: { code: "RESPONSE_PARSE_FAILED", message: text } };
    }
  }

  async function apiRequest(path, options) {
    const response = await fetch(apiUrl(path), {
      ...options,
      headers: authHeaders(options && options.headers),
    });
    const payload = await parseJson(response);
    if (!response.ok) {
      const detail = payload.error || payload.detail || payload;
      const error = new Error(detail.message || "请求暂时失败");
      Object.assign(error, detail);
      error.status = response.status;
      throw error;
    }
    return payload.data || payload;
  }

  function setText(selector, value) {
    const node = qs(selector);
    if (node && value) node.textContent = value;
  }

  function setInputValue(selector, value) {
    const node = qs(selector);
    if (node && value) node.value = value;
  }

  function setDisabled(selector, disabled) {
    const node = qs(selector);
    if (node) node.disabled = !!disabled;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function setPhoneStatus(message, tone) {
    const status = qs("#phone-binding-status");
    if (!status) return;
    status.textContent = message;
    status.classList.remove("success", "error");
    if (tone) status.classList.add(tone);
  }

  function setLoginStatus(message, tone) {
    const status = qs("#login-status");
    if (!status) return;
    status.textContent = message || "";
    status.classList.remove("success", "error");
    if (tone) status.classList.add(tone);
  }

  function setLoginLoading(loading) {
    const button = qs('[data-action="login-cloud-account"]');
    if (!button) return;
    button.disabled = !!loading;
    button.textContent = loading ? "登录中" : button.dataset.defaultLabel || "登录云端账号";
  }

  function setPhoneBindingLocked(locked, message) {
    const shouldLock = !!locked;
    setDisabled("#phone-input", shouldLock);
    setDisabled("#phone-code-input", shouldLock);
    setDisabled('[data-action="confirm-phone-binding"]', shouldLock);

    const sendButton = qs('[data-action="send-phone-code"]');
    if (sendButton) {
      sendButton.disabled = shouldLock || resendCooldown > 0;
      if (shouldLock) {
        sendButton.textContent = sendButton.dataset.defaultLabel || "获取验证码";
      }
    }

    const badge = qs("#phone-verified-badge");
    if (badge) {
      if (shouldLock) {
        badge.textContent = "需登录";
      } else if (badge.textContent.trim() === "需登录") {
        badge.textContent = "未绑定";
      }
    }

    if (shouldLock) {
      verificationId = "";
      clearInterval(resendTimer);
      resendTimer = null;
      resendCooldown = 0;
      setPhoneStatus(message || "请先登录云端账号，再绑定手机号。", "error");
    }
  }

  function setAuthState(authenticated, options) {
    isAuthenticated = !!authenticated;
    const panel = qs("#cloud-login-panel");
    if (panel) panel.classList.toggle("is-hidden", isAuthenticated);
    setText("#cloud-account-status", isAuthenticated ? "已登录" : "未登录");

    if (isAuthenticated) {
      setPhoneBindingLocked(false);
      if (!options || options.showReadyMessage !== false) {
        setPhoneStatus("登录成功，可以绑定手机号。", "success");
      }
      return;
    }

    setPhoneBindingLocked(true, "请先登录云端账号，再绑定手机号。");
  }

  function setPhoneLoading(kind, loading) {
    const sendButton = qs('[data-action="send-phone-code"]');
    const confirmButton = qs('[data-action="confirm-phone-binding"]');
    if (sendButton && kind === "send") {
      sendButton.disabled = loading || resendCooldown > 0 || !isAuthenticated;
      sendButton.textContent = loading ? "发送中" : sendButton.dataset.defaultLabel || "获取验证码";
    }
    if (confirmButton && kind === "confirm") {
      confirmButton.disabled = loading || !isAuthenticated;
      confirmButton.textContent = loading ? "绑定中" : confirmButton.dataset.defaultLabel || "绑定手机号";
    }
  }

  function startPhoneCountdown(seconds) {
    const sendButton = qs('[data-action="send-phone-code"]');
    if (!sendButton) return;
    clearInterval(resendTimer);
    resendCooldown = Math.max(1, Number(seconds) || 60);
    sendButton.disabled = true;
    sendButton.textContent = `${resendCooldown}s`;
    resendTimer = setInterval(() => {
      resendCooldown -= 1;
      if (resendCooldown <= 0) {
        clearInterval(resendTimer);
        resendTimer = null;
        sendButton.disabled = !isAuthenticated;
        sendButton.textContent = sendButton.dataset.defaultLabel || "获取验证码";
        return;
      }
      sendButton.textContent = `${resendCooldown}s`;
    }, 1000);
  }

  function normalizePhoneError(error) {
    if (error.code === "PHONE_CODE_INVALID") {
      return "验证码不正确或已过期，请重新输入。";
    }
    if (error.code === "PHONE_CODE_ATTEMPTS_EXCEEDED") {
      return "验证码尝试次数过多，请重新获取验证码。";
    }
    if (error.code === "PHONE_CODE_RESEND_TOO_SOON") {
      startPhoneCountdown(error.retry_after || error.retryAfter || 60);
      return "验证码发送太频繁，请稍后再试。";
    }
    if (error.code === "PHONE_SMS_NOT_CONFIGURED") {
      return "短信通道暂未配置，当前环境无法发送正式短信。";
    }
    if (error.code === "PHONE_SMS_DELIVERY_FAILED") {
      return "短信发送失败，请稍后再试。";
    }
    if (!getToken()) {
      return "请先登录账号，再绑定手机号。";
    }
    return error.message || "手机号绑定暂时失败，请稍后再试。";
  }

  function requireCloudLogin() {
    if (getToken()) return true;
    setAuthState(false);
    setLoginStatus("请先登录云端账号。", "error");
    const emailInput = qs("#login-email");
    if (emailInput) emailInput.focus();
    return false;
  }

  async function sendPhoneVerification() {
    if (!requireCloudLogin()) return;
    const phoneInput = qs("#phone-input");
    const phone = phoneInput ? phoneInput.value.trim() : "";
    if (!phone) {
      setPhoneStatus("请输入手机号。", "error");
      phoneInput && phoneInput.focus();
      return;
    }
    setPhoneLoading("send", true);
    setPhoneStatus("正在发送验证码...", "");
    try {
      const data = await apiRequest("/api/rehab-arm/app/v1/account/phone-verifications", {
        method: "POST",
        body: JSON.stringify({ phone, purpose: "bind_account" }),
      });
      verificationId = data.verification_id || "";
      const smsHint = data.debug_code ? `当前为内测验证模式，内测验证码：${data.debug_code}` : "验证码已发送，请查看短信。";
      setPhoneStatus(smsHint, "success");
      startPhoneCountdown(Math.min(Number(data.expires_in) || 60, 60));
    } catch (error) {
      setPhoneStatus(normalizePhoneError(error), "error");
      setPhoneLoading("send", false);
    }
  }

  async function confirmPhoneVerification() {
    if (!requireCloudLogin()) return;
    const codeInput = qs("#phone-code-input");
    const code = codeInput ? codeInput.value.trim() : "";
    if (!verificationId) {
      setPhoneStatus("请先获取验证码。", "error");
      return;
    }
    if (!code) {
      setPhoneStatus("请输入验证码。", "error");
      codeInput && codeInput.focus();
      return;
    }
    setPhoneLoading("confirm", true);
    setPhoneStatus("正在绑定手机号...", "");
    let phoneBound = false;
    try {
      const data = await apiRequest(`/api/rehab-arm/app/v1/account/phone-verifications/${verificationId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      const profile = data.profile || {};
      if (profile.phone_verified || profile.phoneVerified || data.phone_verified) {
        setPhoneStatus("手机号已验证，账号已绑定当前手机号。", "success");
      } else {
        setPhoneStatus("手机号已验证，账号已绑定当前手机号。", "success");
      }
      phoneBound = true;
      setText("#phone-verified-badge", "已绑定");
    } catch (error) {
      setPhoneStatus(normalizePhoneError(error), "error");
    } finally {
      setPhoneLoading("confirm", false);
      if (phoneBound) {
        const confirmButton = qs('[data-action="confirm-phone-binding"]');
        if (confirmButton) {
          confirmButton.disabled = true;
          confirmButton.textContent = "已绑定";
        }
      }
    }
  }

  function getBluetoothBridge() {
    if (window.RehabArmBluetoothBridge) return window.RehabArmBluetoothBridge;
    if (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.RehabArmBluetooth) {
      return window.Capacitor.Plugins.RehabArmBluetooth;
    }
    const spp = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.RehabArmSpp;
    if (spp && spp.listBondedDevices) {
      return {
        requestBluetoothPermissions: () => spp.status ? spp.status() : Promise.resolve({ permission: "android_spp" }),
        scanDevices: async () => {
          const result = await spp.listBondedDevices();
          const devices = Array.isArray(result.devices) ? result.devices : [];
          return {
            transport: result.transport || "bluetooth_classic_spp_rfcomm",
            devices: devices.map((device) => ({
              ...device,
              m33_device_id: device.address || device.name,
              ble_name: device.name || "已配对 SPP 设备",
              signalText: "Android 已配对 SPP，点击绑定账号后仍需连接验证",
              transport: "bluetooth_classic_spp_rfcomm",
            })),
          };
        },
      };
    }
    return null;
  }

  function showDeviceStep(index) {
    const firstStep = qs('[data-device-step="prepare"]');
    const secondStep = qs("#step2-content");
    if (index >= 2) {
      firstStep && firstStep.classList.add("hidden");
      secondStep && secondStep.classList.remove("hidden");
      secondStep && secondStep.classList.add("flex");
    }
    qsa(".step-icon").forEach((node, nodeIndex) => {
      if (nodeIndex + 1 <= index) {
        node.classList.remove("bg-surface-variant", "text-on-surface-variant");
        node.classList.add("bg-primary", "text-on-primary", "shadow-md");
      }
    });
    const progress = qs(".step-line");
    if (progress) progress.style.width = index >= 3 ? "100%" : "66%";
  }

  function showBridgeMissing() {
    showDeviceStep(2);
    const unavailable = qs("#bluetoothUnavailable");
    const status = qs("#device-status-message");
    if (status) status.textContent = "需要 Android App 蓝牙桥";
    if (unavailable) unavailable.classList.remove("hidden");
  }

  function setDeviceStatus(message) {
    const status = qs("#device-status-message");
    if (status) status.textContent = message;
  }

  function requireDeviceBindingLogin() {
    if (getToken()) return true;
    showDeviceStep(2);
    setDeviceStatus("请先登录云端账号，再绑定设备。");
    const unavailable = qs("#bluetoothUnavailable");
    const results = qs("#device-results");
    unavailable && unavailable.classList.add("hidden");
    if (results) {
      results.innerHTML = '<div class="w-full bg-surface-container rounded-lg p-md text-body-md text-on-surface-variant">登录后再搜索设备，避免蓝牙权限和设备绑定被错误占用。<a class="text-primary font-label-md" href="profile.html">去我的页面登录</a></div>';
    }
    return false;
  }

  function normalizeDiscoveredDevice(raw, index) {
    const deviceId = raw.m33_device_id || raw.deviceId || raw.id || raw.address || raw.name || `rehab-device-${index + 1}`;
    return {
      ...raw,
      deviceId,
      m33_device_id: deviceId,
      name: raw.ble_name || raw.bleName || raw.name || "康复训练设备",
      signalText: raw.signalText || raw.rssiText || "可连接",
    };
  }

  function renderDeviceResults(devices) {
    const results = qs("#device-results");
    const unavailable = qs("#bluetoothUnavailable");
    const status = qs("#device-status-message");
    if (!results) return;
    results.innerHTML = "";
    unavailable && unavailable.classList.add("hidden");
    discoveredDevices.clear();
    if (!devices.length) {
      if (status) status.textContent = "暂未发现可绑定设备";
      results.innerHTML = '<div class="w-full bg-surface-container rounded-lg p-md text-body-md text-on-surface-variant">请确认设备已开机并靠近手机，再重新搜索。</div>';
      return;
    }
    if (status) status.textContent = "发现附近设备";
    devices.forEach((device) => {
      discoveredDevices.set(device.deviceId, device);
      const card = document.createElement("div");
      card.className = "w-full bg-surface-bright rounded-lg p-md flex items-center gap-md border border-primary-container/30 shadow-sm";
      card.innerHTML = `
        <div class="w-12 h-12 rounded-full bg-secondary-container text-on-secondary-container flex items-center justify-center shrink-0">
          <span class="material-symbols-outlined">precision_manufacturing</span>
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-label-md font-label-md text-on-surface truncate">${device.name}</div>
          <div class="text-body-md font-body-md text-on-surface-variant truncate">${device.signalText}</div>
        </div>
        <button class="h-10 min-h-[44px] px-md bg-surface text-primary border border-primary rounded-full font-label-md text-label-md active:scale-95 transition-transform flex items-center justify-center shrink-0" data-action="bind-rehab-device" data-device-id="${device.deviceId}" type="button">
          绑定
        </button>
      `;
      results.appendChild(card);
    });
  }

  async function scanRehabDevices() {
    showDeviceStep(2);
    if (!requireDeviceBindingLogin()) return;
    const bridge = getBluetoothBridge();
    const status = qs("#device-status-message");
    const scanButton = qs('[data-action="scan-rehab-device"]');
    if (scanButton) scanButton.disabled = true;
    if (status) status.textContent = "正在搜索附近的设备...";
    if (!bridge) {
      showBridgeMissing();
      if (scanButton) scanButton.disabled = false;
      return;
    }
    try {
      if (bridge.requestBluetoothPermissions) {
        await bridge.requestBluetoothPermissions();
      }
      const response = await bridge.scanDevices({ kind: "rehab_arm" });
      const rawDevices = Array.isArray(response) ? response : response.devices || [];
      renderDeviceResults(rawDevices.map(normalizeDiscoveredDevice));
    } catch (error) {
      showBridgeMissing();
      const state = qs("#device-error-state");
      if (state) {
        state.classList.remove("hidden");
        state.querySelector("[data-error-message]").textContent = error.message || "蓝牙搜索失败，请检查权限后再试。";
      }
    } finally {
      if (scanButton) scanButton.disabled = false;
    }
  }

  async function bindSelectedDevice(event) {
    if (!requireDeviceBindingLogin()) return;
    const button = event.currentTarget || event.target.closest('[data-action="bind-rehab-device"]');
    const deviceId = button && button.dataset.deviceId;
    selectedDevice = discoveredDevices.get(deviceId);
    if (!selectedDevice) return;
    button.disabled = true;
    button.textContent = "绑定中";
    try {
      const data = await apiRequest("/api/rehab-arm/app/v1/devices/bind", {
        method: "POST",
        body: JSON.stringify({
          m33_device_id: selectedDevice.m33_device_id || selectedDevice.deviceId,
          ble_name: selectedDevice.name,
          trust_status: "trusted",
          firmware_version: selectedDevice.firmwareVersion || selectedDevice.firmware_version || "",
        }),
      });
      showDeviceStep(3);
      const bound = qs("#device-bound-state");
      if (bound) {
        bound.classList.remove("hidden");
        const deviceLabel = data.ble_name || selectedDevice.name || data.deviceId || data.m33_device_id;
        bound.querySelector("[data-bound-device]").textContent = `已绑定设备：${deviceLabel}`;
      }
    } catch (error) {
      const state = qs("#device-error-state");
      if (state) {
        state.classList.remove("hidden");
        const message = error.code === "DEVICE_ALREADY_BOUND"
          ? "这台设备已绑定到其他账号，请联系客服协助解绑。"
          : (error.message || "设备绑定失败，请稍后再试。");
        state.querySelector("[data-error-message]").textContent = message;
      }
      button.disabled = false;
      button.textContent = "绑定";
    }
  }

  function appendAgentMessage(role, message, tone) {
    const thread = qs("#agent-thread");
    if (!thread || !message) return;
    const wrap = document.createElement("div");
    const isUser = role === "user";
    wrap.className = isUser ? "flex justify-end mb-sm" : "flex justify-start mb-sm";
    wrap.innerHTML = `
      <div class="${isUser ? "bg-primary text-on-primary rounded-tr-none" : tone === "error" ? "bg-error-container/20 border border-error/30 text-on-surface rounded-tl-none" : "bg-surface-container-lowest border border-outline-variant/20 text-on-surface rounded-tl-none"} rounded-2xl px-md py-sm shadow-ambient-md font-body-md text-body-md max-w-[85%]">
        ${escapeHtml(message)}
      </div>
    `;
    thread.appendChild(wrap);
    thread.scrollTop = thread.scrollHeight;
  }

  async function sendAgentMessage() {
    const input = qs("#agent-message-input");
    const button = qs('[data-action="send-agent-message"]');
    const message = input ? input.value.trim() : "";
    if (!message) return;
    appendAgentMessage("user", message);
    input.value = "";
    if (button) button.disabled = true;
    try {
      const data = await apiRequest("/api/rehab-arm/app/v1/agent/messages", {
        method: "POST",
        body: JSON.stringify({ message, context_snapshot: { source: "mobile_app" } }),
      });
      appendAgentMessage("assistant", data.answer || "康复师已收到您的问题。");
      window.rehabAgentModelStatus = data.model_status || data.modelStatus || null;
    } catch (error) {
      const text = error.code === "UNSAFE_MOTION_REQUEST"
        ? "为了安全，我不能提供可能导致过度训练的建议。请保持当前训练节奏，并联系康复师确认。"
        : (error.message || "康复师暂时没有回应，请稍后再试。");
      appendAgentMessage("assistant", text, "error");
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function loginCloudAccount() {
    const emailInput = qs("#login-email");
    const passwordInput = qs("#login-password");
    const email = emailInput ? emailInput.value.trim() : "";
    const password = passwordInput ? passwordInput.value : "";

    if (!email) {
      setLoginStatus("请输入云端账号邮箱。", "error");
      if (emailInput) emailInput.focus();
      return;
    }
    if (!password) {
      setLoginStatus("请输入密码。", "error");
      if (passwordInput) passwordInput.focus();
      return;
    }

    setLoginLoading(true);
    setLoginStatus("正在登录云端账号...", "");
    try {
      const data = await apiRequest(sessionEndpoint, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      const token = data.access_token || data.accessToken || "";
      if (!token) {
        throw new Error("登录成功但没有返回访问凭证。");
      }
      localStorage.setItem("access_token", token);
      setLoginStatus("登录成功，正在同步康复资料...", "success");
      setAuthState(true);
      await loadBootstrap();
    } catch (error) {
      localStorage.removeItem("access_token");
      setAuthState(false);
      const message = error.code === "AUTH_INVALID"
        ? "账号或密码不正确，请重新输入。"
        : (error.message || "登录暂时失败，请稍后再试。");
      setLoginStatus(message, "error");
      if (passwordInput) passwordInput.focus();
    } finally {
      setLoginLoading(false);
    }
  }

  async function loadBootstrap() {
    if (!getToken()) {
      setAuthState(false);
      return;
    }
    try {
      const data = await apiRequest(bootstrapEndpoint, { method: "GET" });
      setAuthState(true, { showReadyMessage: false });
      const home = data.patient_view && data.patient_view.home;
      const profile = data.patient_view && data.patient_view.profile;
      const device = data.patient_view && data.patient_view.device;
      const agent = data.patient_view && data.patient_view.agent;
      window.rehabPatientView = { home, profile, device, agent };
      window.rehabModelStatus = data.model_status || data.modelStatus || null;
      if (profile) {
        setText("#profile-display-name", profile.display_name || profile.displayName || "您好");
        const phone = profile.phone || {};
        if (phone.value) setInputValue("#phone-input", phone.value);
        if (phone.verified || profile.phone_verified || profile.phoneVerified) {
          setText("#phone-verified-badge", "已绑定");
          setPhoneStatus("手机号已验证，账号已绑定当前手机号。", "success");
          const confirmButton = qs('[data-action="confirm-phone-binding"]');
          if (confirmButton) {
            confirmButton.disabled = true;
            confirmButton.textContent = "已绑定";
          }
        }
      }
      setText("#cloud-account-status", "已同步");
    } catch (error) {
      if (error.status === 401 || error.status === 403 || error.code === "AUTH_REQUIRED") {
        localStorage.removeItem("access_token");
        setAuthState(false);
        setLoginStatus("登录已过期，请重新登录。", "error");
        return;
      }
      setAuthState(true, { showReadyMessage: false });
      setText("#cloud-account-status", "同步失败");
    }
  }

  function wirePhoneBinding() {
    const sendButton = qs('[data-action="send-phone-code"]');
    const confirmButton = qs('[data-action="confirm-phone-binding"]');
    if (sendButton) {
      sendButton.dataset.defaultLabel = sendButton.textContent.trim() || "获取验证码";
      sendButton.addEventListener("click", sendPhoneVerification);
    }
    if (confirmButton) {
      confirmButton.dataset.defaultLabel = confirmButton.textContent.trim() || "绑定手机号";
      confirmButton.addEventListener("click", confirmPhoneVerification);
    }
  }

  function wireLogin() {
    const button = qs('[data-action="login-cloud-account"]');
    const emailInput = qs("#login-email");
    const passwordInput = qs("#login-password");
    if (button) {
      button.dataset.defaultLabel = button.textContent.trim() || "登录云端账号";
      button.addEventListener("click", loginCloudAccount);
    }
    [emailInput, passwordInput].forEach((input) => {
      if (!input) return;
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") loginCloudAccount();
      });
    });
  }

  function wireDeviceBinding() {
    const scanButton = qs('[data-action="scan-rehab-device"]');
    if (scanButton) {
      scanButton.addEventListener("click", scanRehabDevices);
    }
    document.addEventListener("click", (event) => {
      const button = event.target.closest('[data-action="bind-rehab-device"]');
      if (!button) return;
      bindSelectedDevice({ currentTarget: button, target: button });
    });
  }

  function wireAgent() {
    const button = qs('[data-action="send-agent-message"]');
    const input = qs("#agent-message-input");
    if (button) button.addEventListener("click", sendAgentMessage);
    if (input) {
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") sendAgentMessage();
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    wirePhoneBinding();
    wireLogin();
    loadBootstrap();
    wireDeviceBinding();
    wireAgent();
  });

  window.loginCloudAccount = loginCloudAccount;
  window.sendPhoneVerification = sendPhoneVerification;
  window.confirmPhoneVerification = confirmPhoneVerification;
  window.scanRehabDevices = scanRehabDevices;
  window.bindSelectedDevice = bindSelectedDevice;
})();
