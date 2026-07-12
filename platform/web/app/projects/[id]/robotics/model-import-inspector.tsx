"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./robotics.module.css";

type ModelInfo = {
  fileName: string;
  format: string;
  joints: number;
  movableJoints: number;
  source: string;
  jointDetails: JointDetail[];
  linkCount: number;
  warnings: string[];
};

type JointDetail = {
  name: string;
  type: string;
  parent: string;
  child: string;
  lower?: string;
  upper?: string;
  axis?: string;
};

const emptyInfo: ModelInfo = {
  fileName: "未导入模型",
  format: "URDF / GLTF",
  joints: 0,
  movableJoints: 0,
  source: "浏览器轻量解析，不上传文件",
  jointDetails: [],
  linkCount: 0,
  warnings: [],
};

function countUrdfJoints(text: string) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  const parseError = doc.getElementsByTagName("parsererror")[0];
  if (parseError) throw new Error("invalid xml");
  const joints = Array.from(doc.getElementsByTagName("joint"));
  const links = Array.from(doc.getElementsByTagName("link"));
  const jointDetails = joints.map((joint, index) => ({
      name: joint.getAttribute("name") || `joint_${index + 1}`,
      type: joint.getAttribute("type") || "unknown",
      parent: joint.getElementsByTagName("parent")[0]?.getAttribute("link") || "-",
      child: joint.getElementsByTagName("child")[0]?.getAttribute("link") || "-",
      lower: joint.getElementsByTagName("limit")[0]?.getAttribute("lower") || "",
      upper: joint.getElementsByTagName("limit")[0]?.getAttribute("upper") || "",
      axis: joint.getElementsByTagName("axis")[0]?.getAttribute("xyz") || "",
    }));
  const movable = joints.filter((joint) => {
    const type = joint.getAttribute("type")?.toLowerCase();
    return type && !["fixed", "floating"].includes(type);
  });
  const warnings = [
    links.length === 0 ? "没有发现结构段，可能不是完整 URDF。" : "",
    jointDetails.some((joint) => joint.parent === "-" || joint.child === "-") ? "部分关节缺少父子结构。" : "",
  ].filter(Boolean);
  return {
    joints: joints.length,
    movableJoints: movable.length || joints.length,
    jointDetails,
    linkCount: links.length,
    warnings,
  };
}

function UrdfPreview({ urdfText, fileName }: { urdfText: string; fileName: string }) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [viewerState, setViewerState] = useState("等待导入 URDF");

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !urdfText) {
      setViewerState(urdfText ? "等待预览容器" : "等待导入 URDF");
      return;
    }

    let disposed = false;
    let cleanup = () => {};

    async function renderUrdf() {
      try {
        setViewerState("正在加载 three.js / urdf-loader");
        const THREE = await import("three");
        const { default: URDFLoader } = await import("urdf-loader");
        const previewMount = mountRef.current;
        if (disposed || !previewMount) return;

        const width = Math.max(320, previewMount.clientWidth || 640);
        const height = Math.max(260, previewMount.clientHeight || 320);
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x07110f);

        const camera = new THREE.PerspectiveCamera(42, width / height, 0.01, 100);
        camera.position.set(1.25, -1.7, 1.15);
        camera.lookAt(0.22, 0, 0.22);

        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.setSize(width, height);
        renderer.domElement.setAttribute("aria-label", `${fileName} URDF 预览`);
        previewMount.replaceChildren(renderer.domElement);

        scene.add(new THREE.HemisphereLight(0xeefcf7, 0x17312a, 2.4));
        const keyLight = new THREE.DirectionalLight(0xf1d06b, 1.2);
        keyLight.position.set(1.4, -1.8, 2.4);
        scene.add(keyLight);

        const grid = new THREE.GridHelper(1.4, 14, 0x3f7769, 0x183a32);
        grid.rotation.x = Math.PI / 2;
        scene.add(grid);

        const loader = new URDFLoader();
        loader.packages = "";
        loader.loadMeshCb = (_url, _manager, done) => {
          done(new THREE.Group(), new Error("external mesh is not loaded in browser preview"));
        };
        const robot = loader.parse(urdfText);
        robot.rotation.x = -Math.PI / 2;
        robot.traverse((object) => {
          const mesh = object as any;
          if (mesh.isMesh && mesh.material) {
            mesh.material = new THREE.MeshStandardMaterial({
              color: 0x8ef0c7,
              roughness: 0.68,
              metalness: 0.08,
            });
          }
        });
        scene.add(robot);

        let frame = 0;
        const animate = () => {
          if (disposed) return;
          frame = window.requestAnimationFrame(animate);
          robot.rotation.z += 0.003;
          renderer.render(scene, camera);
        };
        animate();
        setViewerState("URDF 已渲染为只读模型预览");

        cleanup = () => {
          window.cancelAnimationFrame(frame);
          renderer.dispose();
          scene.clear();
          if (previewMount.contains(renderer.domElement)) previewMount.removeChild(renderer.domElement);
        };
      } catch {
        setViewerState("3D 预览失败，仍可使用下方结构解析结果");
      }
    }

    void renderUrdf();
    return () => {
      disposed = true;
      cleanup();
    };
  }, [fileName, urdfText]);

  return (
    <div className={styles.urdfPreviewShell}>
      <div ref={mountRef} className={styles.urdfPreviewCanvas} />
      <p>{viewerState}</p>
    </div>
  );
}

