import fs from "node:fs";
import path from "node:path";

import Link from "next/link";
import { redirect } from "next/navigation";

import { getProjectState } from "../../../../lib/server-data";
import styles from "./unity-client.module.css";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type UnityManifest = {
  productName?: string;
  status?: string;
  generatedAtUtc?: string;
  unityProjectPath?: string;
  sourceProjectPath?: string;
  scenePath?: string;
  buildTarget?: string;
  outputPath?: string;
  webglSupported?: boolean;
  notes?: string;
  buildSourceNote?: string;
};

const UNITY_PUBLIC_PATH = "/unity/education2d";
const UNITY_PROJECT_PATH = "D:/unity_project/My project";
const UNITY_SCENE_PATH = "Assets/Education2D/Scenes/ReferenceBuilds/Education2D_Ref_InteriorLab.unity";
const TUANJIE_WEBGL_SUPPORT_PATH = "D:/unity/2022.3.62t7/Editor/Data/PlaybackEngines/WebGLSupport";

function getUnityBrowserApiBaseUrl() {
  return (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8010").trim().replace(/\/$/, "");
}

function readJson<T>(filePath: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8")) as T;
  } catch {
    return null;
  }
}

function fileExists(filePath: string) {
  try {
    return fs.existsSync(filePath);
  } catch {
    return false;
  }
}

function readBuildFileNames(buildDir: string) {
  if (!fileExists(buildDir)) {
    return [];
  }

  try {
    return fs.readdirSync(buildDir);
  } catch {
    return [];
  }
}

function getUnityClientState() {
  const publicRoot = path.join(process.cwd(), "public", "unity", "education2d");
  const manifestPath = path.join(publicRoot, "manifest.json");
  const indexPath = path.join(publicRoot, "index.html");
  const previewPath = path.join(publicRoot, "preview.png");
  const buildDir = path.join(publicRoot, "Build");
  const buildFiles = readBuildFileNames(buildDir);
  const loader = buildFiles.find((file) => file.includes(".loader.js")) || "";
  const wasm = buildFiles.find((file) => file.includes(".wasm")) || "";
  const data = buildFiles.find((file) => file.includes(".data")) || "";
  const framework = buildFiles.find((file) => file.includes(".framework.js")) || "";

  return {
    publicRoot,
    manifest: readJson<UnityManifest>(manifestPath),
    hasIndex: fileExists(indexPath),
    hasPreview: fileExists(previewPath),
    hasUnityProject: fileExists(path.join(UNITY_PROJECT_PATH, UNITY_SCENE_PATH)),
    hasBridgeScript: fileExists(path.join(UNITY_PROJECT_PATH, "Assets/Education2D/Scripts/Education2DPlatformBridge.cs")),
    hasWebglSupport: fileExists(TUANJIE_WEBGL_SUPPORT_PATH),
    loader,
    wasm,
    data,
    framework,
    isPlayable: fileExists(indexPath) && Boolean(loader && wasm && data && framework),
  };
}

function statusText(status?: string) {
  if (status === "ready") return "可嵌入";
  if (status === "webgl_support_missing") return "缺少 WebGL 模块";
  if (status === "build_failed") return "构建失败";
  if (status === "manifest_only") return "已接入平台壳";
  return "等待 Unity 构建";
}

function projectAccessMessage(status: number) {
  if (status === 403) {
    return "当前账号没有这个项目的访问权限，请从项目列表重新进入。";
  }

  return "这个项目不存在，或者你没有被授权访问。";
}

