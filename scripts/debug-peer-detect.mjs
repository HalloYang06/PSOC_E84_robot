import { chromium } from "playwright";
const WEB = "http://127.0.0.1:3000";
const TOKEN = process.env.TOKEN;
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addCookies([{ name: "farm_access_token", value: TOKEN, domain: "127.0.0.1", path: "/", sameSite: "Lax" }]);
const page = await ctx.newPage();
await page.goto(`${WEB}/projects/proj_ai_collab/workbench`, { waitUntil: "networkidle", timeout: 30000 });
await page.waitForTimeout(2000);
// 用 strong[class*="npcName"] 直接定位名字元素再 closest('li')
const nameLoc = page.locator(`strong:text-is("前端工位-副")`).first();
await nameLoc.waitFor({ timeout: 8000 });
// 在浏览器里 ascend 到最近的 li.npcRow，并点 button[title="打开瓷砖"]
const clicked = await page.evaluate(() => {
  const strongs = Array.from(document.querySelectorAll('strong'));
  const target = strongs.find(s => s.textContent?.trim() === '前端工位-副');
  if (!target) return { ok: false, why: 'strong not found' };
  let li = target.closest('li');
  // 跳过 group li（含 ul），找内层 li (不含 ul 的 li)
  while (li && li.querySelector('ul')) {
    li = li.parentElement?.closest('li') ?? null;
    // 反向：进入子 li
    break;
  }
  // 实际 closest 已经是最近 li 了，但可能是 group。判断方法：是不是 npcRow class
  let actual = target.closest('li');
  // 若有 ul，则向下找具体 row
  if (actual && actual.querySelector('ul')) {
    const rows = Array.from(actual.querySelectorAll('li'));
    actual = rows.find(r => r.querySelector('strong')?.textContent?.trim() === '前端工位-副') || actual;
  }
  const btn = actual?.querySelector('button[title="打开瓷砖"]');
  if (!btn) return { ok: false, why: 'no btn', cls: actual?.className };
  btn.click();
  return { ok: true, cls: actual?.className };
});
console.log("clicked:", clicked);
await page.waitForTimeout(5500);
// 拿瓷砖 header h2/h3 看 NPC 名
const tileNames = await page.evaluate(() => {
  const heads = Array.from(document.querySelectorAll('h2, h3, [class*="tileHeader"], [class*="seatName"]'));
  return heads.map(h => (h.textContent||'').trim()).filter(Boolean).slice(0,15);
});
console.log("tile heads:", JSON.stringify(tileNames));
const data = await page.evaluate(() => {
  const msgs = Array.from(document.querySelectorAll('[data-role]'));
  const counts = {};
  for (const el of msgs) {
    const r = el.getAttribute('data-role');
    counts[r] = (counts[r]||0)+1;
  }
  const selfSamples = msgs.filter(el => el.getAttribute('data-role')==='self').slice(0,3).map(el => (el.textContent||'').slice(0,80).replace(/\s+/g,' '));
  return { counts, selfSamples, total: msgs.length };
});
console.log("data:", JSON.stringify(data, null, 2));
await browser.close();

