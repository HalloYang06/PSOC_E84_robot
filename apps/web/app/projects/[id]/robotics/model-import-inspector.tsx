"use client";

import { useState } from "react";
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
  }));
  const movable = joints.filter((joint) => {
    const type = joint.getAttribute("type")?.toLowerCase();
    return type && !["fixed", "floating"].includes(type);
  });
  const warnings = [
    links.length === 0 ? "没有发现 link，可能不是完整 URDF。" : "",
    jointDetails.some((joint) => joint.parent === "-" || joint.child === "-") ? "部分 joint 缺 parent/child。" : "",
  ].filter(Boolean);
  return {
    joints: joints.length,
    movableJoints: movable.length || joints.length,
    jointDetails,
    linkCount: links.length,
    warnings,
  };
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

  function handleFileSelection(file: File | undefined) {
    if (file) void inspect(file);
  }

  async function inspect(file: File) {
    setError("");
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    try {
      if (["urdf", "xml"].includes(ext)) {
        const result = countUrdfJoints(await file.text());
        setInfo({ fileName: file.name, format: "URDF", source: "已解析 link / joint / parent-child", ...result });
        return;
      }
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
      <dl>
        <div><dt>格式</dt><dd>{info.format}</dd></div>
        <div><dt>总关节</dt><dd>{info.joints}</dd></div>
        <div><dt>可动</dt><dd>{info.movableJoints}</dd></div>
      </dl>
      <div className={styles.modelActions}>
        <button type="button" data-testid="robotics-model-export" disabled={info.fileName === emptyInfo.fileName} onClick={() => downloadManifest(info)}>
          导出 manifest
        </button>
      </div>
      <div className={styles.jointList}>
        {info.jointDetails.length ? info.jointDetails.slice(0, 6).map((joint) => (
          <article key={`${joint.name}-${joint.child}`}>
            <strong>{joint.name}</strong>
            <span>{joint.type}</span>
            <small>{joint.parent} {"->"} {joint.child}</small>
          </article>
        )) : <p>导入 URDF/GLTF 后显示关节明细。</p>}
      </div>
      {info.warnings.length ? <div className={styles.modelWarnings}>{info.warnings.map((item) => <p key={item}>{item}</p>)}</div> : null}
      {error ? <p className={styles.importError}>{error}</p> : null}
    </section>
  );
}
