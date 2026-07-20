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
from app.models import RotaCampo, RotaIA, Usuario
from app.services import rota_service, schema_service
from app.templating import templates

router = APIRouter(prefix="/painel/rotas", tags=["IA — Rotas"])

OPERACOES = ("buscar", "inserir", "excluir")
MODOS_BUSCA = ("perguntar", "todos", "perguntar_ou_todos")


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


def _validar(
    db_dados: Session,
    operacao: str,
    tabela: str,
    coluna_filtro: str,
    colunas_retorno: list[str],
    modo_busca: str = "perguntar",
    campos_insercao: list[str] | None = None,
) -> None:
    """Fronteira de segurança: nada vai para o SQL sem existir no banco do projeto."""
    if operacao not in OPERACOES:
        raise HTTPException(status_code=400, detail="Operação inválida.")
    if modo_busca not in MODOS_BUSCA:
        raise HTTPException(status_code=400, detail="Modo de busca inválido.")
    try:
        schema_service.validar_tabela(db_dados, tabela)
        colunas_schema = {
            coluna["nome"]: coluna
            for coluna in schema_service.listar_colunas(db_dados, tabela)
        }
        if coluna_filtro:
            schema_service.validar_colunas(db_dados, tabela, [coluna_filtro])
            if colunas_schema[coluna_filtro]["segredo"]:
                raise schema_service.ColunaNaoPermitida(
                    f"A coluna '{coluna_filtro}' é secreta e não pode ser usada no chat."
                )
        if colunas_retorno:
            schema_service.validar_colunas(db_dados, tabela, colunas_retorno)
            segredos_retorno = [
                coluna for coluna in colunas_retorno if colunas_schema[coluna]["segredo"]
            ]
            if segredos_retorno:
                raise schema_service.ColunaNaoPermitida(
                    "Campos secretos não podem aparecer no WhatsApp: "
                    + ", ".join(sorted(set(segredos_retorno)))
                )
        if operacao == "inserir":
            campos = campos_insercao or []
            if campos:
                schema_service.validar_colunas(db_dados, tabela, campos)
            colunas = list(colunas_schema.values())
            segredos = {coluna["nome"] for coluna in colunas if coluna["segredo"]}
            escolhidos_secretos = set(campos) & segredos
            if escolhidos_secretos:
                raise schema_service.ColunaNaoPermitida(
                    "Campos secretos não podem ser coletados pelo WhatsApp: "
                    + ", ".join(sorted(escolhidos_secretos))
                )
            geradas = {coluna["nome"] for coluna in colunas if coluna["gerada"]}
            escolhidas_geradas = set(campos) & geradas
            if escolhidas_geradas:
                raise schema_service.ColunaNaoPermitida(
                    "Campos gerados automaticamente não devem ser selecionados: "
                    + ", ".join(sorted(escolhidas_geradas))
                )
            obrigatorias = {
                coluna["nome"] for coluna in colunas
                if coluna["obrigatoria"] and not coluna["gerada"]
            }
            faltando = obrigatorias - set(campos)
            if faltando:
                raise schema_service.ColunaNaoPermitida(
                    "Os campos obrigatórios da tabela precisam ser selecionados: "
                    + ", ".join(sorted(faltando))
                )
    except (schema_service.TabelaNaoPermitida, schema_service.ColunaNaoPermitida) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _configurar_campos_insercao(
    db_dados: Session, rota: RotaIA, campos_insercao: list[str]
) -> None:
    """Persiste a seleção de campos do cadastro usando o NOT NULL real do banco."""
    por_nome = {
        coluna["nome"]: coluna
        for coluna in schema_service.listar_colunas(db_dados, rota.tabela)
    }
    rota.campos.clear()
    for ordem, nome in enumerate(campos_insercao):
        coluna = por_nome[nome]
        rota.campos.append(
            RotaCampo(
                coluna=nome,
                rotulo=nome,
                obrigatorio=bool(coluna["obrigatoria"]),
                ordem=ordem,
            )
        )


@router.get("", response_class=HTMLResponse, summary="Listar rotas de IA")
def listar(
    request: Request,
    db: Session = Depends(get_db),
    db_dados: Session = Depends(get_db_dados),
    usuario: Usuario = Depends(get_current_admin),
):
    """Mostra as rotas cadastradas, sinalizando as que nunca vão encontrar nada."""
    rotas = rota_service.listar_rotas(db)
    return templates.TemplateResponse(
        request,
        "rotas_list.html",
        {"usuario": usuario, "rotas": rotas, "alertas": _alertas(db_dados, rotas)},
    )


