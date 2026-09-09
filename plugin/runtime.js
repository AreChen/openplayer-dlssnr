"use strict";
openplayer.commands.register("plugin.open-dlssnr", async () => {
  if (!openplayer.capabilities.has("native.video")) {
    await openplayer.ui.toast("DLSSNR requires the OpenPlayer native.video development host.");
    return;
  }
  await openplayer.ui.openView("enhance");
});
