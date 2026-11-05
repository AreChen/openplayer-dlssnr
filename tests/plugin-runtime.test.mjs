import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../plugin/runtime.js", import.meta.url), "utf8");
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise(setImmediate); };
function setup(preferences = {}) {
  const handlers = {}, calls = [], toasts = [];
  let attached = false;
  const runtime = { path: "nr.dll", sha256: "749daadb43f11b2fc0bf39d92a67809978f27b9e96150b631d50fc8d1ec9e3ca" };
  const api = {
    locale: "en", commands: { register: (name, handler) => { handlers[name] = handler; } },
    capabilities: { has: () => true },
    media: { snapshot: async () => ({ path: "video.mp4" }) },
    storage: { get: async () => ({ gpuUuid: "gpu1", runtimePath: "nr.dll", modelPreset: "auto", frameRateLimit: 0, ...preferences }) },
    ui: { toast: async (message) => { toasts.push(message); }, openView: async () => {} },
    log: { error: async () => {} },
    native: {
      start: async () => { calls.push(["start"]); },
      stop: async () => { calls.push(["stop"]); attached = false; },
      call: async (_id, method) => {
        calls.push([method]);
        if (method === "devices.list") return [{ uuid: "gpu1" }];
        if (method === "runtime.inspect") return runtime;
        if (method === "frames.status") return { workerPid: 42, device: { uuid: "gpu1" } };
        return {};
      },
      video: {
        status: async () => ({ supported: true, running: attached, attached }),
        attach: async (_id, options) => { calls.push(["attach", options]); attached = true; return { attached: true }; },
      },
    },
  };
  vm.runInNewContext(source, { openplayer: api, setTimeout: (fn) => { fn(); return 0; } });
  return { handlers, calls, toasts };
}

test("shortcut toggles NR without an open panel and preserves model and adaptive settings", async () => {
  const { handlers, calls } = setup();
  assert.equal(typeof handlers["plugin.toggle-dlssnr"], "function");
  handlers["plugin.toggle-dlssnr"]();
  await flush();
  const options = calls.find(([name]) => name === "attach")[1];
  assert.equal(options.settings.gpu_uuid, "gpu1");
  assert.equal(options.settings.preset, 2);
  assert.equal(options.autoFrameRate, true);
  handlers["plugin.toggle-dlssnr"]();
  await flush();
  assert.equal(calls.filter(([name]) => name === "stop").length, 1);
});

test("shortcut reports missing configuration without starting a module", async () => {
  const { handlers, calls, toasts } = setup({ runtimePath: "" });
  handlers["plugin.toggle-dlssnr"]();
  await flush();
  assert.equal(calls.length, 0);
  assert.ok(toasts.length);
});
