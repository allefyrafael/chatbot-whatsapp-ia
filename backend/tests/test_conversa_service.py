"""Testes do diálogo em etapas (pergunta -> resposta -> execução) e da auth no chat."""

import datetime

import pytest
from sqlalchemy import text

from app.models import RotaIA, SessaoChat, Usuario
from app.security import hash_senha
from app.services import conversa_service as cs

NUMERO = "5561999998888"


def _daqui(minutos: int) -> datetime.datetime:
    """Instante relativo no MESMO relógio do serviço (UTC naive), evitando erro de fuso."""
    agora = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return agora + datetime.timedelta(minutes=minutos)


@pytest.fixture
def tabela_alunos(db_session):
    db_session.execute(
        text("CREATE TABLE alunos (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL, curso VARCHAR(100))")
    )
    db_session.execute(text("INSERT INTO alunos (nome, curso) VALUES ('Maria Silva', 'ADS')"))
    db_session.commit()


@pytest.fixture
def rota_busca(db_session, tabela_alunos):
    rota = RotaIA(
        nome="Buscar aluno", descricao="Busca aluno pelo nome", operacao="buscar",
        tabela="alunos", coluna_filtro="nome", colunas_retorno="nome,curso",
        pergunta="Qual o nome do aluno?", mensagem_vazio="Não encontrei {valor} na base.",
    )
    db_session.add(rota)
    db_session.commit()
    return rota


def test_busca_pergunta_depois_responde(db_session, rota_busca):
    """Sem valor, o bot faz a pergunta configurada; a resposta seguinte e o filtro."""
    pergunta = cs.iniciar_rota(db_session, db_session, NUMERO, rota_busca)
    assert pergunta == "Qual o nome do aluno?"

    resposta = cs.continuar_fluxo(db_session, db_session, NUMERO, "Maria")
    assert "Maria Silva" in resposta and "ADS" in resposta


def test_busca_com_valor_ja_informado_executa_direto(db_session, rota_busca):
    resposta = cs.iniciar_rota(db_session, db_session, NUMERO, rota_busca, valor="Maria")
    assert "Maria Silva" in resposta


def test_nao_encontrado_repete_o_termo_buscado(db_session, rota_busca):
    cs.iniciar_rota(db_session, db_session, NUMERO, rota_busca)
    resposta = cs.continuar_fluxo(db_session, db_session, NUMERO, "Fulano")
    assert resposta == "Não encontrei Fulano na base."


def test_sem_fluxo_pendente_retorna_none(db_session):
    assert cs.continuar_fluxo(db_session, db_session, NUMERO, "oi") is None


def test_cancelar_encerra_o_fluxo(db_session, rota_busca):
    cs.iniciar_rota(db_session, db_session, NUMERO, rota_busca)
    resposta = cs.continuar_fluxo(db_session, db_session, NUMERO, "cancelar")
    assert "cancelei" in resposta.lower()
    assert cs.continuar_fluxo(db_session, db_session, NUMERO, "Maria") is None


# ------------------------------------------------------------------ admin no chat
@pytest.fixture
def rota_restrita(db_session, tabela_alunos):
    rota = RotaIA(
        nome="Excluir aluno", descricao="Exclui aluno", operacao="excluir",
        tabela="alunos", coluna_filtro="nome", pergunta="Qual aluno excluir?",
        requer_admin=True,
    )
    db_session.add(rota)
    db_session.add(Usuario(nome="Chefe", email="admin@x.com", senha_hash=hash_senha("senha12345")))
    db_session.commit()
    return rota


def test_rota_restrita_pede_email_e_senha(db_session, rota_restrita):
    r1 = cs.iniciar_rota(db_session, db_session, NUMERO, rota_restrita)
    assert "e-mail" in r1.lower()

    r2 = cs.continuar_fluxo(db_session, db_session, NUMERO, "admin@x.com")
    assert "senha" in r2.lower()

    r3 = cs.continuar_fluxo(db_session, db_session, NUMERO, "senha12345")
    assert "autenticado" in r3.lower()
    assert "Para excluir" in r3


def test_senha_errada_cancela_a_acao(db_session, rota_restrita):
    cs.iniciar_rota(db_session, db_session, NUMERO, rota_restrita)
    cs.continuar_fluxo(db_session, db_session, NUMERO, "admin@x.com")
    resposta = cs.continuar_fluxo(db_session, db_session, NUMERO, "senha-errada")

    assert "incorretos" in resposta.lower()
    sessao = db_session.get(SessaoChat, NUMERO)
    assert sessao.etapa is None
    assert not cs.admin_autenticado(sessao)


def test_senha_deve_ser_mascarada_no_historico(db_session, rota_restrita):
    """Enquanto espera a senha, a mensagem nao pode ser gravada em claro."""
    cs.iniciar_rota(db_session, db_session, NUMERO, rota_restrita)
    cs.continuar_fluxo(db_session, db_session, NUMERO, "admin@x.com")

    assert cs.deve_mascarar(db_session, NUMERO) is True


def test_sessao_admin_expira(db_session, rota_restrita):
    sessao = cs.obter_sessao(db_session, NUMERO)
    sessao.admin_autenticado_ate = _daqui(-1)
    db_session.commit()
    assert cs.admin_autenticado(sessao) is False


