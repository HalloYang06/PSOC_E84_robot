"use client";

import integrations from "../../../../lib/open-source-integrations.json";
import styles from "./robotics.module.css";

const toolIds = ["foxglove", "robotwebtools", "plotjuggler", "robot-descriptions"];
const tools = integrations.filter((item) => toolIds.includes(item.id));
const internalLabels: Record<string, { name: string; detail: string; action: string }> = {
  foxglove: {
    name: "3D 可视化配置",
    detail: "生成平台内置的机器人 3D 面板布局，包含模型、TF、joint、地图和相机主题。",
    action: "生成 3D 布局",
  },
  robotwebtools: {
    name: "ROS 只读入口",
    detail: "生成平台可消费的 ROS 只读策略，默认阻止 publish/service/action。",
    action: "生成只读策略",
  },
  plotjuggler: {
    name: "波形数据包",
    detail: "生成音频、IMU、关节信号的时序样例，供设备数据工作台复用。",
    action: "生成波形样例",
  },
  "robot-descriptions": {
    name: "模型库索引",
    detail: "生成机器人模型候选索引，只保存类型、自由度、格式和来源元数据，不搬大 mesh。",
    action: "生成模型索引",
  },
};

const nativeReadonlyCapabilities = [
  {
    id: "rosbag",
    name: "rosbag 证据索引",
    detail: "生成 bag / db3 回放索引、时间段和主题清单，供数据标注与图表实验复用。",
    action: "生成 rosbag 索引",
  },
  {
    id: "motor-card",
    name: "电机参数卡",
    detail: "整理电流、速度、温度、限幅和编码器状态，只输出只读证据与风险说明。",
    action: "生成电机卡",
  },
  {
    id: "pid-foc",
    name: "PID / FOC 建议",
    detail: "把 SimpleFOC / ODrive / moteus 的调参经验转成平台建议卡，不直接写参数。",
    action: "生成调参建议",
  },
  {
    id: "review-actions",
    name: "强审动作卡",
    detail: "把 publish / service / action / firmware / motion / deploy 统一生成审批卡。",
    action: "生成强审卡",
  },
  {
    id: "risk-gate",
    name: "风险门摘要",
    detail: "生成只读能力、仿真优先和强审动作的边界摘要，供设备数据工作台统一引用。",
    action: "生成风险门",
  },
];

const deliveryHints: Record<string, string> = {
  foxglove: "下一步交给机器人现场 3D / TF 只读面板。",
  robotwebtools: "下一步交给执行电脑只读接入与工作台最小回执。",
  plotjuggler: "下一步交给数据标注质量检查。",
  "robot-descriptions": "下一步交给模型导入、候选筛选与证据索引。",
  rosbag: "下一步交给图表实验回放或数据标注样本索引。",
  "motor-card": "下一步交给电机参数卡与风险说明。",
  "pid-foc": "下一步交给调参建议看板，不进入写参数。",
  "review-actions": "下一步交给 NPC 工作台审批，不在本页执行。",
  "risk-gate": "下一步交给设备数据工作台统一边界展示。",
};

function downloadText(fileName: string, content: string, type = "application/json") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function buildFoxgloveLayout() {
  return buildPlatformPacket("robot-3d-visualization", {
    artifactType: "foxglove_layout",
    outputPath: "artifacts/robotics/foxglove-robot-field-layout.json",
    payload: {
      name: "AI Collab Robot Field",
      panels: [
        { type: "3D", title: "Robot model / TF / map", topics: ["/robot_description", "/tf", "/joint_states", "/map"] },
        { type: "RawMessages", title: "Joint states", topics: ["/joint_states"] },
        { type: "Image", title: "Front camera", topics: ["/camera/front/image_raw"] },
      ],
    },
      runnerTask: "扫描 robot_description、TF、joint_states、map/camera topic，并把可视化布局写入项目证据。",
    npcPrompt: "请检查 3D 可视化配置是否覆盖模型、TF、joint_states、地图和相机，并用最小回执说明缺失 topic。",
    approval: "只读，无需人审；若后续触发真实机器人动作，必须走硬件人审。",
  });
}

function buildReadonlyRosPolicy() {
  return buildPlatformPacket("readonly-ros-policy", {
    artifactType: "ros_readonly_policy",
    outputPath: "artifacts/robotics/ros-readonly-config.json",
    payload: {
      mode: "readonly",
      readonlyEndpoint: "ws://127.0.0.1:9090",
      subscribe: ["/robot_description", "/tf", "/joint_states", "/camera/front/image_raw", "/imu/data"],
      blockedActions: ["publish", "serviceCall", "actionGoal"],
      approvalRequired: ["hardware_motion", "serial_write", "deployment", "rollback"],
    },
      runnerTask: "执行电脑只上报 ROS 只读入口、topic 列表和连接健康，不允许浏览器直接写入 ROS。",
    npcPrompt: "请根据 ROS 只读策略检查哪些 topic 可安全订阅，哪些动作必须保持阻断。",
    approval: "默认只读；publish/service/actionGoal 一律阻断，硬件动作强制人审。",
  });
}

