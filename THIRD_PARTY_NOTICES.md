# Third-party boundaries

- `third_party/DLSS5Tool` is the unmodified MIT-licensed upstream source, pinned to
  `78ee043e2800317b8140859bec85726b15189696`. Its full copyright and license are
  retained in that submodule. We compile its native host and adapt its Python
  engine, without copying its GUI or changing its proprietary runtime.
- NVIDIA DLSS SDK headers/import libraries are external build inputs. The
  `nvngx_dlssnr.dll` runtime is an explicit external input. Neither the SDK nor
  runtime is committed or redistributed by this repository. Building and
  distribution remain subject to their own applicable terms.
- The tested backend uses experimental Feature 18 and a caller compatibility
  hook in its own worker process. It is not evidence of a supported public NVIDIA
  video SDK contract. No hook is installed into OpenPlayer or another process.
- Source-code MIT permissions do not grant rights to proprietary NVIDIA DLLs.
  Runtime provenance, supported use and redistribution must be reviewed before
  packaging a public plugin. The local proof does not establish those rights.
- NumPy, Pillow, FFmpeg, Python, mpv and optional VapourSynth retain their
  respective licenses. They are not relicensed by this project.
- The upstream `img/01.png` is an AI-generated demonstration image according to
  its README. The local test clip is a generated moving/cropped derivative for
  pipeline validation, not a representative film benchmark or a quality promise.

All `.local` runtime binaries, SDK-derived build products, configuration,
test media and performance artifacts are excluded from version control.
