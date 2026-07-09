"""TDD do webhook do chatbot (recebe mensagens do sidecar)."""

from app.config import settings
from app.models import Mensagem

SECRET = settings.whatsapp_webhook_secret


def test_rejeita_sem_secret(client):
    resp = client.post("/webhook/whatsapp", json={"numero": "5561999998888", "texto": "oi"})
    assert resp.status_code == 401


def test_rejeita_secret_errado(client):
    resp = client.post(
        "/webhook/whatsapp",
        headers={"X-Webhook-Secret": "errado"},
        json={"numero": "5561999998888", "texto": "oi"},
    )
    assert resp.status_code == 401


def test_registra_recebida_e_responde(client, db_session):
    # Sem chave Groq configurada -> usa o texto de fallback (sem chamar a IA).
    resp = client.post(
        "/webhook/whatsapp",
        headers={"X-Webhook-Secret": SECRET},
        json={"numero": "5561999998888", "texto": "olá bot"},
    )
    assert resp.status_code == 200
    assert resp.json()["resposta"]  # o bot sempre devolve alguma resposta

    recebidas = db_session.query(Mensagem).filter_by(direcao="recebida").all()
    enviadas = db_session.query(Mensagem).filter_by(direcao="enviada").all()
    assert len(recebidas) == 1 and recebidas[0].conteudo == "olá bot"
    assert len(enviadas) == 1  # a resposta do bot também fica registrada


def test_formato_evolution_extrai_e_responde(client, db_session, fake_provider):
    # Payload no formato da Evolution API (messages.upsert).
    payload = {
        "event": "messages.upsert",
        "instance": "chatbot",
        "data": {
            "key": {"remoteJid": "5561999998888@s.whatsapp.net", "fromMe": False},
            "message": {"conversation": "quero um lanche"},
        },
    }
    resp = client.post("/webhook/whatsapp", headers={"X-Webhook-Secret": SECRET}, json=payload)
    assert resp.status_code == 200
    assert resp.json()["resposta"]

    recebidas = db_session.query(Mensagem).filter_by(direcao="recebida").all()
    assert len(recebidas) == 1 and recebidas[0].numero == "5561999998888"
    # A resposta do bot foi enviada de volta pelo provedor (dublê).
    assert fake_provider.enviadas and fake_provider.enviadas[0][0] == "5561999998888"


def test_ignora_mensagem_propria_e_grupo(client, db_session):
    proprio = {"data": {"key": {"remoteJid": "5561999998888@s.whatsapp.net", "fromMe": True},
                        "message": {"conversation": "eco"}}}
    grupo = {"data": {"key": {"remoteJid": "123@g.us", "fromMe": False},
                      "message": {"conversation": "oi grupo"}}}
    for p in (proprio, grupo):
        r = client.post("/webhook/whatsapp", headers={"X-Webhook-Secret": SECRET}, json=p)
        assert r.status_code == 200
        assert r.json().get("ignorado") is True
    assert db_session.query(Mensagem).count() == 0


def test_ignora_payload_sem_texto(client, db_session):
    # Eventos sem texto (status, ack, etc.) não devem virar mensagem nem quebrar.
    resp = client.post(
        "/webhook/whatsapp",
        headers={"X-Webhook-Secret": SECRET},
        json={"numero": "5561999998888"},
    )
    assert resp.status_code == 200
    assert db_session.query(Mensagem).count() == 0
