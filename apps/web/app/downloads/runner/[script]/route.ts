import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { NextResponse } from "next/server";

const ALLOWED_RUNNER_SCRIPTS = new Set([
  "register-runner.ps1",
  "register-runner.sh",
  "connect-ai-collab-runner.ps1",
  "connect-ai-collab-runner.sh",
  "sync-runner-threads.ps1",
  "sync-runner-threads.sh",
  "sync-codex-session-threads.ps1",
  "sync-codex-session-threads.sh",
  "sync-claude-session-threads.ps1",
  "sync-claude-session-threads.sh",
  "platform-workstation-adapter.py",
  "platform-provider-executor.py",
]);

function findRunnerScriptPath(filename: string) {
  let current = process.cwd();
  for (let depth = 0; depth < 8; depth += 1) {
    const candidate = path.join(current, "scripts", filename);
    if (existsSync(candidate)) {
      return candidate;
    }
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return path.join(process.cwd(), "scripts", filename);
}

export async function GET(_: Request, context: { params: { script: string } }) {
  const { script } = context.params;
  const filename = path.basename(String(script || ""));
  if (!ALLOWED_RUNNER_SCRIPTS.has(filename)) {
    return NextResponse.json({ error: "runner script not found" }, { status: 404 });
  }

  const scriptPath = findRunnerScriptPath(filename);
  let body = "";
  try {
    body = await readFile(scriptPath, "utf8");
  } catch {
    return NextResponse.json({ error: "runner script not available" }, { status: 404 });
  }
  return new NextResponse(body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}
