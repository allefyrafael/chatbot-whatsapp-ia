@echo off
REM run.bat — atalho clicavel/executavel que roda o run.ps1 sem esbarrar na
REM policy de execucao do PowerShell. Uso:  run.bat  (ou duplo-clique)
powershell -ExecutionPolicy Bypass -File "%~dp0run.ps1"
