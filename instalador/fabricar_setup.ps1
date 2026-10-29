# Saved as UTF-8 WITH BOM: Windows PowerShell 5.1 reads a file without BOM as ANSI (the accents would be garbled).
# RM SOFT - makes the Windows installer instalador\saida\RMSOFT-Setup-<versão>.exe, on the development PC.
#
#     cd C:\Projects\rm-system
#     powershell -ExecutionPolicy Bypass -File instalador\fabricar_setup.ps1 -Versao 1.0.0
#
# Needs: the project's venv (venv\), Node.js (npm), Inno Setup 6. Downloads once into instalador\cache\ (kept):
# PostgreSQL 16 for Windows (binaries), WinSW (the Windows service), the Visual C++ runtime.
# Every run: the screens (npm run build), the program (PyInstaller: rmsoft-servidor.exe, without the source code),
# the package (instalador\trabalho\pacote), then Inno Setup.
param([string]$Versao = "1.0.0")
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is very slow with its progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Raiz = Split-Path $PSScriptRoot -Parent
$Inst = $PSScriptRoot
$Cache = Join-Path $Inst "cache"
$Trab = Join-Path $Inst "trabalho"
$Saida = Join-Path $Inst "saida"
$Pacote = Join-Path $Trab "pacote"
$Py = Join-Path $Raiz "venv\Scripts\python.exe"

# PostgreSQL 16 for Windows x86-64 - binaries (zip), from https://www.enterprisedb.com/download-postgresql-binaries
$PgUrl = "https://sbp.enterprisedb.com/getfile.jsp?fileid=1260623"
$PgZip = Join-Path $Cache "postgresql-16-windows-x64-binaries.zip"
$WinSWUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
$WinSWExe = Join-Path $Cache "WinSW-x64.exe"
$VcUrl = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
$VcExe = Join-Path $Cache "vc_redist.x64.exe"

