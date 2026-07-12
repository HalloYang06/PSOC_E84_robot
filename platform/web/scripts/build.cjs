const { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } = require("fs");
const { spawnSync } = require("child_process");
const path = require("path");

const nextBin = require.resolve("next/dist/bin/next");
const gracefulFs = require.resolve("graceful-fs");
const workspaceRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(workspaceRoot, "..", "..");
const runtimeHome = path.join(repoRoot, ".codex-runtime");
const publishedDistDir = process.env.NEXT_PUBLISH_DIST_DIR?.trim() || ".next-prod";
const finalNextDir = path.join(workspaceRoot, publishedDistDir);
const stagingNextDir = path.join(workspaceRoot, `.next-build-staging-${process.pid}`);
const tsconfigPath = path.join(workspaceRoot, "tsconfig.json");

function removeDir(dir) {
  rmSync(dir, {
    recursive: true,
    force: true,
    maxRetries: 10,
    retryDelay: 200,
  });
}

function cleanArtifacts() {
  removeDir(stagingNextDir);
  mkdirSync(stagingNextDir, { recursive: true });
}

function sanitizeTsConfigIncludes() {
  if (!existsSync(tsconfigPath)) return;
  const raw = readFileSync(tsconfigPath, "utf8");
  const config = JSON.parse(raw);
  if (!Array.isArray(config.include)) return;
  const nextInclude = config.include.filter((item) => {
    const value = String(item ?? "");
    return value === ".next/types/**/*.ts" || !value.startsWith(".next-");
  });
  if (nextInclude.length === config.include.length) return;
  config.include = nextInclude;
  writeFileSync(tsconfigPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");
}

mkdirSync(runtimeHome, { recursive: true });

const buildEnv = {
  ...process.env,
  NODE_ENV: "production",
  AI_COLLAB_SKIP_LOCAL_PROVIDER_SCANS: "1",
  HOME: runtimeHome,
  USERPROFILE: runtimeHome,
  CODEX_HOME: runtimeHome,
  NEXT_DIST_DIR: path.basename(stagingNextDir),
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
  restoreAppPathsManifestIfEmpty(stagingNextDir);
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
  const missing = requiredFiles.filter((relativePath) => !existsSync(path.join(stagingNextDir, relativePath)));
  const appPathsManifestPath = path.join(stagingNextDir, "server/app-paths-manifest.json");
  const hasAppRoutes = existsSync(path.join(stagingNextDir, "server/app"));
  const hasAppPathsManifest = existsSync(appPathsManifestPath) && Object.keys(readJsonFile(appPathsManifestPath, {})).length > 0;
  const hasRouteManifest =
    (!hasAppRoutes || hasAppPathsManifest) && existsSync(path.join(stagingNextDir, "server/pages-manifest.json"));
  if (!hasRouteManifest) {
    missing.push("non-empty server/app-paths-manifest.json and server/pages-manifest.json");
  }
  const buildIdPath = path.join(stagingNextDir, "BUILD_ID");
  if (existsSync(buildIdPath) && !readFileSync(buildIdPath, "utf8").trim()) {
    missing.push("BUILD_ID is empty");
  }
  return missing;
}

function publishArtifacts() {
  const backupDir = path.join(workspaceRoot, `.next-build-backup-${process.pid}`);
  removeDir(backupDir);
  try {
    if (existsSync(finalNextDir)) {
      renameSync(finalNextDir, backupDir);
    }
    try {
      renameSync(stagingNextDir, finalNextDir);
      rewritePublishedServerFiles();
      restoreAppPathsManifestIfEmpty(finalNextDir);
      console.warn(
        `[web build] Published app route manifest entries: ${countAppPathsManifestEntries(finalNextDir)}.`,
      );
      verifyPublishedAppPathsManifest();
      removeDir(backupDir);
      return true;
    } catch (error) {
      if (existsSync(backupDir) && !existsSync(finalNextDir)) {
        renameSync(backupDir, finalNextDir);
      }
      throw error;
    }
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "EPERM") {
      console.warn(
        `[web build] Build completed in ${path.relative(workspaceRoot, stagingNextDir)}, but existing ${publishedDistDir} is locked by another process. Stop the running web server to publish into ${publishedDistDir}.`,
      );
      return false;
    }
    throw error;
  }
}

