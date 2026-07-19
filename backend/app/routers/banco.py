"""Assistente de conexão com o **banco do projeto do aluno** (o que fica na AWS RDS).

Este é o único banco que o aluno configura. O banco de *configuração* do chatbot roda
sozinho num container local (Docker) e não aparece para ele.

Campos no estilo do MySQL Workbench (host, porta, usuário, senha, banco) + instruções de
onde achar cada valor no console da AWS. Ao enviar, a conexão é **testada de verdade**:
- deu certo  -> grava no .env e segue para o painel;
- deu errado -> volta com um popup explicando exatamente o que corrigir.

Nada de tabelas é criado aqui: o schema pertence ao aluno.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import banco_dados_configurado
from app.services import banco_config_service
from app.templating import templates

router = APIRouter(tags=["Configuração do banco"])


@router.get("/configurar-banco", response_class=HTMLResponse, summary="Conectar o banco do projeto (AWS)")
def formulario_banco(request: Request):
    """Mostra o assistente. Se o banco do projeto já estiver conectado, vai para o painel."""
    if banco_dados_configurado():
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "configurar_banco.html", {"dados": {"porta": "3306"}, "wizard": True}
    )


@router.post("/configurar-banco", summary="Testar e salvar a conexão com o banco do projeto")
def salvar_banco(
    request: Request,
    host: str = Form(...),
    porta: str = Form("3306"),
    usuario: str = Form(...),
    senha: str = Form(...),
    banco: str = Form(...),
    ssl_ca: str = Form(""),
):
    """Testa a conexão informada e só salva se ela funcionar.

    Responde em JSON quando chamado pelo próprio formulário (fetch), para que a tela
    possa mostrar o progresso e o resultado sem recarregar. Sem JavaScript, o navegador
    envia o form normalmente e recebe HTML — o fluxo continua funcionando.
    """
    dados = {"host": host, "porta": porta, "usuario": usuario, "banco": banco, "ssl_ca": ssl_ca}
    via_fetch = request.headers.get("x-requested-with") == "fetch"

    # Recusa schemas internos do MySQL antes de tentar (erro classico: apontar p/ 'mysql').
    erro = banco_config_service.validar_nome_banco(banco)
    if not erro:
        url = banco_config_service.montar_url(host, porta, usuario, senha, banco)
        conectou, mensagem = banco_config_service.testar_conexao(url, ssl_ca.strip())
        if not conectou:
            erro = mensagem

    if erro:
        # Mostra o que realmente existe no servidor, em vez de deixar o aluno adivinhar.
        erro += banco_config_service.sugerir_bancos(host, porta, usuario, senha, ssl_ca.strip())
        if via_fetch:
            return JSONResponse({"ok": False, "erro": erro}, status_code=400)
        return templates.TemplateResponse(
            request,
            "configurar_banco.html",
            {"dados": dados, "erro": erro, "wizard": True},
            status_code=400,
        )

    banco_config_service.salvar_configuracao_dados(url, ssl_ca.strip())
    if via_fetch:
        return JSONResponse({"ok": True, "banco": banco.strip(), "host": host.strip(), "destino": "/"})
    return RedirectResponse("/", status_code=303)
