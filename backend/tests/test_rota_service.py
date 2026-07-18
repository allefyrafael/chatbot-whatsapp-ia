"""Testes da execução das rotas de IA — foco em segurança e no comportamento de busca."""

import pytest
from sqlalchemy import text

from app.models import RotaIA
from app.services import rota_service as svc
from app.services.schema_service import ColunaNaoPermitida, TabelaNaoPermitida


@pytest.fixture
def tabela_alunos(db_session):
    """Tabela criada pelo aluno, com alguns registros."""
    db_session.execute(
        text("CREATE TABLE alunos (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL, curso VARCHAR(100))")
    )
    db_session.execute(text("INSERT INTO alunos (nome, curso) VALUES ('Maria Silva', 'ADS')"))
    db_session.execute(text("INSERT INTO alunos (nome, curso) VALUES ('Joao Souza', 'Redes')"))
    db_session.commit()
    return "alunos"


def _rota_busca(db_session, tabela="alunos"):
    rota = RotaIA(
        nome="Buscar aluno",
        descricao="Busca um aluno pelo nome",
        operacao="buscar",
        tabela=tabela,
        coluna_filtro="nome",
        colunas_retorno="nome,curso",
        pergunta="Qual o nome do aluno?",
        mensagem_vazio="Não encontrei {valor} na base.",
    )
    db_session.add(rota)
    db_session.commit()
    return rota


def test_busca_encontra_registro(db_session, tabela_alunos):
    rota = _rota_busca(db_session)
    linhas = svc.executar_busca(db_session, rota, "Maria")
    assert len(linhas) == 1
    assert linhas[0]["nome"] == "Maria Silva"
    assert linhas[0]["curso"] == "ADS"


def test_busca_sem_resultado_retorna_vazio(db_session, tabela_alunos):
    rota = _rota_busca(db_session)
    assert svc.executar_busca(db_session, rota, "Fulano") == []


def test_busca_rejeita_tabela_bloqueada(db_session):
    """Mesmo configurada, uma rota apontando p/ 'usuarios' nao executa."""
    rota = _rota_busca(db_session, tabela="usuarios")
    with pytest.raises(TabelaNaoPermitida):
        svc.executar_busca(db_session, rota, "x")


def test_busca_rejeita_coluna_inexistente(db_session, tabela_alunos):
    rota = _rota_busca(db_session)
    rota.coluna_filtro = "coluna_fantasma"
    db_session.commit()
    with pytest.raises(ColunaNaoPermitida):
        svc.executar_busca(db_session, rota, "x")


def test_busca_nao_sofre_injection(db_session, tabela_alunos):
    """Valor malicioso e tratado como texto, nao como SQL."""
    rota = _rota_busca(db_session)
    linhas = svc.executar_busca(db_session, rota, "'; DROP TABLE alunos; --")
    assert linhas == []
    # a tabela continua la
    assert db_session.execute(text("SELECT COUNT(*) FROM alunos")).scalar() == 2


def test_insercao_grava_registro(db_session, tabela_alunos):
    rota = RotaIA(
        nome="Cadastrar aluno", descricao="Cadastra aluno", operacao="inserir",
        tabela="alunos",
    )
    db_session.add(rota)
    db_session.commit()

    svc.executar_insercao(db_session, rota, {"nome": "Ana Lima", "curso": "Design"})

    total = db_session.execute(text("SELECT COUNT(*) FROM alunos WHERE nome='Ana Lima'")).scalar()
    assert total == 1


def test_insercao_rejeita_coluna_invalida(db_session, tabela_alunos):
    rota = RotaIA(nome="X", descricao="X", operacao="inserir", tabela="alunos")
    db_session.add(rota)
    db_session.commit()
    with pytest.raises(ColunaNaoPermitida):
        svc.executar_insercao(db_session, rota, {"coluna_fantasma": "x"})


def test_exclusao_remove_registro(db_session, tabela_alunos):
    rota = RotaIA(
        nome="Excluir aluno", descricao="Exclui aluno", operacao="excluir",
        tabela="alunos", coluna_filtro="nome",
    )
    db_session.add(rota)
    db_session.commit()

    removidos = svc.executar_exclusao(db_session, rota, "Joao Souza")

    assert removidos == 1
    assert db_session.execute(text("SELECT COUNT(*) FROM alunos")).scalar() == 1
