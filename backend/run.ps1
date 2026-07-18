# run.ps1 - instala e sobe TUDO com um unico comando (use: run.bat).
# ATENCAO: mantenha este arquivo em ASCII puro. O Windows PowerShell 5.1 le .ps1 como
# ANSI; um caractere multi-byte (ex.: travessao) vira "aspa curva" e quebra o parser.
#
# Faz, em ordem:
#   1. Cria o ambiente virtual (Python 3.12).
#   2. Instala as dependencias.
#   3. Cria o .env a partir do .env.example (se faltar).
#   4. Sobe a Evolution API (WhatsApp) no Docker.
#   5. Inicia o painel em http://localhost:8000.
#
# A conexao com o banco (AWS RDS) NAO e configurada aqui: o proprio painel abre um
# assistente em http://localhost:8000/configurar-banco na primeira vez.
#
# Pre-requisitos: Python 3.12 e Docker Desktop.

# Continue (nao Stop): comandos nativos como 'docker' escrevem avisos no stderr que, sob
# 'Stop', o Windows PowerShell 5.1 trataria como erro fatal. Checamos os exit codes na mao.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

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
    Write-Host "     (O painel funciona sem ele; so o WhatsApp precisa do Docker.)" -ForegroundColor Yellow
}

# 1. venv --------------------------------------------------------------------
if (-not (Test-Path ".venv")) {
    Write-Host "[1/5] Criando ambiente virtual (Python 3.12)..." -ForegroundColor Cyan
    cmd /c "py -3.12 -m venv .venv"
} else {
    Write-Host "[1/5] Ambiente virtual ja existe." -ForegroundColor DarkGray
}
$py = ".\.venv\Scripts\python.exe"

# 2. dependencias ------------------------------------------------------------
Write-Host "[2/5] Instalando dependencias..." -ForegroundColor Cyan
cmd /c "`"$py`" -m pip install --upgrade pip -q 2>&1"
cmd /c "`"$py`" -m pip install -r requirements.txt -q 2>&1"
if ($LASTEXITCODE -ne 0) { Falhar "Falha ao instalar as dependencias." }

# 3. .env --------------------------------------------------------------------
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[3/5] Criei o arquivo .env." -ForegroundColor Yellow
} else {
    Write-Host "[3/5] .env ja existe (mantido)." -ForegroundColor DarkGray
}

# Só informa: quem configura o banco e a tela /configurar-banco, no navegador.
$dbUrl = ""
$linhaDb = Select-String -Path ".env" -Pattern "^DATABASE_URL=" | Select-Object -First 1
if ($linhaDb) { $dbUrl = ($linhaDb.Line -replace "^DATABASE_URL=", "").Trim() }
$precisaConfigurarBanco = [string]::IsNullOrWhiteSpace($dbUrl)

# 4. Evolution API (WhatsApp) ------------------------------------------------
if ($dockerOk) {
    Write-Host "[4/5] Subindo a Evolution API (WhatsApp)..." -ForegroundColor Cyan
    Push-Location "..\evolution"
    cmd /c "docker compose up -d 2>&1"
    Pop-Location
} else {
    Write-Host "[4/5] Docker fora: o WhatsApp (Evolution) NAO vai subir." -ForegroundColor Yellow
}

# 5. Painel ------------------------------------------------------------------
Write-Host ""
if ($precisaConfigurarBanco) {
    Write-Host "  >> PRIMEIRO ACESSO: abra o endereco abaixo para conectar seu banco do AWS RDS." -ForegroundColor Yellow
    Write-Host "     A propria tela mostra onde achar cada dado no console da AWS." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "[5/5] Abra:  http://localhost:8000/configurar-banco" -ForegroundColor Green
} else {
    Write-Host "[5/5] Painel em  http://localhost:8000   (documentacao em /docs)" -ForegroundColor Green
}
Write-Host "      Ctrl+C para parar." -ForegroundColor Green
Write-Host ""
& $py -m uvicorn app.main:app --host 0.0.0.0 --port 8000
