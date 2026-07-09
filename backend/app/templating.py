"""Instância única de templates Jinja2, compartilhada pelos routers.

Centralizar aqui evita recriar `Jinja2Templates` em cada router e dá um ponto único para
registrar filtros/variáveis globais de template no futuro.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

# Caminho absoluto (independe do diretório de onde a app é iniciada).
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
