param([string]$MpvInclude = "$PSScriptRoot/../.local/include")
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$include = (Resolve-Path -LiteralPath $MpvInclude).Path
if (!(Test-Path -LiteralPath "$include/mpv/client.h")) { throw 'Provide official mpv client.h under MpvInclude/mpv.' }
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
$vs = & rtk proxy $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or !$vs) { throw 'Visual Studio C++ build tools are required.' }
& "$vs/Common7/Tools/Launch-VsDevShell.ps1" -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$output = Join-Path $root '.local/build'
New-Item -ItemType Directory -Force -Path $output | Out-Null
Push-Location $output
try {
    & rtk proxy cl.exe /nologo /std:c++17 /O2 /EHsc /MT "/I$include" "$root/native/mpv_frame_probe.cpp" /link "/OUT:$output/mpv_frame_probe.exe"
    if ($LASTEXITCODE -ne 0) { throw 'mpv frame probe build failed.' }
} finally { Pop-Location }
