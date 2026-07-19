"""Assistente de conexão com o banco (primeira tela quando o banco não está configurado).

Campos no estilo do MySQL Workbench (host, porta, usuário, senha, banco) + instruções de
onde achar cada valor no console da AWS. Ao enviar, a conexão é **testada de verdade**:
- deu certo  -> grava no .env, cria as tabelas e segue para o cadastro da empresa;
- deu errado -> volta com um popup explicando exatamente o que corrigir.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.bootstrap import criar_database_se_nao_existe, garantir_colunas
from app.database import Base, banco_configurado, get_engine
from app.services import banco_config_service
from app.templating import templates

router = APIRouter(tags=["Configuração do banco"])


@router.get("/configurar-banco", response_class=HTMLResponse, summary="Assistente de conexão com o banco")
def formulario_banco(request: Request):
    """Mostra o assistente. Se o banco já estiver configurado, segue para o painel."""
    if banco_configurado():
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "configurar_banco.html", {"dados": {"porta": "3306"}, "wizard": True})


@router.post("/configurar-banco", summary="Testar e salvar a conexão com o banco")
def salvar_banco(
    request: Request,
    host: str = Form(...),
    porta: str = Form("3306"),
    usuario: str = Form(...),
    senha: str = Form(...),
    banco: str = Form(...),
    ssl_ca: str = Form(""),
):
    """Testa a conexão informada; salva e prepara o banco só se ela funcionar."""
    dados = {"host": host, "porta": porta, "usuario": usuario, "banco": banco, "ssl_ca": ssl_ca}

    # Recusa schemas internos do MySQL antes de tentar (erro classico: apontar p/ 'mysql').
    erro_nome = banco_config_service.validar_nome_banco(banco)
    if erro_nome:
        # Mostra o que realmente existe no servidor, em vez de deixar o usuário adivinhar.
        erro_nome += banco_config_service.sugerir_bancos(host, porta, usuario, senha, ssl_ca.strip())
        return templates.TemplateResponse(
            request,
            "configurar_banco.html",
            {"dados": dados, "erro": erro_nome, "wizard": True},
            status_code=400,
        )

    url = banco_config_service.montar_url(host, porta, usuario, senha, banco)

    ok, mensagem = banco_config_service.testar_conexao(url, ssl_ca.strip())
    if not ok:
        if "não existe" in mensagem:  # nome de banco inexistente: ajuda a escolher
            mensagem += banco_config_service.sugerir_bancos(host, porta, usuario, senha, ssl_ca.strip())
        return templates.TemplateResponse(
            request,
            "configurar_banco.html",
            {"dados": dados, "erro": mensagem, "wizard": True},
            status_code=400,
        )

    banco_config_service.salvar_configuracao(url, ssl_ca.strip())

    # Cria o schema/tabelas agora, para o usuário já cair no cadastro da empresa.
    try:
        criar_database_se_nao_existe()
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        garantir_colunas(engine)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "configurar_banco.html",
            {
                "wizard": True,
                "dados": dados,
                "erro": (
                    "Conectei no servidor, mas não consegui preparar as tabelas.<br>"
                    + banco_config_service.traduzir_erro(exc)
                ),
            },
            status_code=400,
        )

    return RedirectResponse("/setup", status_code=303)
