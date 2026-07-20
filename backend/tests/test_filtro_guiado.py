"""Filtro escolhido durante a conversa, e não fixado na rota.

Uma rota tinha UMA coluna de filtro, definida no painel. Se ela fosse a errada — um id,
por exemplo — toda busca respondia "não encontrei", mesmo com a tabela cheia, e quem
conversava não tinha como filtrar pelo que realmente queria.

No modo "Deixar escolher" o bot passa a oferecer as colunas e a pessoa escolhe:

    Cliente: quero os registros de categoria
    Bot:     Você pode filtrar por estas colunas: 1. nome  2. descricao  3. ativa
    Cliente: ativa
    Bot:     Qual valor você procura em ativa?
    Cliente: 1
    Bot:     [resultados]
"""

import pytest
from sqlalchemy import text

from app.config import settings
from app.models import RotaIA
from app.services import conversa_service, rota_service

NUMERO = "5561999991111"


@pytest.fixture(autouse=True)
def banco_do_projeto_conectado():
    original = settings.dados_database_url
    settings.dados_database_url = "mysql+pymysql://u:p@rds.exemplo:3306/projeto"
    yield
    settings.dados_database_url = original


@pytest.fixture
def categorias(db_session):
    db_session.execute(text(
        "CREATE TABLE categorias (id_categoria INTEGER PRIMARY KEY,"
        " nome VARCHAR(100), descricao VARCHAR(255), ativa INTEGER)"
    ))
    dados = [
        (1, "Corrupcao", "desvio de recursos", 1),
        (2, "Violencia", "agressoes e ameacas", 1),
        (3, "Assedio", "constrangimento", 0),
    ]
    for linha in dados:
        db_session.execute(
            text("INSERT INTO categorias VALUES (:a,:b,:c,:d)"),
            dict(zip("abcd", linha)),
        )
    db_session.commit()
    return db_session


@pytest.fixture
def rota(db_session):
    """Rota com a coluna de filtro ERRADA de propósito: é o cenário real."""
    r = RotaIA(
        nome="Buscar Categorias", descricao="consultar categorias", operacao="buscar",
        tabela="categorias", coluna_filtro="id_categoria",
        modo_busca="perguntar_ou_todos", pergunta="O que você procura?",
    )
    db_session.add(r)
    db_session.commit()
    return r


def _iniciar(db_session, rota):
    return conversa_service.iniciar_rota(db_session, db_session, NUMERO, rota)


def _responder(db_session, texto):
    return conversa_service.continuar_fluxo(db_session, db_session, NUMERO, texto)


class TestColunasOferecidas:
    def test_resposta_desconhecida_lista_as_colunas(self, db_session, categorias, rota):
        _iniciar(db_session, rota)

        resposta = _responder(db_session, "quero filtrar")

        assert "filtrar por estas colunas" in resposta
        assert "nome" in resposta and "descricao" in resposta and "ativa" in resposta

    def test_id_gerado_fica_fora_da_lista(self, db_session, categorias, rota):
        """Ninguém filtra por autoincremento em linguagem natural."""
        colunas = [c["nome"] for c in rota_service.colunas_filtraveis(db_session, rota)]
        assert "id_categoria" not in colunas

    def test_escolher_pelo_numero(self, db_session, categorias, rota):
        _iniciar(db_session, rota)
        _responder(db_session, "quero filtrar")

        resposta = _responder(db_session, "1")

        assert "nome" in resposta and "Qual valor" in resposta


class TestFiltrarDeVerdade:
    def test_coluna_depois_valor(self, db_session, categorias, rota):
        _iniciar(db_session, rota)
        _responder(db_session, "quero filtrar")
        _responder(db_session, "ativa")

        resposta = _responder(db_session, "0")

        assert "Assedio" in resposta
        assert "Corrupcao" not in resposta

    def test_a_rota_filtrava_por_id_e_ainda_assim_funciona(self, db_session, categorias, rota):
        """O ponto central: a coluna errada na rota não condena mais a busca."""
        assert rota.coluna_filtro == "id_categoria"

        _iniciar(db_session, rota)
        _responder(db_session, "nome")
        resposta = _responder(db_session, "Corrupcao")

        assert "Corrupcao" in resposta

    @pytest.mark.parametrize(
        "frase",
        [
            "filtrar por nome = Corrupcao",
            "nome: Corrupcao",
            "quero filtrar por nome com o valor Corrupcao",
            "nome igual a Corrupcao",
        ],
    )
    def test_uma_frase_so(self, db_session, categorias, rota, frase):
        """Quem já sabe o que quer não precisa da ida e volta."""
        _iniciar(db_session, rota)

        resposta = _responder(db_session, frase)

        assert "Corrupcao" in resposta
        assert "Qual valor" not in resposta

    def test_nome_da_coluna_sem_acento_e_com_espaco(self, db_session, rota):
        db_session.execute(text(
            "CREATE TABLE pessoas (id INTEGER PRIMARY KEY, data_cadastro VARCHAR(20))"
        ))
        db_session.execute(text("INSERT INTO pessoas VALUES (1, '2026-07-19')"))
        db_session.commit()
        rota.tabela = "pessoas"
        db_session.commit()

        _iniciar(db_session, rota)
        resposta = _responder(db_session, "data cadastro")

        assert "data_cadastro" in resposta


class TestTudoContinuaValendo:
    def test_todas_ainda_lista_a_tabela(self, db_session, categorias, rota):
        _iniciar(db_session, rota)

        resposta = _responder(db_session, "todas")

        assert "Corrupcao" in resposta and "Assedio" in resposta

    def test_todas_vale_tambem_no_menu_de_colunas(self, db_session, categorias, rota):
        _iniciar(db_session, rota)
        _responder(db_session, "quero filtrar")

        resposta = _responder(db_session, "todas")

        assert "Corrupcao" in resposta

    def test_sem_resultado_explica_coluna_e_valor(self, db_session, categorias, rota):
        _iniciar(db_session, rota)
        _responder(db_session, "nome")

        resposta = _responder(db_session, "Inexistente")

        assert "Inexistente" in resposta
