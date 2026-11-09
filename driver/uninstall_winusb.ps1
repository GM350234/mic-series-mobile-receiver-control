# Undo install_winusb.ps1: remove the driver package and the local signing cert.
# Run elevated. Audio (MI_01) and HID (MI_00) are never touched.
#
# Adapted from hogancv/dji-mic-mini-monitor (MIT).

$ErrorActionPreference = 'Continue'
$subject = 'CN=DJI Mic PC Control Local Signing'

function Say($msg) { Write-Host $msg }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Say "[ERROR] Must run as Administrator."
    exit 1
}

Say "============================================================"
Say " DJI Mic PC Control - WinUSB uninstall"
Say "============================================================"
Say ""

# ---------- 1. driver package ----------
Say "[1/3] Removing driver package(s) built from djimic_pc_winusb.inf ..."
$removed = 0
$enum = & pnputil.exe /enum-drivers 2>&1 | Out-String
foreach ($block in ($enum -split "`r?`n`r?`n")) {
    if ($block -match 'djimic_pc_winusb\.inf') {
        if ($block -match '(oem\d+\.inf)') {
            $oem = $Matches[1]
            Say "      deleting $oem ..."
            & pnputil.exe /delete-driver $oem /uninstall /force | Out-String | Write-Host
            if ($LASTEXITCODE -eq 0) { $removed++ }
        }
    }
}
if ($removed -eq 0) { Say "      nothing to delete (already clean?)" }
Say ""

# ---------- 2. certificates ----------
Say "[2/3] Removing the local signing certificate ..."
$found = Get-ChildItem Cert:\LocalMachine\My, Cert:\LocalMachine\Root, Cert:\LocalMachine\TrustedPublisher |
         Where-Object { $_.Subject -eq $subject }
if (-not $found) {
    Say "      not found (already clean?)"
}
foreach ($c in $found) {
    try {
        $store = $c.PSParentPath -replace '^.*?::', ''
        Remove-Item -LiteralPath $c.PSPath -Force
        Say "      removed $($c.Thumbprint) from $store"
    } catch {
        Say "      [WARN] could not remove $($c.Thumbprint): $_"
    }
}
Say ""

# ---------- 3. rescan ----------
Say "[3/3] Rescanning devices ..."
& pnputil.exe /scan-devices | Out-Null
Start-Sleep -Seconds 2
$dev = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like '*VID_2CA3&PID_4011&MI_06*' }
if ($dev) {
    $dev | Select-Object Status, Class, FriendlyName, Problem |
        Format-List | Out-String | Write-Host
    Say "Problem 28 here is the expected post-uninstall state."
}
Say ""
Say "Finished. Audio (MI_01) and HID (MI_00) were not touched."
