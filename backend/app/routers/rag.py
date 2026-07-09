"""Rotas do painel — configuração do RAG por prompt (blocos fazer/não fazer).

Exigem administrador autenticado. As regras ficam em `app.services.rag_service`; aqui só
tratamos HTTP e renderização. A tela mostra duas colunas (Fazer / Não fazer) e o preview
exibe o system prompt montado que irá ao Groq.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.models import RagBloco, Usuario
from app.services import rag_service
from app.templating import templates

router = APIRouter(prefix="/painel/rag", tags=["IA — RAG"])


@router.get("", response_class=HTMLResponse, summary="Configurar blocos do RAG")
def pagina_rag(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Lista os blocos de instrução, separados em 'Fazer' e 'Não fazer'."""
    return templates.TemplateResponse(
        request,
        "rag_config.html",
        {
            "usuario": usuario,
            "blocos_fazer": rag_service.listar_blocos(db, "fazer"),
            "blocos_nao_fazer": rag_service.listar_blocos(db, "nao_fazer"),
        },
    )


@router.post("/novo", summary="Criar bloco de instrução")
def criar_bloco(
    tipo: str = Form(...),
    titulo: str = Form(...),
    conteudo: str = Form(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Cria um bloco. `tipo` deve ser 'fazer' ou 'nao_fazer' (senão 400)."""
    try:
        rag_service.criar_bloco(db, tipo=tipo, titulo=titulo, conteudo=conteudo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse("/painel/rag", status_code=303)


@router.post("/{bloco_id}/editar", summary="Editar bloco de instrução")
def editar_bloco(
    bloco_id: int,
    titulo: str = Form(...),
    conteudo: str = Form(...),
    ativo: str | None = Form(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Atualiza título/conteúdo e o estado ativo (checkbox `ativo`)."""
    bloco = db.get(RagBloco, bloco_id)
    if bloco is None:
        raise HTTPException(status_code=404, detail="Bloco não encontrado")
    rag_service.atualizar_bloco(db, bloco, titulo=titulo, conteudo=conteudo, ativo=bool(ativo))
    return RedirectResponse("/painel/rag", status_code=303)


@router.post("/{bloco_id}/excluir", summary="Excluir bloco de instrução")
def excluir_bloco(
    bloco_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Remove o bloco (idempotente)."""
    bloco = db.get(RagBloco, bloco_id)
    if bloco is not None:
        rag_service.excluir_bloco(db, bloco)
    return RedirectResponse("/painel/rag", status_code=303)


@router.get("/preview", response_class=PlainTextResponse, summary="Prévia do system prompt")
def preview_prompt(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Devolve, em texto puro, o system prompt montado a partir dos blocos ativos."""
    return rag_service.montar_system_prompt(db) or "(nenhum bloco ativo — o prompt está vazio)"