function buildPlotJugglerCsv() {
  const rows = ["time,audio_rms,imu_acc_x,joint_1"];
  for (let i = 0; i < 40; i += 1) {
    rows.push(`${(i * 0.02).toFixed(2)},${(0.3 + Math.sin(i / 4) * 0.2).toFixed(3)},${(0.02 + Math.cos(i / 5) * 0.03).toFixed(3)},${(1.2 + Math.sin(i / 8) * 0.4).toFixed(3)}`);
  }
  return rows.join("\n");
}

function buildRobotCatalogSeed() {
  return buildPlatformPacket("robot-model-catalog", {
    artifactType: "model_catalog_seed",
    outputPath: "artifacts/robotics/robot-model-catalog-seed.json",
    payload: {
      policy: "Store only project index and license/source metadata; do not vendor large mesh assets into this repo.",
      models: [
        { name: "panda", type: "arm", expectedDof: 7, formats: ["URDF", "MJCF"], status: "candidate" },
        { name: "ur5e", type: "arm", expectedDof: 6, formats: ["URDF"], status: "candidate" },
        { name: "go2", type: "quadruped", expectedDof: 12, formats: ["URDF"], status: "candidate" },
      ],
    },
    runnerTask: "按项目需要拉取/解析机器人模型元数据，记录 license、自由度、格式和 mesh 缺失情况。",
    npcPrompt: "请从模型库候选中选择适合当前项目的模型，说明自由度、格式和缺失资源风险。",
    approval: "只索引元数据；导入大模型资产前需要确认仓库体积和 license。",
  });
}

function buildRosbagIndexSeed() {
  return buildPlatformPacket("rosbag-evidence-index", {
    artifactType: "rosbag_index",
    outputPath: "artifacts/robotics/rosbag-index.json",
    payload: {
      files: [
        { name: "arm_calibration_2026-05-14.bag", durationSec: 720, topics: ["/joint_states", "/arm/current", "/imu/data"] },
        { name: "camera_front_debug.bag", durationSec: 240, topics: ["/camera/front/image_raw", "/tf"] },
      ],
      recommendedReplays: ["对齐 joint/current 波形", "核对相机丢帧与 TF 时间轴"],
    },
    runnerTask: "扫描 rosbag / db3 文件元数据，提取时长、topic、时间片段与来源执行电脑。",
    npcPrompt: "请根据 rosbag 索引给出下一步回放计划，并说明应进入图表实验还是数据标注。",
    approval: "只读索引；真实硬件动作与写入参数不在此能力内。",
  });
}

function buildMotorCardSeed() {
  return buildPlatformPacket("motor-parameter-card", {
    artifactType: "motor_parameter_card",
    outputPath: "artifacts/robotics/motor-parameter-card.json",
    payload: {
      motors: [
        { name: "M1 shoulder", currentA: 1.8, ripplePct: 6, tempC: 43, encoder: "ok" },
        { name: "M2 elbow", overshootPct: 12, tempC: 39, limit: "soft-limit active" },
      ],
      note: "只读展示参数与观测值，不生成写入命令。",
    },
    runnerTask: "收集电流、速度、温度、编码器与限幅状态，回流成平台参数卡。",
    npcPrompt: "请解释哪些参数异常值得进入仿真或台架复核，不要直接下发到电机控制器。",
    approval: "只读证据；任何控制器写参数都必须走强审。",
  });
}

function buildPidFocAdviceSeed() {
  return buildPlatformPacket("pid-foc-advice-card", {
    artifactType: "pid_foc_advice",
    outputPath: "artifacts/robotics/pid-foc-advice.json",
    payload: {
      references: ["SimpleFOC", "ODrive", "moteus"],
      advice: [
        "先采 30s 电流与速度波形，再讨论 P/I/D 调整。",
        "对过冲先做仿真和回放，不直接写入控制器。",
        "FOC 相关建议只能作为下一步实验计划，不是执行命令。",
      ],
    },
    runnerTask: "基于只读波形和日志生成 PID / FOC 调参建议卡。",
    npcPrompt: "请输出建议、风险和下一步实验计划，并明确哪些动作必须审批。",
    approval: "建议卡免审可看；参数写入与真实运动必须强审。",
  });
}

function buildReviewActionSeed() {
  return buildPlatformPacket("robotics-review-actions", {
    artifactType: "review_action_cards",
    outputPath: "artifacts/robotics/review-actions.json",
    payload: {
      actions: [
        { name: "ROS publish/service/action", review: "required", reason: "可能触发真实执行链路" },
        { name: "PID / FOC 参数写入", review: "required", reason: "会改变电机控制器行为" },
        { name: "firmware / 驱动 / 部署", review: "required", reason: "会改变设备或执行电脑状态" },
      ],
    },
    runnerTask: "把高风险动作转成审批卡，附上目标设备、预期结果和回退路径。",
    npcPrompt: "请确认审批卡字段完整，避免任何动作在只读页面直接执行。",
    approval: "本能力本身只生成审批卡，不执行任何高风险动作。",
  });
}