def test_admin_ja_autenticado_nao_pede_senha_de_novo(db_session, rota_restrita):
    sessao = cs.obter_sessao(db_session, NUMERO)
    sessao.admin_autenticado_ate = _daqui(5)
    db_session.commit()

    resposta = cs.iniciar_rota(db_session, db_session, NUMERO, rota_restrita)
    assert "Para excluir" in resposta


# --------------------------------------------------------------------- exclusao
def test_exclusao_pede_confirmacao(db_session, rota_restrita):
    sessao = cs.obter_sessao(db_session, NUMERO)
    sessao.admin_autenticado_ate = _daqui(5)
    db_session.commit()

    primeira = cs.iniciar_rota(db_session, db_session, NUMERO, rota_restrita)
    assert "Registro 1" in primeira and "id" in primeira
    coluna = cs.continuar_fluxo(db_session, db_session, NUMERO, "nome")
    assert "Qual valor" in coluna
    confirmacao = cs.continuar_fluxo(db_session, db_session, NUMERO, "Maria Silva")
    assert "confirma" in confirmacao.lower()

    final = cs.continuar_fluxo(db_session, db_session, NUMERO, "SIM")
    assert "exclu" in final.lower()
    assert db_session.execute(text("SELECT COUNT(*) FROM alunos")).scalar() == 0


def test_exclusao_negada_nao_remove(db_session, rota_restrita):
    sessao = cs.obter_sessao(db_session, NUMERO)
    sessao.admin_autenticado_ate = _daqui(5)
    db_session.commit()

    cs.iniciar_rota(db_session, db_session, NUMERO, rota_restrita)
    cs.continuar_fluxo(db_session, db_session, NUMERO, "nome")
    cs.continuar_fluxo(db_session, db_session, NUMERO, "Maria Silva")
    resposta = cs.continuar_fluxo(db_session, db_session, NUMERO, "não")

    assert "não excluí" in resposta.lower()
    assert db_session.execute(text("SELECT COUNT(*) FROM alunos")).scalar() == 1


# ---------------------------------------------------------------------- insercao
def test_insercao_coleta_campos_e_marca_obrigatorios(db_session, tabela_alunos):
    rota = RotaIA(nome="Cadastrar aluno", descricao="Cadastra", operacao="inserir", tabela="alunos")
    db_session.add(rota)
    db_session.commit()

    p1 = cs.iniciar_rota(db_session, db_session, NUMERO, rota)
    assert "nome" in p1.lower() and "obrigat" in p1.lower()

    p2 = cs.continuar_fluxo(db_session, db_session, NUMERO, "Ana Lima")
    assert "curso" in p2.lower() and "opcional" in p2.lower()

    final = cs.continuar_fluxo(db_session, db_session, NUMERO, "Design")
    assert "cadastrei" in final.lower()
    total = db_session.execute(text("SELECT COUNT(*) FROM alunos WHERE nome='Ana Lima'")).scalar()
    assert total == 1


def test_insercao_permite_pular_campo_opcional(db_session, tabela_alunos):
    rota = RotaIA(nome="Cadastrar", descricao="Cadastra", operacao="inserir", tabela="alunos")
    db_session.add(rota)
    db_session.commit()

    cs.iniciar_rota(db_session, db_session, NUMERO, rota)
    cs.continuar_fluxo(db_session, db_session, NUMERO, "Bruno Alves")
    final = cs.continuar_fluxo(db_session, db_session, NUMERO, "pular")

    assert "cadastrei" in final.lower()
    curso = db_session.execute(text("SELECT curso FROM alunos WHERE nome='Bruno Alves'")).scalar()
    assert curso is None


def test_insercao_nao_permite_pular_campo_obrigatorio(db_session, tabela_alunos):
    rota = RotaIA(nome="Cadastrar", descricao="Cadastra", operacao="inserir", tabela="alunos")
    db_session.add(rota)
    db_session.commit()

    cs.iniciar_rota(db_session, db_session, NUMERO, rota)
    resposta = cs.continuar_fluxo(db_session, db_session, NUMERO, "pular")

    assert "obrigat" in resposta.lower()
    assert db_session.execute(text("SELECT COUNT(*) FROM alunos")).scalar() == 1


def test_erro_na_insercao_fica_explicado_e_permite_tentar_de_novo(db_session):
    db_session.execute(text(
        "CREATE TABLE inscricoes (id INTEGER PRIMARY KEY, email VARCHAR(100) NOT NULL UNIQUE)"
    ))
    db_session.execute(text("INSERT INTO inscricoes (email) VALUES ('ja@existe.com')"))
    rota = RotaIA(nome="Cadastrar", descricao="Cadastra", operacao="inserir", tabela="inscricoes")
    db_session.add(rota)
    db_session.commit()

    cs.iniciar_rota(db_session, db_session, NUMERO, rota)
    resposta = cs.continuar_fluxo(db_session, db_session, NUMERO, "ja@existe.com")

    assert "não consegui cadastrar" in resposta.lower()
    assert "único" in resposta.lower()
    assert db_session.get(SessaoChat, NUMERO).etapa == cs.AGUARDANDO_REPETIR_INSERCAO
