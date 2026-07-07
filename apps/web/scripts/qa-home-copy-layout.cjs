const fs = require("fs");
const path = require("path");

const WEB_HOME = path.resolve(__dirname, "../public/rehab-arm-mobile/home.html");
const ANDROID_HOME = path.resolve(__dirname, "../../mobile/rehab-arm-android/www/home.html");

const TODAY = "\u4eca\u5929";
const CURRENT = "\u4eca";
const L1_SPEC = /L1\s*\u89c4\u8303\u7248/;
const PRODUCT_TITLE_WITH_L1 = /\u9886\u52a8\u5eb7\u590d\u624b\u81c2\uff08\s*L1\s*\u89c4\u8303\u7248\s*\uff09/;
const EXERCISE_IMAGE_CROP = "background-size: cover; background-position: center 58%;";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function read(file) {
  return fs.readFileSync(file, "utf8");
}

function checkHome(file, label) {
  const html = read(file);

  assert(!html.includes(`>${TODAY}</div>`), `${label}: current-day marker must use a single character`);
  assert(html.includes(`>${CURRENT}</div>`), `${label}: current-day marker should render the current-day glyph`);
  assert(!L1_SPEC.test(html), `${label}: patient-facing home must not mention the L1 spec label`);
  assert(!PRODUCT_TITLE_WITH_L1.test(html), `${label}: product title must not include the L1 spec label`);
  assert(html.includes(EXERCISE_IMAGE_CROP), `${label}: exercise image must crop generated top label`);
}

checkHome(WEB_HOME, "web home");
checkHome(ANDROID_HOME, "android webview home");

console.log("PASS home copy/layout QA");
