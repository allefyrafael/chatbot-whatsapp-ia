"""Camada de acesso aos bancos (SQLAlchemy), configurável em tempo de execução.

São **duas conexões independentes**:

1. **Banco da aplicação** (`DATABASE_URL`) — tabelas internas do chatbot: empresa, admins,
   itens, RAG, mensagens, rotas e sessões. É o mínimo para o sistema subir.
2. **Banco de trabalho do aluno** (`DADOS_DATABASE_URL`) — as tabelas que o aluno cria; é
   onde as rotas de IA leem e gravam. Se estiver vazio, **cai no banco da aplicação**, o
   que preserva o comportamento antigo e não quebra instalações existentes.

Essa separação é a fronteira de segurança do projeto: com bancos distintos, a IA não
alcança fisicamente as tabelas internas (hashes de senha, chave do Groq, histórico).

Os engines são criados sob demanda (preguiçosos) e podem ser recarregados depois que o
usuário salva a configuração pelo painel, sem reiniciar o servidor.
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


# ---------------------------------------------------------------------------
# Banco de TRABALHO do aluno (rotas de IA). Espelha o bloco acima.
# ---------------------------------------------------------------------------

_engine_dados: Engine | None = None
_SessionLocalDados: sessionmaker | None = None


def banco_dados_configurado() -> bool:
    """Existe um banco de trabalho próprio, separado do banco da aplicação?"""
    return bool((settings.dados_database_url or "").strip())


def get_engine_dados() -> Engine:
    """Engine do banco de trabalho.

    Sem configuração própria, devolve o engine da aplicação — assim as rotas de IA
    continuam funcionando exatamente como antes (fallback).
    """
    global _engine_dados, _SessionLocalDados
    if not banco_dados_configurado():
        return get_engine()
    if _engine_dados is None:
        connect_args = {"ssl": {"ca": settings.dados_db_ssl_ca}} if settings.dados_db_ssl_ca else {}
        _engine_dados = create_engine(
            settings.dados_database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        _SessionLocalDados = sessionmaker(autocommit=False, autoflush=False, bind=_engine_dados)
    return _engine_dados


def recarregar_engine_dados() -> None:
    """Descarta o engine de trabalho para que o próximo uso leia a configuração nova."""
    global _engine_dados, _SessionLocalDados
    if _engine_dados is not None:
        _engine_dados.dispose()
    _engine_dados = None
    _SessionLocalDados = None


def get_db_dados():
    """Dependency de rota: sessão do banco de trabalho (ou do da aplicação, no fallback)."""
    get_engine_dados()  # garante engine + SessionLocal corretos
    fabrica = _SessionLocalDados if banco_dados_configurado() else _SessionLocal
    db = fabrica()
    try:
        yield db
    finally:
        db.close()
