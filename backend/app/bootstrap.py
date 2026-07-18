"""Preparação do banco no arranque da aplicação.

Objetivo: permitir subir tudo com um único comando, sem passos manuais de banco.
O SQLAlchemy `create_all` cria as *tabelas*, mas não cria o *database* em si — se o
schema (ex.: `chatbot`) ainda não existe, a conexão falha. Este módulo conecta ao
servidor MySQL sem selecionar um database, executa `CREATE DATABASE IF NOT EXISTS` e
depois deixa o fluxo normal (`create_all`) criar as tabelas.

Chamado uma vez no `lifespan` de `app.main`, antes de `Base.metadata.create_all`.
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url

from app.config import settings

# Colunas que podem faltar em bancos criados antes de uma feature nova.
# Como o projeto é educacional e não usa Alembic, garantimos essas colunas de forma
# idempotente no arranque (checando o schema atual antes de qualquer ALTER).
COLUNAS_ESPERADAS: dict[str, dict[str, str]] = {
    "configuracoes": {
        "groq_api_key": "VARCHAR(255) NULL",
        "pairing_code": "VARCHAR(16) NULL",
        "pairing_expira_em": "DATETIME NULL",
    },
    "itens": {
        "preco": "DECIMAL(10,2) NULL",
    },
}


def criar_database_se_nao_existe() -> None:
    """Cria o database indicado na DATABASE_URL caso ainda não exista.

    O nome do database vem da própria configuração da aplicação (.env), nunca de
    entrada de usuário, então a interpolação no SQL é segura (identificadores MySQL
    não podem ser parametrizados como valores).
    """
    url = make_url(settings.database_url)
    nome_database = url.database
    if not nome_database:
        return

    # Engine apontando para o servidor, mas sem selecionar um database.
    # (set(database=None) é ignorado pelo SQLAlchemy; usa-se string vazia para limpar.)
    # Reusa os mesmos connect_args (ex.: TLS do RDS) do engine principal.
    from app.database import montar_connect_args

    engine_servidor = create_engine(url.set(database=""), connect_args=montar_connect_args())
    try:
        with engine_servidor.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{nome_database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    except Exception:
        # Cenário comum: o MySQL do Docker já cria o database via MYSQL_DATABASE e o
        # usuário da aplicação não tem privilégio global de CREATE DATABASE. Se o banco
        # já existe, seguimos; se realmente não existe, o create_all falha logo adiante
        # com um erro claro de conexão.
        pass
    finally:
        engine_servidor.dispose()


def garantir_colunas(engine: Engine) -> None:
    """Adiciona colunas faltantes em tabelas já existentes (idempotente).

    `create_all` só cria tabelas novas; não altera as que já existem. Para bancos criados
    antes de uma coluna nova, aplicamos `ALTER TABLE ADD COLUMN` apenas para o que falta.
    Só roda para tabelas que já existem (as novas são criadas inteiras por `create_all`).
    """
    inspetor = inspect(engine)
    tabelas_existentes = set(inspetor.get_table_names())

    with engine.begin() as conn:
        for tabela, colunas in COLUNAS_ESPERADAS.items():
            if tabela not in tabelas_existentes:
                continue
            presentes = {c["name"] for c in inspetor.get_columns(tabela)}
            for coluna, definicao in colunas.items():
                if coluna not in presentes:
                    conn.execute(text(f"ALTER TABLE `{tabela}` ADD COLUMN `{coluna}` {definicao}"))
