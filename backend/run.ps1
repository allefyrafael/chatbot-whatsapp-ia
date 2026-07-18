# run.ps1 - instala e sobe TUDO com um unico comando (use: run.bat).
# ATENCAO: mantenha este arquivo em ASCII puro. O Windows PowerShell 5.1 le .ps1 como
# ANSI; um caractere multi-byte (ex.: travessao) vira "aspa curva" e quebra o parser.
#
# Faz, em ordem:
#   1. Cria o ambiente virtual (Python 3.12).
#   2. Instala as dependencias.
#   3. Cria o .env a partir do .env.example (se faltar).
#   4. Confere e testa a conexao com o banco no AWS RDS.
#   5. Sobe a Evolution API (WhatsApp) no Docker.
#   6. Inicia o painel em http://localhost:8000.
#
# Pre-requisitos: Python 3.12, Docker Desktop e um banco MySQL criado no AWS RDS.

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
$envNovo = $false
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $envNovo = $true
    Write-Host "[3/6] Criei o arquivo .env a partir do exemplo." -ForegroundColor Yellow
} else {
    Write-Host "[3/6] .env ja existe (mantido)." -ForegroundColor DarkGray
}

# 4. Banco de dados (AWS RDS) ------------------------------------------------
Write-Host "[4/6] Conferindo o banco de dados (AWS RDS)..." -ForegroundColor Cyan

$dbUrl = ""
$linhaDb = Select-String -Path ".env" -Pattern "^DATABASE_URL=" | Select-Object -First 1
if ($linhaDb) { $dbUrl = ($linhaDb.Line -replace "^DATABASE_URL=", "").Trim() }

if ([string]::IsNullOrWhiteSpace($dbUrl)) {
    Write-Host ""
    Write-Host "  >> Falta configurar o banco de dados." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "     1. Abra o arquivo:  backend\.env" -ForegroundColor Yellow
    Write-Host "     2. Preencha a linha DATABASE_URL com os dados do SEU banco no AWS RDS." -ForegroundColor Yellow
    Write-Host "        Dentro do proprio arquivo tem o passo a passo de onde achar cada" -ForegroundColor Yellow
    Write-Host "        valor no console da AWS (endpoint, porta, usuario, senha e banco)." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "     Formato:" -ForegroundColor Yellow
    Write-Host "     DATABASE_URL=mysql+pymysql://USUARIO:SENHA@ENDPOINT:3306/BANCO" -ForegroundColor Yellow
    Write-Host ""
    Falhar "Preencha o DATABASE_URL no backend\.env e rode o run.bat novamente."
}

$dbHost = ""
if ($dbUrl -match ".*@([^:/?]+)") { $dbHost = $Matches[1] }
Write-Host "      Conectando em: $dbHost" -ForegroundColor DarkGray

& $py -c "from app.database import engine; engine.connect().close()" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  X  Nao consegui conectar no banco ($dbHost)." -ForegroundColor Red
    Write-Host ""
    Write-Host "     Verifique, na ordem:" -ForegroundColor Yellow
    Write-Host "     1) Security Group do RDS: precisa liberar a porta 3306 para o SEU IP." -ForegroundColor Yellow
    Write-Host "        (Se sua internet mudou de IP, a regra antiga para de funcionar.)" -ForegroundColor Yellow
    Write-Host "     2) O banco esta com 'Public access' = Yes e status 'Available'." -ForegroundColor Yellow
    Write-Host "     3) Usuario, senha e nome do banco no .env estao corretos." -ForegroundColor Yellow
    Write-Host "        Senha com caractere especial? Troque: @ por %40, : por %3A, / por %2F" -ForegroundColor Yellow
    Write-Host "     4) O endpoint foi copiado inteiro (termina em .rds.amazonaws.com)." -ForegroundColor Yellow
    Write-Host ""
    Falhar "Ajuste o backend\.env (ou o Security Group na AWS) e rode novamente."
}
Write-Host "      Conexao com o banco OK." -ForegroundColor DarkGray

# 5. Evolution API (WhatsApp) ------------------------------------------------
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
