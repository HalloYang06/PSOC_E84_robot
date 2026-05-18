"use client";

import { useMemo, useState } from "react";
import styles from "./robotics.module.css";

type TopicStatus = "ready" | "missing" | "blocked";

const requiredTopics = [
  { name: "/robot_description", type: "std_msgs/String", purpose: "模型" },
  { name: "/tf", type: "tf2_msgs/TFMessage", purpose: "坐标" },
  { name: "/joint_states", type: "sensor_msgs/JointState", purpose: "关节" },
  { name: "/arm/torque", type: "sensor_msgs/JointState", purpose: "力矩" },
  { name: "/arm/current", type: "sensor_msgs/JointState", purpose: "电流" },
  { name: "/wrench", type: "geometry_msgs/WrenchStamped", purpose: "末端力" },
  { name: "/imu/data", type: "sensor_msgs/Imu", purpose: "波形" },
  { name: "/camera/front/image_raw", type: "sensor_msgs/Image", purpose: "相机" },
];

const sensorChannels = [
  ["关节角度", "/joint_states", "位置/速度/力矩"],
  ["电机电流", "/arm/current", "过流和负载"],
  ["末端力", "/wrench", "接触/碰撞"],
  ["IMU", "/imu/data", "振动/姿态"],
  ["相机", "/camera/front/image_raw", "视觉标注"],
];

const diagnosticsFeeds = [
  ["诊断聚合", "/diagnostics", "温度 / 总线 / 驱动状态"],
  ["执行电脑日志", "/desktop/logs", "执行电脑与 ROS 同步只读日志"],
  ["rosbag 索引", "/bags/index", "回放文件与片段定位"],
];

const exportTargets = [
  ["进入数据标注", "传感器样本、manifest、质量检查"],
  ["进入图表实验", "回放、对齐、仿真计划"],
  ["回 NPC 工作台", "提交最小回执、阻塞、审批需求"],
];

function downloadText(fileName: string, content: string) {
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function RosNodeConnector() {
  const [readonlyEndpoint, setReadonlyEndpoint] = useState("ws://127.0.0.1:9090");
  const [robotId, setRobotId] = useState("robot-01");
  const [checked, setChecked] = useState(false);
  const [presentTopics, setPresentTopics] = useState<string[]>(["/tf", "/joint_states", "/imu/data", "/arm/current"]);

  const topicStates = useMemo(() => requiredTopics.map((topic) => {
    const status: TopicStatus = presentTopics.includes(topic.name) ? "ready" : "missing";
    return { ...topic, status };
  }), [presentTopics]);
  const readyCount = topicStates.filter((topic) => topic.status === "ready").length;

  function toggleTopic(topic: string) {
    setPresentTopics((current) => current.includes(topic) ? current.filter((item) => item !== topic) : [...current, topic]);
  }

  function buildPacket() {
    const missing = topicStates.filter((topic) => topic.status === "missing").map((topic) => topic.name);
    return {
      capabilityId: "ros-node-readonly-intake",
      robotId,
      readonlyEndpoint,
      mode: "readonly",
      requiredTopics,
      topicStatus: topicStates,
      safetyPolicy: {
        blocked: ["publish", "serviceCall", "actionGoal", "parameterWrite"],
        approvalRequired: ["hardware_motion", "serial_write", "deployment", "rollback"],
      },
      sensorChannels: sensorChannels.map(([label, topic, use]) => ({ label, topic, use })),
      dataFactoryRouting: {
        destination: "设备数据工作台",
        manifest: "artifacts/robotics/arm-sensor-manifest.json",
        qualityChecks: ["timestamp_continuity", "topic_presence", "force_spike", "current_overload", "privacy"],
      },
      runnerTask: `连接 ${readonlyEndpoint}，只读扫描 ${robotId} 的模型、TF、joint_states、电流、力矩/末端力、IMU 和相机 topic；只采集传感器数据，不执行 publish/service/action。`,
      npcPrompt: missing.length
        ? `ROS 接入缺少 ${missing.join(", ")}。请给出最小修复计划，说明应该在哪台执行电脑或 ROS 主机补齐。`
        : "机械臂 ROS 只读接入 topic 已齐，请确认是否可以进入 3D 可视化、波形监控和设备数据采集。",
      receiptRequired: ["connection_health", "topic_inventory", "sensor_manifest", "missing_topics", "final_status"],
    };
  }

  function exportPacket() {
    downloadText("platform-ros-node-intake-packet.json", JSON.stringify(buildPacket(), null, 2));
  }

  const packetPreview = buildPacket();

  return (
    <section className={styles.rosConnector}>
      <div className={styles.panelHead}>
        <span>ROS 节点接入</span>
        <button type="button" data-testid="robotics-ros-export" onClick={exportPacket}>生成任务包</button>
      </div>
      <div className={styles.rosForm}>
        <label>
          机器人 ID
          <input value={robotId} onChange={(event) => setRobotId(event.target.value)} />
        </label>
        <label>
          ROS 只读入口
          <input value={readonlyEndpoint} onChange={(event) => setReadonlyEndpoint(event.target.value)} />
        </label>
        <button type="button" data-testid="robotics-ros-check" onClick={() => setChecked(true)}>只读检查</button>
      </div>
      <div className={styles.rosReadiness}>
        <strong>{readyCount}/{requiredTopics.length}</strong>
        <span>{checked ? "已生成只读检查结果" : "等待检查"}</span>
      </div>
      <div className={styles.sensorGrid}>
        {sensorChannels.map(([label, topic, use]) => (
          <article key={label} data-ready={presentTopics.includes(topic) ? "1" : "0"}>
            <strong>{label}</strong>
            <span>{topic}</span>
            <small>{use}</small>
          </article>
        ))}
      </div>
      <div className={styles.topicChecklist}>
        {diagnosticsFeeds.map(([label, topic, use]) => (
          <button key={topic} type="button" data-state="ready">
            <strong>{label}</strong>
            <span>{topic}</span>
            <small>{use}</small>
          </button>
        ))}
      </div>
      <div className={styles.topicChecklist}>
        {topicStates.map((topic) => (
          <button key={topic.name} type="button" data-state={topic.status} onClick={() => toggleTopic(topic.name)}>
            <strong>{topic.name}</strong>
            <span>{topic.purpose}</span>
            <small>{topic.type}</small>
          </button>
        ))}
      </div>
      <div className={styles.packetSummary}>
        <article>
          <strong>缺失 topic</strong>
          <span>{packetPreview.topicStatus.filter((item) => item.status === "missing").length}</span>
          <small>只读检查只会标缺口，不会补写 ROS。</small>
        </article>
        <article>
          <strong>下一步去向</strong>
          <span>{packetPreview.dataFactoryRouting.destination}</span>
          <small>证据优先进入数据标注，回放与仿真进入图表实验。</small>
        </article>
        <article>
          <strong>最小回执</strong>
          <span>{packetPreview.receiptRequired.length} 项</span>
          <small>connection_health / topic_inventory / final_status 等必须回流。</small>
        </article>
      </div>
      <div className={styles.exportTargets}>
        {exportTargets.map(([label, detail]) => (
          <article key={label}>
            <strong>{label}</strong>
            <small>{detail}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
