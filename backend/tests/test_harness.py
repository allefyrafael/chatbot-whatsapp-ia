"""Testes de fumaça do próprio harness (fixtures de conftest funcionam?)."""


def test_rota_painel_exige_admin(client):
    # Sem cookie de admin, o painel redireciona para /login (sem seguir o redirect).
    resp = client.get("/painel/itens", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_client_acessa_painel(admin_client):
    resp = admin_client.get("/painel/itens")
    assert resp.status_code == 200


def test_tools_consultar_rejeita_tabela_fora_do_catalogo(client):
    resp = client.post("/tools/consultar", json={"tabela": "usuarios", "filtros": {}})
    assert resp.status_code == 400
