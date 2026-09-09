// Real host-generated view bridge and styles, simulated host replies; no GPU work.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { createRequire } from "node:module";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: {
  host: { type: "string", default: "../RustPlayer/apps/desktop" },
  modules: { type: "string" }, output: { type: "string" },
  channel: { type: "string", default: "chrome" },
} });
assert(values.modules && values.output, "provide --modules (Playwright node_modules) and --output (new directory)");
const host = path.resolve(values.host), output = path.resolve(values.output);
assert(!fs.existsSync(output), "output must be new");
fs.mkdirSync(output, { recursive: true });
const { chromium } = createRequire(path.join(path.resolve(values.modules), "package.json"))("playwright");
const ts = createRequire(path.join(host, "package.json"))("typescript");
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file);
  const module = { exports: {} }; cache.set(file, module.exports);
  const compiled = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(compiled, { exports: module.exports, require: (name) => load(path.resolve(path.dirname(file), name + ".ts")) }, { filename: file });
  return module.exports;
}
const { buildPluginViewDocument } = load(path.join(host, "src/app/pluginRuntime/viewDocument.ts"));
const template = fs.readFileSync("plugin/view.html", "utf8"), script = fs.readFileSync("plugin/view.js", "utf8");
const theme = { surface: "#141618", panel: "#202326", panelStrong: "#292d31", text: "#f0f2f4", muted: "#b0b7bf", faint: "#7c858e", accent: "#62c5ac", danger: "#e47777", line: "#3d444b", control: "#30363c" };
function fixture(seed) {
  window.fixture = { calls: [], preferences: seed, running: false, attached: false, fail: false };
  const devices = [{ uuid: "GPU-0", name: "NVIDIA GeForce RTX 3080 Ti", pciBusId: "0000:01:00.0" }, { uuid: "GPU-1", name: "NVIDIA GeForce RTX 3080 Ti", pciBusId: "0000:07:00.0" }];
  window.addEventListener("message", ({ data: m }) => {
    if (m.type !== "openplayer:viewRequest") return;
    const f = window.fixture; f.calls.push(m);
    let result = null, error;
    try {
      if (m.command === "plugin.storage.get") result = f.preferences;
      else if (m.command === "plugin.storage.set") f.preferences = m.args.value;
      else if (m.command === "filesystem.pickDirectory") result = "E:/Runtime";
      else if (m.command === "native.start") f.running = true;
      else if (m.command === "native.stop") { f.running = false; f.attached = false; }
      else if (m.command === "native.video.status") result = { supported: true, running: f.running, attached: f.attached, filterEnabled: f.attached };
      else if (m.command === "native.video.attach") {
        if (f.fail) throw new Error("Simulated attachment failure");
        if (m.args.options.settings.gpu_uuid !== "GPU-1") throw new Error("GPU 0 must not be selected by default");
        f.attached = true;
      } else if (m.command === "native.call") {
        const { method } = m.args;
        if (method === "devices.list") result = devices;
        else if (method === "frames.status") result = { workerPid: f.attached ? 123 : null, device: f.attached ? devices[1] : null };
        else if (method === "runtime.inspect") result = { path: "E:/Runtime/nvngx_dlssnr.dll", sha256: "a".repeat(64) };
        else if (method !== "runtime.configure") throw new Error(`Unexpected native method ${method}`);
      } else if (!m.command.startsWith("plugin.log.") && m.command !== "ui.closePluginView") throw new Error(`Unexpected command ${m.command}`);
    } catch (e) { error = e.message; }
    window.postMessage({ type: "openplayer:viewResponse", pluginId: m.pluginId, requestId: m.requestId, ok: !error, result, error }, "*");
  });
}
function document(locale, seed = null) {
  const html = template.replace("<!-- SCRIPT -->", `<script>(${fixture.toString()})(${JSON.stringify(seed)});${script}</script>`);
  return buildPluginViewDocument(html, { id: "test.dlssnr", permissions: ["native.process", "native.video", "filesystem.pick"] }, locale, theme);
}
const browser = await chromium.launch({ headless: true, channel: values.channel });
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 420, height: 720 } });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setContent(document("zh-CN"));
  await page.waitForFunction(() => !document.getElementById("connect").disabled);
  assert.equal(await page.locator("#gpu").inputValue(), "");
  await page.locator("#connect").click();
  await page.waitForFunction(() => !document.getElementById("gpu").disabled);
  assert.equal(await page.locator("#gpu").inputValue(), "", "never select the first GPU automatically");
  await page.locator("#gpu").selectOption("GPU-1");
  await page.locator("#browse").click();
  await page.waitForFunction(() => window.fixture.preferences?.runtimePath === "E:/Runtime/nvngx_dlssnr.dll");
  await page.locator("#start").click();
  await page.waitForFunction(() => document.getElementById("status").textContent === "增强已开启");
  assert(await page.locator("#gpu").isDisabled());
  await page.screenshot({ path: path.join(output, "active-zh.png") });
  const saved = await page.evaluate(() => window.fixture.preferences);
  assert.equal(saved.gpuUuid, "GPU-1");
  await page.locator("#stop").click();
  await page.waitForFunction(() => !window.fixture.running && !document.getElementById("start").disabled);
  await page.setContent(document("en-US", saved));
  await page.waitForFunction(() => !document.getElementById("connect").disabled);
  assert.equal(await page.locator("#gpu").inputValue(), "GPU-1");
  await page.evaluate(() => { window.fixture.fail = true; });
  await page.locator("#start").click();
  await page.waitForFunction(() => document.getElementById("error").textContent.includes("Simulated"));
  await page.waitForTimeout(2300);
  assert.match(await page.locator("#error").textContent(), /Simulated/, "polling must not erase errors");
  assert.equal(await page.evaluate(() => window.fixture.running), false, "failed attachment releases native module");
  for (const size of [{ width: 420, height: 720 }, { width: 320, height: 480 }]) {
    await page.setViewportSize(size);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const overflow = await page.locator("button, label, h1").evaluateAll((nodes) => nodes.filter((n) => n.scrollWidth > n.clientWidth + 1).map((n) => n.id || n.tagName));
    assert.deepEqual(overflow, []);
    await page.locator("#error").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, `error-en-${size.width}.png`) });
  }
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(output, "report.json"), JSON.stringify({ passed: true, simulatedHost: true, gpuWork: false, assertions: ["explicit GPU selection", "storage restore", "shared filesystem bridge", "enable/stop", "failure cleanup", "persistent error", "responsive layout"], pageErrors: errors }, null, 2));
  console.log("PASS: plugin view bridge, controls, persistence, errors and layouts (simulated host)");
} finally { await browser.close(); }
