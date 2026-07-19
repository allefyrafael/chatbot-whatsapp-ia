"""Rotas de sistema/configurações do painel.

Exigem administrador autenticado. Reúne: dados da empresa, a **conexão com o banco de
dados** (o admin pode trocar o RDS pela própria tela, sem editar arquivo) e a 'zona de
perigo' com o reset total, que devolve o sistema ao primeiro acesso.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.bootstrap import criar_database_se_nao_existe, garantir_colunas
from app.config import settings
from app.database import Base, get_db, get_engine
from app.deps import COOKIE_NAME, get_current_admin
from app.models import Configuracao, Usuario
from app.services import banco_config_service, reset_service
from app.templating import templates
from app.whatsapp.factory import provedor_whatsapp
from app.whatsapp.provider import WhatsAppProvider

router = APIRouter(prefix="/painel/config", tags=["Configurações"])


@router.get("", response_class=HTMLResponse, summary="Configurações do sistema")
def pagina_config(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Mostra dados da empresa, as duas conexões de banco e a zona de perigo (reset)."""
    config = db.get(Configuracao, 1)
    total_usuarios = db.query(Usuario).count()
    return templates.TemplateResponse(
        request,
        "config_sistema.html",
        {
            "usuario": usuario,
            "config": config,
            "total_usuarios": total_usuarios,
            "banco": banco_config_service.partes_da_url(settings.database_url),
            "banco_dados": banco_config_service.partes_da_url(settings.dados_database_url),
        },
    )


@router.get("/banco", response_class=HTMLResponse, summary="Conexão com o banco de dados")
def pagina_banco(
    request: Request,
    ok: int = 0,
    usuario: Usuario = Depends(get_current_admin),
):
    """Mostra a conexão atual (sem a senha) e permite trocá-la."""
    return templates.TemplateResponse(
        request,
        "config_banco.html",
        {
            "usuario": usuario,
            "dados": banco_config_service.partes_da_url(settings.database_url),
            "sucesso": "Conexão atualizada com sucesso." if ok else None,
        },
    )


@router.get("/banco/status", summary="Status da conexão com o banco (JSON)")
def status_banco(usuario: Usuario = Depends(get_current_admin)):
    """Testa a conexão atual. A tela consulta em segundo plano (o RDS pode demorar)."""
    status, mensagem = banco_config_service.status_conexao_atual()
    return {"status": status, "mensagem": mensagem}


@router.post("/banco", summary="Trocar a conexão com o banco de dados")
def salvar_banco(
    request: Request,
    host: str = Form(...),
    porta: str = Form("3306"),
    usuario_banco: str = Form(...),
    senha: str = Form(...),
    banco: str = Form(...),
    ssl_ca: str = Form(""),
    usuario: Usuario = Depends(get_current_admin),
):
    """Testa a nova conexão e só troca se ela funcionar (não derruba o que já roda)."""
    dados = {"host": host, "porta": porta, "usuario": usuario_banco, "banco": banco, "ssl_ca": ssl_ca}

    erro = banco_config_service.validar_nome_banco(banco)
    if not erro:
        url = banco_config_service.montar_url(host, porta, usuario_banco, senha, banco)
        conectou, mensagem = banco_config_service.testar_conexao(url, ssl_ca.strip())
        if not conectou:
            erro = mensagem
    if erro:
        # Mostra os bancos existentes no servidor para o admin escolher.
        erro += banco_config_service.sugerir_bancos(host, porta, usuario_banco, senha, ssl_ca.strip())

    if erro:
        return templates.TemplateResponse(
            request,
            "config_banco.html",
            {"usuario": usuario, "dados": dados, "erro": erro},
            status_code=400,
        )

    banco_config_service.salvar_configuracao(url, ssl_ca.strip())
    try:
        criar_database_se_nao_existe()
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        garantir_colunas(engine)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "config_banco.html",
            {
                "usuario": usuario,
                "dados": dados,
                "erro": "Conectei, mas não consegui preparar as tabelas.<br>"
                + banco_config_service.traduzir_erro(exc),
            },
            status_code=400,
        )

    return RedirectResponse("/painel/config/banco?ok=1", status_code=303)


@router.get("/banco-dados", response_class=HTMLResponse, summary="Banco de dados do projeto (AWS RDS)")
def pagina_banco_dados(
    request: Request,
    ok: int = 0,
    usuario: Usuario = Depends(get_current_admin),
):
    """Conexão do banco onde as rotas de IA leem e gravam (o banco do aluno)."""
    return templates.TemplateResponse(
        request,
        "config_banco.html",
        {
            "usuario": usuario,
            "dados": banco_config_service.partes_da_url(settings.dados_database_url),
            "modo_dados": True,
            "sucesso": "Conexão com o banco do projeto atualizada." if ok else None,
        },
    )


@router.get("/banco-dados/status", summary="Status do banco do projeto (JSON)")
def status_banco_dados(usuario: Usuario = Depends(get_current_admin)):
    status, mensagem = banco_config_service.status_conexao_dados()
    return {"status": status, "mensagem": mensagem}


@router.post("/banco-dados", summary="Trocar a conexão do banco do projeto")
def salvar_banco_dados(
    request: Request,
    host: str = Form(...),
    porta: str = Form("3306"),
    usuario_banco: str = Form(...),
    senha: str = Form(...),
    banco: str = Form(...),
    ssl_ca: str = Form(""),
    usuario: Usuario = Depends(get_current_admin),
):
    """Testa e salva a conexão do banco de trabalho. Não cria tabelas: o schema é do aluno."""
    dados = {"host": host, "porta": porta, "usuario": usuario_banco, "banco": banco, "ssl_ca": ssl_ca}

    erro = banco_config_service.validar_nome_banco(banco)
    if not erro:
        url = banco_config_service.montar_url(host, porta, usuario_banco, senha, banco)
        conectou, mensagem = banco_config_service.testar_conexao(url, ssl_ca.strip())
        if not conectou:
            erro = mensagem
    if erro:
        # Mostra os bancos existentes no servidor para o admin escolher.
        erro += banco_config_service.sugerir_bancos(host, porta, usuario_banco, senha, ssl_ca.strip())

    if erro:
        return templates.TemplateResponse(
            request,
            "config_banco.html",
            {"usuario": usuario, "dados": dados, "erro": erro, "modo_dados": True},
            status_code=400,
        )

    banco_config_service.salvar_configuracao_dados(url, ssl_ca.strip())
    return RedirectResponse("/painel/config/banco-dados?ok=1", status_code=303)


@router.post("/reset", summary="Apagar tudo (reset do sistema)")
def resetar(
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(provedor_whatsapp),
    usuario: Usuario = Depends(get_current_admin),
):
    """Apaga todos os dados, encerra a sessão do WhatsApp e volta ao primeiro acesso."""
    try:
        provider.desconectar()  # zera o estado em memória do provedor (best effort)
    except Exception:
        pass
    reset_service.resetar_tudo(db)

    # Sessão do admin não existe mais no banco: limpa o cookie e manda para o setup.
    resposta = RedirectResponse("/setup", status_code=303)
    resposta.delete_cookie(COOKIE_NAME)
    return resposta
