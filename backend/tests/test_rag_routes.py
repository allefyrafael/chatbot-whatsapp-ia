"""TDD das rotas do painel de RAG (CRUD de blocos)."""

from app.models import RagBloco


def test_pagina_rag_exige_admin(client):
    resp = client.get("/painel/rag", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_ve_pagina_rag(admin_client):
    resp = admin_client.get("/painel/rag")
    assert resp.status_code == 200


def test_criar_bloco(admin_client, db_session):
    resp = admin_client.post(
        "/painel/rag/novo",
        data={"tipo": "fazer", "titulo": "Saudação", "conteudo": "Cumprimente"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    blocos = db_session.query(RagBloco).all()
    assert len(blocos) == 1
    assert blocos[0].titulo == "Saudação"
    assert blocos[0].tipo == "fazer"
    assert blocos[0].ativo is True


def test_criar_bloco_com_tipo_invalido_falha(admin_client, db_session):
    resp = admin_client.post(
        "/painel/rag/novo",
        data={"tipo": "qualquer", "titulo": "X", "conteudo": "Y"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert db_session.query(RagBloco).count() == 0


def test_excluir_bloco(admin_client, db_session):
    bloco = RagBloco(tipo="fazer", titulo="Del", conteudo="conteudo")
    db_session.add(bloco)
    db_session.commit()

    resp = admin_client.post(f"/painel/rag/{bloco.id}/excluir", follow_redirects=False)
    assert resp.status_code == 303
    assert db_session.query(RagBloco).count() == 0


def test_preview_mostra_prompt_montado(admin_client, db_session):
    db_session.add(RagBloco(tipo="fazer", titulo="Idioma", conteudo="Responda em português"))
    db_session.commit()

    resp = admin_client.get("/painel/rag/preview")
    assert resp.status_code == 200
    assert "Responda em português" in resp.text
