"""Etapa 2 — a fronteira de segurança entre a IA e as tabelas internas.

Nenhuma rota de IA pode alcançar tabela interna do chatbot: elas guardam hash de senha,
a chave do Groq, o histórico privado de conversas e as próprias regras do bot.
"""

import pytest
from sqlalchemy import text

from app.services import schema_service


@pytest.fixture
def engine_com_tabelas(engine):
    """Banco de teste com as tabelas internas (via models) + uma tabela do aluno."""
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alunos (id INTEGER PRIMARY KEY, nome VARCHAR(100))"))
    return engine


def test_tabela_do_aluno_aparece(engine_com_tabelas):
    assert "alunos" in schema_service.listar_tabelas(engine_com_tabelas)


@pytest.mark.parametrize(
    "tabela_interna",
    ["usuarios", "configuracoes", "mensagens", "sessoes_chat", "rotas_ia", "rota_campos",
     "rag_blocos", "tabelas_dinamicas", "colunas_dinamicas"],
)
def test_tabelas_internas_nunca_sao_listadas(engine_com_tabelas, tabela_interna):
    """Regressão: rag_blocos, tabelas_dinamicas e colunas_dinamicas ficaram de fora
    da blocklist original — um aluno conseguiria alterar as regras do próprio bot."""
    assert tabela_interna not in schema_service.listar_tabelas(engine_com_tabelas)


@pytest.mark.parametrize("tabela_interna", ["usuarios", "rag_blocos", "configuracoes"])
def test_validar_tabela_recusa_interna(engine_com_tabelas, tabela_interna):
    with pytest.raises(schema_service.TabelaNaoPermitida):
        schema_service.validar_tabela(engine_com_tabelas, tabela_interna)


def test_aceita_engine_e_session(engine_com_tabelas, db_session):
    """A introspecção funciona tanto com Engine quanto com Session (compatibilidade)."""
    por_engine = schema_service.listar_tabelas(engine_com_tabelas)
    por_sessao = schema_service.listar_tabelas(db_session)
    assert por_engine == por_sessao
