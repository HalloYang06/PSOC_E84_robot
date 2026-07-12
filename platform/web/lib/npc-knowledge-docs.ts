import "server-only";

import { promises as fs } from "node:fs";
import path from "node:path";

type SnapshotRequest = {
  seatId: string;
  handoffPath: string;
};

export type NpcKnowledgeSnapshot = {
  exists: boolean;
  updatedAt: string | null;
  highlights: string[];
};

function workspaceRoot() {
  return path.resolve(process.cwd(), "..", "..");
}

function normalizeRelativeHandoffPath(value: string) {
  const relativePath = String(value || "").replace(/\\/g, "/").replace(/^\/+/, "");
  if (!relativePath.startsWith("docs/ai-handoffs/")) return "";
  return relativePath;
}

function collectSectionBulletLines(markdown: string, heading: string) {
  const lines = markdown.split(/\r?\n/);
  const target = heading.trim().toLowerCase();
  const collected: string[] = [];
  let active = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      if (active && collected.length) break;
      continue;
    }
    if (/^##\s+/.test(line)) {
      if (line.toLowerCase() === target) {
        active = true;
        continue;
      }
      if (active) break;
    }
    if (!active) continue;
    if (/^- /.test(line)) {
      collected.push(line.slice(2).trim());
    }
  }
  return collected.filter(Boolean);
}

function extractHighlights(markdown: string) {
  const currentShell = collectSectionBulletLines(markdown, "## Current execution shell").slice(0, 2);
  const continuation = collectSectionBulletLines(markdown, "## Continuation notes").slice(0, 1);
  const addOnSkills = collectSectionBulletLines(markdown, "## Add-on skills")
    .filter((line) => !/no add-on skills yet/i.test(line))
    .slice(0, 1);
  const combined = [...currentShell, ...addOnSkills, ...continuation].filter(Boolean);
  if (combined.length) return combined.slice(0, 3);

  return markdown
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !/^#/.test(line))
    .slice(0, 3);
}

async function readSnapshot(relativePath: string): Promise<NpcKnowledgeSnapshot> {
  const root = workspaceRoot();
  const filePath = path.resolve(root, relativePath);
  const normalizedRoot = root.replace(/\\/g, "/").toLowerCase();
  const normalizedFile = filePath.replace(/\\/g, "/").toLowerCase();
  if (!normalizedFile.startsWith(normalizedRoot)) {
    return {
      exists: false,
      updatedAt: null,
      highlights: [],
    };
  }

  try {
    const [stats, markdown] = await Promise.all([
      fs.stat(filePath),
      fs.readFile(filePath, "utf8"),
    ]);
    return {
      exists: true,
      updatedAt: stats.mtime.toISOString(),
      highlights: extractHighlights(markdown),
    };
  } catch {
    return {
      exists: false,
      updatedAt: null,
      highlights: [],
    };
  }
}

export async function loadNpcKnowledgeSnapshots(requests: SnapshotRequest[]) {
  const entries = await Promise.all(
    requests.map(async (request) => {
      const seatId = String(request.seatId || "").trim();
      const relativePath = normalizeRelativeHandoffPath(request.handoffPath);
      if (!seatId || !relativePath) {
        return [
          seatId,
          {
            exists: false,
            updatedAt: null,
            highlights: [],
          } satisfies NpcKnowledgeSnapshot,
        ] as const;
      }
      return [seatId, await readSnapshot(relativePath)] as const;
    }),
  );

  return Object.fromEntries(entries);
}
