"""Schemas Pydantic — contratos de entrada/saída das rotas JSON.

Usados principalmente pelas rotas **Tools (IA)** (`/tools/*`), que trocam JSON.
As rotas HTML do painel recebem `Form(...)` e devolvem páginas, então não usam
estes schemas. Cada classe abaixo vira um bloco de "Schema" no Swagger, com os
exemplos declarados em `json_schema_extra`.
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ItemOut(BaseModel):
    """Representa um produto/serviço retornado pela API."""

    id: int
    nome: str
    descricao: str | None
    preco: Decimal | None = Field(None, description="Preço em reais; nulo = 'sob consulta'.")

    model_config = {"from_attributes": True}


class ConsultarIn(BaseModel):
    """Corpo de `POST /tools/consultar` — uma leitura filtrada de uma tabela liberada."""

    tabela: str = Field(..., description="Nome da tabela liberada no catálogo (ex.: 'itens').")
    filtros: dict[str, Any] = Field(
        default_factory=dict,
        description="Pares coluna→valor para o WHERE (igualdade). Só colunas liberadas.",
    )
    campos: list[str] | None = Field(
        default=None,
        description="Colunas a retornar. Nulo = todas as colunas liberadas da tabela.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"tabela": "itens", "filtros": {}, "campos": ["id", "nome", "preco"]},
                {"tabela": "itens", "filtros": {"nome": "X-Burguer"}, "campos": None},
            ]
        }
    }


class ConsultarOut(BaseModel):
    """Resposta de `POST /tools/consultar`."""

    resultados: list[dict[str, Any]] = Field(..., description="Linhas encontradas, como objetos.")

    model_config = {
        "json_schema_extra": {
            "examples": [{"resultados": [{"id": 1, "nome": "X-Burguer", "preco": 18.90}]}]
        }
    }


class InserirIn(BaseModel):
    """Corpo de `POST /tools/inserir` — insere uma linha numa tabela liberada."""

    tabela: str = Field(..., description="Nome da tabela liberada no catálogo (ex.: 'itens').")
    dados: dict[str, Any] = Field(
        ...,
        description="Pares coluna→valor a inserir. Só colunas liberadas; obrigatórias devem estar presentes.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"tabela": "itens", "dados": {"nome": "Suco", "descricao": "Laranja", "preco": "8.00"}},
                {"tabela": "itens", "dados": {"nome": "Consultoria"}},
            ]
        }
    }


class InserirOut(BaseModel):
    """Resposta de `POST /tools/inserir` — o registro recém-criado."""

    registro: dict[str, Any] = Field(..., description="A linha inserida, incluindo o id gerado.")

    model_config = {
        "json_schema_extra": {
            "examples": [{"registro": {"id": 4, "nome": "Suco", "descricao": "Laranja", "preco": 8.00}}]
        }
    }