function parseGlbJson(buffer: ArrayBuffer) {
  const view = new DataView(buffer);
  if (view.getUint32(0, true) !== 0x46546c67) return null;
  const jsonLength = view.getUint32(12, true);
  const jsonType = view.getUint32(16, true);
  if (jsonType !== 0x4e4f534a) return null;
  const bytes = new Uint8Array(buffer, 20, jsonLength);
  return JSON.parse(new TextDecoder("utf-8").decode(bytes));
}

function countGltfJoints(model: any) {
  const nodes = Array.isArray(model?.nodes) ? model.nodes : [];
  const skinJoints = Array.isArray(model?.skins)
    ? model.skins.reduce((total: number, skin: any) => total + (Array.isArray(skin?.joints) ? skin.joints.length : 0), 0)
    : 0;
  const namedNodes = nodes.filter((node: any) => /joint|axis|link/i.test(String(node?.name ?? "")));
  const namedJoints = namedNodes.length;
  const joints = skinJoints || namedJoints;
  const jointDetails = namedNodes.slice(0, 12).map((node: any, index: number) => ({
    name: String(node?.name ?? `node_${index + 1}`),
    type: "node",
    parent: "-",
    child: "-",
  }));
  return {
    joints,
    movableJoints: joints,
    jointDetails,
    linkCount: nodes.length,
    warnings: joints ? [] : ["GLTF 未发现 skin joints 或 joint/link 命名节点。"],
  };
}

function downloadManifest(info: ModelInfo) {
  const manifest = {
    fileName: info.fileName,
    format: info.format,
    joints: info.joints,
    movableJoints: info.movableJoints,
    linkCount: info.linkCount,
    jointDetails: info.jointDetails,
    warnings: info.warnings,
    source: "AI Collab Platform local model inspector",
  };
  const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${info.fileName.replace(/\.[^.]+$/, "") || "robot-model"}-manifest.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ModelImportInspector() {
  const [info, setInfo] = useState<ModelInfo>(emptyInfo);
  const [error, setError] = useState("");
  const [urdfText, setUrdfText] = useState("");

  function handleFileSelection(file: File | undefined) {
    if (file) void inspect(file);
  }

  async function inspect(file: File) {
    setError("");
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    try {
      if (["urdf", "xml"].includes(ext)) {
        const text = await file.text();
        const result = countUrdfJoints(text);
        setUrdfText(text);
        setInfo({ fileName: file.name, format: "URDF", source: "已解析结构段、关节和父子关系", ...result });
        return;
      }
      setUrdfText("");
      if (ext === "gltf") {
        const result = countGltfJoints(JSON.parse(await file.text()));
        setInfo({ fileName: file.name, format: "GLTF", source: "已解析 skin/node", ...result });
        return;
      }
      if (ext === "glb") {
        const json = parseGlbJson(await file.arrayBuffer());
        const result = countGltfJoints(json);
        setInfo({ fileName: file.name, format: "GLB", source: json ? "已解析 JSON chunk" : "无法读取 GLB JSON", ...result });
        return;
      }
      setInfo({
        fileName: file.name,
        format: ext.toUpperCase() || "未知",
        joints: 0,
        movableJoints: 0,
        jointDetails: [],
        linkCount: 0,
        source: "已登记，等待执行电脑或插件解析",
        warnings: ["当前浏览器只做轻量解析，STL/mesh 细节交给执行电脑插件。"],
      });
    } catch {
      setUrdfText("");
      setError("模型解析失败，请检查文件格式。");
    }
  }

  return (
    <section className={styles.modelInspector}>
      <div>
        <span>模型导入</span>
        <strong>{info.fileName}</strong>
        <p>{info.source}</p>
      </div>
      <label>
        选择 URDF / GLTF / GLB / STL
        <input
          type="file"
          accept=".urdf,.xml,.gltf,.glb,.stl"
          data-testid="robotics-model-file"
          onChange={(event) => {
            handleFileSelection(event.target.files?.[0]);
          }}
          onInput={(event) => {
            handleFileSelection((event.currentTarget as HTMLInputElement).files?.[0]);
          }}
        />
      </label>
      <UrdfPreview urdfText={urdfText} fileName={info.fileName} />
      <dl>
        <div><dt>格式</dt><dd>{info.format}</dd></div>
        <div><dt>link</dt><dd>{info.linkCount}</dd></div>
        <div><dt>总关节</dt><dd>{info.joints}</dd></div>
        <div><dt>可动</dt><dd>{info.movableJoints}</dd></div>
      </dl>
      <div className={styles.modelActions}>
        <button type="button" data-testid="robotics-model-export" disabled={info.fileName === emptyInfo.fileName} onClick={() => downloadManifest(info)}>
          导出项目清单
        </button>
      </div>
      <div className={styles.jointList}>
        {info.jointDetails.length ? info.jointDetails.slice(0, 6).map((joint) => (
          <article key={`${joint.name}-${joint.child}`}>
            <strong>{joint.name}</strong>
            <span>{joint.type}</span>
            <small>{joint.parent} {"->"} {joint.child}</small>
            {joint.lower || joint.upper ? <small>限制 {joint.lower || "-∞"} ~ {joint.upper || "+∞"}</small> : null}
            {joint.axis ? <small>axis {joint.axis}</small> : null}
          </article>
        )) : <p>导入 URDF/GLTF 后显示关节明细。</p>}
      </div>
      {info.warnings.length ? <div className={styles.modelWarnings}>{info.warnings.map((item) => <p key={item}>{item}</p>)}</div> : null}
      {error ? <p className={styles.importError}>{error}</p> : null}
    </section>
  );
}
