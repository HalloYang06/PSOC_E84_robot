const { spawn } = require("child_process");
const path = require("path");

const nextBin = require.resolve("next/dist/bin/next");
const workspaceRoot = path.resolve(__dirname, "..");
const distDir = process.env.NEXT_DIST_DIR?.trim() || ".next-prod";
process.env.NEXT_DIST_DIR = distDir;

const child = spawn(process.execPath, [nextBin, "start", ...process.argv.slice(2)], {
  cwd: workspaceRoot,
  stdio: "inherit",
  env: {
    ...process.env,
    NEXT_DIST_DIR: distDir,
  },
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
