"""Regras do RAG por prompt — blocos de instrução e montagem do system prompt.

Os blocos ficam em `rag_blocos` (tipo 'fazer'/'nao_fazer', título, conteúdo, ordem,
ativo). `montar_system_prompt` junta os blocos ativos, agrupados por tipo e ordenados,
produzindo o texto que será usado como *system prompt* do Groq (fase 5). Manter esta
lógica isolada aqui deixa o roteador de IA futuro trivial e testável.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RagBloco

TIPOS_VALIDOS = ("fazer", "nao_fazer")

_CABECALHOS = {
    "fazer": "# O QUE VOCÊ DEVE FAZER",
    "nao_fazer": "# O QUE VOCÊ NÃO DEVE FAZER",
}


def listar_blocos(db: Session, tipo: str | None = None) -> list[RagBloco]:
    stmt = select(RagBloco)
    if tipo is not None:
        stmt = stmt.where(RagBloco.tipo == tipo)
    stmt = stmt.order_by(RagBloco.ordem, RagBloco.id)
    return list(db.execute(stmt).scalars().all())


def criar_bloco(db: Session, tipo: str, titulo: str, conteudo: str) -> RagBloco:
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"Tipo inválido: {tipo!r}. Use um de {TIPOS_VALIDOS}.")
    bloco = RagBloco(tipo=tipo, titulo=titulo.strip(), conteudo=conteudo.strip())
    db.add(bloco)
    db.commit()
    return bloco


def atualizar_bloco(db: Session, bloco: RagBloco, titulo: str, conteudo: str, ativo: bool) -> RagBloco:
    bloco.titulo = titulo.strip()
    bloco.conteudo = conteudo.strip()
    bloco.ativo = ativo
    db.commit()
    return bloco


def excluir_bloco(db: Session, bloco: RagBloco) -> None:
    db.delete(bloco)
    db.commit()


def montar_system_prompt(db: Session) -> str:
    """Monta o system prompt juntando os blocos ativos, por tipo e ordem.

    Retorna string vazia quando não há blocos ativos.
    """
    secoes: list[str] = []
    for tipo in TIPOS_VALIDOS:
        blocos = [b for b in listar_blocos(db, tipo) if b.ativo]
        if not blocos:
            continue
        linhas = [_CABECALHOS[tipo]]
        for bloco in blocos:
            linhas.append(f"- {bloco.titulo}: {bloco.conteudo}")
        secoes.append("\n".join(linhas))
    return "\n\n".join(secoes)
