"use strict";
(() => {
  const api = window.openplayer;
  const t = String(api.locale).startsWith("zh") ? {
    close: "关闭", gpu: "处理显卡", loading: "正在检测显卡…", retry: "重试检测", detectionFailed: "显卡检测失败", runtime: "NR 运行时 DLL", browse: "选择 DLL 所在目录",
    style: "风格", standard: "默认", natural: "自然", cinema: "电影", local_tone: "局部色调", local_struct: "局部结构",
    skin_struct: "肤色结构", use_auto_mask: "自动肤色蒙版", applied: "参数已应用",
    frameRate: "增强帧率上限", sourceRate: "原始帧率（自动适配）", measuredRate: "测速上限", legacyRate: "兼容模式上限：30 FPS",
    modelPreset: "模型预设", modelAuto: "自动识别", modelDefault: "默认（预设 1）", modelSmall: "Small（预设 2）",
    modelDetectedSmall: "已识别 RTX 30 优化运行库，使用 Small 预设 2", modelDetectedDefault: "自动选择默认预设 1",
    sdr: "兼容模式：HDR / 杜比视界转 SDR", output: "增强输出：SDR · 保持原分辨率",
    intensity: "增强强度", start: "开启增强", stop: "停止并释放", choose: "请选择显卡", idle: "增强未开启", busy: "正在处理…",
    active: "增强已开启", waiting: "等待首帧", select: "请选择处理显卡和 NR 运行时。", unavailable: "当前播放器不支持原生视频挂载。",
    failed: "视频处理未能启动，请检查媒体格式与运行时。", savedMissing: "已保存的显卡当前不可用", stopped: "原生模块已停止",
  } : {
    close: "Close", gpu: "Processing GPU", loading: "Detecting GPUs…", retry: "Retry detection", detectionFailed: "GPU detection failed", runtime: "NR runtime DLL", browse: "Choose DLL directory",
    style: "Style", standard: "Default", natural: "Natural", cinema: "Cinema", local_tone: "Local tone", local_struct: "Local structure",
    skin_struct: "Skin structure", use_auto_mask: "Automatic skin mask", applied: "Settings applied",
    frameRate: "Enhancement frame rate limit", sourceRate: "Source frame rate (adaptive)", measuredRate: "Calibrated limit", legacyRate: "Compatibility limit: 30 FPS",
    modelPreset: "Model preset", modelAuto: "Automatic", modelDefault: "Default (preset 1)", modelSmall: "Small (preset 2)",
    modelDetectedSmall: "RTX 30 optimized runtime detected: using Small preset 2", modelDetectedDefault: "Automatically selected default preset 1",
    sdr: "Compatibility: HDR / Dolby Vision to SDR", output: "Enhancement output: SDR · Original resolution",
    intensity: "Intensity", start: "Enable enhancement", stop: "Stop and release", choose: "Select a GPU", idle: "Enhancement off", busy: "Working…",
    active: "Enhancement active", waiting: "Waiting for first frame", select: "Select a processing GPU and NR runtime.", unavailable: "This host does not support native video attachment.",
    failed: "Video processing did not start. Check media format and runtime.", savedMissing: "Saved GPU is unavailable", stopped: "Native module stopped",
  };
  const $ = (id) => document.getElementById(id);
  const smallPresetRuntimes = new Set(["749daadb43f11b2fc0bf39d92a67809978f27b9e96150b631d50fc8d1ec9e3ca"]);
  for (const node of document.querySelectorAll("[data-text]")) node.textContent = t[node.dataset.text];
  let busy = false, running = false, attached = false, devices = [];
  let deviceState = "loading";
  const defaults = { style: 0, intensity: 0.5, local_tone: 1, local_struct: 1, skin_struct: 0.5, use_auto_mask: false };
  const parameters = Object.keys(defaults);
  let preferences = { gpuUuid: "", runtimePath: "", modelPreset: "auto", normalizeSdr: true, frameRateLimit: 15, ...defaults };
  let pending = false, updateTimer;
  function readSettings() {
    return Object.fromEntries(parameters.map((key) => [key, key === "use_auto_mask" ? $(key).checked : Number($(key).value)]));
  }
  function amounts() {
    for (const key of parameters) {
      const output = $(key === "intensity" ? "amount" : `${key}-amount`);
      if (output) output.textContent = Number($(key).value).toFixed(2);
    }
  }
  function controls() {
    for (const id of ["retry", "browse", "gpu", "runtime", "modelPreset", "normalizeSdr", "frameRateLimit", "start"]) $(id).disabled = busy || attached;
    $("gpu").disabled ||= deviceState !== "ready";
    $("start").disabled ||= deviceState !== "ready";
    for (const id of parameters) $(id).disabled = busy && !attached;
    $("skin_struct").disabled ||= !$("use_auto_mask").checked;
    $("stop").disabled = busy || !running;
  }
  function renderDevices() {
    $("gpu").replaceChildren(new Option(deviceState === "loading" ? t.loading : deviceState === "failed" ? t.detectionFailed : t.choose, ""));
    for (const device of devices) $("gpu").add(new Option(`PCI ${device.pciBusId} | ${device.name}`, device.uuid));
    if (deviceState === "ready" && preferences.gpuUuid && !devices.some((d) => d.uuid === preferences.gpuUuid)) {
      $("gpu").add(new Option(`${t.savedMissing}: ${preferences.gpuUuid}`, preferences.gpuUuid));
    }
    if (deviceState === "ready") $("gpu").value = preferences.gpuUuid;
    $("retry").hidden = deviceState !== "failed";
  }
  async function save(settings = readSettings()) {
    preferences = { gpuUuid: deviceState === "ready" ? $("gpu").value : preferences.gpuUuid, runtimePath: $("runtime").value.trim(), modelPreset: $("modelPreset").value, normalizeSdr: $("normalizeSdr").checked, frameRateLimit: Number($("frameRateLimit").value), ...settings };
    await api.storage.set("preferences", preferences);
  }
  async function action(work) {
    if (busy) return;
    busy = true; $("error").textContent = ""; $("status").textContent = t.busy; controls();
    try { await work(); } catch (error) {
      $("error").textContent = String(error.message || error);
      await api.log.error($("error").textContent).catch(() => {});
    } finally { busy = false; await refresh().catch(() => {}); controls(); }
  }
  async function refresh() {
    const state = await api.native.video.status("enhance");
    running = state.running; attached = state.attached;
    $("status").textContent = state.supported ? (attached ? t.waiting : t.idle) : t.unavailable;
    $("device").textContent = "";
    if (running) {
      const owner = await api.native.call("enhance", "frames.status");
      if (owner.error) throw new Error(owner.error);
      if (owner.device) $("device").textContent = `${owner.device.name} | PCI ${owner.device.pciBusId}\n${owner.device.uuid}`;
      if (attached && !preferences.frameRateLimit) {
        const rate = Number(owner.profiledFrameRate);
        if (owner.profiledFrameRate != null && Number.isFinite(rate)) $("device").textContent += `\n${t.measuredRate}: ${rate.toFixed(1)} FPS`;
        else if (!api.capabilities.has("native.video.autoFrameRate")) $("device").textContent += `\n${t.legacyRate}`;
      }
      if (attached && state.filterEnabled && owner.workerPid) $("status").textContent = t.active;
      else if (attached && !state.filterEnabled) throw new Error(t.failed);
    }
    controls();
  }
  async function detectDevices() {
    deviceState = "loading"; renderDevices(); controls();
    try {
      await api.native.start("enhance");
      running = true;
      devices = await api.native.call("enhance", "devices.list");
      deviceState = "ready";
    } catch (error) { deviceState = "failed"; throw error; }
    finally { renderDevices(); }
  }
  $("retry").onclick = () => action(detectDevices);
  $("browse").onclick = () => action(async () => {
    const directory = await api.filesystem.pickDirectory();
    if (directory) { $("runtime").value = directory.replace(/[\\/]+$/, "") + "/nvngx_dlssnr.dll"; $("modelDetected").textContent = ""; await save(); }
  });
  async function flushSettings() {
    if (!pending) return;
    if (busy) { updateTimer = setTimeout(flushSettings, 150); return; }
    pending = false;
    await action(async () => {
      const settings = readSettings();
      if (attached) {
        const result = await api.native.call("enhance", "frames.update", { settings });
        if (!result.applied) throw new Error(result.error);
        await api.native.video.refreshPaused("enhance");
        $("applied").textContent = `${t.applied} (${result.revision})`;
      }
      await save(settings);
    });
    if (pending) updateTimer = setTimeout(flushSettings, 150);
  }
  for (const id of parameters) $(id).oninput = () => {
    amounts(); controls(); pending = true;
    clearTimeout(updateTimer); updateTimer = setTimeout(flushSettings, 150);
  };
  for (const id of ["gpu", "runtime", "modelPreset", "normalizeSdr", "frameRateLimit"]) $(id).onchange = () => action(() => {
    if (id === "runtime" || id === "modelPreset") $("modelDetected").textContent = "";
    return save();
  });
  $("start").onclick = () => action(async () => {
    await save();
    if (!preferences.gpuUuid || !preferences.runtimePath) throw new Error(t.select);
    try {
      await api.native.start("enhance"); running = true;
      devices = await api.native.call("enhance", "devices.list");
      renderDevices();
      if (!devices.some((d) => d.uuid === preferences.gpuUuid)) throw new Error(t.savedMissing);
      const runtime = await api.native.call("enhance", "runtime.inspect", { path: preferences.runtimePath });
      await api.native.call("enhance", "runtime.configure", runtime);
      const recognized = smallPresetRuntimes.has(runtime.sha256.toLowerCase());
      const preset = preferences.modelPreset === "auto" ? (recognized ? 2 : 1) : Number(preferences.modelPreset);
      $("modelDetected").textContent = preferences.modelPreset === "auto" ? (recognized ? t.modelDetectedSmall : t.modelDetectedDefault) : "";
      const rateOptions = preferences.frameRateLimit ? { frameRateLimit: preferences.frameRateLimit } : {
        ...(api.capabilities.has("native.video.autoFrameRate") ? { autoFrameRate: true } : { frameRateLimit: 30 }), adaptive: true,
      };
      await api.native.video.attach("enhance", { inputConversion: preferences.normalizeSdr ? "sdr-bt709" : "none", ...rateOptions, settings: { gpu_uuid: preferences.gpuUuid, preset, ...readSettings() } });
      for (let attempt = 0; attempt < 20; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 400));
        const owner = await api.native.call("enhance", "frames.status");
        if (owner.error) throw new Error(owner.error);
        if (owner.workerPid) {
          if (owner.device?.uuid !== preferences.gpuUuid) throw new Error("Processing GPU identity mismatch");
          return;
        }
      }
      throw new Error(t.failed);
    } catch (error) { await api.native.stop("enhance"); throw error; }
  });
  $("stop").onclick = () => action(() => api.native.stop("enhance"));
  $("close").onclick = () => api.ui.closeView();
  async function initialize() {
    if (!api.capabilities.has("native.video")) throw new Error(t.unavailable);
    preferences = { ...preferences, ...await api.storage.get("preferences") };
    $("runtime").value = preferences.runtimePath;
    $("modelPreset").value = ["auto", "1", "2"].includes(preferences.modelPreset) ? preferences.modelPreset : "auto";
    $("normalizeSdr").checked = preferences.normalizeSdr !== false;
    $("frameRateLimit").value = [0, 10, 15, 20, 24, 30].includes(preferences.frameRateLimit) ? preferences.frameRateLimit : 15;
    for (const key of parameters) {
      if (key === "use_auto_mask") $(key).checked = preferences[key] === true;
      else $(key).value = Number.isFinite(preferences[key]) ? preferences[key] : defaults[key];
    }
    amounts();
    renderDevices();
    await refresh();
    await detectDevices();
  }
  action(initialize);
  const timer = setInterval(() => {
    if (busy) return;
    busy = true;
    refresh().catch(async (error) => {
      if (/native (?:module|video operation) is busy/i.test(String(error.message || error))) return;
      $("error").textContent = String(error.message || error);
      await api.native.stop("enhance").catch(() => {});
      running = false; attached = false;
      $("status").textContent = t.stopped;
    }).finally(() => { busy = false; controls(); });
  }, 2000);
  window.addEventListener("pagehide", () => { clearInterval(timer); clearTimeout(updateTimer); });
})();
