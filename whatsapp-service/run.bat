@echo off
REM Sobe o sidecar Baileys (conexao real do WhatsApp).
REM O WEBHOOK_SECRET precisa bater com WHATSAPP_WEBHOOK_SECRET do backend/.env.
cd /d "%~dp0"

if not exist node_modules (
  echo Instalando dependencias do sidecar...
  call npm install
)

if "%WEBHOOK_SECRET%"=="" set WEBHOOK_SECRET=troque-este-secret-do-webhook
if "%WEBHOOK_URL%"=="" set WEBHOOK_URL=http://localhost:8000/webhook/whatsapp

echo Iniciando whatsapp-service em http://localhost:3001 ...
node index.js