function rewritePublishedServerFiles() {
  const requiredFilesPath = path.join(finalNextDir, "required-server-files.json");
  if (!existsSync(requiredFilesPath)) return;
  const raw = readFileSync(requiredFilesPath, "utf8");
  const manifest = JSON.parse(raw);
  const stagingName = path.basename(stagingNextDir);
  if (manifest.config && typeof manifest.config === "object") {
    manifest.config.distDir = publishedDistDir;
  }
  if (Array.isArray(manifest.files)) {
    manifest.files = manifest.files.map((file) => String(file).replaceAll(stagingName, publishedDistDir));
  }
  writeFileSync(requiredFilesPath, `${JSON.stringify(manifest)}\n`, "utf8");
}

function readJsonFile(filePath, fallback) {
  try {
    return JSON.parse(readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

function restoreAppPathsManifestIfEmpty(nextDir) {
  const manifestPath = path.join(nextDir, "server/app-paths-manifest.json");
  const existing = readJsonFile(manifestPath, {});
  if (Object.keys(existing).length > 0) return;

  const routeManifestPath = path.join(nextDir, "app-path-routes-manifest.json");
  const routeManifest = readJsonFile(routeManifestPath, {});
  const serverAppDir = path.join(nextDir, "server/app");
  const restored = {};

  for (const appPath of Object.keys(routeManifest)) {
    const relativePath = `${appPath.replace(/^\/+/, "")}.js`;
    const outputPath = path.join(serverAppDir, relativePath);
    if (existsSync(outputPath)) {
      restored[appPath] = path.posix.join("app", relativePath.replaceAll(path.sep, "/"));
    }
  }

  if (Object.keys(restored).length === 0 && existsSync(serverAppDir)) {
    for (const relativePath of collectServerAppEntries(serverAppDir)) {
      const appPath = `/${relativePath.replace(/\.js$/, "")}`;
      restored[appPath] = path.posix.join("app", relativePath.replaceAll(path.sep, "/"));
    }
  }

  if (Object.keys(restored).length === 0) {
    throw new Error("Unable to restore server/app-paths-manifest.json from published app artifacts.");
  }
  writeFileSync(manifestPath, `${JSON.stringify(restored, null, 2)}\n`, "utf8");
  console.warn(`[web build] Restored ${Object.keys(restored).length} app route entries in ${path.relative(workspaceRoot, manifestPath)}.`);
}

function collectServerAppEntries(dir, prefix = "") {
  const entries = [];
  for (const item of readdirSync(dir)) {
    const absolutePath = path.join(dir, item);
    const relativePath = path.join(prefix, item);
    if (statSync(absolutePath).isDirectory()) {
      entries.push(...collectServerAppEntries(absolutePath, relativePath));
      continue;
    }
    if (item === "page.js" || item === "route.js") {
      entries.push(relativePath);
    }
  }
  return entries;
}

function verifyPublishedAppPathsManifest() {
  const serverAppDir = path.join(finalNextDir, "server/app");
  if (!existsSync(serverAppDir)) return;
  const manifestPath = path.join(finalNextDir, "server/app-paths-manifest.json");
  const manifest = readJsonFile(manifestPath, {});
  if (Object.keys(manifest).length === 0) {
    throw new Error("Published server/app-paths-manifest.json is empty, so Next production app routes would 404.");
  }
}

function countAppPathsManifestEntries(nextDir) {
  return Object.keys(readJsonFile(path.join(nextDir, "server/app-paths-manifest.json"), {})).length;
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
  sanitizeTsConfigIncludes();
  cleanArtifacts();
  try {
    result = runNextBuild();
  } finally {
    sanitizeTsConfigIncludes();
  }
  if (result.status === 0) {
    const missing = verifyArtifacts();
    if (missing.length === 0) {
      publishArtifacts();
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
