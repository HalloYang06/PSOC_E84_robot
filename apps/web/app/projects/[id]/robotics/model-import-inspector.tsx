"use client";

import { useState } from "react";
import styles from "./robotics.module.css";

type ModelInfo = {
  fileName: string;
  format: string;
  joints: number;
  movableJoints: number;
  source: string;
};

const emptyInfo: ModelInfo = {
  fileName: "未导入模型",
  format: "URDF / GLTF",
  joints: 0,
  movableJoints: 0,
  source: "本地解析，不上传文件",
};

function countUrdfJoints(text: string) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  const joints = Array.from(doc.querySelectorAll("joint"));
  const movable = joints.filter((joint) => {
    const type = joint.getAttribute("type")?.toLowerCase();
    return type && !["fixed", "floating"].includes(type);
  });
  return { joints: joints.length, movableJoints: movable.length || joints.length };
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
  const skinJoints = Array.isArray(model?.skins)
    ? model.skins.reduce((total: number, skin: any) => total + (Array.isArray(skin?.joints) ? skin.joints.length : 0), 0)
    : 0;
  const namedJoints = Array.isArray(model?.nodes)
    ? model.nodes.filter((node: any) => /joint|axis|link/i.test(String(node?.name ?? ""))).length
    : 0;
  const joints = skinJoints || namedJoints;
  return { joints, movableJoints: joints };
}

export function ModelImportInspector() {
  const [info, setInfo] = useState<ModelInfo>(emptyInfo);
  const [error, setError] = useState("");

  async function inspect(file: File) {
    setError("");
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    try {
      if (["urdf", "xml"].includes(ext)) {
        const result = countUrdfJoints(await file.text());
        setInfo({ fileName: file.name, format: "URDF", source: "已解析 XML joint", ...result });
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
      setInfo({ fileName: file.name, format: ext.toUpperCase() || "未知", joints: 0, movableJoints: 0, source: "已登记，等待 Runner 或插件解析" });
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
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void inspect(file);
          }}
        />
      </label>
      <dl>
        <div><dt>格式</dt><dd>{info.format}</dd></div>
        <div><dt>总关节</dt><dd>{info.joints}</dd></div>
        <div><dt>可动</dt><dd>{info.movableJoints}</dd></div>
      </dl>
      {error ? <p className={styles.importError}>{error}</p> : null}
    </section>
  );
}
