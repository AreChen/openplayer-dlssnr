"use strict";
(() => {
  const api = window.openplayer;
  const t = String(api.locale).startsWith("zh") ? {
    close: "关闭", gpu: "处理显卡", connect: "授权并读取显卡", runtime: "NR 运行时 DLL", browse: "选择 DLL 所在目录",
    intensity: "增强强度", start: "开启增强", stop: "停止并释放", choose: "请选择显卡", idle: "增强未开启", busy: "正在处理…",
    active: "增强已开启", waiting: "等待首帧", select: "请选择处理显卡和 NR 运行时。", unavailable: "当前播放器不支持原生视频挂载。",
    failed: "视频处理未能启动，请检查媒体格式与运行时。", savedMissing: "已保存的显卡当前不可用", stopped: "原生模块已停止",
  } : {
    close: "Close", gpu: "Processing GPU", connect: "Authorize and list GPUs", runtime: "NR runtime DLL", browse: "Choose DLL directory",
    intensity: "Intensity", start: "Enable enhancement", stop: "Stop and release", choose: "Select a GPU", idle: "Enhancement off", busy: "Working…",
    active: "Enhancement active", waiting: "Waiting for first frame", select: "Select a processing GPU and NR runtime.", unavailable: "This host does not support native video attachment.",
    failed: "Video processing did not start. Check media format and runtime.", savedMissing: "Saved GPU is unavailable", stopped: "Native module stopped",
  };
  const $ = (id) => document.getElementById(id);
  for (const node of document.querySelectorAll("[data-text]")) node.textContent = t[node.dataset.text];
  let busy = false, running = false, attached = false, devices = [];
  let preferences = { gpuUuid: "", runtimePath: "", intensity: 0.5 };
  function controls() {
    for (const id of ["connect", "browse", "gpu", "runtime", "intensity", "start"]) $(id).disabled = busy || attached;
    $("stop").disabled = busy || !running;
  }
  function renderDevices() {
    $("gpu").replaceChildren(new Option(t.choose, ""));
    for (const device of devices) $("gpu").add(new Option(`PCI ${device.pciBusId} | ${device.name}`, device.uuid));
    if (preferences.gpuUuid && !devices.some((d) => d.uuid === preferences.gpuUuid)) {
      $("gpu").add(new Option(`${t.savedMissing}: ${preferences.gpuUuid}`, preferences.gpuUuid));
    }
    $("gpu").value = preferences.gpuUuid;
  }
  async function save() {
    preferences = { gpuUuid: $("gpu").value, runtimePath: $("runtime").value.trim(), intensity: Number($("intensity").value) };
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
      if (attached && state.filterEnabled && owner.workerPid) $("status").textContent = t.active;
      else if (attached && !state.filterEnabled) throw new Error(t.failed);
    }
    controls();
  }
  $("connect").onclick = () => action(async () => {
    await api.native.start("enhance");
    running = true;
    devices = await api.native.call("enhance", "devices.list");
    renderDevices();
  });
  $("browse").onclick = () => action(async () => {
    const directory = await api.filesystem.pickDirectory();
    if (directory) { $("runtime").value = directory.replace(/[\\/]+$/, "") + "/nvngx_dlssnr.dll"; await save(); }
  });
  $("intensity").oninput = () => { $("amount").textContent = Number($("intensity").value).toFixed(2); };
  for (const id of ["intensity", "gpu", "runtime"]) $(id).onchange = () => action(save);
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
      await api.native.video.attach("enhance", { settings: { gpu_uuid: preferences.gpuUuid, intensity: preferences.intensity } });
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
    $("intensity").value = preferences.intensity;
    $("intensity").oninput();
    renderDevices();
    await refresh();
    if (running) { devices = await api.native.call("enhance", "devices.list"); renderDevices(); }
  }
  action(initialize);
  const timer = setInterval(() => {
    if (busy) return;
    busy = true;
    refresh().catch(async (error) => {
      $("error").textContent = String(error.message || error);
      await api.native.stop("enhance").catch(() => {});
      running = false; attached = false;
      $("status").textContent = t.stopped;
    }).finally(() => { busy = false; controls(); });
  }, 2000);
  window.addEventListener("pagehide", () => clearInterval(timer));
})();
