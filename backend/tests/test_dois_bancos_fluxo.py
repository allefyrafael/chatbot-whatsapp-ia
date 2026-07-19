"""Etapa 4 — o fluxo conversacional com duas conexões.

Como aplicação e banco de trabalho são bancos distintos, não existe transação comum.
A regra adotada é: **executa no banco do aluno primeiro, limpa o estado depois**. Assim,
se a operação falhar, o usuário continua no mesmo ponto da conversa e pode tentar de novo
(em vez de perder o que já respondeu).
"""

import pytest
from sqlalchemy import text

from app.models import RotaIA, SessaoChat
from app.services import conversa_service as cs

NUMERO = "5561999998888"


@pytest.fixture
def rota_busca(db_session):
    db_session.execute(text("CREATE TABLE alunos (id INTEGER PRIMARY KEY, nome VARCHAR(100))"))
    db_session.execute(text("INSERT INTO alunos (nome) VALUES ('Maria Silva')"))
    rota = RotaIA(
        nome="Buscar aluno", descricao="Busca aluno pelo nome", operacao="buscar",
        tabela="alunos", coluna_filtro="nome", pergunta="Qual o nome do aluno?",
    )
    db_session.add(rota)
    db_session.commit()
    return rota


def test_falha_no_banco_do_aluno_preserva_o_fluxo(db_session, rota_busca, monkeypatch):
    """Se o banco de trabalho cair no meio, o estado da conversa continua de pé."""
    cs.iniciar_rota(db_session, db_session, NUMERO, rota_busca)  # bot pergunta o nome
    assert db_session.get(SessaoChat, NUMERO).etapa == cs.AGUARDANDO_VALOR

    def banco_fora_do_ar(*a, **k):
        raise RuntimeError("banco de trabalho indisponível")

    monkeypatch.setattr(cs.rota_service, "executar_busca", banco_fora_do_ar)

    with pytest.raises(RuntimeError):
        cs.continuar_fluxo(db_session, db_session, NUMERO, "Maria")

    # O fluxo NÃO foi limpo: o usuário pode responder de novo sem recomeçar.
    sessao = db_session.get(SessaoChat, NUMERO)
    assert sessao.etapa == cs.AGUARDANDO_VALOR
    assert sessao.rota_id_pendente == rota_busca.id


def test_sucesso_limpa_o_fluxo(db_session, rota_busca):
    """No caminho feliz, o estado é encerrado após a execução."""
    cs.iniciar_rota(db_session, db_session, NUMERO, rota_busca)
    resposta = cs.continuar_fluxo(db_session, db_session, NUMERO, "Maria")

    assert "Maria Silva" in resposta
    assert db_session.get(SessaoChat, NUMERO).etapa is None


def test_reset_nunca_apaga_os_dados_do_aluno(db_session, rota_busca):
    """O 'Apagar tudo' zera o chatbot, mas as tabelas do aluno continuam intactas."""
    from app.services import reset_service

    reset_service.resetar_tudo(db_session)

    # A tabela do aluno e suas linhas permanecem.
    total = db_session.execute(text("SELECT COUNT(*) FROM alunos")).scalar()
    assert total == 1


def test_webhook_falhando_no_banco_do_aluno_responde_amigavel(db_session, rota_busca, monkeypatch):
    """O erro vira mensagem amigável em vez de derrubar o atendimento."""
    from app.models import Configuracao
    from app.services import mensagem_service

    db_session.add(Configuracao(id=1, nome_empresa="X", groq_api_key="gsk_fake"))
    db_session.commit()

    cs.iniciar_rota(db_session, db_session, NUMERO, rota_busca)
    monkeypatch.setattr(
        cs.rota_service, "executar_busca",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fora do ar")),
    )

    resposta = mensagem_service.tratar_mensagem_recebida(
        db_session, NUMERO, "Maria", db_dados=db_session
    )

    assert "problema" in resposta.lower()
    assert db_session.get(SessaoChat, NUMERO).etapa == cs.AGUARDANDO_VALOR
