#!/usr/bin/env bash
# run.sh — sobe TODA a aplicação com um único comando (Linux/macOS/Git-Bash).
# Equivalente ao run.ps1. Uso (dentro da pasta backend):  ./run.sh
#
# Pré-requisito externo: um servidor MySQL acessível pela DATABASE_URL do .env.
set -euo pipefail
cd "$(dirname "$0")"

# 1. Ambiente virtual (Python 3.12 — as dependências não suportam 3.14)
if [ ! -d ".venv" ]; then
    echo "[1/4] Criando ambiente virtual com Python 3.12..."
    python3.12 -m venv .venv
else
    echo "[1/4] Ambiente virtual já existe."
fi

# Caminho do python do venv (Scripts no Windows/Git-Bash, bin no Unix)
if [ -f ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"; else PY=".venv/bin/python"; fi

# 2. Dependências
echo "[2/4] Instalando dependências..."
"$PY" -m pip install --upgrade pip -q
"$PY" -m pip install -r requirements.txt -q

# 3. Arquivo .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[3/4] Criado .env a partir de .env.example. AJUSTE as credenciais do MySQL se necessário."
else
    echo "[3/4] Arquivo .env já existe."
fi

# 4. Sobe a aplicação (cria database + tabelas no startup)
echo "[4/4] Iniciando em http://localhost:8000  (docs em /docs). Ctrl+C para parar."
"$PY" -m uvicorn app.main:app --reload
