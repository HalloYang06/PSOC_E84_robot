import { readFileSync } from "node:fs";
import { join } from "node:path";

const clientPath = join(
  process.cwd(),
  "apps/web/app/projects/[id]/rehab-arm-control/rehab-arm-control-client.tsx",
);
const source = readFileSync(clientPath, "utf8");

const requiredPatterns = [
  {
    label: "dedicated muscle iframe telemetry helper",
    pattern: /const syncStitchMuscleTelemetry = \(\) =>/,
  },
  {
    label: "stable DOM markers for live EMG channels",
    pattern: /data-codex-emg-channel/,
  },
  {
    label: "CH1 stale baseline value is overwritten",
    pattern: /\["基线 15µV",\s*emgChannelTexts\[0\]\]/,
  },
  {
    label: "CH2 stale active value is overwritten",
    pattern: /\["活跃 142µV",\s*emgChannelTexts\[1\]\]/,
  },
  {
    label: "CH3 stale weak value is overwritten",
    pattern: /\["微弱 24µV",\s*emgChannelTexts\[2\]\]/,
  },
  {
    label: "CH4 stale baseline value is overwritten",
    pattern: /\["基线 12µV",\s*emgChannelTexts\[3\]\]/,
  },
];

const missing = requiredPatterns.filter(({ pattern }) => !pattern.test(source));
if (missing.length) {
  console.error("Missing Stitch muscle EMG bridge coverage:");
  for (const item of missing) {
    console.error(`- ${item.label}`);
  }
  process.exit(1);
}

if (source.includes('["活跃 142µV", "等待遥测"]')) {
  console.error("Stale CH2 EMG text is still replaced with a fake waiting state.");
  process.exit(1);
}

console.log("Stitch muscle EMG bridge covers the four live ADC voltage channels.");
