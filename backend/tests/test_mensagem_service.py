"""TDD do mensagem_service — resposta do bot (com IA mockada) e fallbacks."""

from app.models import Configuracao, Item, Mensagem
from app.services import mensagem_service


def test_sem_chave_groq_usa_fallback(db_session):
    db_session.add(Configuracao(id=1, nome_empresa="X", groq_api_key=None))
    db_session.commit()

    resposta = mensagem_service.tratar_mensagem_recebida(db_session, "5561999998888", "oi")

    assert "configurado" in resposta.lower() or "recebemos" in resposta.lower()
    assert db_session.query(Mensagem).filter_by(direcao="enviada").count() == 1


def test_com_chave_chama_ia_e_registra(db_session, monkeypatch):
    db_session.add(Configuracao(id=1, nome_empresa="X", groq_api_key="gsk_fake"))
    db_session.commit()

    chamado = {}

    def fake_responder(chave, system_prompt, mensagem_usuario):
        chamado["system_prompt"] = system_prompt
        chamado["msg"] = mensagem_usuario
        return "Olá! Como posso ajudar?"

    monkeypatch.setattr(mensagem_service.groq_service, "responder_com_ia", fake_responder)

    resposta = mensagem_service.tratar_mensagem_recebida(db_session, "5561999998888", "quero um lanche")

    assert resposta == "Olá! Como posso ajudar?"
    assert chamado["msg"] == "quero um lanche"
    assert db_session.query(Mensagem).filter_by(direcao="recebida").count() == 1
    assert db_session.query(Mensagem).filter_by(direcao="enviada").count() == 1


def test_erro_da_ia_cai_no_fallback(db_session, monkeypatch):
    db_session.add(Configuracao(id=1, nome_empresa="X", groq_api_key="gsk_fake"))
    db_session.commit()

    def explode(*a, **k):
        raise RuntimeError("Groq fora do ar")

    monkeypatch.setattr(mensagem_service.groq_service, "responder_com_ia", explode)

    resposta = mensagem_service.tratar_mensagem_recebida(db_session, "5561999998888", "oi")

    assert "desculpe" in resposta.lower()


def test_system_prompt_inclui_catalogo(db_session):
    db_session.add(Configuracao(id=1, nome_empresa="X"))
    db_session.add(Item(nome="X-Burguer", descricao="Lanche", preco=None))
    db_session.commit()

    prompt = mensagem_service.montar_system_prompt(db_session)

    assert "CATÁLOGO" in prompt
    assert "X-Burguer" in prompt
    assert "sob consulta" in prompt
