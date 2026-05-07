type AnyRecord = Record<string, any>;

export type ResourceId =
  | "demand"
  | "taskSeeds"
  | "aiEnergy"
  | "compute"
  | "approval"
  | "delivery"
  | "knowledge"
  | "morale";

export type EconomyZoneId =
  | "project"
  | "requirements"
  | "tasks"
  | "ai"
  | "computers"
  | "chat"
  | "approvals"
  | "delivery";

export type EconomyPhase = "bootstrap" | "expansion" | "strain";

export type EconomyPersistedState = {
  version: 1;
  buildingLevels: Partial<Record<EconomyZoneId, 1 | 2 | 3>>;
  resourceStocks: Partial<Record<ResourceId, number>>;
  updatedAt?: string;
};

export type ResourceSnapshot = {
  id: ResourceId;
  label: string;
  unit: string;
  stock: number;
  cap: number;
  income: number;
  upkeep: number;
  net: number;
  scarcity: number;
  note: string;
  sources: string[];
  sinks: string[];
};

export type UpgradeCost = {
  resource: ResourceId;
  amount: number;
};

export type RoleFlow = {
  resource: ResourceId;
  amount: number;
};

type ResourceModifier = Partial<Record<ResourceId, number>>;

type UpgradeModifiers = {
  stock?: ResourceModifier;
  cap?: ResourceModifier;
  income?: ResourceModifier;
  upkeep?: ResourceModifier;
};

export type UpgradePlan = {
  level: 2 | 3;
  focus: "capacity" | "efficiency" | "stability";
  payoffCycles: number;
  costs: UpgradeCost[];
  effects: string[];
  modifiers: UpgradeModifiers;
};

export type BuildingEconomy = {
  id: EconomyZoneId;
  label: string;
  currentLevel: 1 | 2 | 3;
  maxLevel: 3;
  baseThroughput: number;
  throughput: number;
  throughputPenalty: number;
  state: "stable" | "strained" | "blocked";
  workers: number;
  consumes: ResourceId[];
  produces: ResourceId[];
  reason: string;
  bottleneckResourceId?: ResourceId;
  nextUpgrade?: UpgradePlan;
};

export type RoleEconomy = {
  id: string;
  label: string;
  count: number;
  penaltyRate: number;
  linkedBuildingIds: EconomyZoneId[];
  baseConsumes: RoleFlow[];
  baseProduces: RoleFlow[];
  consumes: RoleFlow[];
  produces: RoleFlow[];
  note: string;
};

export type EconomyConflict = {
  id: string;
  zoneId: EconomyZoneId;
  title: string;
  severity: "low" | "medium" | "high";
  affectedResources: ResourceId[];
  summary: string;
  action: string;
  penaltyRate: number;
};

export type EconomyContext = {
  projectName: string;
  requirementCount: number;
  runnerCommandCount: number;
  relayTimelineCount: number;
  tokenSpend: number;
  activeTaskCount: number;
  blockedTaskCount: number;
  pendingApprovalCount: number;
  completedTaskCount: number;
  providerCount: number;
  workstationCount: number;
  nodeCount: number;
  staffedSeats: number;
  totalTaskCount: number;
};

export type EconomyBalance = {
  phase: EconomyPhase;
  context: EconomyContext;
  persistedState: EconomyPersistedState;
  overview: {
    cycleMinutes: number;
    throughputScore: number;
    scarceResourceIds: ResourceId[];
    recommendations: string[];
    conflicts: EconomyConflict[];
  };
  resources: ResourceSnapshot[];
  buildings: BuildingEconomy[];
  roles: RoleEconomy[];
};

export type EconomyInput = {
  projectName: string;
  requirementCount: number;
  tasks: AnyRecord[];
  config: {
    nodes: AnyRecord[];
    providers: AnyRecord[];
    workstations: AnyRecord[];
  };
  runnerCommandCount: number;
  relayTimelineCount: number;
  tokenSpend: number;
  activeTaskCount: number;
  blockedTaskCount: number;
  pendingApprovalCount: number;
  completedTaskCount: number;
  persistedState?: EconomyPersistedState | null;
};

export type UpgradeAttempt = {
  ok: boolean;
  balance: EconomyBalance;
  message: string;
};

const RESOURCE_META: Record<
  ResourceId,
  Pick<ResourceSnapshot, "label" | "unit" | "note" | "sources" | "sinks">
