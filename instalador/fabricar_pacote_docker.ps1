# Saved as UTF-8 WITH BOM: Windows PowerShell 5.1 reads a file without BOM as ANSI (the accents would be garbled).
# RM SOFT - makes the Docker installation package instalador\saida\rmsoft-docker-<versão>\, on the development PC.
#
#     cd C:\Projects\rm-system
#     powershell -ExecutionPolicy Bypass -File instalador\fabricar_pacote_docker.ps1 -Versao 1.0.0
#
# Needs: Docker Desktop running (and internet the first time: the base images). Makes:
#   - the image rmsoft-backend:<versão> with the program compiled only (.pyc - no .py in any layer),
#   - the image rmsoft-web:<versão> (the screens, already built),
#   - rmsoft-imagens-<versão>.tar.gz: these two + PostgreSQL + Redis, so the client's server needs no internet,
#   - the folder with only what the client's server needs: no source code, no git, no GitHub access.
param([string]$Versao = "1.0.0")
$ErrorActionPreference = "Stop"

$Raiz = Split-Path $PSScriptRoot -Parent
$Modelo = Join-Path $Raiz "docker\cliente"
$Saida = Join-Path $PSScriptRoot "saida"
$Pacote = Join-Path $Saida "rmsoft-docker-$Versao"
$Imagens = Join-Path $Pacote "rmsoft-imagens-$Versao.tar.gz"
$Base = @("postgres:16-alpine", "redis:7-alpine")

function Say($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`nERRO: $text" -ForegroundColor Red; exit 1 }
# a native command whose messages are hidden: Windows PowerShell 5.1 would stop the script on its first error line
function Invoke-Quiet([scriptblock]$command) {
  $previous = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  try { & $command *> $null } finally { $ErrorActionPreference = $previous }
  return ($LASTEXITCODE -eq 0)
}
function Invoke-Docker([string[]]$arguments, [string]$what) {
  $previous = $ErrorActionPreference; $ErrorActionPreference = "Continue"  # docker writes its progress on stderr
  try { & docker @arguments 2>&1 | ForEach-Object { Write-Host $_ } } finally { $ErrorActionPreference = $previous }
  if ($LASTEXITCODE -ne 0) { Fail "$what falhou (ver as mensagens acima)" }
}
# the supplier shown on the login screen: the same as in the clients' .env
function Get-ModelValue($key) {
  $line = Get-Content (Join-Path $Modelo ".env.example") | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
  if ($line) { ($line -split '=', 2)[1] } else { "" }
}

Say "1/5 Verificações"
if ($Versao -notmatch '^\d+\.\d+\.\d+$') { Fail "versão inválida '$Versao' (ex.: 1.0.0)" }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker Desktop não encontrado" }
if (-not (Invoke-Quiet { docker info })) { Fail "o Docker Desktop não está a funcionar: abra-o e espere que diga 'Engine running'" }
if (Test-Path $Pacote) { Remove-Item $Pacote -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Pacote | Out-Null
Write-Host "Versão $Versao -> $Pacote"

Say "2/5 Imagem do programa (rmsoft-backend:$Versao, sem código-fonte)"
Invoke-Docker @("build", "-f", (Join-Path $Raiz "docker\saas\Dockerfile.backend"), "--build-arg", "SOURCELESS=true",
  "-t", "rmsoft-backend:$Versao", $Raiz) "a imagem do programa"
# the check: not one .py of the program in the image, and the program starts from the compiled files
$left = (& docker run --rm --entrypoint sh "rmsoft-backend:$Versao" -c "find /app/app /app/alembic -name '*.py' | wc -l").Trim()
if ($left -ne "0") { Fail "a imagem ainda contém $left ficheiros .py" }
Invoke-Docker @("run", "--rm", "--entrypoint", "python", "-e", "DATABASE_URL=postgresql+asyncpg://x:x@localhost/x",
  "-e", "JWT_SECRET_KEY=verificacao", "rmsoft-backend:$Versao", "-c", "import app.main; print('programa: OK')") "a verificação do programa"

Say "3/5 Imagem dos ecrãs (rmsoft-web:$Versao)"
Invoke-Docker @("build", "-f", (Join-Path $Raiz "docker\saas\Dockerfile.web"),
  "--build-arg", "VITE_SUPPLIER_NAME=$(Get-ModelValue 'SUPPLIER_NAME')",
  "--build-arg", "VITE_SUPPLIER_EMAIL=$(Get-ModelValue 'SUPPLIER_EMAIL')",
  "--build-arg", "VITE_SUPPLIER_PHONE=$(Get-ModelValue 'SUPPLIER_PHONE')",
  "--build-arg", "VITE_SUPPLIER_WEBSITE=$(Get-ModelValue 'SUPPLIER_WEBSITE')",
  "--build-arg", "VITE_APP_VERSION=$Versao",
  "-t", "rmsoft-web:$Versao", $Raiz) "a imagem dos ecrãs"

Say "4/5 Ficheiro das imagens (alguns minutos)"
foreach ($image in $Base) { Invoke-Docker @("pull", $image) "o download de $image" }
$tar = Join-Path $Saida "rmsoft-imagens-$Versao.tar"
Invoke-Docker (@("save", "-o", $tar, "rmsoft-backend:$Versao", "rmsoft-web:$Versao") + $Base) "a exportação das imagens"
# gzip (docker load reads it as it is): about a third of the size, for the USB stick
$source = [IO.File]::OpenRead($tar)
$target = [IO.File]::Create($Imagens)
$gzip = New-Object IO.Compression.GZipStream($target, [IO.Compression.CompressionLevel]::Optimal)
try { $source.CopyTo($gzip) } finally { $gzip.Dispose(); $target.Dispose(); $source.Dispose() }
Remove-Item $tar
Write-Host ("rmsoft-imagens-$Versao.tar.gz: {0:N0} MB" -f ((Get-Item $Imagens).Length / 1MB))

Say "5/5 Pasta do pacote"
foreach ($file in @("docker-compose.yml", "docker-compose.linux.yml", "Caddyfile", ".env.example",
    "instalar.ps1", "instalar.sh", "atualizar.ps1", "atualizar.sh", "INSTALLATION_LOCAL.md")) {
  Copy-Item (Join-Path $Modelo $file) $Pacote
}
Copy-Item (Join-Path $Raiz "docker\saas\backup.sh") $Pacote
[IO.File]::WriteAllText((Join-Path $Pacote "VERSAO"), "$Versao`n", (New-Object Text.UTF8Encoding($false)))
# the Linux scripts must keep LF line ends, whatever git did on this Windows PC
foreach ($script in @("instalar.sh", "atualizar.sh", "backup.sh")) {
  $path = Join-Path $Pacote $script
  [IO.File]::WriteAllText($path, ([IO.File]::ReadAllText($path) -replace "`r`n", "`n"), (New-Object Text.UTF8Encoding($false)))
}
Get-ChildItem $Pacote | ForEach-Object { Write-Host ("   {0,-32} {1,10:N0} KB" -f $_.Name, ($_.Length / 1KB)) }
Write-Host "`nPronto: $Pacote"
Write-Host "Copie esta pasta inteira para o servidor do cliente (pen USB) e siga INSTALLATION_LOCAL.md."
