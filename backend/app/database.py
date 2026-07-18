"""Camada de acesso ao banco (SQLAlchemy), com conexão configurável em tempo de execução.

O app precisa subir **mesmo sem banco configurado** — nesse caso o painel leva o usuário
para a tela `/configurar-banco`, onde ele informa os dados do AWS RDS. Por isso o engine
é criado sob demanda (preguiçoso) e pode ser recarregado depois que o usuário salva a
configuração, sem reiniciar o servidor.
"""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class BancoNaoConfigurado(Exception):
    """Levantada quando algo tenta usar o banco antes de haver uma DATABASE_URL."""


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def banco_configurado() -> bool:
    """Há uma string de conexão preenchida no .env?"""
    return bool((settings.database_url or "").strip())


def montar_connect_args() -> dict:
    """Argumentos extras do driver. Ativa TLS quando há um certificado (ex.: AWS RDS)."""
    if settings.db_ssl_ca:
        return {"ssl": {"ca": settings.db_ssl_ca}}
    return {}


def get_engine() -> Engine:
    """Devolve o engine, criando-o na primeira necessidade."""
    global _engine, _SessionLocal
    if not banco_configurado():
        raise BancoNaoConfigurado("DATABASE_URL não configurada.")
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args=montar_connect_args(),
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def recarregar_engine() -> None:
    """Descarta o engine atual para que o próximo uso leia a configuração nova."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_db():
    """Dependency de rota: entrega uma sessão por requisição e fecha ao final."""
    get_engine()  # garante engine + SessionLocal
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
