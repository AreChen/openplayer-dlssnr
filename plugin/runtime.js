"use strict";
openplayer.commands.register("plugin.open-dlssnr", async () => {
  if (!openplayer.capabilities.has("native.video")) {
    await openplayer.ui.toast("DLSSNR requires OpenPlayer 1.6.10 or newer.");
    return;
  }
  await openplayer.ui.openView("enhance");
});

(() => {
  const api = openplayer;
  const zh = String(api.locale).startsWith("zh");
  const text = zh ? {
    configure: "请先打开 DLSSNR 面板，选择显卡和运行时。", noMedia: "请先打开视频。",
    missingGpu: "已保存的处理显卡不可用，请重新选择。", failed: "DLSSNR 未能启动。",
    on: "DLSSNR 增强已开启", off: "DLSSNR 增强已关闭",
  } : {
    configure: "Open DLSSNR and select a GPU and runtime first.", noMedia: "Open a video first.",
    missingGpu: "The saved processing GPU is unavailable; select it again.", failed: "DLSSNR did not start.",
    on: "DLSSNR enabled", off: "DLSSNR disabled",
  };
  const smallRuntime = "749daadb43f11b2fc0bf39d92a67809978f27b9e96150b631d50fc8d1ec9e3ca";
  const defaults = { style: 0, intensity: 0.5, local_tone: 1, local_struct: 1, skin_struct: 0.5, use_auto_mask: false };
  const busyError = (error) => /native (?:module|video operation) is busy/i.test(String(error?.message || error));
  async function retryBusy(work) {
    for (let attempt = 0; ; attempt++) {
      try { return await work(); } catch (error) {
        if (!busyError(error) || attempt >= 119) throw error;
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
    }
  }
  let latestSpeed = 1, lastObservedSpeed = null, syncingSpeed = false;
  async function syncSpeed() {
    if (syncingSpeed) return;
    syncingSpeed = true;
    try {
      let sent;
      do {
        sent = latestSpeed;
        const state = await api.native.video.status("enhance");
        if (state.attached) await retryBusy(() => api.native.call("enhance", "frames.speed", { speed: sent }));
      } while (sent !== latestSpeed);
    } catch (error) {
      await api.log.error(String(error?.message || error)).catch(() => {});
    } finally { syncingSpeed = false; }
  }
  api.onReady(() => api.events.subscribe("playback.snapshot"));
  api.onEvent((event, snapshot) => {
    const speed = snapshot?.speed;
    if (event !== "playback.snapshot" || !Number.isFinite(speed) || speed <= 0 || speed > 100 || speed === lastObservedSpeed) return;
    lastObservedSpeed = latestSpeed = speed;
    void syncSpeed();
  });
  let toggling = false;
  async function toggle() {
    if (!api.capabilities.has("native.video")) throw new Error(text.failed);
    const state = await api.native.video.status("enhance");
    if (state.attached) {
      await retryBusy(() => api.native.stop("enhance"));
      await api.ui.toast(text.off);
      return;
    }
    const preferences = { gpuUuid: "", runtimePath: "", modelPreset: "auto", normalizeSdr: true, frameRateLimit: 15,
      ...defaults, ...await api.storage.get("preferences") };
    if (!preferences.gpuUuid || !preferences.runtimePath) throw new Error(text.configure);
    const media = await api.media.snapshot();
    if (!media?.path) throw new Error(text.noMedia);
    let attachedByUs = false, started = false;
    try {
      await retryBusy(() => api.native.start("enhance"));
      started = true;
      const devices = await retryBusy(() => api.native.call("enhance", "devices.list"));
      if (!devices.some((device) => device.uuid === preferences.gpuUuid)) throw new Error(text.missingGpu);
      const runtime = await retryBusy(() => api.native.call("enhance", "runtime.inspect", { path: preferences.runtimePath }));
      await retryBusy(() => api.native.call("enhance", "runtime.configure", runtime));
      const modelPreset = ["auto", "1", "2"].includes(preferences.modelPreset) ? preferences.modelPreset : "auto";
      const preset = modelPreset === "auto" ? (runtime.sha256.toLowerCase() === smallRuntime ? 2 : 1) : Number(modelPreset);
      const rate = [0, 10, 15, 20, 24, 30].includes(preferences.frameRateLimit) ? preferences.frameRateLimit : 15;
      const rateOptions = rate ? { frameRateLimit: rate, adaptive: true } : {
        ...(api.capabilities.has("native.video.autoFrameRate") ? { autoFrameRate: true } : { frameRateLimit: 30 }), adaptive: true,
      };
      const settings = Object.fromEntries(Object.entries(defaults).map(([key, fallback]) => [key,
        key === "use_auto_mask" ? preferences[key] === true : Number.isFinite(preferences[key]) ? preferences[key] : fallback]));
      await retryBusy(() => api.native.video.attach("enhance", { inputConversion: preferences.normalizeSdr !== false ? "sdr-bt709" : "none",
        ...rateOptions, settings: { gpu_uuid: preferences.gpuUuid, preset, ...settings } }));
      attachedByUs = true;
      const current = await api.media.snapshot();
      const speed = Number.isFinite(current?.speed) && current.speed > 0 && current.speed <= 100 ? current.speed : 1;
      await retryBusy(() => api.native.call("enhance", "frames.speed", { speed }));
      for (let attempt = 0; attempt < 20; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 400));
        const owner = await retryBusy(() => api.native.call("enhance", "frames.status"));
        if (owner.error) throw new Error(owner.error);
        if (owner.workerPid) {
          if (owner.device?.uuid !== preferences.gpuUuid) throw new Error("Processing GPU identity mismatch");
          await api.ui.toast(text.on).catch(() => {});
          return;
        }
      }
      throw new Error(text.failed);
    } catch (error) {
      const current = await api.native.video.status("enhance").catch(() => null);
      if (started && (attachedByUs || (!state.running && !current?.attached)) && !busyError(error)) {
        await api.native.stop("enhance").catch(() => {});
      }
      throw error;
    }
  }
  api.commands.register("plugin.toggle-dlssnr", () => {
    if (toggling) return;
    toggling = true;
    void toggle().catch(async (error) => {
      const message = String(error?.message || error);
      await api.log.error(message).catch(() => {});
      await api.ui.toast(message).catch(() => {});
    }).finally(() => { toggling = false; });
  });
})();
