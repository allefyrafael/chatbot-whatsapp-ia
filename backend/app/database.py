"""Camada de acesso ao banco (SQLAlchemy).

Expõe o `engine`, a fábrica de sessões `SessionLocal`, a `Base` declarativa (herdada
por todos os models) e a dependency `get_db()`, que entrega uma sessão por requisição
e a fecha ao final. A criação do database/tabelas é feita no arranque (ver
`app.bootstrap` e o `lifespan` em `app.main`).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
