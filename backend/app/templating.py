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


def estatico(caminho: str) -> str:
    """URL de um arquivo estático com a data de modificação embutida.

    Sem isso, o navegador continua servindo o `style.css` e o `ui.js` que baixou antes:
    depois de um `git pull` a tela abre com o CSS antigo e componentes novos aparecem
    quebrados (ícones sem tamanho, por exemplo) até um refresh forçado — que ninguém
    adivinha que precisa dar. Como a versão muda junto com o arquivo, o cache é
    invalidado exatamente quando deve, e continua valendo enquanto nada muda.
    """
    arquivo = STATIC_DIR / caminho
    try:
        versao = int(arquivo.stat().st_mtime)
    except OSError:
        return f"/static/{caminho}"
    return f"/static/{caminho}?v={versao}"


templates.env.globals["estatico"] = estatico
