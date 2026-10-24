# Saved as UTF-8 WITH BOM: Windows PowerShell 5.1 reads a file without BOM as ANSI (the accents would be garbled).
# RM SOFT - run by the uninstaller (Painel de controlo > Programas): removes the 2 services, the firewall rule and the
# daily copy task. The DATA STAY in C:\ProgramData\RMSOFT (database, .env, logs) and in the copies' folder: a new
# installation finds them again. To erase everything, delete C:\ProgramData\RMSOFT by hand - after a last copy.
$ErrorActionPreference = "Continue"
$App = Split-Path $PSScriptRoot -Parent
$D = Join-Path $env:ProgramData "RMSOFT"
New-Item -ItemType Directory -Force -Path (Join-Path $D "logs") | Out-Null
Start-Transcript -Path (Join-Path $D "logs\instalacao.log") -Append | Out-Null
Write-Host "`n######## $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - desinstalação ($App)"

$WinSW = Join-Path $App "servico\rmsoft-servico.exe"
if (Get-Service "RMSOFT-Servidor" -ErrorAction SilentlyContinue) {
  & $WinSW stop 2>&1 | ForEach-Object { Write-Host $_ }
  & $WinSW uninstall 2>&1 | ForEach-Object { Write-Host $_ }
}
if (Get-Service "RMSOFT-BaseDados" -ErrorAction SilentlyContinue) {
  Stop-Service "RMSOFT-BaseDados" -Force
  & (Join-Path $App "pgsql\bin\pg_ctl.exe") unregister -N "RMSOFT-BaseDados" 2>&1 | ForEach-Object { Write-Host $_ }
}
Get-NetFirewallRule -DisplayName "RM SOFT" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Unregister-ScheduledTask -TaskName "RMSOFT-CopiaBase" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Serviços removidos. Os dados ficam em $D."
Stop-Transcript | Out-Null
exit 0
