const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

function hasDisabledAttribute(html, id) {
  const match = html.match(new RegExp(`<[^>]+id="${id}"[^>]*>`, "i"));
  return !!match && /\sdisabled(?:\s|>|=)/i.test(match[0]);
}

function main() {
  const profilePath = path.resolve(__dirname, "../public/rehab-arm-mobile/profile.html");
  const runtimePath = path.resolve(__dirname, "../public/rehab-arm-mobile/rehab-mobile-runtime.js");
  const profileHtml = fs.readFileSync(profilePath, "utf8");
  const runtime = fs.readFileSync(runtimePath, "utf8");

  assert.match(profileHtml, /id="cloud-login-panel"/);
  assert.match(profileHtml, /id="login-email"/);
  assert.match(profileHtml, /id="login-password"/);
  assert.match(profileHtml, /data-action="login-cloud-account"/);
  assert.match(profileHtml, /请先登录云端账号，再绑定手机号。/);

  assert.equal(hasDisabledAttribute(profileHtml, "phone-input"), true);
  assert.equal(hasDisabledAttribute(profileHtml, "phone-code-input"), true);
  assert.equal(hasDisabledAttribute(profileHtml, "send-code-btn"), true);
  assert.equal(hasDisabledAttribute(profileHtml, "confirm-phone-btn"), true);

  assert.match(runtime, /function setAuthState/);
  assert.match(runtime, /function setPhoneBindingLocked/);
  assert.match(runtime, /function loginCloudAccount/);
  assert.match(runtime, /const apiBase = "http:\/\/106\.55\.62\.122:8011"/);
  assert.match(runtime, /function apiUrl/);
  assert.match(runtime, /fetch\(apiUrl\(path\)/);
  assert.match(runtime, /localStorage\.setItem\("access_token"/);
  assert.match(runtime, /setAuthState\(false\)/);
  assert.match(runtime, /setAuthState\(true\)/);

  console.log("profile auth lock PASS");
}

try {
  main();
} catch (error) {
  console.error(error);
  process.exit(1);
}
