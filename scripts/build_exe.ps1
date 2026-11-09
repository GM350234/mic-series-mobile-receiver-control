# Build MicSeriesControl.exe and a release folder.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name MicSeriesControl --icon (Join-Path $root 'assets\icon.ico') `
  --add-data "$root\web;web" `
  (Join-Path $root 'launcher.py')

$release = Join-Path $root 'release\MicSeriesControl'
if (Test-Path $release) { Remove-Item -LiteralPath $release -Recurse -Force }
New-Item -ItemType Directory -Path $release -Force | Out-Null
Copy-Item (Join-Path $root 'dist\MicSeriesControl.exe') $release
Copy-Item (Join-Path $root 'driver') $release -Recurse
Copy-Item (Join-Path $root 'README.md') $release
Copy-Item (Join-Path $root '使用说明.txt') $release
Copy-Item (Join-Path $root 'LICENSE') $release
New-Item -ItemType Directory -Path (Join-Path $release 'docs') -Force | Out-Null
Copy-Item (Join-Path $root 'docs\screenshot.png') (Join-Path $release 'docs')
Copy-Item (Join-Path $root 'docs\screenshot-dark.png') (Join-Path $release 'docs')
Copy-Item (Join-Path $root 'docs\CREDITS.md') (Join-Path $release 'docs')
Copy-Item (Join-Path $root 'docs\PROTOCOL.md') (Join-Path $release 'docs')
Copy-Item (Join-Path $root 'docs\可行性报告.md') (Join-Path $release 'docs')

$zip = Join-Path $root 'release\MicSeriesControl-win64.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $release -DestinationPath $zip
Write-Host "Built: $zip"
