# Saved as UTF-8 WITH BOM: Windows PowerShell 5.1 reads a file without BOM as ANSI (the accents would be garbled).
# RM SOFT - configures this server once the setup (RMSOFT-Setup.exe) has copied the program. Run by the setup, as
# administrator, at the first installation and at every update; it can be run again by hand without danger:
#     powershell -ExecutionPolicy Bypass -File "C:\Program Files\RMSOFT\instalacao\configurar.ps1" -App "C:\Program Files\RMSOFT"
#
# First installation (-Respostas: the setup's answers, a file deleted at once): the .env with new secrets, the database
# (PostgreSQL in C:\ProgramData\RMSOFT\base, reachable from this PC only), the SUPER_ADMIN account.
# Every time: the database brought to the program's version, the 2 Windows services (RMSOFT-BaseDados, RMSOFT-Servidor),
# the firewall rule, the daily copy of the whole database, the installation code.
# Never changes a password or a secret already created, never deletes data. Log: C:\ProgramData\RMSOFT\logs\instalacao.log
param(
  [Parameter(Mandatory = $true)][string]$App,
  [string]$Respostas = ""
)
$ErrorActionPreference = "Stop"
$D = Join-Path $env:ProgramData "RMSOFT"
$Exe = Join-Path $App "servidor\rmsoft-servidor.exe"
$PgBin = Join-Path $App "pgsql\bin"
$Base = Join-Path $D "base"
$DbService = "RMSOFT-BaseDados"
$Servico = "RMSOFT-Servidor"
$WinSW = Join-Path $App "servico\rmsoft-servico.exe"

New-Item -ItemType Directory -Force -Path $D, (Join-Path $D "logs"), (Join-Path $D "uploads") | Out-Null
Start-Transcript -Path (Join-Path $D "logs\instalacao.log") -Append | Out-Null
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"

