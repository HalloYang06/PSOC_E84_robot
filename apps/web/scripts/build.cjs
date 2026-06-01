const { mkdirSync, rmSync } = require("fs");
const { spawnSync } = require("child_process");
const path = require("path");

const nextBin = require.resolve("next/dist/bin/next");
const gracefulFs = require.resolve("graceful-fs");
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

mkdirSync(runtimeHome, { recursive: true });

const buildEnv = {
  ...process.env,
  NODE_ENV: "production",
  AI_COLLAB_SKIP_LOCAL_PROVIDER_SCANS: "1",
  HOME: runtimeHome,
  USERPROFILE: runtimeHome,
  CODEX_HOME: runtimeHome,
};

function runNextBuild() {
  const result = spawnSync(process.execPath, ["-r", gracefulFs, nextBin, "build"], {
    cwd: workspaceRoot,
    env: buildEnv,
    encoding: "utf8",
    maxBuffer: 50 * 1024 * 1024,
  });
  if (result.stdout) {
    process.stdout.write(result.stdout);
  }
  if (result.stderr) {
    process.stderr.write(result.stderr);
  }
  return result;
}

function isRecoverableManifestRace(result) {
  if (result.error) {
    return false;
  }
  if (result.status === 0) {
    return false;
  }
  const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
  return (
    output.includes("ENOENT") &&
    (output.includes("build-manifest.json") ||
      output.includes("_ssgManifest.js") ||
      output.includes(".next/static/"))
  );
}

let result;
for (let attempt = 1; attempt <= 2; attempt += 1) {
  cleanArtifacts();
  result = runNextBuild();
  if (result.status === 0) {
    process.exit(0);
  }
  if (attempt === 1 && isRecoverableManifestRace(result)) {
    console.warn("[web build] Next build failed once; retrying after a clean artifact pass.");
    continue;
  }
  break;
}

if (result.error) {
  throw result.error;
}
process.exit(result.status ?? 1);