> = {
  demand: {
    label: "需求单",
    unit: "orders",
    note: "Incoming business pressure. If demand piles up faster than approvals clear, the whole base starts dragging.",
    sources: ["HQ", "Requirements Desk"],
    sinks: ["Task Farm", "Approval Gate"],
  },
  taskSeeds: {
    label: "任务种子",
    unit: "seeds",
    note: "Workable task starters. Too few starves AI seats, too many creates backlog rot.",
    sources: ["Requirements Desk", "Task Farm"],
    sinks: ["AI Seats"],
  },
  aiEnergy: {
    label: "AI 精力",
    unit: "charge",
    note: "Operator stamina for sustained parallel work. Shortages make seats sit idle even when demand exists.",
    sources: ["AI Seats", "Chat Yard"],
    sinks: ["Task Farm", "Delivery Dock"],
  },
  compute: {
    label: "算力",
    unit: "core-h",
    note: "Execution throughput from online nodes and runners. Low compute becomes the first real machine bottleneck.",
    sources: ["Machine Room"],
    sinks: ["AI Seats", "Delivery Dock"],
  },
  approval: {
    label: "审批点",
    unit: "points",
    note: "Human confirmation budget. High-risk work and final delivery both compete for it.",
    sources: ["HQ", "Approval Gate"],
    sinks: ["Machine Room", "Delivery Dock"],
  },
  delivery: {
    label: "交付包",
    unit: "bundles",
    note: "Shippable outputs. Delivery only stabilizes if compute and approvals can keep up.",
    sources: ["AI Seats", "Delivery Dock"],
    sinks: ["HQ", "Chat Yard"],
  },
  knowledge: {
    label: "知识值",
    unit: "points",
    note: "Captured patterns and documentation. More knowledge keeps the base stable and makes upgrades calm down faster.",
    sources: ["Chat Yard", "Delivery Dock"],
    sinks: ["HQ", "Approval Gate"],
  },
  morale: {
    label: "士气",
    unit: "points",
    note: "Team resilience. When demand and blockers pile up, morale drops and every building line gets sloppier.",
    sources: ["Chat Yard", "Delivery Dock"],
    sinks: ["Requirements Desk", "Machine Room"],
  },
};

