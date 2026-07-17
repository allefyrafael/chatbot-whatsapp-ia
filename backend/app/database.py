"""Camada de acesso ao banco (SQLAlchemy).

Expõe o `engine`, a fábrica de sessões `SessionLocal`, a `Base` declarativa (herdada
por todos os models) e a dependency `get_db()`, que entrega uma sessão por requisição
e a fecha ao final. A criação do database/tabelas é feita no arranque (ver
`app.bootstrap` e o `lifespan` em `app.main`).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def montar_connect_args() -> dict:
    """Argumentos extras de conexão do driver. Ativa TLS quando há um CA (ex.: AWS RDS)."""
    if settings.db_ssl_ca:
        return {"ssl": {"ca": settings.db_ssl_ca}}
    return {}


CONNECT_ARGS = montar_connect_args()

engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=CONNECT_ARGS)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
