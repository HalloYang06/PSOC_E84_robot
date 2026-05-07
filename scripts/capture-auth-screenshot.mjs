import fs from "node:fs";
import http from "node:http";
import https from "node:https";
import path from "node:path";
import os from "node:os";
import { spawn } from "node:child_process";

const EDGE_PATHS = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
];

function findEdge() {
  for (const candidate of EDGE_PATHS) {
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error("Microsoft Edge not found");
}

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const part = argv[i];
    if (!part.startsWith("--")) continue;
    const key = part.slice(2);
    const value = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : "true";
    out[key] = value;
  }
  return out;
}

async function wait(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function numberArg(value, fallback) {
  if (value === undefined || value === null || value === "") return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

async function fetchJson(url, attempts = 40, init = undefined) {
  let lastError;
  for (let i = 0; i < attempts; i += 1) {
    try {
      const payload = await requestJson(url, init);
      if (payload !== undefined) return payload;
    } catch (error) {
      lastError = error;
    }
    await wait(250);
  }
  throw lastError ?? new Error(`Failed to fetch ${url}`);
}

function requestJson(url, init = undefined) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const client = target.protocol === "https:" ? https : http;
    const method = String(init?.method ?? "GET").toUpperCase();
    const headers = { ...(init?.headers ?? {}) };
    const req = client.request(
      target,
      {
        method,
        headers,
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const body = Buffer.concat(chunks).toString("utf8");
          const statusCode = Number(res.statusCode ?? 0);
          if (statusCode < 200 || statusCode >= 300) {
            reject(new Error(`HTTP ${statusCode} for ${url}: ${body.slice(0, 240)}`));
            return;
          }
          try {
            resolve(JSON.parse(body));
          } catch (error) {
            reject(error);
          }
        });
      },
    );
    req.on("error", reject);
    req.end();
  });
}

async function connectCdp(wsUrl) {
  const socket = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  let seq = 0;
  const pending = new Map();

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.id && pending.has(payload.id)) {
      const { resolve, reject } = pending.get(payload.id);
      pending.delete(payload.id);
      if (payload.error) reject(new Error(payload.error.message));
      else resolve(payload.result);
    }
  });

  function send(method, params = {}) {
    const id = ++seq;
    socket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
    });
  }

  return { socket, send };
}

async function waitForMarkers(send, markers, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const { result } = await send("Runtime.evaluate", {
      expression: "document.body ? document.body.innerText : ''",
      returnByValue: true,
    });
    const text = String(result?.value ?? "");
    if (markers.every((marker) => text.includes(marker))) return text;
    await wait(300);
  }
  throw new Error(`Markers not found: ${markers.join(", ")}`);
}

async function waitForUrl(send, matcher, timeoutMs = 12000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const { result } = await send("Runtime.evaluate", {
      expression: "location.href",
      returnByValue: true,
    });
    const href = String(result?.value ?? "");
    if (matcher(href)) return href;
    await wait(250);
  }
  throw new Error("Timed out waiting for expected URL");
}

async function scrollElement(send, selector, top) {
  const { result } = await send("Runtime.evaluate", {
    expression: `
      (() => {
        const target = document.querySelector(${JSON.stringify(selector)});
        if (!target) return { ok: false, reason: "not-found" };
        target.scrollTo({ top: ${JSON.stringify(top)}, behavior: "instant" });
        return {
          ok: true,
          scrollTop: target.scrollTop,
          clientHeight: target.clientHeight,
          scrollHeight: target.scrollHeight,
        };
      })()
    `,
    returnByValue: true,
  });
  const payload = result?.value ?? null;
  if (!payload?.ok) {
    throw new Error(`Failed to scroll selector ${selector}: ${payload?.reason ?? "unknown"}`);
  }
  return payload;
}

async function focusText(send, value) {
  const { result } = await send("Runtime.evaluate", {
    expression: `
      (() => {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node = walker.nextNode();
        while (node) {
          const content = (node.textContent || "").trim();
          if (content.includes(${JSON.stringify(value)})) {
            const host = node.parentElement;
            if (!host) return { ok: false, reason: "host-missing" };
            host.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
            return {
              ok: true,
              tag: host.tagName.toLowerCase(),
              id: host.id || "",
              className: typeof host.className === "string" ? host.className : "",
              text: content.slice(0, 120),
            };
          }
          node = walker.nextNode();
        }
        return { ok: false, reason: "text-not-found" };
      })()
    `,
    returnByValue: true,
  });
  const payload = result?.value ?? null;
  if (!payload?.ok) {
    throw new Error(`Failed to focus text ${value}: ${payload?.reason ?? "unknown"}`);
  }
  return payload;
}

