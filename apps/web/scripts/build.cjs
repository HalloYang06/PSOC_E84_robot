const { mkdirSync, rmSync } = require("fs");
const path = require("path");

const nextBin = require.resolve("next/dist/bin/next");
const workspaceRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(workspaceRoot, "..", "..");
const runtimeHome = path.join(repoRoot, ".codex-runtime");

function cleanArtifacts() {
  const nextDir = path.join(workspaceRoot, ".next");
  rmSync(nextDir, {
    recursive: true,
    force: true,
    maxRetries: 5,
    retryDelay: 100,
  });
}

cleanArtifacts();
mkdirSync(runtimeHome, { recursive: true });
process.chdir(workspaceRoot);
process.env.NODE_ENV = "production";
process.env.AI_COLLAB_SKIP_LOCAL_PROVIDER_SCANS = "1";
process.env.HOME = runtimeHome;
process.env.USERPROFILE = runtimeHome;
process.env.CODEX_HOME = runtimeHome;
process.argv = [process.execPath, nextBin, "build"];

require("graceful-fs");
require(nextBin);
