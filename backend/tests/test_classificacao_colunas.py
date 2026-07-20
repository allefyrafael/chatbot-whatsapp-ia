"""Classificação de colunas sem depender de uma lista de nomes conhecidos.

O construtor precisa responder duas perguntas em QUALQUER banco de aluno:
- esta coluna é um identificador? (filtrar por id devolve sempre vazio)
- esta coluna carrega segredo? (o que for marcado o bot manda no WhatsApp)

O schema não guarda "sensibilidade", então combinamos sinais estruturais (chave
primária, estrangeira, unicidade, largura do tipo) com radicais de nome normalizados.
Cada marcação vem com o motivo, para a tela justificar e o aluno decidir.
"""

import pytest
from sqlalchemy import text

from app.config import settings
from app.services import schema_service


@pytest.fixture(autouse=True)
def banco_do_projeto_conectado():
    original = settings.dados_database_url
    settings.dados_database_url = "mysql+pymysql://u:p@rds.exemplo:3306/projeto"
    yield
    settings.dados_database_url = original


def _colunas(db_session, ddl: str, tabela: str) -> dict:
    db_session.execute(text(ddl))
    db_session.commit()
    return {c["nome"]: c for c in schema_service.listar_colunas(db_session, tabela)}


class TestIdentificadores:
    def test_chave_primaria_sem_nome_de_id(self, db_session):
        """`matricula` é PK: estrutura vence o nome."""
        cols = _colunas(
            db_session,
            "CREATE TABLE alunos (matricula VARCHAR(20) PRIMARY KEY, nome VARCHAR(80))",
            "alunos",
        )
        assert cols["matricula"]["chave"] is True
        assert cols["nome"]["chave"] is False

    def test_chave_estrangeira_e_identificador(self, db_session):
        db_session.execute(text("CREATE TABLE cat (id INTEGER PRIMARY KEY)"))
        cols = _colunas(
            db_session,
            "CREATE TABLE post (id INTEGER PRIMARY KEY, titulo VARCHAR(80),"
            " cat_ref INTEGER REFERENCES cat(id))",
            "post",
        )
        assert cols["cat_ref"]["chave"] is True
        assert cols["titulo"]["chave"] is False


class TestSensibilidade:
    @pytest.mark.parametrize(
        "coluna",
        ["senha", "Senha_Hash", "PASSWORD", "api_token", "nr_cpf", "numeroCartao"],
    )
    def test_radical_no_nome_em_qualquer_estilo(self, db_session, coluna):
        cols = _colunas(
            db_session,
            f'CREATE TABLE t1_{abs(hash(coluna)) % 9999} (id INTEGER PRIMARY KEY, "{coluna}" VARCHAR(80))',
            f"t1_{abs(hash(coluna)) % 9999}",
        )
        assert cols[coluna]["sensivel"] is True
        assert cols[coluna]["motivo_sensivel"]

    def test_hash_reconhecido_pela_largura(self, db_session):
        """CHAR(60) é bcrypt — pega mesmo com nome inocente como `verificador`."""
        cols = _colunas(
            db_session,
            "CREATE TABLE contas (id INTEGER PRIMARY KEY, verificador CHAR(60))",
            "contas",
        )
        assert cols["verificador"]["sensivel"] is True
        assert "hash" in cols["verificador"]["motivo_sensivel"]

    def test_texto_unico_e_tratado_como_identificacao(self, db_session):
        """UNIQUE precisa ser nomeado: o SQLite não expõe o `UNIQUE` inline pela
        introspecção (`get_unique_constraints` volta vazio). No MySQL do aluno as duas
        formas aparecem."""
        cols = _colunas(
            db_session,
            "CREATE TABLE pessoas (id INTEGER PRIMARY KEY, login VARCHAR(80),"
            " apelido VARCHAR(80), CONSTRAINT uq_login UNIQUE (login))",
            "pessoas",
        )
        assert cols["login"]["sensivel"] is True
        assert "único" in cols["login"]["motivo_sensivel"]
        assert cols["apelido"]["sensivel"] is False

    def test_indice_unico_tambem_conta(self, db_session):
        db_session.execute(text(
            "CREATE TABLE contas2 (id INTEGER PRIMARY KEY, email VARCHAR(120))"
        ))
        db_session.execute(text("CREATE UNIQUE INDEX ix_email ON contas2 (email)"))
        db_session.commit()
        cols = {c["nome"]: c for c in schema_service.listar_colunas(db_session, "contas2")}

        assert cols["email"]["sensivel"] is True

    def test_coluna_comum_nao_e_marcada(self, db_session):
        """Falso positivo custa caro: o aluno perde a coluna que queria mostrar."""
        cols = _colunas(
            db_session,
            "CREATE TABLE categorias (id_categoria INTEGER PRIMARY KEY,"
            " nome VARCHAR(100), descricao VARCHAR(255), ativa BOOLEAN)",
            "categorias",
        )
        for coluna in ("nome", "descricao", "ativa"):
            assert cols[coluna]["sensivel"] is False, coluna


class TestPapel:
    def test_familia_do_tipo(self, db_session):
        cols = _colunas(
            db_session,
            "CREATE TABLE variados (id INTEGER PRIMARY KEY, txt VARCHAR(10),"
            " qtd INTEGER, quando DATE, flag BOOLEAN)",
            "variados",
        )
        assert cols["txt"]["papel"] == "texto"
        assert cols["qtd"]["papel"] == "numero"
        assert cols["quando"]["papel"] == "data"
        assert cols["flag"]["papel"] == "booleano"
