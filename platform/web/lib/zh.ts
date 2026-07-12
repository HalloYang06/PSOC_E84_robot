function 替换(value: string): string {
  return value
    .replaceAll("AI-Boss", "总控主管")
    .replaceAll("AI-FE-LEAD", "前端主理人")
    .replaceAll("AI-BE-LEAD", "后端主理人")
    .replaceAll("AI-RUNNER-GIT", "执行与版本")
    .replaceAll("AI-FE-GAME", "界面造景师")
    .replaceAll("AI-DEVOPS", "部署工位")
    .replaceAll("AI-PM", "项目管家")
    .replaceAll("AI-ARCH", "架构工位")
    .replaceAll("AI", "智能体")
    .replaceAll("Codex Thread", "线程模型")
    .replaceAll("Codex", "编码代理")
    .replaceAll("Thread", "线程")
    .replaceAll("MVP", "第一版")
    .replaceAll("develop", "开发主线")
    .replaceAll("main", "主分支")
    .replaceAll("PC1", "一号工位")
    .replaceAll("windows", "视窗系统")
    .replaceAll("Windows", "视窗系统")
    .replaceAll("linux", "开源系统")
    .replaceAll("Linux", "开源系统")
    .replaceAll("git", "版本库")
    .replaceAll("Git", "版本库")
    .replaceAll("node", "节点")
    .replaceAll("Node", "节点")
    .replaceAll("python", "脚本")
    .replaceAll("Python", "脚本")
    .replaceAll("web", "网页")
    .replaceAll("frontend", "前端")
    .replaceAll("backend", "后端")
    .replaceAll("hardware", "硬件")
    .replaceAll("runner", "执行节点")
    .replaceAll("api", "接口")
    .replaceAll("TASK-", "任务 ");
}

export function 中文化(text: string): string {
  return 替换(text);
}

export function 分支中文(text: string): string {
  return 替换(text)
    .replaceAll("ai/fe-lead", "前端主线")
    .replaceAll("ai/be-lead", "后端主线")
    .replaceAll("ai/runner", "执行主线")
    .replaceAll("ai/fe-game", "造景主线")
    .replaceAll("ai/be", "后端工位");
}

export function 系统中文(text: string): string {
  return 替换(text);
}
