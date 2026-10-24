# Saved as UTF-8 WITH BOM: Windows PowerShell 5.1 reads a file without BOM as ANSI (the accents would be garbled).
# RM SOFT - atualiza o servidor Windows do cliente para a versão nova (os dados ficam; a base é atualizada sozinha).
#     Set-ExecutionPolicy -Scope Process Bypass; .\atualizar.ps1      (PowerShell "Executar como administrador")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Compose = @("compose", "-f", "docker-compose.yml", "--env-file", ".env")
if (-not (Test-Path .env)) { Write-Host "Falta o .env: esta pasta não é uma instalação (use .\instalar.ps1)."; exit 1 }
$envValues = @{}; Get-Content .env | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $k, $v = $_ -split '=', 2; $envValues[$k] = $v }

# the server's identity, written again (the licence follows the machine, not the folder)
$guid = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Cryptography").MachineGuid
$lines = Get-Content .env | ForEach-Object { if ($_ -match "^RMSOFT_MACHINE_ID=") { "RMSOFT_MACHINE_ID=$guid" } else { $_ } }
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot ".env"), [string[]]$lines, (New-Object Text.UTF8Encoding($false)))

$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
Write-Host "== 1/3 Cópia da base antes de atualizar"
$dump = Join-Path (Join-Path $envValues["BACKUP_DIR"] "base") "antes_atualizacao_$stamp.dump"
New-Item -ItemType Directory -Force -Path (Split-Path $dump) | Out-Null
docker @Compose exec -T postgres sh -c "pg_dump -U `$POSTGRES_USER -d `$POSTGRES_DB -Fc > /tmp/antes.dump"
$container = (docker @Compose ps -q postgres).Trim()
docker cp "${container}:/tmp/antes.dump" $dump
Write-Host "   $dump"

Write-Host "== 2/3 Versão nova"
if (Test-Path ..\..\.git) { git -C ..\.. pull --ff-only } else { Write-Host "   (sem git: copie primeiro a pasta nova do RM SOFT por cima desta, mantendo o .env)" }

Write-Host "== 3/3 Reconstruir e reiniciar"
docker @Compose up -d --build
docker image prune -f | Out-Null
Write-Host "Atualizado. Os postos: Ctrl+F5 no navegador."
