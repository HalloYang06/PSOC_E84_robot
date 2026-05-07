export type OpenSourceAssetPack = {
  id: string;
  name: string;
  url: string;
  license: string;
  status: "planned" | "approved" | "reference-only";
  categories: string[];
  intendedUse: string[];
};

export const openSourceAssetPacks: OpenSourceAssetPack[] = [
  {
    id: "phaser-template-nextjs",
    name: "Phaser Next.js Template",
    url: "https://github.com/phaserjs/template-nextjs",
    license: "MIT",
    status: "approved",
    categories: ["engine", "scene", "integration"],
    intendedUse: ["项目地图主基底", "Phaser 与 React/Next 的桥接"]
  },
  {
    id: "top-down-react-phaser-template",
    name: "Top Down React Phaser Game Template",
    url: "https://github.com/blopa/top-down-react-phaser-game-template",
    license: "Repository-declared",
    status: "reference-only",
    categories: ["movement", "top-down", "interaction"],
    intendedUse: ["顶视角移动参考", "地图交互结构参考"]
  },
  {
    id: "kenney-tiny-town",
    name: "Kenney Tiny Town",
    url: "https://kenney.nl/assets/tiny-town",
    license: "CC0",
    status: "approved",
    categories: ["tileset", "town", "map"],
    intendedUse: ["项目广场", "城镇道路", "公共建筑底图"]
  },
  {
    id: "kenney-isometric-miniature-farm",
    name: "Kenney Isometric Miniature Farm",
    url: "https://kenney.nl/assets/isometric-miniature-farm",
    license: "CC0",
    status: "approved",
    categories: ["farm", "buildings", "map"],
    intendedUse: ["项目农场主地图", "地块和建筑主题"]
  },
  {
    id: "kenney-ui-pack",
    name: "Kenney UI Pack",
    url: "https://opengameart.org/content/ui-pack",
    license: "CC0",
    status: "approved",
    categories: ["hud", "toolbar", "buttons"],
    intendedUse: ["顶部 HUD", "底部工具栏", "按钮和面板皮肤"]
  },
  {
    id: "farming-set-pixel-art",
    name: "Farming Set Pixel Art",
    url: "https://opengameart.org/content/farming-set-pixel-art",
    license: "Source page review required",
    status: "planned",
    categories: ["farm", "crops", "decoration"],
    intendedUse: ["地块成长状态", "农场细节补充"]
  },
  {
    id: "farmhand",
    name: "Farmhand",
    url: "https://github.com/jeremyckahn/farmhand",
    license: "GPL-2.0 / CC BY-NC-SA 4.0 assets",
    status: "reference-only",
    categories: ["economy", "ux", "farming-loop"],
    intendedUse: ["经营节奏参考", "资源条和操作节奏参考"]
  }
];

export const projectMapModuleOrder = [
  "project-gate",
  "requirements-mailbox",
  "task-fields",
  "ai-station",
  "runner-workshop",
  "approval-gate",
  "discussion-yard",
  "delivery-forge",
  "lab-building",
  "archive-barn"
] as const;

export const projectMapModuleLabels: Record<(typeof projectMapModuleOrder)[number], string> = {
  "project-gate": "项目大门",
  "requirements-mailbox": "需求信箱",
  "task-fields": "任务田块",
  "ai-station": "AI 工位站",
  "runner-workshop": "电脑车间",
  "approval-gate": "审批门岗",
  "discussion-yard": "留言小院",
  "delivery-forge": "交付工坊",
  "lab-building": "实验楼",
  "archive-barn": "档案仓"
};