function Say($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`nERRO: $text" -ForegroundColor Red; exit 1 }
function Get-Download($url, $dest, $what) {
  if (Test-Path $dest) { Write-Host "$what : já em cache"; return }
  Write-Host "A descarregar $what ..."
  try {
    Invoke-WebRequest -Uri $url -OutFile "$dest.part" -UseBasicParsing
    Move-Item "$dest.part" $dest -Force
  } catch {
    Remove-Item "$dest.part" -ErrorAction SilentlyContinue
    Fail "não foi possível descarregar $what. Descarregue-o à mão ($url) e guarde-o como $dest"
  }
}
function Copy-Folder($from, $to) {
  New-Item -ItemType Directory -Force -Path $to | Out-Null
  Copy-Item -Path (Join-Path $from "*") -Destination $to -Recurse -Force
}

Say "1/6 Verificações"
if (-not (Test-Path $Py)) { Fail "venv não encontrado ($Py): crie-o e instale requirements.txt" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "Node.js (npm) não encontrado" }
$Iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { Fail "Inno Setup 6 não encontrado (https://jrsoftware.org/isdl.php)" }
if ($Versao -notmatch '^\d+\.\d+\.\d+$') { Fail "versão inválida '$Versao' (ex.: 1.0.0)" }
New-Item -ItemType Directory -Force -Path $Cache, $Trab, $Saida | Out-Null
Write-Host "Versão $Versao - Inno Setup: $Iscc"

Say "2/6 Ecrãs (npm run build)"
Push-Location (Join-Path $Raiz "frontend")
try {
  if (-not (Test-Path "node_modules")) {
    npm ci
    if ($LASTEXITCODE -ne 0) { Fail "npm ci falhou" }
  }
  $env:VITE_APP_VERSION = $Versao  # shown at the bottom of the screens
  npm run build
  if ($LASTEXITCODE -ne 0) { Fail "npm run build falhou" }
} finally {
  Remove-Item Env:VITE_APP_VERSION -ErrorAction SilentlyContinue
  Pop-Location
}
$Dist = Join-Path $Raiz "frontend\dist"
if (-not (Test-Path (Join-Path $Dist "index.html"))) { Fail "frontend\dist\index.html não encontrado" }

Say "3/6 Programa (PyInstaller)"
$ErrorActionPreference = "Continue"
& $Py -m PyInstaller --version *> $null
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -ne 0) {
  & $Py -m pip install "pyinstaller==6.7.0"
  if ($LASTEXITCODE -ne 0) { Fail "não foi possível instalar o PyInstaller" }
}
$PyiOut = Join-Path $Trab "pyi"
$PyiArgs = @(
  "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
  "--name", "rmsoft-servidor", "--console", "--icon", (Join-Path $Inst "rmsoft.ico"),
  "--distpath", $PyiOut, "--workpath", (Join-Path $Trab "pyi_build"), "--specpath", (Join-Path $Trab "pyi_build"),
  "--paths", $Raiz,
  "--collect-submodules", "app",
  "--collect-submodules", "uvicorn",
  "--collect-submodules", "asyncpg",
  "--collect-submodules", "passlib",
  "--collect-submodules", "num2words",
  "--collect-data", "reportlab",
  "--hidden-import", "sqlalchemy.dialects.postgresql.asyncpg",
  "--exclude-module", "pkg_resources",
  "--add-data", "$(Join-Path $Raiz 'alembic');alembic",
  "--add-data", "$(Join-Path $Raiz 'alembic.ini');.",
  "--add-data", "$(Join-Path $Raiz 'app\assets');app\assets",  # the AGT's logo, in the QR of an electronic document
  (Join-Path $Inst "rmsoft_servidor.py")
)
Push-Location $Raiz
try {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"  # PyInstaller writes its messages on stderr
  & $Py @PyiArgs
  $code = $LASTEXITCODE
  $ErrorActionPreference = $old
} finally {
  Pop-Location
}
$ServidorDir = Join-Path $PyiOut "rmsoft-servidor"
if ($code -ne 0 -or -not (Test-Path (Join-Path $ServidorDir "rmsoft-servidor.exe"))) { Fail "PyInstaller falhou" }

Say "4/6 PostgreSQL, WinSW, Visual C++"
Get-Download $PgUrl $PgZip "PostgreSQL 16 (cerca de 300 MB)"
Get-Download $WinSWUrl $WinSWExe "WinSW"
Get-Download $VcUrl $VcExe "Visual C++ (vc_redist.x64)"
$PgDir = Join-Path $Trab "postgresql"
if (-not (Test-Path (Join-Path $PgDir "pgsql\bin\postgres.exe"))) {
  Write-Host "A descompactar o PostgreSQL ..."
  Remove-Item $PgDir -Recurse -Force -ErrorAction SilentlyContinue
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  try {
    [IO.Compression.ZipFile]::ExtractToDirectory($PgZip, $PgDir)
  } catch {
    Fail "o ficheiro $PgZip não é um zip válido: apague-o e descarregue-o de novo (Windows x86-64, versão 16)"
  }
  if (-not (Test-Path (Join-Path $PgDir "pgsql\bin\postgres.exe"))) { Fail "pgsql\bin\postgres.exe não está no zip do PostgreSQL" }
}

Say "5/6 Pacote"
Remove-Item $Pacote -Recurse -Force -ErrorAction SilentlyContinue
Copy-Folder $ServidorDir (Join-Path $Pacote "servidor")
Copy-Folder $Dist (Join-Path $Pacote "ecras")
foreach ($part in @("bin", "lib", "share")) {  # pgAdmin, the documentation and StackBuilder are left out
  Copy-Folder (Join-Path $PgDir "pgsql\$part") (Join-Path $Pacote "pgsql\$part")
}
New-Item -ItemType Directory -Force -Path (Join-Path $Pacote "servico"), (Join-Path $Pacote "instalacao") | Out-Null
Copy-Item $WinSWExe (Join-Path $Pacote "servico\rmsoft-servico.exe")
Copy-Item $VcExe (Join-Path $Pacote "vc_redist.x64.exe")
Copy-Item (Join-Path $Inst "rmsoft.ico") $Pacote
Copy-Item (Join-Path $Inst "scripts\parar.ps1") $Pacote
foreach ($script in @("configurar.ps1", "copia_base.ps1", "remover.ps1")) {
  Copy-Item (Join-Path $Inst "scripts\$script") (Join-Path $Pacote "instalacao")
}
$size = (Get-ChildItem $Pacote -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ("Pacote: {0:N0} MB" -f $size)

Say "6/6 Inno Setup"
& $Iscc "/Qp" "/DVersao=$Versao" "/DPacote=$Pacote" "/DSaida=$Saida" (Join-Path $Inst "rmsoft.iss")
if ($LASTEXITCODE -ne 0) { Fail "o Inno Setup falhou" }
$Setup = Join-Path $Saida "RMSOFT-Setup-$Versao.exe"
if (-not (Test-Path $Setup)) { Fail "$Setup não foi criado" }
Write-Host ("`nPronto: {0} ({1:N0} MB)" -f $Setup, ((Get-Item $Setup).Length / 1MB)) -ForegroundColor Green
