import { spawnSync } from "node:child_process";
import fs from "node:fs";

const checks = [
  ["java", ["-version"]],
  ["javac", ["-version"]],
  ["adb", ["version"]],
  ["sdkmanager.bat", ["--list_installed"]]
];

for (const [cmd, args] of checks) {
  const result = spawnSync(cmd, args, { stdio: "inherit", shell: true });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

for (const required of ["www/index.html", "capacitor.config.json"]) {
  if (!fs.existsSync(required)) {
    throw new Error(`Missing ${required}`);
  }
}

console.log("Android wrapper environment looks ready.");
