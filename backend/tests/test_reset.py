"""TDD do reset do sistema."""

from app.models import Configuracao, Item, RagBloco, Usuario


def test_pagina_config_exige_admin(client):
    resp = client.get("/painel/config", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_ve_pagina_config(admin_client, config_empresa):
    resp = admin_client.get("/painel/config")
    assert resp.status_code == 200


def test_reset_apaga_tudo_e_volta_para_setup(admin_client, config_empresa, admin, db_session):
    db_session.add(Item(nome="X", preco=None))
    db_session.add(RagBloco(tipo="fazer", titulo="T", conteudo="C"))
    db_session.commit()

    resp = admin_client.post("/painel/config/reset", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/setup"

    assert db_session.query(Configuracao).count() == 0
    assert db_session.query(Usuario).count() == 0
    assert db_session.query(Item).count() == 0
    assert db_session.query(RagBloco).count() == 0


def test_reset_exige_admin(client):
    resp = client.post("/painel/config/reset", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
