# Saved as UTF-8 WITH BOM: Windows PowerShell 5.1 reads a file without BOM as ANSI (the accents would be garbled).
# RM SOFT - instala o RM SOFT num servidor Windows com Docker Desktop (Windows 10/11 Pro ou Windows Server), a partir
# da pasta do pacote (rmsoft-docker-<versão>, copiada por pen USB): as imagens vêm prontas, sem código-fonte.
# Feito pelo técnico da RM SOFT, uma vez, numa janela PowerShell "Executar como administrador", dentro dessa pasta:
#     Set-ExecutionPolicy -Scope Process Bypass; .\instalar.ps1
# Pode ser repetido sem perigo: nunca muda as palavras-passe já criadas nem apaga dados.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Compose = @("compose", "-f", "docker-compose.yml", "--env-file", ".env")

function Say($text)  { Write-Host "`n== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`nERRO: $text" -ForegroundColor Red; exit 1 }
function Read-Env { $values = @{}; Get-Content .env | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $k, $v = $_ -split '=', 2; $values[$k] = $v }; $values }
function Set-EnvValue($key, $value) {
  $lines = @(Get-Content .env | ForEach-Object { if ($_ -match "^$key=") { "$key=$value" } else { $_ } })
  if (-not ($lines -match "^$key=")) { $lines += "$key=$value" }  # an older .env without this line
  [IO.File]::WriteAllLines((Join-Path $PSScriptRoot ".env"), [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
}
# a native command whose messages are hidden: Windows PowerShell 5.1 would stop the script on its first error line
function Invoke-Quiet([scriptblock]$command) {
  $previous = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  try { & $command *> $null } finally { $ErrorActionPreference = $previous }
  return ($LASTEXITCODE -eq 0)
}
function New-Secret { $bytes = New-Object byte[] 36; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes); ([Convert]::ToBase64String($bytes) -replace '[/+=]', '').Substring(0, 40) }

if (-not (Test-Path VERSAO)) { Fail "ficheiro VERSAO em falta: execute este script dentro da pasta do pacote rmsoft-docker-<versão>" }
$Versao = (Get-Content VERSAO -TotalCount 1).Trim()

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Fail "abra o PowerShell com 'Executar como administrador'" }

Say "1/8 Docker Desktop"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Fail "instale primeiro o Docker Desktop (https://www.docker.com/products/docker-desktop), abra-o uma vez, e repita."
}
if (-not (Invoke-Quiet { docker info })) { Fail "o Docker Desktop não está a funcionar: abra-o e espere que diga 'Engine running'" }
Write-Host "Lembrete: no Docker Desktop > Settings > General, ative 'Start Docker Desktop when you sign in'."

Say "2/8 Configuração (.env)"
if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  $client  = Read-Host "Nome do cliente (ex.: Padaria Kilamba)"
  $backups = Read-Host "Pasta das cópias de segurança [C:/RMSOFT/copias]"
  $port    = Read-Host "Porta para os postos [80]"
  if (-not $backups) { $backups = "C:/RMSOFT/copias" }
  if (-not $port) { $port = "80" }
  Set-EnvValue "CLIENT_NAME" $client
  Set-EnvValue "POSTGRES_PASSWORD" (New-Secret)
  Set-EnvValue "JWT_SECRET_KEY" (New-Secret)
  Set-EnvValue "BACKUP_DIR" ($backups -replace '\\', '/')
  Set-EnvValue "HTTP_PORT" $port
  Write-Host ".env criado (palavras-passe geradas - não o envie a ninguém)."
} else {
  Write-Host ".env já existe: mantido (as palavras-passe nunca mudam)."
}

Say "3/8 Identidade deste servidor (para a licença)"
$guid = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Cryptography").MachineGuid
if (-not $guid) { Fail "MachineGuid do Windows não encontrado" }
Set-EnvValue "RMSOFT_MACHINE_ID" $guid   # written again at each install/update: a copied folder takes the new machine's
Set-EnvValue "APP_VERSION" $Versao
$envValues = Read-Env
if (-not $envValues["JWT_SECRET_KEY"] -or -not $envValues["POSTGRES_PASSWORD"]) { Fail ".env incompleto (JWT_SECRET_KEY / POSTGRES_PASSWORD)" }

Say "4/8 Pastas das cópias e firewall"
New-Item -ItemType Directory -Force -Path (Join-Path $envValues["BACKUP_DIR"] "empresas"), (Join-Path $envValues["BACKUP_DIR"] "base") | Out-Null
$port = $envValues["HTTP_PORT"]; if (-not $port) { $port = "80" }
if (-not (Get-NetFirewallRule -DisplayName "RM SOFT" -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName "RM SOFT" -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Private,Domain | Out-Null
}

Say "5/8 Imagens do RM SOFT $Versao"
if (Invoke-Quiet { docker image inspect "rmsoft-backend:$Versao" }) {
  Write-Host "Já carregadas."
} else {
  $images = "rmsoft-imagens-$Versao.tar.gz"
  if (-not (Test-Path $images)) { Fail "$images não está nesta pasta (copie o pacote inteiro)" }
  Write-Host "A carregar $images (alguns minutos)..."
  docker load -i $images
  if ($LASTEXITCODE -ne 0) { Fail "não foi possível carregar as imagens" }
}

Say "6/8 Arrancar"
docker @Compose up -d
if ($LASTEXITCODE -ne 0) { Fail "o arranque falhou (ver as mensagens acima)" }
Write-Host -NoNewline "A aguardar o arranque"
for ($i = 0; $i -lt 60; $i++) {
  if (Invoke-Quiet { docker @Compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" }) { Write-Host " - pronto."; break }
  Write-Host -NoNewline "."; Start-Sleep -Seconds 5
}

Say "7/8 Conta SUPER_ADMIN da RM SOFT"
docker @Compose exec backend python -m app.cli create-superadmin --if-none

Say "8/8 Pronto"
$code = (docker @Compose exec -T backend python -m app.cli installation-code | Out-String).Trim()
$suffix = if ($port -ne "80") { ":$port" } else { "" }
Write-Host "Cliente:                 $($envValues['CLIENT_NAME'])"
Write-Host "Abrir nos postos:        http://$($env:COMPUTERNAME.ToLower())$suffix"
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notlike '*WSL*' -and $_.InterfaceAlias -notlike '*vEthernet*' } |
  ForEach-Object { Write-Host "                         http://$($_.IPAddress)$suffix" }
Write-Host "Código de instalação:    $code"
Write-Host ""
Write-Host "Próximo passo: gerar a licença deste código na plataforma RM SOFT (Empresas > Contrato > Gerar licença)"
Write-Host "e importá-la em Definições da Empresa > Licença (ou Empresas > Licença, como SUPER_ADMIN)."
