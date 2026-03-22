$ErrorActionPreference = "Stop"

$versionTag = "v0_3"
$appName = "Portable Backup Tool"
$buildRoot = "build_$versionTag"
$distRootRelative = "dist_$versionTag\$appName"

if (Test-Path $buildRoot) {
  Remove-Item $buildRoot -Recurse -Force
}

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --windowed `
  --workpath $buildRoot `
  --distpath "dist_$versionTag" `
  --name $appName `
  app/main.py

$distRoot = Join-Path $PSScriptRoot $distRootRelative
$exePath = Join-Path $distRoot "Portable Backup Tool.exe"

if (-not (Test-Path $exePath)) {
  throw "Build succeeded but output EXE was not found: $exePath"
}

if (Test-Path $buildRoot) {
  Remove-Item $buildRoot -Recurse -Force
}

Write-Host ""
Write-Host "Built EXE:"
Write-Host $exePath
