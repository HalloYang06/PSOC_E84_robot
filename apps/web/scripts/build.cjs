const { existsSync, mkdirSync, readFileSync, rmSync } = require("fs");
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
  mkdirSync(nextDir, { recursive: true });
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

function verifyArtifacts() {
  const nextDir = path.join(workspaceRoot, ".next");
  const requiredFiles = [
    "BUILD_ID",
    "package.json",
    "build-manifest.json",
    "prerender-manifest.json",
    "react-loadable-manifest.json",
    "required-server-files.json",
    "routes-manifest.json",
    "server/middleware-manifest.json",
  ];
  const missing = requiredFiles.filter((relativePath) => !existsSync(path.join(nextDir, relativePath)));
  const hasRouteManifest =
    existsSync(path.join(nextDir, "server/app-paths-manifest.json")) ||
    existsSync(path.join(nextDir, "server/pages-manifest.json"));
  if (!hasRouteManifest) {
    missing.push("server/app-paths-manifest.json or server/pages-manifest.json");
  }
  const buildIdPath = path.join(nextDir, "BUILD_ID");
  if (existsSync(buildIdPath) && !readFileSync(buildIdPath, "utf8").trim()) {
    missing.push("BUILD_ID is empty");
  }
  return missing;
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
      output.includes("font-manifest.json") ||
      output.includes("pages-manifest.json") ||
      output.includes(".nft.json") ||
      output.includes("collect-build-traces") ||
      output.includes(".next\\package.json") ||
      output.includes(".next/package.json") ||
      output.includes(".next\\export\\") ||
      output.includes(".next/export/") ||
      output.includes("_ssgManifest.js") ||
      output.includes(".next/static/"))
  );
}

let result;
for (let attempt = 1; attempt <= 3; attempt += 1) {
  cleanArtifacts();
  result = runNextBuild();
  if (result.status === 0) {
    const missing = verifyArtifacts();
    if (missing.length === 0) {
      process.exit(0);
    }
    console.warn(`[web build] Next build completed but artifacts are incomplete: ${missing.join(", ")}`);
    if (attempt < 3) {
      console.warn("[web build] Retrying after a clean artifact pass.");
      result = { status: 1 };
      continue;
    }
    result = { status: 1 };
    break;
  }
  if (attempt < 3 && isRecoverableManifestRace(result)) {
    console.warn("[web build] Next build failed once; retrying after a clean artifact pass.");
    continue;
  }
  break;
}

if (result.error) {
  throw result.error;
}
process.exit(result.status ?? 1);
