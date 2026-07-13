# compact_docker_disk.ps1 — shrink the ballooned Docker/WSL virtual disk back to real size.
# MUST run as Administrator. Data in Docker volumes (incl. the loaded Qdrant RAG) is NOT touched.
#
# How to run:
#   1. Quit Docker Desktop (tray icon -> Quit Docker Desktop).
#   2. Open PowerShell AS ADMINISTRATOR.
#   3.  cd C:\Users\rubin\Documents\Chavruta.AI
#       powershell -ExecutionPolicy Bypass -File scripts\compact_docker_disk.ps1

$vhdx = "C:\Users\rubin\AppData\Local\Docker\wsl\disk\docker_data.vhdx"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "❌ Not elevated. Re-open PowerShell as Administrator and run again." -ForegroundColor Red
    exit 1
}

Write-Host "Stopping Docker + WSL so the disk is released..." -ForegroundColor Cyan
Get-Process "Docker Desktop","com.docker.backend","com.docker.build","docker-sandbox" -EA SilentlyContinue |
    Stop-Process -Force
try { Stop-Service com.docker.service -Force -EA SilentlyContinue } catch {}
wsl --shutdown
Start-Sleep -Seconds 8

if (-not (Test-Path $vhdx)) { Write-Host "vhdx not found: $vhdx" -ForegroundColor Red; exit 1 }
$before = (Get-Item $vhdx).Length / 1GB
Write-Host ("vhdx before: {0:N1} GB" -f $before)

Write-Host "Compacting (a few minutes)..." -ForegroundColor Cyan
try {
    Optimize-VHD -Path $vhdx -Mode Full -ErrorAction Stop
} catch {
    Write-Host "Optimize-VHD unavailable, falling back to diskpart..." -ForegroundColor Yellow
    $dp = @"
select vdisk file="$vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@
    $dp | diskpart
}

$after = (Get-Item $vhdx).Length / 1GB
Write-Host ("✅ vhdx after: {0:N1} GB  (freed {1:N1} GB)" -f $after, ($before - $after)) -ForegroundColor Green
Write-Host "Done. Re-open Docker Desktop when you want to resume the RAG load."
