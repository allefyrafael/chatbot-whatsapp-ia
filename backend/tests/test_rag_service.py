"""TDD do rag_service — montagem do system prompt a partir dos blocos."""

from app.models import RagBloco
from app.services import rag_service


def _add(db, tipo, titulo, conteudo, ordem=0, ativo=True):
    bloco = RagBloco(tipo=tipo, titulo=titulo, conteudo=conteudo, ordem=ordem, ativo=ativo)
    db.add(bloco)
    db.commit()
    return bloco


def test_prompt_vazio_quando_sem_blocos(db_session):
    prompt = rag_service.montar_system_prompt(db_session)
    assert isinstance(prompt, str)
    assert prompt == ""


def test_prompt_agrupa_por_tipo_e_ordem(db_session):
    _add(db_session, "fazer", "Saudação", "Cumprimente o cliente", ordem=1)
    _add(db_session, "nao_fazer", "Preços", "Não invente preços", ordem=1)
    _add(db_session, "fazer", "Idioma", "Responda em português", ordem=0)

    prompt = rag_service.montar_system_prompt(db_session)

    # Ambos os grupos aparecem, com os títulos dos blocos.
    assert "Responda em português" in prompt
    assert "Cumprimente o cliente" in prompt
    assert "Não invente preços" in prompt
    # "Idioma" (ordem 0) vem antes de "Saudação" (ordem 1) dentro de "fazer".
    assert prompt.index("Responda em português") < prompt.index("Cumprimente o cliente")
    # A seção "fazer" vem antes da seção "nao_fazer".
    assert prompt.index("Cumprimente o cliente") < prompt.index("Não invente preços")


def test_prompt_ignora_blocos_inativos(db_session):
    _add(db_session, "fazer", "Ativo", "Bloco ativo", ativo=True)
    _add(db_session, "fazer", "Inativo", "Bloco inativo", ativo=False)

    prompt = rag_service.montar_system_prompt(db_session)

    assert "Bloco ativo" in prompt
    assert "Bloco inativo" not in prompt
