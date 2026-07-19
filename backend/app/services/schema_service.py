"""Introspecção do banco do aluno — descobre tabelas e colunas reais.

Além de alimentar o construtor de rotas no painel, este módulo é a **fronteira de
segurança** do recurso: nenhum nome de tabela ou coluna chega ao SQL sem ter sido
confirmado aqui. Assim, mesmo que a IA (ou o usuário do chat) invente um nome, ele é
rejeitado antes de qualquer execução.

Tabelas internas da aplicação ficam de fora: guardam segredos (hash de senha, chave do
Groq), estado de autenticação ou o histórico privado de conversas.
"""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# Nunca expostas às rotas de IA.
#
# Com o banco de trabalho separado (DADOS_DATABASE_URL) estas tabelas nem existem lá;
# a lista continua como defesa em profundidade para o modo fallback, em que o banco de
# trabalho é o mesmo da aplicação. Ao criar uma tabela interna nova, acrescente-a aqui.
TABELAS_BLOQUEADAS = {
    "usuarios",           # hashes de senha
    "configuracoes",      # chave do Groq, código de pareamento
    "sessoes_chat",       # estado de autenticação do chat
    "rotas_ia",           # a própria configuração das rotas
    "rota_campos",
    "mensagens",          # histórico privado de conversas
    "rag_blocos",         # as regras de comportamento do próprio bot
    "tabelas_dinamicas",  # metadados internos do catálogo
    "colunas_dinamicas",
}


def _engine_de(origem: Engine | Session) -> Engine:
    """Aceita Engine ou Session e devolve sempre o Engine.

    A introspecção só precisa do Engine; aceitar `Session` mantém compatibilidade com os
    chamadores que já têm uma sessão em mãos.
    """
    return origem if isinstance(origem, Engine) else origem.get_bind()


class TabelaNaoPermitida(Exception):
    """Tabela inexistente ou bloqueada para uso pelas rotas de IA."""


class ColunaNaoPermitida(Exception):
    """Coluna inexistente na tabela informada."""


def listar_tabelas(origem: Engine | Session) -> list[str]:
    """Tabelas do banco de trabalho disponíveis para montar rotas (sem as internas)."""
    inspetor = inspect(_engine_de(origem))
    return sorted(t for t in inspetor.get_table_names() if t not in TABELAS_BLOQUEADAS)


def listar_colunas(origem: Engine | Session, tabela: str) -> list[dict]:
    """Colunas da tabela, com o que o construtor precisa saber.

    `obrigatoria` indica que a coluna precisa de valor ao inserir (NOT NULL, sem default
    e sem autoincremento) — é o que permite o bot avisar o que é obrigatório.
    """
    validar_tabela(origem, tabela)
    inspetor = inspect(_engine_de(origem))
    colunas = []
    for col in inspetor.get_columns(tabela):
        autoincremento = bool(col.get("autoincrement")) or col.get("name") == "id"
        obrigatoria = (
            not col.get("nullable", True)
            and col.get("default") is None
            and not autoincremento
        )
        colunas.append(
            {
                "nome": col["name"],
                "tipo": str(col["type"]),
                "obrigatoria": obrigatoria,
                "gerada": autoincremento,
            }
        )
    return colunas


def validar_tabela(origem: Engine | Session, tabela: str) -> str:
    """Confirma que a tabela existe e não é bloqueada. Devolve o nome validado."""
    nome = (tabela or "").strip()
    if nome not in listar_tabelas(origem):
        raise TabelaNaoPermitida(f"Tabela '{tabela}' não existe ou não é permitida.")
    return nome


def validar_colunas(origem: Engine | Session, tabela: str, colunas: list[str]) -> list[str]:
    """Confirma que todas as colunas existem na tabela. Devolve a lista validada."""
    existentes = {c["nome"] for c in listar_colunas(origem, tabela)}
    invalidas = [c for c in colunas if c not in existentes]
    if invalidas:
        raise ColunaNaoPermitida(f"Coluna(s) inexistente(s) em '{tabela}': {invalidas}")
    return list(colunas)