def _alertas(db_dados: Session, rotas: list[RotaIA]) -> dict[int, str]:
    """Problemas de configuração detectáveis, por id de rota.

    Uma rota que filtra por um ID responde "não encontrei" para qualquer busca por
    texto, e o aluno não tem como saber disso olhando a lista — foi assim que uma rota
    ficou quebrada sem ninguém perceber. Aqui o problema fica visível onde ele é
    resolvido.
    """
    if not banco_dados_configurado():
        return {}

    chaves_por_tabela: dict[str, set[str]] = {}
    alertas: dict[int, str] = {}

    for rota in rotas:
        if rota.operacao != "buscar" or rota.modo_busca == "todos" or not rota.coluna_filtro:
            continue
        if rota.tabela not in chaves_por_tabela:
            try:
                colunas = schema_service.listar_colunas(db_dados, rota.tabela)
            except Exception:  # noqa: BLE001 - banco fora do ar não pode quebrar a lista
                colunas = []
            chaves_por_tabela[rota.tabela] = {c["nome"] for c in colunas if c["chave"]}
        if rota.coluna_filtro in chaves_por_tabela[rota.tabela]:
            alertas[rota.id] = (
                f"Filtra por <b>{rota.coluna_filtro}</b>, que é um código/ID: buscas por "
                "texto não encontram nada. Edite e escolha uma coluna de texto."
            )
    return alertas


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
            "modos_busca": MODOS_BUSCA,
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
    modo_busca: str = Form("perguntar"),
    colunas_retorno: list[str] = Form(default=[]),
    campos_insercao: list[str] = Form(default=[]),
    pergunta: str = Form(""),
    mensagem_vazio: str = Form(""),
    requer_admin: str | None = Form(None),
    db: Session = Depends(get_db),
    db_dados: Session = Depends(get_db_dados),
    usuario: Usuario = Depends(get_current_admin),
):
    """Valida tabela/colunas no banco do projeto e grava a rota no banco da aplicação."""
    _validar(
        db_dados, operacao, tabela, coluna_filtro, colunas_retorno,
        modo_busca, campos_insercao,
    )

    rota = RotaIA(
        nome=nome.strip(),
        descricao=descricao.strip(),
        operacao=operacao,
        tabela=tabela,
        coluna_filtro=coluna_filtro or None,
        modo_busca=modo_busca,
        colunas_retorno=",".join(colunas_retorno) or None,
        pergunta=pergunta.strip() or None,
        mensagem_vazio=mensagem_vazio.strip() or None,
        requer_admin=bool(requer_admin),
    )
    db.add(rota)
    if operacao == "inserir":
        _configurar_campos_insercao(db_dados, rota, campos_insercao)
    db.commit()
    return RedirectResponse("/painel/rotas", status_code=303)


@router.get("/{rota_id}/editar", response_class=HTMLResponse, summary="Formulário de edição")
def formulario_editar(
    request: Request,
    rota_id: int,
    db: Session = Depends(get_db),
    db_dados: Session = Depends(get_db_dados),
    usuario: Usuario = Depends(get_current_admin),
):
    """Reabre o construtor com a rota preenchida.

    Poder corrigir importa: uma rota criada com a coluna de filtro errada nunca acha nada,
    e sem edição a única saída seria apagar e refazer.
    """
    rota = db.get(RotaIA, rota_id)
    if rota is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")
    return templates.TemplateResponse(
        request,
        "rotas_form.html",
        {
            "usuario": usuario,
            "rota": rota,
            "tabelas": _tabelas(db_dados),
            "operacoes": OPERACOES,
            "modos_busca": MODOS_BUSCA,
            "banco_conectado": banco_dados_configurado(),
        },
    )


@router.post("/{rota_id}/editar", summary="Salvar edição da rota")
def salvar_edicao(
    rota_id: int,
    nome: str = Form(...),
    descricao: str = Form(...),
    operacao: str = Form(...),
    tabela: str = Form(...),
    coluna_filtro: str = Form(""),
    modo_busca: str = Form("perguntar"),
    colunas_retorno: list[str] = Form(default=[]),
    campos_insercao: list[str] = Form(default=[]),
    pergunta: str = Form(""),
    mensagem_vazio: str = Form(""),
    requer_admin: str | None = Form(None),
    db: Session = Depends(get_db),
    db_dados: Session = Depends(get_db_dados),
    usuario: Usuario = Depends(get_current_admin),
):
    """Revalida tabela/colunas no banco do projeto e grava por cima."""
    rota = db.get(RotaIA, rota_id)
    if rota is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")

    _validar(
        db_dados, operacao, tabela, coluna_filtro, colunas_retorno,
        modo_busca, campos_insercao,
    )

    rota.nome = nome.strip()
    rota.descricao = descricao.strip()
    rota.operacao = operacao
    rota.tabela = tabela
    rota.coluna_filtro = coluna_filtro or None
    rota.modo_busca = modo_busca
    rota.colunas_retorno = ",".join(colunas_retorno) or None
    rota.pergunta = pergunta.strip() or None
    rota.mensagem_vazio = mensagem_vazio.strip() or None
    rota.requer_admin = bool(requer_admin)
    if operacao == "inserir":
        _configurar_campos_insercao(db_dados, rota, campos_insercao)
    else:
        rota.campos.clear()
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
