"""Catálogo de tabelas liberadas para as rotas /tools/*.

Nesta fase é um dicionário estático cobrindo só as tabelas fixas já expostas à IA
(por enquanto "itens"). A fase 6 (catálogo dinâmico) troca a fonte deste dicionário
por uma consulta a tabelas_dinamicas/colunas_dinamicas via introspecção do banco —
as funções validar_tabela/validar_campos_consulta/validar_campos_insercao abaixo não
devem precisar mudar de assinatura quando isso acontecer.
"""

from fastapi import HTTPException

from app.models import Item

TABELAS_LIBERADAS: dict[str, dict] = {
    "itens": {
        "tabela_sql": Item.__table__,
        "colunas_consulta": {"id", "nome", "descricao", "preco"},
        "colunas_insercao": {"nome", "descricao", "preco"},
        "colunas_insercao_obrigatorias": {"nome"},
    },
}


def validar_tabela(nome_tabela: str) -> dict:
    entrada = TABELAS_LIBERADAS.get(nome_tabela)
    if entrada is None:
        raise HTTPException(
            status_code=400,
            detail=f"Tabela '{nome_tabela}' não está liberada no catálogo.",
        )
    return entrada


def validar_campos_consulta(nome_tabela: str, filtros: dict, campos: list[str] | None) -> dict:
    entrada = validar_tabela(nome_tabela)
    permitidas = entrada["colunas_consulta"]

    invalidos_filtro = set(filtros) - permitidas
    if invalidos_filtro:
        raise HTTPException(
            status_code=400,
            detail=f"Filtro(s) inválido(s) para '{nome_tabela}': {sorted(invalidos_filtro)}",
        )

    if campos is not None:
        invalidos_campo = set(campos) - permitidas
        if invalidos_campo:
            raise HTTPException(
                status_code=400,
                detail=f"Campo(s) inválido(s) para '{nome_tabela}': {sorted(invalidos_campo)}",
            )

    return entrada


def validar_campos_insercao(nome_tabela: str, dados: dict) -> dict:
    entrada = validar_tabela(nome_tabela)
    permitidas = entrada["colunas_insercao"]

    invalidos = set(dados) - permitidas
    if invalidos:
        raise HTTPException(
            status_code=400,
            detail=f"Campo(s) inválido(s) para inserir em '{nome_tabela}': {sorted(invalidos)}",
        )

    faltando = entrada["colunas_insercao_obrigatorias"] - set(dados)
    if faltando:
        raise HTTPException(
            status_code=400,
            detail=f"Campo(s) obrigatório(s) faltando para '{nome_tabela}': {sorted(faltando)}",
        )

    return entrada
