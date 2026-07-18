"""Fixtures compartilhadas dos testes.

Estratégia: banco **SQLite em memória** (rápido, isolado), com as tabelas criadas a
partir dos próprios models. O `get_db` da aplicação é substituído para usar esse banco, e
o provedor de WhatsApp é trocado por um `FakeWhatsAppProvider` controlável. O `lifespan`
(que tocaria o MySQL real) é evitado — instanciamos o `TestClient` sem o context manager.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db

# Os testes usam SQLite em memória (fixture `engine`) e nunca o banco real. Definir a
# DATABASE_URL aqui deixa a suíte independente do .env da máquina e satisfaz o middleware
# que exige banco configurado.
settings.database_url = "sqlite://"
from app.deps import COOKIE_NAME
from app.main import app
from app.models import Configuracao, Usuario
from app.security import criar_token_acesso, hash_senha
from app.whatsapp.factory import provedor_whatsapp
from app.whatsapp.fake import FakeWhatsAppProvider


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def db_session(engine):
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def fake_provider() -> FakeWhatsAppProvider:
    # auto_conectar_apos=0 => conecta já no primeiro status() (determinístico nos testes).
    return FakeWhatsAppProvider(ttl_seconds=120, auto_conectar_apos=0)


@pytest.fixture
def client(db_session, fake_provider):
    """TestClient com get_db e provedor de WhatsApp substituídos pelos dublês de teste."""

    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[provedor_whatsapp] = lambda: fake_provider
    # Sem o context manager de propósito: não dispara o lifespan (que tocaria o MySQL real).
    # As tabelas de teste já são criadas pela fixture `engine` (SQLite em memória).
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.clear()


@pytest.fixture
def config_empresa(db_session) -> Configuracao:
    """Cria a configuração singleton da empresa (necessária para várias rotas)."""
    config = Configuracao(id=1, nome_empresa="Empresa Teste", numero_whatsapp="5561999998888")
    db_session.add(config)
    db_session.commit()
    return config


@pytest.fixture
def admin(db_session) -> Usuario:
    usuario = Usuario(
        nome="Admin Teste",
        email="admin@teste.com",
        senha_hash=hash_senha("senha12345"),
        papel="admin",
    )
    db_session.add(usuario)
    db_session.commit()
    return usuario


@pytest.fixture
def admin_client(client, admin):
    """Cliente já autenticado como admin (cookie JWT setado sem passar pelo /login)."""
    client.cookies.set(COOKIE_NAME, criar_token_acesso(admin.id))
    return client
