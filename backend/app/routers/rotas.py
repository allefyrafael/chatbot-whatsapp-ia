"""Painel — construtor de rotas de IA (as ações que o chatbot executa no banco).

O aluno monta a rota por um formulário guiado, sem escrever SQL: escolhe a operação, a
tabela (vinda da introspecção do **banco de trabalho** dele), as colunas e o que o bot
deve perguntar. Exigem administrador autenticado, como as demais telas do painel.

Duas conexões: `db` guarda o cadastro da rota (banco da aplicação) e `db_dados` é o banco
de trabalho do aluno, de onde vêm as tabelas e colunas oferecidas no formulário.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import banco_dados_configurado, get_db, get_db_dados
from app.deps import get_current_admin
from app.models import RotaIA, Usuario
from app.services import rota_service, schema_service
from app.templating import templates

router = APIRouter(prefix="/painel/rotas", tags=["IA — Rotas"])

OPERACOES = ("buscar", "inserir", "excluir")


def _tabelas(db_dados: Session) -> list[str]:
    """Tabelas do banco do projeto (AWS); lista vazia se ele não responder.

    Nunca lista o banco de configuração: quando o aluno ainda não conectou o dele,
    `get_db_dados` devolve a sessão da aplicação como fallback, e sem esta checagem o
    construtor ofereceria as tabelas de exemplo do chatbot (`clientes`, `pedidos`…)
    como se fossem do projeto dele.
    """
    if not banco_dados_configurado():
        return []
    try:
        return schema_service.listar_tabelas(db_dados)
    except Exception:  # noqa: BLE001 - a tela abre com aviso em vez de estourar
        return []


@router.get("", response_class=HTMLResponse, summary="Listar rotas de IA")
def listar(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Mostra as rotas cadastradas."""
    return templates.TemplateResponse(
        request, "rotas_list.html", {"usuario": usuario, "rotas": rota_service.listar_rotas(db)}
    )


@router.get("/nova", response_class=HTMLResponse, summary="Formulário de nova rota")
def formulario_nova(
    request: Request,
    db_dados: Session = Depends(get_db_dados),
    usuario: Usuario = Depends(get_current_admin),
):
    return templates.TemplateResponse(
        request,
        "rotas_form.html",
        {
            "usuario": usuario,
            "rota": None,
            "tabelas": _tabelas(db_dados),
            "operacoes": OPERACOES,
            # Sem o banco do projeto conectado não há o que oferecer: a tela explica
            # isso e manda conectar, em vez de mostrar um seletor vazio sem motivo.
            "banco_conectado": banco_dados_configurado(),
        },
    )


@router.get("/colunas", summary="Colunas de uma tabela (JSON, para o construtor)")
def colunas_da_tabela(
    tabela: str,
    db_dados: Session = Depends(get_db_dados),
    usuario: Usuario = Depends(get_current_admin),
):
    """Usado pelo formulário para carregar as colunas assim que a tabela é escolhida."""
    if not banco_dados_configurado():
        return {"colunas": []}  # mesmo motivo de `_tabelas`: não expor o banco local
    try:
        return {"colunas": schema_service.listar_colunas(db_dados, tabela)}
    except schema_service.TabelaNaoPermitida:
        return {"colunas": []}


@router.post("/nova", summary="Criar rota de IA")
def criar(
    nome: str = Form(...),
    descricao: str = Form(...),
    operacao: str = Form(...),
    tabela: str = Form(...),
    coluna_filtro: str = Form(""),
    colunas_retorno: list[str] = Form(default=[]),
    pergunta: str = Form(""),
    mensagem_vazio: str = Form(""),
    requer_admin: str | None = Form(None),
    db: Session = Depends(get_db),
    db_dados: Session = Depends(get_db_dados),
    usuario: Usuario = Depends(get_current_admin),
):
    """Valida tabela/colunas no banco de trabalho e grava a rota no banco da aplicação."""
    if operacao not in OPERACOES:
        raise HTTPException(status_code=400, detail="Operação inválida.")
    try:
        schema_service.validar_tabela(db_dados, tabela)
        if coluna_filtro:
            schema_service.validar_colunas(db_dados, tabela, [coluna_filtro])
        if colunas_retorno:
            schema_service.validar_colunas(db_dados, tabela, colunas_retorno)
    except (schema_service.TabelaNaoPermitida, schema_service.ColunaNaoPermitida) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.add(
        RotaIA(
            nome=nome.strip(),
            descricao=descricao.strip(),
            operacao=operacao,
            tabela=tabela,
            coluna_filtro=coluna_filtro or None,
            colunas_retorno=",".join(colunas_retorno) or None,
            pergunta=pergunta.strip() or None,
            mensagem_vazio=mensagem_vazio.strip() or None,
            requer_admin=bool(requer_admin),
        )
    )
    db.commit()
    return RedirectResponse("/painel/rotas", status_code=303)


@router.post("/{rota_id}/alternar", summary="Ativar/desativar rota")
def alternar(
    rota_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    rota = db.get(RotaIA, rota_id)
    if rota is not None:
        rota.ativo = not rota.ativo
        db.commit()
    return RedirectResponse("/painel/rotas", status_code=303)


@router.post("/{rota_id}/excluir", summary="Excluir rota")
def excluir(
    rota_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    rota = db.get(RotaIA, rota_id)
    if rota is not None:
        db.delete(rota)
        db.commit()
    return RedirectResponse("/painel/rotas", status_code=303)
