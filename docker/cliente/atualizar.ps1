# Saved as UTF-8 WITH BOM: Windows PowerShell 5.1 reads a file without BOM as ANSI (the accents would be garbled).
# RM SOFT - atualiza o servidor Windows do cliente para a versão nova (os dados ficam; a base é atualizada sozinha).
# Copie primeiro os ficheiros do pacote novo (rmsoft-docker-<versão>) por cima desta pasta - o .env fica - e depois:
#     Set-ExecutionPolicy -Scope Process Bypass; .\atualizar.ps1      (PowerShell "Executar como administrador")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Compose = @("compose", "-f", "docker-compose.yml", "--env-file", ".env")
if (-not (Test-Path .env)) { Write-Host "Falta o .env: esta pasta não é uma instalação (use .\instalar.ps1)."; exit 1 }
if (-not (Test-Path VERSAO)) { Write-Host "Falta o ficheiro VERSAO: copie o pacote novo inteiro para esta pasta."; exit 1 }
$Versao = (Get-Content VERSAO -TotalCount 1).Trim()

# a native command whose messages are hidden: Windows PowerShell 5.1 would stop the script on its first error line
function Invoke-Quiet([scriptblock]$command) {
  $previous = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  try { & $command *> $null } finally { $ErrorActionPreference = $previous }
  return ($LASTEXITCODE -eq 0)
}
function Set-EnvValue($key, $value) {
  $lines = @(Get-Content .env | ForEach-Object { if ($_ -match "^$key=") { "$key=$value" } else { $_ } })
  if (-not ($lines -match "^$key=")) { $lines += "$key=$value" }  # an older .env without this line
  [IO.File]::WriteAllLines((Join-Path $PSScriptRoot ".env"), [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
}
$envValues = @{}; Get-Content .env | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $k, $v = $_ -split '=', 2; $envValues[$k] = $v }

# the server's identity, written again (the licence follows the machine, not the folder)
Set-EnvValue "RMSOFT_MACHINE_ID" (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Cryptography").MachineGuid

$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
Write-Host "== 1/4 Cópia da base antes de atualizar"
$dump = Join-Path (Join-Path $envValues["BACKUP_DIR"] "base") "antes_atualizacao_$stamp.dump"
New-Item -ItemType Directory -Force -Path (Split-Path $dump) | Out-Null
docker @Compose exec -T postgres sh -c "pg_dump -U `$POSTGRES_USER -d `$POSTGRES_DB -Fc > /tmp/antes.dump"
if ($LASTEXITCODE -ne 0) { Write-Host "ERRO: a cópia da base falhou - nada foi mudado."; exit 1 }
$container = (docker @Compose ps -q postgres).Trim()
docker cp "${container}:/tmp/antes.dump" $dump
Write-Host "   $dump"

Write-Host "== 2/4 Imagens da versão $Versao"
if (Invoke-Quiet { docker image inspect "rmsoft-backend:$Versao" }) {
  Write-Host "   já carregadas"
} else {
  $images = "rmsoft-imagens-$Versao.tar.gz"
  if (-not (Test-Path $images)) { Write-Host "ERRO: $images não está nesta pasta (copie o pacote novo inteiro)"; exit 1 }
  docker load -i $images
  if ($LASTEXITCODE -ne 0) { Write-Host "ERRO: não foi possível carregar as imagens - nada foi mudado."; exit 1 }
}
Set-EnvValue "APP_VERSION" $Versao

Write-Host "== 3/4 Reiniciar com a versão nova"
docker @Compose up -d
if ($LASTEXITCODE -ne 0) { Write-Host "ERRO: o arranque falhou (ver as mensagens acima)"; exit 1 }

Write-Host "== 4/4 Limpar as versões antigas"
foreach ($repo in @("rmsoft-backend", "rmsoft-web")) {
  docker images $repo --format "{{.Tag}}" | Where-Object { $_ -and $_ -ne $Versao } | ForEach-Object {
    $tag = $_
    Invoke-Quiet { docker image rm "${repo}:$tag" } | Out-Null
  }
}
Get-ChildItem "rmsoft-imagens-*.tar.gz" | Where-Object { $_.Name -ne "rmsoft-imagens-$Versao.tar.gz" } | Remove-Item
Write-Host "Atualizado para a versão $Versao. Os postos: Ctrl+F5 no navegador."
