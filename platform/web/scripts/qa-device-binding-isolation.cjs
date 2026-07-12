const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

function main() {
  const mobileDir = path.resolve(__dirname, "../public/rehab-arm-mobile");
  const runtime = fs.readFileSync(path.join(mobileDir, "rehab-mobile-runtime.js"), "utf8");
  const deviceHtml = fs.readFileSync(path.join(mobileDir, "device.html"), "utf8");

  assert.match(runtime, /function requireDeviceBindingLogin/);
  assert.match(runtime, /async function scanRehabDevices\(\) \{[\s\S]*?if \(!requireDeviceBindingLogin\(\)\) return;[\s\S]*?bridge\.requestBluetoothPermissions/);
  assert.match(runtime, /async function bindSelectedDevice\(event\) \{[\s\S]*?if \(!requireDeviceBindingLogin\(\)\) return;/);
  assert.match(runtime, /setDeviceStatus\("请先登录云端账号，再绑定设备。"/);

  assert.match(deviceHtml, /data-action="scan-rehab-device"/);
  assert.match(deviceHtml, /id="bluetoothUnavailable"/);
  assert.doesNotMatch(deviceHtml, /data-device-id="demo/i);

  console.log("device binding isolation PASS");
}

try {
  main();
} catch (error) {
  console.error(error);
  process.exit(1);
}
