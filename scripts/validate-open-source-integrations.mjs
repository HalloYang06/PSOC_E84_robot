import fs from "node:fs/promises";

const filePath = new URL("../apps/web/lib/open-source-integrations.json", import.meta.url);
const integrations = JSON.parse(await fs.readFile(filePath, "utf8"));

const required = ["id", "name", "category", "github", "docs", "uiUse", "runnerUse", "platformAction"];
const failures = [];

for (const item of integrations) {
  for (const key of required) {
    if (!String(item[key] ?? "").trim()) {
      failures.push(`${item.id ?? item.name ?? "unknown"} missing ${key}`);
    }
  }
  for (const key of ["github", "docs"]) {
    const url = String(item[key] ?? "");
    if (!/^https:\/\/github\.com\/|^https:\/\/docs\.foxglove\.dev\/|^https:\/\/labelstud\.io\/|^https:\/\/mlflow\.org\/|^https:\/\/langfuse\.com\//.test(url)) {
      failures.push(`${item.id} has unsupported ${key}: ${url}`);
    }
  }
}

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}

console.log(JSON.stringify({ integrations: integrations.length, ids: integrations.map((item) => item.id) }, null, 2));
