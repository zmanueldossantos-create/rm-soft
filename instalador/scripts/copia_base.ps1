# Saved as UTF-8 WITH BOM: Windows PowerShell 5.1 reads a file without BOM as ANSI (the accents would be garbled).
# RM SOFT - the daily copy of the whole database (Windows task "RMSOFT-CopiaBase", 23:30, made by configurar.ps1):
# <copies' folder>\base\rmsoft_<date>.dump, kept 14 days. On this PC (C:\ProgramData\RMSOFT\copias_base) when the
# copies' folder is not reachable. The companies' own copies (Definições da Empresa) are made by the server itself.
$ErrorActionPreference = "Stop"
$App = Split-Path $PSScriptRoot -Parent
$D = Join-Path $env:ProgramData "RMSOFT"
$PgBin = Join-Path $App "pgsql\bin"
$Log = Join-Path $D "logs\copia_base.log"

function Log($text) { Add-Content -Path $Log -Encoding UTF8 -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $text" }

try {
  $cfg = @{}
  Get-Content (Join-Path $D ".env") -Encoding UTF8 | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    $cfg[$k] = $v.Trim()
  }
  if ($cfg["DATABASE_URL"] -notmatch '://rmsoft:([^@]+)@127\.0\.0\.1:(\d+)/') { throw "DATABASE_URL inesperado" }
  $dbPassword = $Matches[1]
  $dbPort = $Matches[2]

  $folder = Join-Path $cfg["BACKUP_DIR"] "base"
  New-Item -ItemType Directory -Force -Path $folder -ErrorAction SilentlyContinue | Out-Null
  if (-not (Test-Path $folder)) {
    Log "AVISO: $folder inacessível - cópia feita neste PC"
    $folder = Join-Path $D "copias_base"
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
  }
  $file = Join-Path $folder "rmsoft_$(Get-Date -Format 'yyyyMMdd_HHmm').dump"
  $env:PGPASSWORD = $dbPassword
  $ErrorActionPreference = "Continue"
  $output = & (Join-Path $PgBin "pg_dump.exe") -h 127.0.0.1 -p $dbPort -U rmsoft -Fc -f $file rmsoft 2>&1
  $code = $LASTEXITCODE
  $ErrorActionPreference = "Stop"
  Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
  if ($code -ne 0) { throw "pg_dump falhou ($code): $output" }
  Log "OK $file ($([math]::Round((Get-Item $file).Length / 1MB, 1)) MB)"

  Get-ChildItem $folder -Filter "rmsoft_*.dump" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } | ForEach-Object {
    Remove-Item $_.FullName -Force
    Log "Apagada (mais de 14 dias): $($_.Name)"
  }
} catch {
  Log "ERRO: $($_.Exception.Message)"
  exit 1
}