export default async function UnityClientPage({ params }: { params: { id: string } }) {
  const projectState = await getProjectState(params.id);
  const returnTo = encodeURIComponent(`/projects/${params.id}/unity-client`);

  if (projectState.status === 401) {
    redirect(`/login?returnTo=${returnTo}`);
  }
  if (projectState.status === 403 || projectState.status === 404) {
    redirect(`/projects?tab=projects&team_error=${encodeURIComponent(projectAccessMessage(projectState.status))}`);
  }

  const project = projectState.data as Record<string, unknown>;
  const unityState = getUnityClientState();
  const manifest = unityState.manifest;
  const displayStatus = unityState.isPlayable ? "ready" : manifest?.status;
  const unityApiBaseUrl = getUnityBrowserApiBaseUrl();
  const unityLaunchQuery = new URLSearchParams({
    projectId: params.id,
    serverBaseUrl: unityApiBaseUrl,
  }).toString();

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>Unity 客户端接入现场</p>
          <h1>{String(project.name ?? "当前项目")} / Education2D</h1>
          <p>
            这里是平台的正式 Unity 客户端入口。旧农场底座不会在这里继续堆功能；Unity WebGL 包落到
            <code>public/unity/education2d</code>
            后，本页会直接嵌入可玩的 Unity 版本，并自动带上当前项目和 API 地址。
          </p>
        </div>
        <div className={styles.actions}>
          <Link href="/projects" className={styles.secondaryButton}>返回项目列表</Link>
          <Link href={`/projects/${params.id}/2d-upgrade`} className={styles.secondaryButton}>查看 2D 升级入口</Link>
          <Link href={`/projects/${params.id}`} className={styles.secondaryButton}>回当前协作页</Link>
        </div>
      </section>

      <section className={styles.statusGrid} aria-label="Unity 接入状态">
        <article>
          <span>平台入口</span>
          <strong>已创建</strong>
          <p>/projects/[id]/unity-client</p>
        </article>
        <article>
          <span>Unity 源工程</span>
          <strong>{unityState.hasUnityProject ? "已识别" : "未找到"}</strong>
          <p>{manifest?.sourceProjectPath || UNITY_PROJECT_PATH}</p>
        </article>
        <article>
          <span>后端桥接脚本</span>
          <strong>{unityState.hasBridgeScript ? "已挂载" : "缺失"}</strong>
          <p>Education2DPlatformBridge</p>
        </article>
        <article className={unityState.hasWebglSupport ? styles.okCard : styles.warnCard}>
          <span>WebGL 导出模块</span>
          <strong>{unityState.hasWebglSupport ? "已识别" : "未安装"}</strong>
          <p>
            当前使用 Tuanjie 2022.3.62t7 的 WebGLSupport 做安全副本构建，避免直接改动源工程。
          </p>
        </article>
        <article className={styles.okCard}>
          <span>平台启动参数</span>
          <strong>自动注入</strong>
          <p>Unity WebGL 启动后会读取 projectId 和 serverBaseUrl，不再让用户手动填写项目。</p>
        </article>
      </section>

      <section className={styles.playerShell}>
        <div className={styles.playerTopbar}>
          <div>
            <span>{statusText(displayStatus)}</span>
            <strong>{manifest?.productName || "A Agent Education2D Unity Client"}</strong>
          </div>
          <small>{manifest?.generatedAtUtc ? `Manifest: ${manifest.generatedAtUtc}` : "Manifest 尚未生成"}</small>
        </div>

        {unityState.isPlayable ? (
          <iframe
            title="A Agent Education2D Unity WebGL"
            className={styles.unityFrame}
            src={`${UNITY_PUBLIC_PATH}/index.html?${unityLaunchQuery}`}
            allow="fullscreen; gamepad; clipboard-read; clipboard-write"
          />
        ) : (
          <div className={styles.pendingBuild}>
            {unityState.hasPreview ? (
              <img src={`${UNITY_PUBLIC_PATH}/preview.png`} alt="Unity Education2D 当前场景预览" />
            ) : (
              <div className={styles.previewPlaceholder}>A</div>
            )}
            <div>
              <p className={styles.eyebrow}>下一步不是再改 React 假游戏</p>
              <h2>等待 Unity WebGL 构建落入平台目录</h2>
              <p>
                平台构建脚本已经固定为 <code>scripts/build-unity-education2d-webgl.ps1</code>。
                如果构建文件完整，本页会自动切换为可玩 iframe；如果失败，会继续显示缺失文件，方便定位。
              </p>
              <ol>
                <li>用兼容的 Tuanjie 2022.3.62t7 生成临时 ASCII 工程副本。</li>
                <li>执行 Unity WebGL 构建，输出到 Web public 目录。</li>
                <li>刷新本页，确认 index、loader、wasm、data、framework 五类文件全部存在。</li>
              </ol>
            </div>
          </div>
        )}
      </section>

      <section className={styles.detailPanel}>
        <h2>构建文件检查</h2>
        <dl>
          <div><dt>index.html</dt><dd>{unityState.hasIndex ? "存在" : "缺失"}</dd></div>
          <div><dt>loader.js</dt><dd>{unityState.loader || "缺失"}</dd></div>
          <div><dt>wasm</dt><dd>{unityState.wasm || "缺失"}</dd></div>
          <div><dt>data</dt><dd>{unityState.data || "缺失"}</dd></div>
          <div><dt>framework</dt><dd>{unityState.framework || "缺失"}</dd></div>
          <div><dt>输出目录</dt><dd>{unityState.publicRoot}</dd></div>
          <div><dt>Unity API</dt><dd>{unityApiBaseUrl}</dd></div>
          <div><dt>启动参数</dt><dd>{`?${unityLaunchQuery}`}</dd></div>
        </dl>
        {manifest?.notes ? <p className={styles.notes}>{manifest.notes}</p> : null}
        {manifest?.buildSourceNote ? <p className={styles.notes}>{manifest.buildSourceNote}</p> : null}
      </section>
    </main>
  );
}