function buildRiskGateSeed() {
  return buildPlatformPacket("robotics-risk-gate-summary", {
    artifactType: "risk_gate_summary",
    outputPath: "artifacts/robotics/risk-gate-summary.json",
    payload: {
      readonly: ["topic", "diagnostics", "tf", "urdf", "rosbag", "waveform", "motor parameter card"],
      simulateFirst: ["moveit planning", "gazebo replay", "webots replay", "ai-lab scenario"],
      strongReview: ["ros publish", "ros service", "ros action", "parameter write", "firmware", "deploy", "motion"],
    },
    runnerTask: "生成机器人现场的风险门摘要，供前端区分只读能力与强审动作。",
    npcPrompt: "请确认哪些能力可以直接展示，哪些动作只能生成审批卡。",
    approval: "本能力仅生成边界摘要，不触发任何设备动作。",
  });
}

function buildPlatformPacket(capabilityId: string, data: {
  artifactType: string;
  outputPath: string;
  payload: unknown;
  runnerTask: string;
  npcPrompt: string;
  approval: string;
}) {
  return {
    capabilityId,
    generatedBy: "AI Collab Platform robotics workbench",
    platformLoop: {
      resourceIndex: "项目主界面维护执行电脑、NPC、知识与能力资源。",
      runner: data.runnerTask,
      npc: data.npcPrompt,
      audit: "平台记录用户动作、生成产物、审批策略和最终回执；完整处理过程留在桌面线程。",
      receipt: "NPC 只回传最小送达回执、阻塞原因和最终结果。",
    },
    artifact: {
      type: data.artifactType,
      path: data.outputPath,
      payload: data.payload,
    },
    approvalPolicy: data.approval,
  };
}

function runAction(id: string) {
  if (id === "foxglove") {
    downloadText("platform-robot-3d-visualization-packet.json", JSON.stringify(buildFoxgloveLayout(), null, 2));
    return;
  }
  if (id === "robotwebtools") {
    downloadText("platform-readonly-ros-policy-packet.json", JSON.stringify(buildReadonlyRosPolicy(), null, 2));
    return;
  }
  if (id === "plotjuggler") {
    const packet = buildPlatformPacket("telemetry-waveform-package", {
      artifactType: "telemetry_csv",
      outputPath: "artifacts/robotics/plotjuggler-telemetry-sample.csv",
      payload: buildPlotJugglerCsv(),
      runnerTask: "采集 audio、IMU、joint/current 等时序信号并对齐时间戳，异常点回流数据标注。",
      npcPrompt: "请查看波形样例和异常点，判断是否可进入数据标注或需要重采。",
      approval: "只读采集可自动；真实硬件写入或动作控制必须人审。",
    });
    downloadText("platform-telemetry-waveform-packet.json", JSON.stringify(packet, null, 2));
    return;
  }
  if (id === "robot-descriptions") {
    downloadText("platform-robot-model-catalog-packet.json", JSON.stringify(buildRobotCatalogSeed(), null, 2));
    return;
  }
  if (id === "rosbag") {
    downloadText("platform-rosbag-index-packet.json", JSON.stringify(buildRosbagIndexSeed(), null, 2));
    return;
  }
  if (id === "motor-card") {
    downloadText("platform-motor-card-packet.json", JSON.stringify(buildMotorCardSeed(), null, 2));
    return;
  }
  if (id === "pid-foc") {
    downloadText("platform-pid-foc-advice-packet.json", JSON.stringify(buildPidFocAdviceSeed(), null, 2));
    return;
  }
  if (id === "review-actions") {
    downloadText("platform-review-action-cards-packet.json", JSON.stringify(buildReviewActionSeed(), null, 2));
    return;
  }
  if (id === "risk-gate") {
    downloadText("platform-risk-gate-summary-packet.json", JSON.stringify(buildRiskGateSeed(), null, 2));
  }
}

export function ToolActionPanel() {
  return (
    <div className={styles.externalList}>
      {tools.map((tool) => (
        <article key={tool.id}>
          <strong>{internalLabels[tool.id]?.name ?? tool.name}</strong>
          <small>{internalLabels[tool.id]?.detail ?? tool.runnerUse}</small>
          <em>{deliveryHints[tool.id] ?? "下一步交给对应平台工作面。"}</em>
          <button type="button" data-testid={`robotics-tool-${tool.id}`} onClick={() => runAction(tool.id)}>
            {internalLabels[tool.id]?.action ?? tool.platformAction}
          </button>
        </article>
      ))}
      {nativeReadonlyCapabilities.map((tool) => (
        <article key={tool.id}>
          <strong>{tool.name}</strong>
          <small>{tool.detail}</small>
          <em>{deliveryHints[tool.id] ?? "下一步交给对应平台工作面。"}</em>
          <button type="button" data-testid={`robotics-tool-${tool.id}`} onClick={() => runAction(tool.id)}>
            {tool.action}
          </button>
        </article>
      ))}
    </div>
  );
}
