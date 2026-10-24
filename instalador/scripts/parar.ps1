# Saved as UTF-8 WITH BOM: Windows PowerShell 5.1 reads a file without BOM as ANSI (the accents would be garbled).
# RM SOFT - before an update (run by RMSOFT-Setup.exe when RM SOFT is already installed, before the files are replaced):
# stops the server, makes a copy of the whole database (antes_atualizacao_<date>.dump), stops the database.
# Exit code 1 (the update is cancelled, nothing changed) when the copy cannot be made.
param([Parameter(Mandatory = $true)][string]$App)
$ErrorActionPreference = "Stop"
$D = Join-Path $env:ProgramData "RMSOFT"
$PgBin = Join-Path $App "pgsql\bin"
New-Item -ItemType Directory -Force -Path (Join-Path $D "logs") | Out-Null
Start-Transcript -Path (Join-Path $D "logs\instalacao.log") -Append | Out-Null

function Fail($text) {
  Write-Host "`nERRO: $text"
  Stop-Transcript | Out-Null
  exit 1
}

try {
  Write-Host "`n######## $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - antes da atualização"
  $cfg = @{}
  Get-Content (Join-Path $D ".env") -Encoding UTF8 | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    $cfg[$k] = $v.Trim()
  }

  if (Get-Service "RMSOFT-Servidor" -ErrorAction SilentlyContinue) {
    Stop-Service "RMSOFT-Servidor" -Force
    Write-Host "Servidor parado"
  }

  $db = Get-Service "RMSOFT-BaseDados" -ErrorAction SilentlyContinue
  if ($db -and (Test-Path (Join-Path $PgBin "pg_dump.exe")) -and $cfg["DATABASE_URL"] -match '://rmsoft:([^@]+)@127\.0\.0\.1:(\d+)/') {
    $dbPassword = $Matches[1]
    $dbPort = $Matches[2]
    Start-Service "RMSOFT-BaseDados"
    for ($i = 0; $i -lt 90; $i++) {
      & (Join-Path $PgBin "pg_isready.exe") -h 127.0.0.1 -p $dbPort -q
      if ($LASTEXITCODE -eq 0) { break }
      Start-Sleep -Seconds 1
    }
    # In the copies' folder; on this PC when it is not reachable (external disk unplugged)
    $folder = Join-Path $cfg["BACKUP_DIR"] "base"
    New-Item -ItemType Directory -Force -Path $folder -ErrorAction SilentlyContinue | Out-Null
    if (-not (Test-Path $folder)) {
      $folder = Join-Path $D "copias_base"
      New-Item -ItemType Directory -Force -Path $folder | Out-Null
    }
    $file = Join-Path $folder "antes_atualizacao_$(Get-Date -Format 'yyyyMMdd_HHmm').dump"
    $env:PGPASSWORD = $dbPassword
    $ErrorActionPreference = "Continue"
    & (Join-Path $PgBin "pg_dump.exe") -h 127.0.0.1 -p $dbPort -U rmsoft -Fc -f $file rmsoft 2>&1 | ForEach-Object { Write-Host $_ }
    $code = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    if ($code -ne 0 -or -not (Test-Path $file) -or (Get-Item $file).Length -eq 0) { Fail "a cópia da base antes da atualização falhou" }
    Write-Host "Cópia da base: $file"
    Stop-Service "RMSOFT-BaseDados" -Force
    Write-Host "Base de dados parada"
  } else {
    Write-Host "Sem base de dados instalada: nada a copiar"
  }
  Stop-Transcript | Out-Null
  exit 0
} catch {
  Fail $_.Exception.Message
}
