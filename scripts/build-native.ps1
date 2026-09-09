param([Parameter(Mandatory)][string]$DlssSdk)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sdk = (Resolve-Path -LiteralPath $DlssSdk).Path
$include = Join-Path $sdk 'include'
$library = Join-Path $sdk 'lib/Windows_x86_64/x64/nvsdk_ngx_s.lib'
if (!(Test-Path -LiteralPath "$include/nvsdk_ngx.h") -or !(Test-Path -LiteralPath $library)) {
    throw 'NVIDIA DLSS SDK headers or import library are missing.'
}
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
$vs = & rtk proxy $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or !$vs) { throw 'Visual Studio C++ build tools are required.' }
# Import the toolchain into this process; do not change the machine environment.
& "$vs/Common7/Tools/Launch-VsDevShell.ps1" -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$output = Join-Path $root '.local/build'
New-Item -ItemType Directory -Force -Path $output | Out-Null
$patched = Join-Path $output 'patched/native_host_v2'
New-Item -ItemType Directory -Force -Path $patched | Out-Null
Copy-Item -LiteralPath "$root/third_party/DLSS5Tool/native_host_v2/dlssnr_host_v2.cpp" -Destination "$patched/dlssnr_host_v2.cpp"
& rtk proxy git -C $root apply --directory=.local/build/patched "$root/native/dlssnr-adapter-selection.patch"
if ($LASTEXITCODE -ne 0) { throw 'Local adapter-selection patch does not match the pinned upstream source.' }
Push-Location $output
try {
    & rtk proxy cl.exe /nologo /std:c++17 /O2 /EHsc /MT /LD "/I$include" "$patched/dlssnr_host_v2.cpp" $library Advapi32.lib User32.lib dxgi.lib /link "/OUT:$output/dlssnr_host_v2.dll"
    if ($LASTEXITCODE -ne 0) { throw 'Native host build failed.' }
} finally { Pop-Location }