async function main() {
  const args = parseArgs(process.argv);
  const url = args.url;
  const primeUrl = args["prime-url"] ?? "";
  const token = args.token;
  const output = args.output;
  const userJson = args.userjson ?? "";
  const textDump = args["text-dump"] ?? "";
  const htmlDump = args["html-dump"] ?? "";
  const waitMs = numberArg(args["wait-ms"], 2500);
  const primeWaitMs = numberArg(args["prime-wait-ms"], 2500);
  const scrollY = numberArg(args["scroll-y"], 0);
  const scrollSelector = args["scroll-selector"] ?? "";
  const selectorScrollY = numberArg(args["selector-scroll-y"], 0);
  const focusTextValue = args["focus-text"] ?? "";
  const viewportWidth = numberArg(args["viewport-width"], 1600);
  const viewportHeight = numberArg(args["viewport-height"], 1200);
  const loginEmail = args["login-email"] ?? "";
  const loginPassword = args["login-password"] ?? "";
  const expectedUrlContains = args["expected-url-contains"] ?? "";
  const debugPort = numberArg(args["debug-port"], 0);
  const externalDebugPort = debugPort > 0;
  const noAuth = String(args["no-auth"] ?? "").toLowerCase() === "true";
  const markers = String(args.markers ?? "")
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean);

  const hasCookieAuth = Boolean(token);
  const hasFormAuth = Boolean(loginEmail && loginPassword);

  if (!url || !output || (!hasCookieAuth && !hasFormAuth && !noAuth)) {
    throw new Error(
      "Usage: node capture-auth-screenshot.mjs --url <url> --output <png> ((--token <token> | --login-email <email> --login-password <password>) | --no-auth true) [--markers a|b]",
    );
  }

  fs.mkdirSync(path.dirname(output), { recursive: true });
  const targetOrigin = new URL(url).origin;
  const primingUrl = primeUrl || "";
  const returnTarget = primingUrl || url;
  const defaultExpectedLocation = (() => {
    try {
      const parsed = new URL(returnTarget);
      return `${parsed.pathname}${parsed.search}`;
    } catch {
      return "";
    }
  })();
  const loginExpectedLocation = expectedUrlContains || defaultExpectedLocation;
  const edge = findEdge();
  const port = externalDebugPort ? debugPort : 9222 + Math.floor(Math.random() * 400);
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "codex-edge-auth-"));

  const edgeProcess = externalDebugPort
    ? null
    : spawn(
        edge,
        [
          "--headless=new",
          "--disable-gpu",
          `--remote-debugging-port=${port}`,
          `--user-data-dir=${userDataDir}`,
          "--no-first-run",
          "--no-default-browser-check",
          "about:blank",
        ],
        { stdio: "ignore" },
      );

  try {
    await wait(externalDebugPort ? 300 : 1800);
    let targets = await fetchJson(`http://127.0.0.1:${port}/json/list`, 80);
    let pageTarget = targets.find((target) => target.type === "page" && target.webSocketDebuggerUrl);
    if (!pageTarget) {
      await fetchJson(`http://127.0.0.1:${port}/json/new?about:blank`, 80, { method: "PUT" });
      targets = await fetchJson(`http://127.0.0.1:${port}/json/list`, 80);
      pageTarget = targets.find((target) => target.type === "page" && target.webSocketDebuggerUrl);
    }
    if (!pageTarget) {
      throw new Error("No page target available for Edge remote debugging");
    }
    const { send, socket } = await connectCdp(pageTarget.webSocketDebuggerUrl);
    try {
      await send("Page.enable");
      await send("Runtime.enable");
      await send("Network.enable");
      await send("Emulation.setDeviceMetricsOverride", {
        width: viewportWidth,
        height: viewportHeight,
        deviceScaleFactor: 1,
        mobile: false,
      });
      if (loginEmail && loginPassword) {
        const loginUrl = `${targetOrigin}/login?returnTo=${encodeURIComponent(returnTarget.replace(targetOrigin, ""))}`;
        await send("Page.navigate", { url: loginUrl });
        await waitForUrl(send, (href) => href.includes("/login"), 8000);
        await wait(1000);
        await send("Runtime.evaluate", {
          expression: `
            (() => {
              const email = document.querySelector('input[name="email"]');
              const password = document.querySelector('input[name="password"]');
              const form = email && password ? email.closest('form') : null;
              if (!email || !password || !form) return 'login-form-missing';
              email.value = ${JSON.stringify(loginEmail)};
              email.dispatchEvent(new Event('input', { bubbles: true }));
              password.value = ${JSON.stringify(loginPassword)};
              password.dispatchEvent(new Event('input', { bubbles: true }));
              form.requestSubmit();
              return 'submitted';
            })()
          `,
          returnByValue: true,
        });
        if (loginExpectedLocation) {
          await waitForUrl(send, (href) => href.includes(loginExpectedLocation), 12000);
        } else {
          await wait(2000);
        }
        await wait(primeWaitMs);
        if (primingUrl) {
          await send("Page.navigate", { url });
        }
      } else if (noAuth) {
        await send("Page.navigate", { url: primingUrl || url });
        if (primingUrl) {
          await wait(primeWaitMs);
          await send("Page.navigate", { url });
        }
      } else {
        const accessCookie = await send("Network.setCookie", {
          name: "farm_access_token",
          value: token,
          url: `${targetOrigin}/`,
          path: "/",
          httpOnly: false,
          sameSite: "Lax",
        });
        if (!accessCookie?.success) {
          throw new Error("Failed to set farm_access_token cookie");
        }
        if (userJson) {
          const userCookie = await send("Network.setCookie", {
            name: "farm_user",
            value: userJson,
            url: `${targetOrigin}/`,
            path: "/",
            httpOnly: false,
            sameSite: "Lax",
          });
          if (!userCookie?.success) {
            throw new Error("Failed to set farm_user cookie");
          }
        }
        await send("Page.navigate", { url: primingUrl || url });
        if (primingUrl) {
          await wait(primeWaitMs);
          await send("Page.navigate", { url });
        }
      }
      if (markers.length) {
        try {
          await waitForMarkers(send, markers, 12000);
        } catch (error) {
          if (textDump) {
            const { result } = await send("Runtime.evaluate", {
              expression: "document.body ? document.body.innerText : ''",
              returnByValue: true,
            });
            fs.writeFileSync(textDump, String(result?.value ?? ""), "utf8");
          }
          throw error;
        }
      } else {
        await wait(waitMs);
      }
      if (markers.length && waitMs > 0) {
        await wait(waitMs);
      }
      if (scrollY > 0) {
        await send("Runtime.evaluate", {
          expression: `window.scrollTo({ top: ${JSON.stringify(scrollY)}, behavior: "instant" });`,
          returnByValue: true,
        });
        await wait(400);
      }
      if (scrollSelector) {
        await scrollElement(send, scrollSelector, selectorScrollY);
        await wait(400);
      }
      if (focusTextValue) {
        await focusText(send, focusTextValue);
        await wait(400);
      }
      if (htmlDump) {
        const { result } = await send("Runtime.evaluate", {
          expression: "document.documentElement ? document.documentElement.outerHTML : ''",
          returnByValue: true,
        });
        fs.mkdirSync(path.dirname(htmlDump), { recursive: true });
        fs.writeFileSync(htmlDump, String(result?.value ?? ""), "utf8");
      }
      if (textDump) {
        const { result } = await send("Runtime.evaluate", {
          expression: "document.body ? document.body.innerText : ''",
          returnByValue: true,
        });
        fs.mkdirSync(path.dirname(textDump), { recursive: true });
        fs.writeFileSync(textDump, String(result?.value ?? ""), "utf8");
      }
      const { data } = await send("Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: true,
      });
      fs.writeFileSync(output, Buffer.from(data, "base64"));
    } finally {
      socket.close();
    }
  } finally {
    if (edgeProcess) {
      edgeProcess.kill("SIGTERM");
      await wait(500);
    }
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true });
    } catch {}
  }
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
