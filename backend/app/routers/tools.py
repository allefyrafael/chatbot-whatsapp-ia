"""Rotas Tools (IA) — a ponte segura entre a IA e o banco de dados.

Estas rotas são a **única** forma pela qual a camada de IA (fase 5) toca o banco.
Toda requisição passa por `app.catalogo`: o nome da tabela e das colunas precisam
estar previamente liberados; caso contrário, a rota responde 400 e nada é executado.
O SQL é montado com SQLAlchemy Core parametrizado (`select`, `insert().values(...)`),
nunca por concatenação de strings — então valores vindos da IA jamais viram SQL.

Nesta fase as rotas não têm autenticação de painel (serão chamadas pelo backend do
bot, não pelo navegador); a proteção efetiva é a restrição por catálogo.
"""

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo import validar_campos_consulta, validar_campos_insercao
from app.database import get_db
from app.schemas import ConsultarIn, ConsultarOut, InserirIn, InserirOut

router = APIRouter(prefix="/tools", tags=["Tools (IA)"])

_RESP_400 = {400: {"description": "Tabela ou coluna fora do catálogo liberado."}}


@router.post(
    "/consultar",
    response_model=ConsultarOut,
    responses=_RESP_400,
    summary="Consultar dados de uma tabela liberada",
)
def consultar_dados(payload: ConsultarIn, db: Session = Depends(get_db)):
    """Executa um SELECT filtrado sobre uma tabela do catálogo.

    - **Recebe**: `tabela`, `filtros` (WHERE por igualdade) e `campos` (colunas a retornar).
    - **Retorna**: `{ "resultados": [ {coluna: valor}, ... ] }`.
    - **Valida**: tabela e todas as colunas de `filtros`/`campos` precisam estar liberadas,
      senão retorna **400** sem tocar no banco.
    """
    entrada = validar_campos_consulta(payload.tabela, payload.filtros, payload.campos)
    tabela_sql = entrada["tabela_sql"]
    colunas = payload.campos or sorted(entrada["colunas_consulta"])

    stmt = select(*[tabela_sql.c[c] for c in colunas])
    for coluna, valor in payload.filtros.items():
        stmt = stmt.where(tabela_sql.c[coluna] == valor)

    linhas = db.execute(stmt).mappings().all()
    return {"resultados": jsonable_encoder([dict(linha) for linha in linhas])}


@router.post(
    "/inserir",
    response_model=InserirOut,
    responses=_RESP_400,
    summary="Inserir um registro numa tabela liberada",
)
def inserir_dados(payload: InserirIn, db: Session = Depends(get_db)):
    """Insere uma linha numa tabela do catálogo e devolve o registro criado.

    - **Recebe**: `tabela` e `dados` (coluna→valor).
    - **Retorna**: `{ "registro": { ...linha inserida com o id... } }`.
    - **Valida**: só colunas liberadas são aceitas e as colunas obrigatórias precisam
      estar presentes; caso contrário retorna **400** sem inserir nada.
    """
    entrada = validar_campos_insercao(payload.tabela, payload.dados)
    tabela_sql = entrada["tabela_sql"]

    resultado = db.execute(tabela_sql.insert().values(**payload.dados))
    db.commit()

    novo_id = resultado.inserted_primary_key[0]
    linha = db.execute(
        select(tabela_sql).where(tabela_sql.c.id == novo_id)
    ).mappings().first()
    return {"registro": jsonable_encoder(dict(linha))}