function Say($text) { Write-Host "`n== $text" }
function Fail($text) {
  Write-Host "`nERRO: $text"
  Stop-Transcript | Out-Null
  exit 1
}
function New-Secret {
  $bytes = New-Object byte[] 36
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  ([Convert]::ToBase64String($bytes) -replace '[/+=]', '').Substring(0, 40)
}
function Write-Utf8($path, [string[]]$lines, [bool]$bom = $false) {
  [IO.File]::WriteAllLines($path, $lines, (New-Object Text.UTF8Encoding($bom)))
}
function Read-Env {
  $values = @{}
  Get-Content (Join-Path $D ".env") -Encoding UTF8 | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    $values[$k] = $v.Trim()
  }
  $values
}
# A program of ours (PostgreSQL, rmsoft-servidor.exe): its messages go to the log, its exit code is returned.
function Invoke-Native($file, [string[]]$arguments) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $file @arguments 2>&1 | ForEach-Object { Write-Host $_ }
  $code = $LASTEXITCODE
  $ErrorActionPreference = $old
  return $code
}
function Test-PortBusy([int]$port) {
  [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}
function Wait-Database([int]$port) {
  for ($i = 0; $i -lt 90; $i++) {
    & (Join-Path $PgBin "pg_isready.exe") -h 127.0.0.1 -p $port -q
    if ($LASTEXITCODE -eq 0) { return }
    Start-Sleep -Seconds 1
  }
  Fail "a base de dados não arrancou (veja $Base\log)"
}

try {
  Write-Host "`n######## $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - configuração do RM SOFT ($App)"
  if (-not (Test-Path $Exe)) { Fail "o programa não está em $Exe" }

  # ---------------------------------------------------------------------------------------------- the setup's answers
  $answers = @{}
  if ($Respostas -and (Test-Path $Respostas)) {
    Get-Content $Respostas -Encoding UTF8 | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object {
      $k, $v = $_ -split '=', 2
      $answers[$k] = $v
    }
    Remove-Item $Respostas -Force  # it holds the SUPER_ADMIN password: never left on the disk
  }

  # ------------------------------------------------------------------------------------------------------------ .env
  Say "1/8 Configuração"
  $envFile = Join-Path $D ".env"
  if (-not (Test-Path $envFile)) {
    if (-not $answers.ContainsKey("PORTA")) { Fail "primeira instalação sem as respostas do instalador: execute de novo o RMSOFT-Setup.exe" }
    $dbPort = 5433  # never 5432: a PostgreSQL of another program may already be there
    while ((Test-PortBusy $dbPort) -and $dbPort -lt 5450) { $dbPort++ }
    $copias = $answers["COPIAS"]
    if (-not $copias) { $copias = Join-Path $D "copias" }
    Write-Utf8 $envFile @(
      "# RM SOFT - a configuração deste servidor, feita pelo instalador.",
      "# Nunca enviar este ficheiro a ninguém: tem as palavras-passe.",
      "# Nunca mudar JWT_SECRET_KEY: os segredos guardados (SMTP, Telegram...) ficariam ilegíveis.",
      "DEPLOYMENT_MODE=local",
      "DEBUG=false",
      "LICENSE_REQUIRED=true",
      "AGT_QUEUE=base",
      "DATABASE_URL=postgresql+asyncpg://rmsoft:$(New-Secret)@127.0.0.1:$dbPort/rmsoft",
      "JWT_SECRET_KEY=$(New-Secret)",
      "FRONTEND_DIR=$(Join-Path $App 'ecras')",
      "BACKUP_DIR=$copias",
      "RMSOFT_PORT=$($answers['PORTA'])"
    )
    # Only the administrators and the services (SYSTEM) may read it
    icacls $envFile /inheritance:r /grant:r "*S-1-5-32-544:(F)" "*S-1-5-18:(F)" | Out-Null
    Write-Host "Criado: $envFile"
  } else {
    Write-Host "Já existe: $envFile (mantido)"
  }
  $cfg = Read-Env
  if ($cfg["DATABASE_URL"] -notmatch '://rmsoft:([^@]+)@127\.0\.0\.1:(\d+)/') { Fail "DATABASE_URL inesperado em $envFile" }
  $dbPassword = $Matches[1]
  $dbPort = [int]$Matches[2]
  $port = [int]$cfg["RMSOFT_PORT"]
  $copias = $cfg["BACKUP_DIR"]
  New-Item -ItemType Directory -Force -Path $copias -ErrorAction SilentlyContinue | Out-Null
  if (-not (Test-Path $copias)) { Write-Host "AVISO: a pasta das cópias $copias não está acessível (disco externo desligado?)" }

  # -------------------------------------------------------------------------------------------------------- database
  Say "2/8 Base de dados"
  if (-not (Test-Path (Join-Path $Base "PG_VERSION"))) {
    New-Item -ItemType Directory -Force -Path $Base | Out-Null
    $me = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    icacls $Base /grant "*${me}:(OI)(CI)F" "*S-1-5-20:(OI)(CI)F" | Out-Null  # S-1-5-20: NetworkService, who runs it
    $pwFile = Join-Path $env:TEMP "rmsoft_db_$(Get-Random).txt"
    try {
      Write-Utf8 $pwFile @($dbPassword)
      $code = Invoke-Native (Join-Path $PgBin "initdb.exe") @("-D", $Base, "-U", "rmsoft", "--pwfile=$pwFile", "-E", "UTF8",
        "--locale-provider=icu", "--icu-locale=pt-PT", "--locale=C", "-A", "scram-sha-256")
    } finally {
      Remove-Item $pwFile -Force -ErrorAction SilentlyContinue
    }
    if ($code -ne 0) { Fail "initdb falhou (código $code)" }
    Add-Content -Path (Join-Path $Base "postgresql.conf") -Encoding ASCII -Value @(
      "",
      "# RM SOFT",
      "listen_addresses = '127.0.0.1'",
      "port = $dbPort",
      "logging_collector = on",
      "log_directory = 'log'",
      "log_filename = 'postgresql-%a.log'",
      "log_truncate_on_rotation = on"
    )
    icacls $Base /grant "*S-1-5-20:(OI)(CI)F" /T /Q | Out-Null
    Write-Host "Base criada em $Base (porta $dbPort, só este PC)"
  }
  if (-not (Get-Service $DbService -ErrorAction SilentlyContinue)) {
    $code = Invoke-Native (Join-Path $PgBin "pg_ctl.exe") @("register", "-N", $DbService, "-U", "NT AUTHORITY\NetworkService",
      "-D", $Base, "-S", "auto", "-w", "-t", "120")
    if ($code -ne 0) { Fail "não foi possível criar o serviço $DbService" }
    sc.exe description $DbService "RM SOFT: a base de dados (PostgreSQL). Precisa de estar a funcionar para o RMSOFT-Servidor." | Out-Null
  }
  Start-Service $DbService
  Wait-Database $dbPort
  $env:PGPASSWORD = $dbPassword
  try {
    $exists = & (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $dbPort -U rmsoft -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'rmsoft'"
    if ("$exists".Trim() -ne "1") {
      $code = Invoke-Native (Join-Path $PgBin "createdb.exe") @("-h", "127.0.0.1", "-p", "$dbPort", "-U", "rmsoft", "rmsoft")
      if ($code -ne 0) { Fail "não foi possível criar a base rmsoft" }
    }
  } finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
  }

  # ------------------------------------------------------------------------------------------- schema, SUPER_ADMIN
  Say "3/8 Estrutura da base (versão do programa)"
  Push-Location $D  # rmsoft-servidor.exe reads the .env of the current folder
  try {
    $code = Invoke-Native $Exe @("atualizar-base")
    if ($code -ne 0) { Fail "a atualização da base falhou (código $code)" }

    Say "4/8 Conta SUPER_ADMIN"
    if ($answers.ContainsKey("ADMIN_TELEFONE")) {
      $env:RMSOFT_ADMIN_NAME = $answers["ADMIN_NOME"]
      $env:RMSOFT_ADMIN_PHONE = $answers["ADMIN_TELEFONE"]
      $env:RMSOFT_ADMIN_PASSWORD = $answers["ADMIN_SENHA"]
      try {
        $code = Invoke-Native $Exe @("cli", "create-superadmin", "--if-none")
      } finally {
        Remove-Item Env:RMSOFT_ADMIN_NAME, Env:RMSOFT_ADMIN_PHONE, Env:RMSOFT_ADMIN_PASSWORD -ErrorAction SilentlyContinue
      }
      if ($code -ne 0) { Fail "não foi possível criar a conta SUPER_ADMIN" }
    } else {
      Write-Host "Atualização: contas mantidas"
    }
  } finally {
    Pop-Location
  }

  # ----------------------------------------------------------------------------------------------- the server service
  Say "5/8 Serviço RMSOFT-Servidor (porta $port)"
  if (Get-Service $Servico -ErrorAction SilentlyContinue) {
    Invoke-Native $WinSW @("stop") | Out-Null
    Invoke-Native $WinSW @("uninstall") | Out-Null
    Start-Sleep -Seconds 2
  }
  if (Test-PortBusy $port) {
    $owner = Get-NetTCPConnection -LocalPort $port -State Listen | Select-Object -First 1
    $name = (Get-Process -Id $owner.OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Fail ("a porta $port já está ocupada por outro programa ($name). Abra $envFile no Bloco de notas (como administrador), " +
      "mude RMSOFT_PORT (ex.: 8080) e execute de novo o RMSOFT-Setup.exe.")
  }
  Write-Utf8 ([IO.Path]::ChangeExtension($WinSW, ".xml")) @(
    '<?xml version="1.0" encoding="utf-8"?>',
    '<service>',
    "  <id>$Servico</id>",
    '  <name>RM SOFT - Servidor</name>',
    '  <description>RM SOFT: os ecrãs, a API, o envio das faturas à AGT e as cópias automáticas.</description>',
    "  <executable>$Exe</executable>",
    '  <arguments>servir</arguments>',
    "  <workingdirectory>$D</workingdirectory>",
    "  <depend>$DbService</depend>",
    '  <startmode>Automatic</startmode>',
    '  <onfailure action="restart" delay="10 sec"/>',
    '  <resetfailure>1 hour</resetfailure>',
    '  <stoptimeout>20 sec</stoptimeout>',
    '  <env name="PYTHONIOENCODING" value="utf-8"/>',
    "  <logpath>$D\logs</logpath>",
    '  <log mode="roll-by-size"><sizeThreshold>10240</sizeThreshold><keepFiles>5</keepFiles></log>',
    '</service>'
  )
  $code = Invoke-Native $WinSW @("install")
  if ($code -ne 0) { Fail "não foi possível criar o serviço $Servico" }
  Start-Service $Servico

  Say "6/8 Firewall"
  Get-NetFirewallRule -DisplayName "RM SOFT" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  New-NetFirewallRule -DisplayName "RM SOFT" -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any | Out-Null
  Write-Host "Porta $port aberta para os postos da rede"

  Say "7/8 Cópia diária da base inteira (23:30)"
  $action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $App 'instalacao\copia_base.ps1')`""
  $trigger = New-ScheduledTaskTrigger -Daily -At "23:30"
  $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
  Register-ScheduledTask -TaskName "RMSOFT-CopiaBase" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
  Write-Host "Cópias em $copias\base (14 dias)"

  Say "8/8 A verificar"
  $ok = $false
  for ($i = 0; $i -lt 120; $i++) {
    try {
      Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 3 | Out-Null
      $ok = $true
      break
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  if (-not $ok) { Fail "o servidor não respondeu na porta $port. Veja $D\logs\rmsoft-servico.err.log e rmsoft-servico.out.log" }

  Push-Location $D
  try { $installationCode = ((& $Exe cli installation-code) | Select-Object -Last 1).Trim() } finally { Pop-Location }
  Write-Utf8 (Join-Path $D "codigo_instalacao.txt") @($installationCode)
  $suffix = if ($port -eq 80) { "" } else { ":$port" }
  $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {
      $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | ForEach-Object { "http://$($_.IPAddress)$suffix" })
  $addresses = "http://$($env:COMPUTERNAME.ToLower())$suffix"
  if ($ips.Count -gt 0) { $addresses += "   ou   " + ($ips -join "   ou   ") }
  Write-Utf8 (Join-Path $D "resumo_instalacao.txt") @(
    "O RM SOFT está instalado e a funcionar.",
    "",
    "Nos postos (caixa, escritório), abrir no Chrome:",
    "   $addresses",
    "",
    "Código de instalação deste servidor (para a licença):",
    "   $installationCode",
    "",
    "Também guardado em $D\codigo_instalacao.txt"
  ) $true
  Write-Host "Postos: $addresses"
  Write-Host "Código de instalação: $installationCode"
  Write-Host "`nConfiguração terminada."
  Stop-Transcript | Out-Null
  exit 0
} catch {
  Fail $_.Exception.Message
}
