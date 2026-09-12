# OpenPlayer DLSSNR 插件

为 [OpenPlayer](https://github.com/AreChen/OpenPlayer) 提供 DLSSNR 视频画面增强的可选插件，支持选择处理显卡、实时调整参数和暂停画面对比调节。

**实验性版本，需要 OpenPlayer 1.6.4 或更高版本、Windows x64 和兼容的 NVIDIA 显卡。** 这不是独立播放器，也不是 NVIDIA 官方产品。

## 安装使用

1. 从 [Releases](https://github.com/AreChen/openplayer-dlssnr/releases) 下载 `.opplugin`，在 OpenPlayer 的插件设置中安装。
2. 播放视频，从播放器控制栏打开 **DLSSNR** 面板，选择用于增强的显卡。
3. 选择包含 `nvngx_dlssnr.dll` 的目录，或填写 DLL 完整路径，然后开启增强。

**插件不附带 NVIDIA 运行库或 SDK**，需要自行准备有权使用且来源可信的 DLL。插件包含原生代码，请仅安装可信来源的插件和运行库。

## 主要能力

- 调整强度、风格、局部色调、结构和皮肤遮罩等参数，播放中和暂停时均可预览效果。
- 自动检测显卡并记住选择，多显卡环境下可指定增强使用的 GPU。
- 可在开启增强前选择处理帧率，默认 15 FPS；降低画面帧率，不改变音频播放速度。
- 支持将 HDR / Dolby Vision 输入转换为 SDR 后增强。
- 使用播放器原有控制层和主题组件，无需窗口捕获。

## 当前限制

- 支持最高 3840×2160 输入，增强输出为 SDR，不保留 HDR 输出。
- 实际处理速度取决于显卡、分辨率和参数，不保证实时 4K；帧率上限不是插帧，也不会提高显卡推理速度。
- 显卡选择仅作用于 NR 增强，不改变播放器解码和显示所用的显卡。
- 切换视频后需重新开启增强；关闭插件面板不会停止增强。
- 当前不提供插帧或超分辨率功能。

## 更多信息

- [版本说明](docs/releases/v0.4.0.md)
- [配置、使用细节与兼容性](docs/plugin-ui.md)
- [开发与测试](docs/development.md)
- [第三方组件与许可](THIRD_PARTY_NOTICES.md)

原生增强后端基于 [DLSS5Tool](https://github.com/banbanzhige/DLSS5Tool)。
