import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

try {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const mobileRoot = path.resolve(here, "..");
  const repoRoot = path.resolve(mobileRoot, "..", "..");
  const source = path.join(repoRoot, "platform", "web", "public", "rehab-arm-mobile");
  const target = path.join(mobileRoot, "www");

  if (!fs.existsSync(source)) {
    throw new Error(`Missing PWA source directory: ${source}`);
  }

  fs.rmSync(target, { recursive: true, force: true });
  fs.mkdirSync(target, { recursive: true });
  copyTree(source, target);

  const indexPath = path.join(target, "index.html");
  let indexHtml = fs.readFileSync(indexPath, "utf8");
  indexHtml = indexHtml.replace(
    "</head>",
    '    <meta name="capacitor-app-shell" content="android" />\n  </head>'
  );
  fs.writeFileSync(indexPath, indexHtml, "utf8");

  console.log(`Synced ${source} -> ${target}`);
} catch (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
}

function copyTree(sourceDir, targetDir) {
  for (const entry of fs.readdirSync(sourceDir, { withFileTypes: true })) {
    const sourcePath = path.join(sourceDir, entry.name);
    const targetPath = path.join(targetDir, entry.name);
    if (entry.isDirectory()) {
      fs.mkdirSync(targetPath, { recursive: true });
      copyTree(sourcePath, targetPath);
      continue;
    }
    if (entry.isFile()) {
      fs.copyFileSync(sourcePath, targetPath);
    }
  }
}
