(function () {
  const icons = {
    arrow_back: "‹",
    bluetooth_disabled: "⌁",
    bluetooth_searching: "⌕",
    calendar_today: "□",
    check: "✓",
    check_circle: "✓",
    construction: "!",
    error: "!",
    fitness_center: "训",
    folder_open: "□",
    forum: "问",
    group: "社",
    groups: "社",
    home: "⌂",
    mail: "信",
    medical_services: "医",
    person: "我",
    play_arrow: "▶",
    power_settings_new: "⏻",
    precision_manufacturing: "械",
    send: "➤",
    settings: "设",
    smart_toy: "AI",
    sync: "↻",
  };

  function installStyle() {
    if (document.getElementById("rehab-icon-fallback-style")) return;
    const style = document.createElement("style");
    style.id = "rehab-icon-fallback-style";
    style.textContent = `
      .material-symbols-outlined {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 1.35em !important;
        min-width: 1.35em !important;
        height: 1.35em !important;
        overflow: hidden !important;
        color: currentColor !important;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
        font-size: 0 !important;
        line-height: 1 !important;
        white-space: nowrap !important;
      }
      .material-symbols-outlined::before {
        content: attr(data-icon-fallback);
        font-size: 1.15rem;
        font-weight: 700;
        line-height: 1;
      }
      .bottom-nav .material-symbols-outlined::before,
      nav .material-symbols-outlined::before {
        font-size: 1.05rem;
      }
    `;
    document.head.appendChild(style);
  }

  function applyFallbacks() {
    installStyle();
    document.querySelectorAll(".material-symbols-outlined").forEach((node) => {
      const name = (node.textContent || "").trim();
      node.dataset.iconName = name;
      node.dataset.iconFallback = icons[name] || "•";
      node.setAttribute("aria-hidden", "true");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyFallbacks);
  } else {
    applyFallbacks();
  }
})();
