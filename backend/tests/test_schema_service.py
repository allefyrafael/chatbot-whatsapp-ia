"""Testes da introspecção — inclui a fronteira de segurança (tabelas bloqueadas)."""

import pytest
from sqlalchemy import text

from app.services import schema_service as svc


def test_nao_expoe_tabelas_sensiveis(db_session):
    """usuarios/configuracoes guardam segredos e nunca podem aparecer."""
    tabelas = svc.listar_tabelas(db_session)
    assert "usuarios" not in tabelas
    assert "configuracoes" not in tabelas
    assert "mensagens" not in tabelas
    assert "sessoes_chat" not in tabelas
    assert "rotas_ia" not in tabelas


def test_lista_tabelas_de_dominio(db_session):
    """Tabelas normais do banco continuam disponíveis para montar rotas."""
    tabelas = svc.listar_tabelas(db_session)
    assert "itens" in tabelas
    assert "clientes" in tabelas


def test_lista_tabela_criada_pelo_aluno(db_session):
    """O aluno cria a própria tabela e ela aparece no construtor."""
    db_session.execute(
        text("CREATE TABLE alunos (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL, email VARCHAR(100))")
    )
    db_session.commit()

    assert "alunos" in svc.listar_tabelas(db_session)


def test_colunas_indicam_obrigatoriedade(db_session):
    db_session.execute(
        text("CREATE TABLE chamados (id INTEGER PRIMARY KEY, titulo VARCHAR(100) NOT NULL, obs VARCHAR(200))")
    )
    db_session.commit()

    colunas = {c["nome"]: c for c in svc.listar_colunas(db_session, "chamados")}
    assert colunas["titulo"]["obrigatoria"] is True
    assert colunas["obs"]["obrigatoria"] is False
    assert colunas["id"]["gerada"] is True  # id nao e pedido ao usuario


def test_validar_tabela_rejeita_bloqueada_e_inexistente(db_session):
    with pytest.raises(svc.TabelaNaoPermitida):
        svc.validar_tabela(db_session, "usuarios")
    with pytest.raises(svc.TabelaNaoPermitida):
        svc.validar_tabela(db_session, "tabela_que_nao_existe")


def test_validar_colunas_rejeita_inexistente(db_session):
    with pytest.raises(svc.ColunaNaoPermitida):
        svc.validar_colunas(db_session, "itens", ["nome", "coluna_fantasma"])
    # colunas reais passam
    assert svc.validar_colunas(db_session, "itens", ["nome", "preco"]) == ["nome", "preco"]
