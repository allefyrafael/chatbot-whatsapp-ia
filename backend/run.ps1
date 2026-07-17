# run.ps1 — instala e sobe TUDO com um unico comando (use: run.bat).
#
# Faz, em ordem:
#   0. Confere pre-requisitos (Python 3.12 e Docker).
#   1. Cria o ambiente virtual (Python 3.12).
#   2. Instala as dependencias.
#   3. Cria o .env a partir do .env.example (se faltar).
#   4. Sobe o MySQL no Docker (se ja nao houver um na porta 3306).
#   5. Sobe a Evolution API (WhatsApp) no Docker.
#   6. Inicia o painel em http://localhost:8000.
#
# Pre-requisitos que o ALUNO instala na maquina: Python 3.12 e Docker Desktop.

# Continue (nao Stop): comandos nativos como 'docker' escrevem avisos no stderr que, sob
# 'Stop', o Windows PowerShell 5.1 trataria como erro fatal. Checamos os exit codes na mao.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

function Test-Porta($porta) {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect("localhost", $porta); $c.Close(); return $true
    } catch { return $false }
}

function Falhar($msg) {
    Write-Host ""
    Write-Host "  X  $msg" -ForegroundColor Red
    Read-Host "Pressione Enter para fechar"
    exit 1
}

Write-Host "===== Chatbot WhatsApp + IA =====" -ForegroundColor Cyan

# 0. Pre-requisitos ----------------------------------------------------------
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Falhar "Python nao encontrado. Instale o Python 3.12 (python.org) marcando 'Add to PATH'."
}
cmd /c "py -3.12 --version >nul 2>nul"
if ($LASTEXITCODE -ne 0) {
    Falhar "Python 3.12 nao encontrado. Instale exatamente a versao 3.12 (as libs nao suportam 3.14)."
}

cmd /c "docker info >nul 2>nul"
$dockerOk = ($LASTEXITCODE -eq 0)
if (-not $dockerOk) {
    Write-Host "  !  Docker nao esta rodando. Abra o Docker Desktop e espere 'Engine running'." -ForegroundColor Yellow
}

# 1. venv --------------------------------------------------------------------
if (-not (Test-Path ".venv")) {
    Write-Host "[1/6] Criando ambiente virtual (Python 3.12)..." -ForegroundColor Cyan
    cmd /c "py -3.12 -m venv .venv"
} else {
    Write-Host "[1/6] Ambiente virtual ja existe." -ForegroundColor DarkGray
}
$py = ".\.venv\Scripts\python.exe"

# 2. dependencias ------------------------------------------------------------
Write-Host "[2/6] Instalando dependencias..." -ForegroundColor Cyan
cmd /c "`"$py`" -m pip install --upgrade pip -q 2>&1"
cmd /c "`"$py`" -m pip install -r requirements.txt -q 2>&1"
if ($LASTEXITCODE -ne 0) { Falhar "Falha ao instalar as dependencias." }

# 3. .env --------------------------------------------------------------------
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[3/6] Criado .env a partir do exemplo." -ForegroundColor Yellow
} else {
    Write-Host "[3/6] .env ja existe (mantido)." -ForegroundColor DarkGray
}

# 4. MySQL -------------------------------------------------------------------
# Le o host do banco no .env: se for remoto (ex.: AWS RDS), NAO mexemos no MySQL local.
$dbHost = ""
$linhaDb = Select-String -Path ".env" -Pattern "^DATABASE_URL=" | Select-Object -First 1
if ($linhaDb -and $linhaDb.Line -match ".*@([^:/?]+)") { $dbHost = $Matches[1] }
$dbLocal = ($dbHost -eq "" -or $dbHost -eq "localhost" -or $dbHost -eq "127.0.0.1")

if (-not $dbLocal) {
    Write-Host "[4/6] Banco remoto ($dbHost) — conectando direto (nao subo MySQL local)." -ForegroundColor DarkGray
} elseif (Test-Porta 3306) {
    Write-Host "[4/6] MySQL ja responde na porta 3306 (usando o existente)." -ForegroundColor DarkGray
} elseif ($dockerOk) {
    Write-Host "[4/6] Subindo o MySQL no Docker (aguarde ficar pronto)..." -ForegroundColor Cyan
    cmd /c "docker compose up -d mysql --wait 2>&1"
    if ($LASTEXITCODE -ne 0) { Falhar "Nao consegui subir o MySQL no Docker." }
} else {
    Falhar "Sem MySQL na porta 3306 e o Docker esta fora. Abra o Docker Desktop e rode de novo."
}

# 5. Evolution API (WhatsApp real) -------------------------------------------
if ($dockerOk) {
    Write-Host "[5/6] Subindo a Evolution API (WhatsApp)..." -ForegroundColor Cyan
    Push-Location "..\evolution"
    cmd /c "docker compose up -d 2>&1"
    Pop-Location
} else {
    Write-Host "[5/6] Docker fora: o WhatsApp (Evolution) NAO vai subir." -ForegroundColor Yellow
    Write-Host "      Abra o Docker Desktop para conectar o WhatsApp; o painel funciona sem ele." -ForegroundColor Yellow
}

# 6. Painel ------------------------------------------------------------------
Write-Host ""
Write-Host "[6/6] Painel em  http://localhost:8000   (documentacao em /docs)" -ForegroundColor Green
Write-Host "      Primeiro acesso: http://localhost:8000/setup   |   Ctrl+C para parar." -ForegroundColor Green
Write-Host ""
& $py -m uvicorn app.main:app --host 0.0.0.0 --port 8000
