"""Rotas de IA — cadastro e execução segura das ações no banco do aluno.

Como o aluno monta as rotas pelo painel (sem escrever SQL), é aqui que a query é
construída. Duas regras que valem para tudo neste módulo:

1. **Nomes** de tabela/coluna nunca vão direto para o SQL: passam pelo `schema_service`,
   que confirma existência e permissão contra o banco real.
2. **Valores** nunca são concatenados: vão como bind parameters. Assim, o que o usuário
   digita no WhatsApp jamais é interpretado como comando.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import RotaIA
from app.services import schema_service

# Limite de linhas devolvidas numa busca (a resposta vai para uma mensagem de WhatsApp).
LIMITE_RESULTADOS = 10


def listar_rotas(db: Session, apenas_ativas: bool = False) -> list[RotaIA]:
    consulta = db.query(RotaIA)
    if apenas_ativas:
        consulta = consulta.filter(RotaIA.ativo.is_(True))
    return consulta.order_by(RotaIA.nome).all()


def _colunas_retorno(db: Session, rota: RotaIA) -> list[str]:
    """Colunas a devolver na busca (as configuradas ou todas as da tabela)."""
    if rota.colunas_retorno:
        pedidas = [c.strip() for c in rota.colunas_retorno.split(",") if c.strip()]
        return schema_service.validar_colunas(db, rota.tabela, pedidas)
    return [c["nome"] for c in schema_service.listar_colunas(db, rota.tabela)]


def executar_busca(db: Session, rota: RotaIA, valor: str) -> list[dict]:
    """SELECT parametrizado, filtrando pela coluna configurada (busca parcial)."""
    tabela = schema_service.validar_tabela(db, rota.tabela)
    coluna = schema_service.validar_colunas(db, tabela, [rota.coluna_filtro or ""])[0]
    colunas = _colunas_retorno(db, rota)

    lista_colunas = ", ".join(f"`{c}`" for c in colunas)
    sql = text(
        f"SELECT {lista_colunas} FROM `{tabela}` WHERE `{coluna}` LIKE :valor LIMIT {LIMITE_RESULTADOS}"
    )
    linhas = db.execute(sql, {"valor": f"%{valor}%"}).mappings().all()
    return [dict(linha) for linha in linhas]


def executar_insercao(db: Session, rota: RotaIA, dados: dict) -> None:
    """INSERT parametrizado com as colunas informadas (todas validadas)."""
    tabela = schema_service.validar_tabela(db, rota.tabela)
    colunas = schema_service.validar_colunas(db, tabela, list(dados.keys()))

    lista_colunas = ", ".join(f"`{c}`" for c in colunas)
    marcadores = ", ".join(f":{c}" for c in colunas)
    sql = text(f"INSERT INTO `{tabela}` ({lista_colunas}) VALUES ({marcadores})")
    db.execute(sql, dados)
    db.commit()


def executar_exclusao(db: Session, rota: RotaIA, valor: str) -> int:
    """DELETE parametrizado pela coluna de filtro. Devolve quantas linhas saíram."""
    tabela = schema_service.validar_tabela(db, rota.tabela)
    coluna = schema_service.validar_colunas(db, tabela, [rota.coluna_filtro or ""])[0]

    sql = text(f"DELETE FROM `{tabela}` WHERE `{coluna}` = :valor")
    resultado = db.execute(sql, {"valor": valor})
    db.commit()
    return resultado.rowcount or 0


def campos_para_inserir(db: Session, rota: RotaIA) -> list[dict]:
    """Campos que o bot deve coletar numa inserção.

    Usa os campos configurados pelo aluno; se ele não configurou nenhum, cai para as
    colunas reais da tabela (marcando as obrigatórias e ignorando as geradas, como o id).
    """
    if rota.campos:
        return [
            {"coluna": c.coluna, "rotulo": c.rotulo, "obrigatorio": c.obrigatorio}
            for c in sorted(rota.campos, key=lambda c: (c.ordem, c.id))
        ]
    return [
        {"coluna": c["nome"], "rotulo": c["nome"], "obrigatorio": c["obrigatoria"]}
        for c in schema_service.listar_colunas(db, rota.tabela)
        if not c["gerada"]
    ]


def formatar_resultados(linhas: list[dict]) -> str:
    """Transforma as linhas encontradas num texto amigável para o WhatsApp."""
    partes = []
    for i, linha in enumerate(linhas, start=1):
        campos = [f"{chave}: {valor}" for chave, valor in linha.items() if valor is not None]
        partes.append(f"{i}. " + " | ".join(campos))
    return "\n".join(partes)
