const { spawn } = require("child_process");
const path = require("path");

const nextBin = require.resolve("next/dist/bin/next");
const workspaceRoot = path.resolve(__dirname, "..");

const child = spawn(process.execPath, [nextBin, "dev", ...process.argv.slice(2)], {
  cwd: workspaceRoot,
  stdio: "inherit",
  env: {
    ...process.env,
    NEXT_DIST_DIR: process.env.NEXT_DIST_DIR || ".next-dev",
  },
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
