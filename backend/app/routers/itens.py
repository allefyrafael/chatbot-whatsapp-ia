"""Rotas do painel — CRUD de produtos/serviços (`itens`).

Todas exigem administrador autenticado (dependência `get_current_admin`): sem o cookie
de sessão válido, `app.main` intercepta e redireciona para `/login`. As telas são
formulários Jinja2 (sem framework de JS). O preço é opcional: itens "sob consulta"
ficam com `preco = NULL`.
"""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.models import Item, Usuario
from app.templating import templates

router = APIRouter(prefix="/painel/itens", tags=["Painel — Itens"])


def _parse_preco(preco: str, sem_preco: str | None) -> Decimal | None:
    """Converte o preço do formulário. Retorna None quando 'sob consulta' ou vazio."""
    if sem_preco or not preco.strip():
        return None
    try:
        return Decimal(preco)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Preço inválido")


@router.get("", response_class=HTMLResponse, summary="Listar itens")
def listar_itens(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Lista todos os produtos/serviços cadastrados, ordenados por nome."""
    itens = db.query(Item).order_by(Item.nome).all()
    return templates.TemplateResponse(request, "itens_list.html", {"itens": itens, "usuario": usuario})


@router.get("/novo", response_class=HTMLResponse, summary="Formulário de novo item")
def formulario_novo_item(
    request: Request,
    usuario: Usuario = Depends(get_current_admin),
):
    """Mostra o formulário em branco para cadastrar um item."""
    return templates.TemplateResponse(request, "itens_form.html", {"item": None, "usuario": usuario})


@router.post("/novo", summary="Criar item")
def criar_item(
    nome: str = Form(...),
    descricao: str = Form(""),
    preco: str = Form(""),
    sem_preco: str | None = Form(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Cadastra um item.

    - **Recebe** (form): `nome`, `descricao` (opcional), `preco` (opcional),
      `sem_preco` ("1" marca "sob consulta" → salva sem preço).
    - **Retorna**: redireciona para a lista de itens.
    """
    item = Item(
        nome=nome,
        descricao=descricao or None,
        preco=_parse_preco(preco, sem_preco),
    )
    db.add(item)
    db.commit()
    return RedirectResponse("/painel/itens", status_code=303)


@router.get("/{item_id}/editar", response_class=HTMLResponse, summary="Formulário de edição")
def formulario_editar_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Mostra o formulário preenchido com os dados do item. **404** se não existir."""
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return templates.TemplateResponse(request, "itens_form.html", {"item": item, "usuario": usuario})


@router.post("/{item_id}/editar", summary="Salvar edição do item")
def editar_item(
    item_id: int,
    nome: str = Form(...),
    descricao: str = Form(""),
    preco: str = Form(""),
    sem_preco: str | None = Form(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Atualiza um item existente (mesmos campos do cadastro). **404** se não existir."""
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    item.nome = nome
    item.descricao = descricao or None
    item.preco = _parse_preco(preco, sem_preco)
    db.commit()
    return RedirectResponse("/painel/itens", status_code=303)


@router.post("/{item_id}/excluir", summary="Excluir item")
def excluir_item(
    item_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Remove o item (idempotente: se não existir, apenas volta para a lista)."""
    item = db.get(Item, item_id)
    if item is not None:
        db.delete(item)
        db.commit()
    return RedirectResponse("/painel/itens", status_code=303)
