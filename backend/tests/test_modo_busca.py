"""Modos de busca da rota — e o bug que eles corrigem.

Conversa real que motivou isto (tabela `categorias` com 10 registros):

    Allefy: Quero buscar as categorias
    Bot:    Essa ação é restrita a administradores. Qual o seu e-mail?
    ...
    Bot:    Autenticado, Allefy. Não existe nenhum registro nessa tabela.

Duas causas: a IA preencheu `valor="categorias"` (o objeto da frase), o que pulou a
pergunta configurada; e a rota então filtrou por esse termo, que não existe em nenhum
registro. O resultado é "vazio" numa tabela cheia.
"""

import pytest
from sqlalchemy import text

from app.config import settings
from app.models import RotaIA, SessaoChat
from app.services import conversa_service

NUMERO = "5561999990000"


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
        " nome VARCHAR(100), descricao VARCHAR(255), ativa BOOLEAN)"
    ))
    for i, nome in enumerate(["Corrupcao", "Violencia", "Assedio"], start=1):
        db_session.execute(
            text("INSERT INTO categorias VALUES (:i, :n, 'desc', 1)"), {"i": i, "n": nome}
        )
    db_session.commit()
    return db_session


def _rota(db_session, **kwargs):
    padrao = dict(
        nome="Buscar Categorias", descricao="consultar categorias", operacao="buscar",
        tabela="categorias", coluna_filtro="nome",
        colunas_retorno="id_categoria,nome", pergunta="O que você procura?",
        modo_busca="perguntar",
    )
    padrao.update(kwargs)
    rota = RotaIA(**padrao)
    db_session.add(rota)
    db_session.commit()
    return rota


class TestModoTodos:
    def test_lista_tudo_sem_perguntar(self, db_session, categorias):
        """"Quero ver as categorias" devolve a tabela, não uma pergunta."""
        rota = _rota(db_session, modo_busca="todos")

        resposta = conversa_service.iniciar_rota(
            db_session, db_session, NUMERO, rota, valor="categorias"
        )

        assert "Corrupcao" in resposta and "Violencia" in resposta
        assert "procura" not in resposta

    def test_tabela_vazia_avisa_sem_mentir(self, db_session, categorias):
        db_session.execute(text("DELETE FROM categorias"))
        db_session.commit()
        rota = _rota(db_session, modo_busca="todos")

        resposta = conversa_service.iniciar_rota(db_session, db_session, NUMERO, rota)

        assert "não tem registros" in resposta


class TestValorGenerico:
    @pytest.mark.parametrize("valor", ["categorias", "Categorias", "categoria", "todas"])
    def test_objeto_da_frase_nao_vira_filtro(self, db_session, categorias, valor):
        """A IA preenche `valor` com o assunto; isso não pode virar termo de busca."""
        rota = _rota(db_session, modo_busca="perguntar")

        resposta = conversa_service.iniciar_rota(
            db_session, db_session, NUMERO, rota, valor=valor
        )

        assert resposta == "O que você procura?"   # perguntou, em vez de filtrar

    def test_termo_de_verdade_e_respeitado(self, db_session, categorias):
        rota = _rota(db_session, modo_busca="perguntar")

        resposta = conversa_service.iniciar_rota(
            db_session, db_session, NUMERO, rota, valor="Corrupcao"
        )

        assert "Corrupcao" in resposta


class TestPerguntarOuTodos:
    def test_pergunta_avisa_que_aceita_todas(self, db_session, categorias):
        rota = _rota(db_session, modo_busca="perguntar_ou_todos")

        resposta = conversa_service.iniciar_rota(db_session, db_session, NUMERO, rota)

        assert "O que você procura?" in resposta
        assert "todas" in resposta

    def test_responder_todas_lista_tudo(self, db_session, categorias):
        rota = _rota(db_session, modo_busca="perguntar_ou_todos")
        conversa_service.iniciar_rota(db_session, db_session, NUMERO, rota)

        resposta = conversa_service.continuar_fluxo(
            db_session, db_session, NUMERO, "todas"
        )

        assert "Corrupcao" in resposta and "Assedio" in resposta

    def test_responder_um_termo_filtra(self, db_session, categorias):
        rota = _rota(db_session, modo_busca="perguntar_ou_todos")
        conversa_service.iniciar_rota(db_session, db_session, NUMERO, rota)

        resposta = conversa_service.continuar_fluxo(
            db_session, db_session, NUMERO, "Assedio"
        )

        assert "Assedio" in resposta
        assert "Corrupcao" not in resposta

    def test_todas_nao_lista_tudo_no_modo_perguntar(self, db_session, categorias):
        """Onde a rota não aceita "todas", a lista completa não pode escapar."""
        rota = _rota(db_session, modo_busca="perguntar")
        conversa_service.iniciar_rota(db_session, db_session, NUMERO, rota)

        resposta = conversa_service.continuar_fluxo(
            db_session, db_session, NUMERO, "todas"
        )

        assert "Corrupcao" not in resposta


class TestNaoEntrarEmLoop:
    """A resposta que a pessoa digita nunca pode ser descartada.

    Loop relatado em produção, com a rota em modo `perguntar`:

        Bot:     Você quer buscar todas ou alguma em específico?
        Cliente: Todos
        Bot:     Você quer buscar todas ou alguma em específico?
        Cliente: Todos
        ...

    O guarda de "valor genérico" existe para ignorar o que a IA extrai da frase inicial
    ("categorias"). Aplicá-lo também à resposta digitada fazia o bot perguntar de novo
    sem parar, porque "todos" cai no mesmo filtro.
    """

    def test_responder_todos_no_modo_perguntar_nao_repete_a_pergunta(
        self, db_session, categorias
    ):
        rota = _rota(db_session, modo_busca="perguntar", pergunta="Todas ou específica?")
        primeira = conversa_service.iniciar_rota(db_session, db_session, NUMERO, rota)
        assert primeira == "Todas ou específica?"

        segunda = conversa_service.continuar_fluxo(db_session, db_session, NUMERO, "Todos")

        assert segunda != primeira, "perguntou de novo — é o loop"

    def test_pedir_tudo_onde_nao_ha_essa_opcao_explica(self, db_session, categorias):
        """"Não achei Todos" seria inútil: a pessoa pediu a lista, não buscou por "Todos"."""
        rota = _rota(
            db_session, modo_busca="perguntar", pergunta="Qual?",
            mensagem_vazio="Não achei {valor}.",
        )
        conversa_service.iniciar_rota(db_session, db_session, NUMERO, rota)

        resposta = conversa_service.continuar_fluxo(db_session, db_session, NUMERO, "Todos")

        assert "termo específico" in resposta
        assert "Não achei" not in resposta

    def test_termo_seguinte_funciona_normalmente(self, db_session, categorias):
        """A recusa mantém o fluxo aberto — a pessoa digita o termo e a busca acontece."""
        rota = _rota(db_session, modo_busca="perguntar", pergunta="Qual?")
        conversa_service.iniciar_rota(db_session, db_session, NUMERO, rota)
        conversa_service.continuar_fluxo(db_session, db_session, NUMERO, "todas")

        resposta = conversa_service.continuar_fluxo(db_session, db_session, NUMERO, "Assedio")

        assert "Assedio" in resposta

    def test_guarda_continua_valendo_para_o_valor_da_ia(self, db_session, categorias):
        """O motivo original do guarda não pode se perder na correção."""
        rota = _rota(db_session, modo_busca="perguntar", pergunta="Qual?")

        resposta = conversa_service.iniciar_rota(
            db_session, db_session, NUMERO, rota, valor="categorias"
        )

        assert resposta == "Qual?"