const ZONE_RESOURCES: Record<EconomyZoneId, ResourceId[]> = {
  project: ["demand", "approval", "delivery", "morale"],
  requirements: ["demand", "taskSeeds", "approval"],
  tasks: ["demand", "taskSeeds", "aiEnergy"],
  ai: ["taskSeeds", "aiEnergy", "compute", "knowledge"],
  computers: ["compute", "approval", "morale"],
  chat: ["knowledge", "morale", "aiEnergy"],
  approvals: ["approval", "knowledge", "demand"],
  delivery: ["delivery", "compute", "approval"],
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function round(value: number) {
  return Math.round(value * 10) / 10;
}

function ratio(numerator: number, denominator: number) {
  if (denominator <= 0) return 0;
  return numerator / denominator;
}

function asLevel(value: number): 1 | 2 | 3 {
  if (value >= 3) return 3;
  if (value >= 2) return 2;
  return 1;
}

function resourceById(resources: ResourceSnapshot[], id: ResourceId) {
  return resources.find((resource) => resource.id === id)!;
}

function resourceLabel(resources: ResourceSnapshot[], id: ResourceId) {
  return resourceById(resources, id).label;
}

function buildResource(
  id: ResourceId,
  stock: number,
  cap: number,
  income: number,
  upkeep: number,
): ResourceSnapshot {
  const meta = RESOURCE_META[id];
  const safeCap = Math.max(1, cap);
  const safeStock = clamp(stock, 0, safeCap);
  const safeIncome = Math.max(0, income);
  const safeUpkeep = Math.max(0, upkeep);
  const net = safeIncome - safeUpkeep;
  const availability = ratio(safeStock, safeCap);
  const scarcity = clamp(
    (1 - availability) * 0.62 + (net < 0 ? Math.min(0.38, Math.abs(net) / Math.max(1, safeUpkeep + 1)) : 0),
    0,
    1,
  );
  return {
    id,
    label: meta.label,
    unit: meta.unit,
    stock: safeStock,
    cap: safeCap,
    income: safeIncome,
    upkeep: safeUpkeep,
    net,
    scarcity: round(scarcity),
    note: meta.note,
    sources: meta.sources,
    sinks: meta.sinks,
  };
}

function patchResource(resource: ResourceSnapshot, patch: { stock?: number; cap?: number; income?: number; upkeep?: number }) {
  return buildResource(
    resource.id,
    resource.stock + (patch.stock ?? 0),
    resource.cap + (patch.cap ?? 0),
    resource.income + (patch.income ?? 0),
    resource.upkeep + (patch.upkeep ?? 0),
  );
}

function applyModifiers(resources: ResourceSnapshot[], modifiers: UpgradeModifiers) {
  return resources.map((resource) =>
    patchResource(resource, {
      stock: modifiers.stock?.[resource.id] ?? 0,
      cap: modifiers.cap?.[resource.id] ?? 0,
      income: modifiers.income?.[resource.id] ?? 0,
      upkeep: modifiers.upkeep?.[resource.id] ?? 0,
    }),
  );
}

function contextFromInput(input: EconomyInput): EconomyContext {
  const providerCount = input.config.providers.length;
  const workstationCount = input.config.workstations.length;
  const nodeCount = input.config.nodes.length;
  return {
    projectName: input.projectName,
    requirementCount: input.requirementCount,
    runnerCommandCount: input.runnerCommandCount,
    relayTimelineCount: input.relayTimelineCount,
    tokenSpend: input.tokenSpend,
    activeTaskCount: input.activeTaskCount,
    blockedTaskCount: input.blockedTaskCount,
    pendingApprovalCount: input.pendingApprovalCount,
    completedTaskCount: input.completedTaskCount,
    providerCount,
    workstationCount,
    nodeCount,
    staffedSeats: Math.max(providerCount, workstationCount, 1),
    totalTaskCount: input.tasks.length,
  };
}

function buildBaseResources(context: EconomyContext) {
  const tokenPressure = Math.ceil(context.tokenSpend / 25);
  return [
    buildResource(
      "demand",
      7 + context.requirementCount * 3 + context.blockedTaskCount * 2,
      13 + context.requirementCount * 2 + context.pendingApprovalCount * 3,
      2 + Math.ceil(context.requirementCount / 2) + Math.ceil(context.relayTimelineCount / 4),
      1 + context.activeTaskCount + context.pendingApprovalCount,
    ),
    buildResource(
      "taskSeeds",
      context.requirementCount * 2 + context.completedTaskCount - context.activeTaskCount - Math.floor(context.blockedTaskCount / 2),
      10 + context.requirementCount * 2 + context.staffedSeats * 3,
      1 + Math.ceil(context.requirementCount / 2) + Math.ceil(context.completedTaskCount / 3),
      Math.max(1, context.activeTaskCount + Math.ceil(context.blockedTaskCount / 2)),
    ),
    buildResource(
      "aiEnergy",
      8 + context.providerCount * 5 + context.workstationCount * 3 - context.activeTaskCount * 2 - context.blockedTaskCount - tokenPressure,
      12 + context.providerCount * 6 + context.workstationCount * 4,
      Math.max(1, context.providerCount * 3 + Math.ceil(context.relayTimelineCount / 4)),
      Math.max(1, context.activeTaskCount * 2 + context.staffedSeats + tokenPressure),
    ),
    buildResource(
      "compute",
      8 + context.nodeCount * 6 - context.activeTaskCount * 2 - context.runnerCommandCount + context.completedTaskCount,
      12 + context.nodeCount * 10 + context.workstationCount * 3,
      Math.max(1, context.nodeCount * 4 + Math.ceil(context.runnerCommandCount / 3)),
      Math.max(1, context.activeTaskCount * 2 + Math.ceil(context.runnerCommandCount / 2) + context.staffedSeats),
    ),
    buildResource(
      "approval",
      4 + context.completedTaskCount + Math.ceil(context.requirementCount / 2) - context.pendingApprovalCount * 2,
      8 + context.completedTaskCount * 2 + context.pendingApprovalCount * 3,
      Math.max(1, 2 + Math.ceil(context.completedTaskCount / 2)),
      Math.max(1, context.pendingApprovalCount * 2 + context.blockedTaskCount + Math.ceil(context.runnerCommandCount / 3)),
    ),
    buildResource(
      "delivery",
      context.completedTaskCount * 2 + Math.max(0, context.runnerCommandCount - context.blockedTaskCount),
      8 + context.completedTaskCount * 3 + context.runnerCommandCount * 2,
      Math.max(1, Math.ceil(context.completedTaskCount / 2) + Math.ceil(context.staffedSeats / 2)),
      Math.max(1, Math.ceil(context.requirementCount / 2) + context.pendingApprovalCount),
    ),
    buildResource(
      "knowledge",
      6 + context.completedTaskCount * 3 + context.relayTimelineCount + context.runnerCommandCount - context.blockedTaskCount * 2,
      12 + context.completedTaskCount * 4 + context.staffedSeats * 3,
      Math.max(1, context.completedTaskCount * 2 + Math.ceil(context.relayTimelineCount / 2)),
      Math.max(1, context.pendingApprovalCount + Math.ceil(context.requirementCount / 2) + tokenPressure),
    ),
    buildResource(
      "morale",
      12 + context.completedTaskCount - context.blockedTaskCount * 3 - context.pendingApprovalCount + Math.ceil(context.relayTimelineCount / 4),
      14 + context.staffedSeats * 4 + context.completedTaskCount * 2,
      Math.max(1, 1 + Math.ceil(context.completedTaskCount / 2)),
      Math.max(1, context.blockedTaskCount * 2 + context.requirementCount + tokenPressure),
    ),
  ];
}

function defaultLevels(context: EconomyContext): Record<EconomyZoneId, 1 | 2 | 3> {
  return {
    project: asLevel(1 + Math.floor((context.requirementCount + context.completedTaskCount) / 4)),
    requirements: asLevel(1 + Math.floor(context.requirementCount / 3)),
    tasks: asLevel(1 + Math.floor(context.totalTaskCount / 4)),
    ai: asLevel(1 + Math.floor((context.providerCount + context.workstationCount) / 2)),
    computers: asLevel(1 + Math.floor((context.nodeCount + context.runnerCommandCount) / 3)),
    chat: asLevel(1 + Math.floor((context.relayTimelineCount + context.runnerCommandCount) / 5)),
    approvals: asLevel(1 + Math.floor((context.pendingApprovalCount + context.completedTaskCount) / 4)),
    delivery: asLevel(1 + Math.floor((context.completedTaskCount + context.runnerCommandCount) / 4)),
  };
}

function normalizePersistedState(state: EconomyPersistedState | null | undefined): EconomyPersistedState {
  return {
    version: 1,
    buildingLevels: state?.buildingLevels ?? {},
    resourceStocks: state?.resourceStocks ?? {},
    updatedAt: state?.updatedAt,
  };
}

function applyPersistedState(
  resources: ResourceSnapshot[],
  defaults: Record<EconomyZoneId, 1 | 2 | 3>,
  persistedState: EconomyPersistedState,
) {
  const levels = { ...defaults, ...persistedState.buildingLevels };
  const nextResources = resources.map((resource) => {
    const savedStock = persistedState.resourceStocks[resource.id];
    return typeof savedStock === "number" ? buildResource(resource.id, savedStock, resource.cap, resource.income, resource.upkeep) : resource;
  });
  return { resources: nextResources, levels };
}

function upgradePlanFor(buildingId: EconomyZoneId, currentLevel: 1 | 2 | 3): UpgradePlan | undefined {
  if (currentLevel >= 3) return undefined;
  if (buildingId === "requirements") {
    return {
      level: (currentLevel + 1) as 2 | 3,
      focus: "capacity",
      payoffCycles: 2,
      costs: [
        { resource: "approval", amount: 6 * currentLevel },
        { resource: "morale", amount: 4 * currentLevel },
        { resource: "taskSeeds", amount: 3 * currentLevel },
      ],
      effects: ["Demand cap +6", "Task seed income +3", "Morale upkeep -1"],
      modifiers: { cap: { demand: 6 }, income: { taskSeeds: 3, demand: 1 }, upkeep: { morale: -1 } },
    };
  }
  if (buildingId === "tasks") {
    return {
      level: (currentLevel + 1) as 2 | 3,
      focus: "capacity",
      payoffCycles: 3,
      costs: [
        { resource: "demand", amount: 5 * currentLevel },
        { resource: "taskSeeds", amount: 4 * currentLevel },
        { resource: "aiEnergy", amount: 3 * currentLevel },
      ],
      effects: ["Knowledge income +2", "Task seed upkeep -1", "Task seed stock +2"],
      modifiers: { income: { knowledge: 2, taskSeeds: 1 }, upkeep: { taskSeeds: -1 }, stock: { taskSeeds: 2 } },
    };
  }
  if (buildingId === "ai") {
    return {
      level: (currentLevel + 1) as 2 | 3,
      focus: "efficiency",
      payoffCycles: 2,
      costs: [
        { resource: "compute", amount: 7 * currentLevel },
        { resource: "aiEnergy", amount: 6 * currentLevel },
        { resource: "knowledge", amount: 4 * currentLevel },
      ],
      effects: ["Delivery income +4", "AI energy upkeep -2", "Compute upkeep -1"],
      modifiers: { income: { delivery: 4, knowledge: 1 }, upkeep: { aiEnergy: -2, compute: -1 } },
    };
  }
  if (buildingId === "computers") {
    return {
      level: (currentLevel + 1) as 2 | 3,
      focus: "efficiency",
      payoffCycles: 4,
      costs: [
        { resource: "approval", amount: 6 * currentLevel },
        { resource: "compute", amount: 5 * currentLevel },
        { resource: "morale", amount: 4 * currentLevel },
      ],
      effects: ["Compute cap +10", "Compute income +4", "Approval upkeep -1"],
      modifiers: { cap: { compute: 10 }, income: { compute: 4 }, upkeep: { approval: -1 }, stock: { compute: 3 } },
    };
  }
  if (buildingId === "chat") {
    return {
      level: (currentLevel + 1) as 2 | 3,
      focus: "stability",
      payoffCycles: 3,
      costs: [
        { resource: "delivery", amount: 4 * currentLevel },
        { resource: "knowledge", amount: 5 * currentLevel },
        { resource: "morale", amount: 4 * currentLevel },
      ],
      effects: ["Knowledge income +3", "Morale income +2", "AI energy upkeep -1"],
      modifiers: { income: { knowledge: 3, morale: 2 }, upkeep: { aiEnergy: -1 }, stock: { morale: 2 } },
    };
  }
  if (buildingId === "approvals") {
    return {
      level: (currentLevel + 1) as 2 | 3,
      focus: "stability",
      payoffCycles: 2,
      costs: [
        { resource: "knowledge", amount: 5 * currentLevel },
        { resource: "approval", amount: 4 * currentLevel },
        { resource: "morale", amount: 3 * currentLevel },
      ],
      effects: ["Approval income +4", "Demand upkeep -1", "Approval stock +3"],
      modifiers: { income: { approval: 4 }, upkeep: { demand: -1 }, stock: { approval: 3 } },
    };
  }
  if (buildingId === "delivery") {
    return {
      level: (currentLevel + 1) as 2 | 3,
      focus: "capacity",
      payoffCycles: 3,
      costs: [
        { resource: "delivery", amount: 6 * currentLevel },
        { resource: "compute", amount: 5 * currentLevel },
        { resource: "approval", amount: 4 * currentLevel },
      ],
      effects: ["Delivery income +3", "Knowledge income +3", "Approval upkeep -1"],
      modifiers: { income: { delivery: 3, knowledge: 3 }, upkeep: { approval: -1 }, cap: { delivery: 6 } },
    };
  }
  return {
    level: (currentLevel + 1) as 2 | 3,
    focus: "stability",
    payoffCycles: 3,
    costs: [
      { resource: "knowledge", amount: 5 * currentLevel },
      { resource: "delivery", amount: 4 * currentLevel },
      { resource: "approval", amount: 3 * currentLevel },
    ],
    effects: ["Demand income +2", "Approval income +2", "Morale upkeep -1"],
    modifiers: { income: { demand: 2, approval: 2 }, upkeep: { morale: -1 }, stock: { approval: 2 } },
  };
}

function buildConflicts(resources: ResourceSnapshot[], context: EconomyContext): EconomyConflict[] {
  const demand = resourceById(resources, "demand");
  const taskSeeds = resourceById(resources, "taskSeeds");
  const aiEnergy = resourceById(resources, "aiEnergy");
  const compute = resourceById(resources, "compute");
  const approval = resourceById(resources, "approval");
  const delivery = resourceById(resources, "delivery");
  const knowledge = resourceById(resources, "knowledge");
  const morale = resourceById(resources, "morale");
  const conflicts: EconomyConflict[] = [];

  if (compute.scarcity >= 0.38 || aiEnergy.scarcity >= 0.38) {
    const high = compute.scarcity >= 0.62 || aiEnergy.scarcity >= 0.62;
    conflicts.push({
      id: "compute-energy-race",
      zoneId: "ai",
      title: "Compute-energy race",
      severity: high ? "high" : "medium",
      affectedResources: ["compute", "aiEnergy", "taskSeeds"],
      summary: "AI seats are competing for both compute and energy, so extra task seeds do not translate into output.",
      action: "Favor AI efficiency upgrades or reduce simultaneous task activation before seeding more work.",
      penaltyRate: high ? 0.34 : 0.18,
    });
  }
  if (approval.scarcity >= 0.34 || delivery.scarcity >= 0.34 || context.pendingApprovalCount >= 2) {
    const high = approval.scarcity >= 0.62 || context.pendingApprovalCount >= 4;
    conflicts.push({
      id: "approval-delivery-gate",
      zoneId: "delivery",
      title: "Approval gate on delivery",
      severity: high ? "high" : "medium",
      affectedResources: ["approval", "delivery", "compute"],
      summary: "Delivery bundles are ready to move, but approval points are being burned faster than they recover.",
      action: "Clear approvals first or upgrade Approval Gate before investing more in final packaging.",
      penaltyRate: high ? 0.3 : 0.16,
    });
  }
  if (demand.scarcity >= 0.32 || morale.scarcity >= 0.32 || context.blockedTaskCount >= 2) {
    const high = morale.scarcity >= 0.58 || context.blockedTaskCount >= 4;
    conflicts.push({
      id: "demand-morale-overload",
      zoneId: "requirements",
      title: "Demand overload",
      severity: high ? "high" : "medium",
      affectedResources: ["demand", "morale", "approval"],
      summary: "New requests are entering faster than the team can absorb them, so morale is carrying the hidden cost.",
      action: "Invest in capacity or morale recovery instead of opening another intake spike.",
      penaltyRate: high ? 0.26 : 0.14,
    });
  }
  if (taskSeeds.scarcity >= 0.34 || knowledge.scarcity >= 0.34) {
    const high = taskSeeds.scarcity >= 0.6 || knowledge.scarcity >= 0.6;
    conflicts.push({
      id: "seed-knowledge-debt",
      zoneId: "tasks",
      title: "Seed debt",
      severity: high ? "high" : "medium",
      affectedResources: ["taskSeeds", "knowledge", "aiEnergy"],
      summary: "The team is pushing raw task seeds through faster than knowledge can accumulate, so upgrades pay back more slowly.",
      action: "Stabilize task flow and knowledge retention before scaling throughput again.",
      penaltyRate: high ? 0.24 : 0.12,
    });
  }
  if (!conflicts.length) {
    conflicts.push({
      id: "no-major-conflict",
      zoneId: "project",
      title: "No hard choke point",
      severity: "low",
      affectedResources: ["delivery", "knowledge"],
      summary: "The economy is balanced enough to support one more planned expansion step.",
      action: "Pick one building line and specialize instead of spreading upgrades evenly.",
      penaltyRate: 0.04,
    });
  }
  return conflicts;
}

function levelThroughputMultiplier(buildingId: EconomyZoneId, level: 1 | 2 | 3) {
  const growth =
    buildingId === "requirements" || buildingId === "tasks" || buildingId === "delivery"
      ? 0.18
      : buildingId === "ai" || buildingId === "computers"
        ? 0.14
        : 0.1;
  return 1 + (level - 1) * growth;
}

function levelPenaltyRelief(buildingId: EconomyZoneId, level: 1 | 2 | 3) {
  const relief =
    buildingId === "chat" || buildingId === "approvals" || buildingId === "project"
      ? 0.08
      : buildingId === "ai" || buildingId === "computers"
        ? 0.05
        : 0.04;
  return (level - 1) * relief;
}

function baseThroughputFor(id: EconomyZoneId, context: EconomyContext, level: 1 | 2 | 3) {
  const raw =
    id === "project"
      ? 8 + context.requirementCount + context.completedTaskCount * 1.5
      : id === "requirements"
        ? 6 + context.requirementCount * 1.8
        : id === "tasks"
          ? 8 + context.activeTaskCount * 2 + context.completedTaskCount
          : id === "ai"
            ? 10 + context.staffedSeats * 3 + context.completedTaskCount
            : id === "computers"
              ? 9 + context.nodeCount * 4 + context.runnerCommandCount
              : id === "chat"
                ? 6 + context.relayTimelineCount * 1.5 + context.completedTaskCount
                : id === "approvals"
                  ? 5 + context.completedTaskCount * 1.5 + context.pendingApprovalCount
                  : 7 + context.completedTaskCount * 2 + context.runnerCommandCount;
  return round(raw * levelThroughputMultiplier(id, level));
}

function workerCountFor(id: EconomyZoneId, context: EconomyContext, level: 1 | 2 | 3) {
  const raw =
    id === "project"
      ? 1 + Math.max(1, Math.ceil(context.requirementCount / 4))
      : id === "requirements"
        ? Math.max(1, Math.ceil(context.requirementCount / 3))
        : id === "tasks"
          ? Math.max(1, Math.ceil(context.activeTaskCount / 2))
          : id === "ai"
            ? context.staffedSeats
            : id === "computers"
              ? Math.max(1, context.nodeCount)
              : id === "chat"
                ? Math.max(1, Math.ceil(context.relayTimelineCount / 4))
                : id === "approvals"
                  ? Math.max(1, Math.ceil((context.pendingApprovalCount + 1) / 2))
                  : Math.max(1, Math.ceil((context.completedTaskCount + 1) / 2));
  return raw + Math.max(0, level - 1);
}

function buildingSpec(id: EconomyZoneId) {
  if (id === "project") return { label: "HQ", consumes: ["knowledge", "delivery"] as ResourceId[], produces: ["demand", "approval"] as ResourceId[] };
  if (id === "requirements") return { label: "Requirements Desk", consumes: ["approval", "morale"] as ResourceId[], produces: ["demand", "taskSeeds"] as ResourceId[] };
  if (id === "tasks") return { label: "Task Farm", consumes: ["demand", "taskSeeds", "aiEnergy"] as ResourceId[], produces: ["taskSeeds", "knowledge"] as ResourceId[] };
  if (id === "ai") return { label: "AI Seats", consumes: ["taskSeeds", "aiEnergy", "compute"] as ResourceId[], produces: ["knowledge", "delivery"] as ResourceId[] };
  if (id === "computers") return { label: "Machine Room", consumes: ["compute", "approval"] as ResourceId[], produces: ["compute"] as ResourceId[] };
  if (id === "chat") return { label: "Chat Yard", consumes: ["delivery", "aiEnergy"] as ResourceId[], produces: ["knowledge", "morale"] as ResourceId[] };
  if (id === "approvals") return { label: "Approval Gate", consumes: ["approval", "knowledge", "morale"] as ResourceId[], produces: ["approval"] as ResourceId[] };
  return { label: "Delivery Dock", consumes: ["delivery", "compute", "approval"] as ResourceId[], produces: ["delivery", "knowledge"] as ResourceId[] };
}

function buildingPenalty(
  id: EconomyZoneId,
  consumes: ResourceId[],
  resources: ResourceSnapshot[],
  conflicts: EconomyConflict[],
  level: 1 | 2 | 3,
) {
  const worstResource = [...consumes].map((resourceId) => resourceById(resources, resourceId)).sort((a, b) => b.scarcity - a.scarcity)[0];
  const resourcePenalty =
    worstResource.scarcity >= 0.72 ? 0.44 : worstResource.scarcity >= 0.42 ? 0.24 : worstResource.scarcity * 0.16;
  const conflictPenalty = conflicts.filter((conflict) => conflict.zoneId === id).reduce((sum, conflict) => sum + conflict.penaltyRate, 0);
  return clamp(resourcePenalty + conflictPenalty - levelPenaltyRelief(id, level), 0, 0.82);
}

function buildingStateFromPenalty(penalty: number) {
  if (penalty >= 0.54) return "blocked" as const;
  if (penalty >= 0.22) return "strained" as const;
  return "stable" as const;
}

function buildingReason(label: string, state: BuildingEconomy["state"], bottleneck: ResourceSnapshot, throughputPenalty: number) {
  if (state === "blocked") return `${label} is jammed by ${bottleneck.label}. The line is losing ${Math.round(throughputPenalty * 100)}% of its output until that shortage is relieved.`;
  if (state === "strained") return `${label} is running hot on ${bottleneck.label}. Another push here will widen the slowdown and shave ${Math.round(throughputPenalty * 100)}% off output.`;
  return `${label} is still holding. Current drag is only ${Math.round(throughputPenalty * 100)}%, so this line can survive one more planned push.`;
}

function buildBuildings(
  context: EconomyContext,
  resources: ResourceSnapshot[],
  conflicts: EconomyConflict[],
  levels: Record<EconomyZoneId, 1 | 2 | 3>,
) {
  const ids: EconomyZoneId[] = ["project", "requirements", "tasks", "ai", "computers", "chat", "approvals", "delivery"];
  return ids.map((id) => {
    const spec = buildingSpec(id);
    const currentLevel = levels[id];
    const bottleneck = [...spec.consumes].map((resourceId) => resourceById(resources, resourceId)).sort((a, b) => b.scarcity - a.scarcity)[0];
    const throughputPenalty = buildingPenalty(id, spec.consumes, resources, conflicts, currentLevel);
    const baseThroughput = baseThroughputFor(id, context, currentLevel);
    const throughput = round(baseThroughput * (1 - throughputPenalty));
    const state = buildingStateFromPenalty(throughputPenalty);
    return {
      id,
      label: spec.label,
      currentLevel,
      maxLevel: 3 as const,
      baseThroughput,
      throughput,
      throughputPenalty: round(throughputPenalty),
      state,
      workers: workerCountFor(id, context, currentLevel),
      consumes: spec.consumes,
      produces: spec.produces,
      reason: buildingReason(spec.label, state, bottleneck, throughputPenalty),
      bottleneckResourceId: bottleneck.id,
      nextUpgrade: upgradePlanFor(id, currentLevel),
    };
  });
}

function scaleRoleFlows(flows: RoleFlow[], multiplier: number) {
  return flows.map((flow) => ({ ...flow, amount: Math.max(0, round(flow.amount * multiplier)) }));
}

function buildRoles(buildings: BuildingEconomy[], context: EconomyContext): RoleEconomy[] {
  const byId = Object.fromEntries(buildings.map((building) => [building.id, building] as const));
  const rolePenalty = (ids: EconomyZoneId[]) =>
    round(ids.reduce((sum, id) => sum + (byId[id]?.throughputPenalty ?? 0), 0) / Math.max(1, ids.length));

  const specs = [
    {
      id: "planner",
      label: "Planning Lead",
      count: 1,
      linkedBuildingIds: ["project", "requirements", "approvals"] as EconomyZoneId[],
      baseConsumes: [
        { resource: "knowledge", amount: Math.max(1, Math.ceil(context.requirementCount / 3)) },
        { resource: "delivery", amount: Math.max(1, Math.ceil(context.completedTaskCount / 3)) },
      ] as RoleFlow[],
      baseProduces: [
        { resource: "demand", amount: Math.max(2, Math.ceil(context.requirementCount / 2)) },
        { resource: "approval", amount: Math.max(1, Math.ceil(context.completedTaskCount / 2)) },
      ] as RoleFlow[],
      note: "Keeps the base aligned and turns momentum into new demand, but heavy intake and slow approvals now blunt its impact.",
    },
    {
      id: "ai-operators",
      label: "AI Operators",
      count: context.staffedSeats,
      linkedBuildingIds: ["tasks", "ai", "computers"] as EconomyZoneId[],
      baseConsumes: [
        { resource: "taskSeeds", amount: Math.max(1, context.staffedSeats * 2) },
        { resource: "compute", amount: Math.max(1, context.staffedSeats * 2) },
      ] as RoleFlow[],
      baseProduces: [
        { resource: "knowledge", amount: Math.max(1, context.staffedSeats * 2 + context.completedTaskCount) },
        { resource: "delivery", amount: Math.max(1, Math.ceil(context.completedTaskCount / 2) + context.staffedSeats) },
      ] as RoleFlow[],
      note: "Main production crew. When seeds, energy, or compute tighten, this is the first role chain that visibly loses pace.",
    },
    {
      id: "ops",
      label: "Ops and Delivery",
      count: Math.max(1, context.nodeCount),
      linkedBuildingIds: ["computers", "approvals", "delivery"] as EconomyZoneId[],
      baseConsumes: [
        { resource: "approval", amount: Math.max(1, context.pendingApprovalCount + context.nodeCount) },
        { resource: "morale", amount: Math.max(1, context.blockedTaskCount + 1) },
      ] as RoleFlow[],
      baseProduces: [
        { resource: "compute", amount: Math.max(1, context.nodeCount * 3) },
        { resource: "delivery", amount: Math.max(1, Math.ceil(context.runnerCommandCount / 2)) },
      ] as RoleFlow[],
      note: "Keeps the machines and final mile alive, but approval jams and delivery backlog now waste work across the whole line.",
    },
  ];

  return specs.map((spec) => {
    const penaltyRate = rolePenalty(spec.linkedBuildingIds);
    return {
      id: spec.id,
      label: spec.label,
      count: spec.count,
      penaltyRate,
      linkedBuildingIds: spec.linkedBuildingIds,
      baseConsumes: spec.baseConsumes,
      baseProduces: spec.baseProduces,
      consumes: scaleRoleFlows(spec.baseConsumes, 1 + penaltyRate * 0.5),
      produces: scaleRoleFlows(spec.baseProduces, 1 - penaltyRate),
      note: spec.note,
    };
  });
}

function serializePersistedState(
  levels: Record<EconomyZoneId, 1 | 2 | 3>,
  resources: ResourceSnapshot[],
): EconomyPersistedState {
  return {
    version: 1,
    buildingLevels: levels,
    resourceStocks: resources.reduce((map, resource) => {
      map[resource.id] = resource.stock;
      return map;
    }, {} as Partial<Record<ResourceId, number>>),
    updatedAt: new Date().toISOString(),
  };
}

function buildBalanceFromRuntime(
  context: EconomyContext,
  resources: ResourceSnapshot[],
  levels: Record<EconomyZoneId, 1 | 2 | 3>,
): EconomyBalance {
  const phase: EconomyPhase =
    context.blockedTaskCount + context.pendingApprovalCount >= 4
      ? "strain"
      : context.providerCount + context.workstationCount + context.nodeCount + context.totalTaskCount >= 8
        ? "expansion"
        : "bootstrap";
  const conflicts = buildConflicts(resources, context);
  const buildings = buildBuildings(context, resources, conflicts, levels);
  const roles = buildRoles(buildings, context);
  const scarceResourceIds = [...resources].sort((a, b) => b.scarcity - a.scarcity).slice(0, 3).map((resource) => resource.id);
  const throughputScore = round(
    (buildings.reduce((sum, building) => sum + building.throughput, 0) +
      roles.reduce((sum, role) => sum + role.produces.reduce((inner, item) => inner + item.amount, 0), 0)) /
      (buildings.length + roles.length),
  );
  const recommendations = [
    `Patch ${resourceLabel(resources, scarceResourceIds[0])} first or the next cycle will slow down before it even pays you back.`,
    conflicts[0]?.action ?? "Pick one district to strengthen instead of spreading upgrades across the whole base.",
    roles.some((role) => role.penaltyRate >= 0.22)
      ? "Role output is already sagging under pressure. Fix the upstream bottleneck before opening another work lane."
      : "Role chains are still holding. One sharp upgrade is safer than a broad expansion.",
  ];
  return {
    phase,
    context,
    persistedState: serializePersistedState(levels, resources),
    overview: {
      cycleMinutes: phase === "bootstrap" ? 6 : phase === "expansion" ? 8 : 10,
      throughputScore,
      scarceResourceIds,
      recommendations,
      conflicts,
    },
    resources,
    buildings,
    roles,
  };
}

export function buildEconomyBalance(input: EconomyInput): EconomyBalance {
  const context = contextFromInput(input);
  const persistedState = normalizePersistedState(input.persistedState);
  const runtime = applyPersistedState(buildBaseResources(context), defaultLevels(context), persistedState);
  return buildBalanceFromRuntime(context, runtime.resources, runtime.levels);
}

export function serializeEconomyState(balance: EconomyBalance) {
  return balance.persistedState;
}

export function canAffordUpgrade(balance: EconomyBalance, zoneId: EconomyZoneId) {
  const building = getBuilding(balance, zoneId);
  if (!building?.nextUpgrade) return { affordable: false, missing: [] as UpgradeCost[] };
  const missing = building.nextUpgrade.costs
    .map((cost) => ({
      resource: cost.resource,
      amount: Math.max(0, cost.amount - resourceById(balance.resources, cost.resource).stock),
    }))
    .filter((cost) => cost.amount > 0);
  return { affordable: missing.length === 0, missing };
}

export function applyBuildingUpgrade(balance: EconomyBalance, zoneId: EconomyZoneId): UpgradeAttempt {
  const building = getBuilding(balance, zoneId);
  if (!building?.nextUpgrade) return { ok: false, balance, message: "This building line is already at the current cap." };
  const affordability = canAffordUpgrade(balance, zoneId);
  if (!affordability.affordable) {
    const missingText = affordability.missing.map((cost) => `${resourceLabel(balance.resources, cost.resource)} +${cost.amount}`).join(" / ");
    return { ok: false, balance, message: `Not enough resources for ${building.label}. Missing ${missingText}.` };
  }

  const afterCosts = balance.resources.map((resource) => {
    const cost = building.nextUpgrade?.costs.find((item) => item.resource === resource.id);
    return patchResource(resource, { stock: -(cost?.amount ?? 0) });
  });
  const upgradedResources = applyModifiers(afterCosts, building.nextUpgrade.modifiers);
  const levels = balance.buildings.reduce((map, item) => {
    map[item.id] = item.id === zoneId ? ((item.currentLevel + 1) as 1 | 2 | 3) : item.currentLevel;
    return map;
  }, {} as Record<EconomyZoneId, 1 | 2 | 3>);
  const nextBalance = buildBalanceFromRuntime(balance.context, upgradedResources, levels);
  return {
    ok: true,
    balance: nextBalance,
    message: `${building.label} upgraded to Lv.${levels[zoneId]}. Resources, role flows, and conflict penalties were recalculated.`,
  };
}

export function getZoneResources(balance: EconomyBalance, zoneId: EconomyZoneId) {
  return ZONE_RESOURCES[zoneId].map((resourceId) => resourceById(balance.resources, resourceId));
}

export function getBuilding(balance: EconomyBalance, zoneId: EconomyZoneId) {
  return balance.buildings.find((building) => building.id === zoneId) ?? null;
}

export function getZoneConflicts(balance: EconomyBalance, zoneId: EconomyZoneId) {
  return balance.overview.conflicts.filter((conflict) => conflict.zoneId === zoneId || zoneId === "project");
}
