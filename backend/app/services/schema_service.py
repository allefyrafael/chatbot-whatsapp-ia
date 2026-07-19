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

# Nomes exclusivos desta aplicação: nunca são tabelas legítimas de um aluno, e guardam
# segredos ou o estado interno do bot. Ficam bloqueados em qualquer banco — inclusive no
# do aluno, porque uma cópia pode ter ido parar lá (foi o que aconteceu quando a
# configuração apontou para a AWS por engano). Ao criar uma tabela interna, inclua-a aqui.
TABELAS_INTERNAS = {
    "configuracoes",      # chave do Groq, código de pareamento
    "sessoes_chat",       # estado de autenticação do chat
    "rotas_ia",           # a própria configuração das rotas
    "rota_campos",
    "mensagens",          # histórico privado de conversas
    "rag_blocos",         # as regras de comportamento do próprio bot
    "tabelas_dinamicas",  # metadados internos do catálogo
    "colunas_dinamicas",
}

# Nome genérico demais para bloquear sempre: quase todo projeto de aluno tem o seu
# `usuarios` (um sistema de denúncias, por exemplo). No banco da aplicação ele guarda
# hashes de senha, então só é bloqueado quando o banco em uso É o da aplicação.
TABELAS_INTERNAS_SO_NA_APLICACAO = {"usuarios"}

TABELAS_BLOQUEADAS = TABELAS_INTERNAS | TABELAS_INTERNAS_SO_NA_APLICACAO


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


def _colunas_dos_modelos() -> dict[str, set[str]]:
    """Assinatura (nome -> colunas) de cada tabela que ESTA aplicação define."""
    import app.models  # noqa: F401 - registra as tabelas no metadata
    from app.database import Base

    return {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}


def _bloqueadas_para(engine: Engine) -> set[str]:
    """Quais nomes esconder neste engine.

    No banco da **aplicação**, tudo o que é interno — inclusive `usuarios`, que ali guarda
    hashes de senha.

    No banco do **aluno**, o projeto dele aparece inteiro. A única exceção são os nomes que
    carregam segredo (`configuracoes` tem a chave do Groq, `sessoes_chat` tem estado de
    autenticação): versões anteriores gravavam essas tabelas no RDS por engano, e expor uma
    sobra dessas a uma rota de IA seria vazamento. São nomes desta aplicação, não de um
    projeto de aula.
    """
    from app.database import get_engine

    if str(engine.url) == str(get_engine().url):
        return TABELAS_BLOQUEADAS
    return TABELAS_INTERNAS


def listar_tabelas(origem: Engine | Session) -> list[str]:
    """Tabelas do banco do projeto disponíveis para montar rotas."""
    engine = _engine_de(origem)
    inspetor = inspect(engine)
    bloqueadas = _bloqueadas_para(engine)
    return sorted(t for t in inspetor.get_table_names() if t not in bloqueadas)


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
