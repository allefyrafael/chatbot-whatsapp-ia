"""Rotas de IA — cadastro e execução segura das ações no banco de trabalho do aluno.

Como o aluno monta as rotas pelo painel (sem escrever SQL), é aqui que a query é
construída. Três regras que valem para tudo neste módulo:

1. **Nomes** de tabela/coluna nunca vão direto para o SQL: passam pelo `schema_service`,
   que confirma existência e permissão contra o banco real.
2. **Valores** nunca são concatenados: vão como bind parameters. Assim, o que o usuário
   digita no WhatsApp jamais é interpretado como comando.
3. **Duas conexões**: `db` (aplicação) guarda o cadastro das rotas; `db_dados` é o banco
   de trabalho do aluno, onde o SELECT/INSERT/DELETE realmente acontece. O parâmetro
   diz a qual banco a função se refere — não misture.

Detalhe sutil: o objeto `rota` vem da sessão da aplicação, então acessar `rota.campos`
(relacionamento) consulta o banco da aplicação, mesmo dentro de funções que operam no
banco de trabalho. Isso é intencional.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import RotaIA
from app.services import schema_service

# Limite de linhas devolvidas numa busca (a resposta vai para uma mensagem de WhatsApp).
LIMITE_RESULTADOS = 10


def listar_rotas(db: Session, apenas_ativas: bool = False) -> list[RotaIA]:
    """Rotas cadastradas. Lê o banco da **aplicação**."""
    consulta = db.query(RotaIA)
    if apenas_ativas:
        consulta = consulta.filter(RotaIA.ativo.is_(True))
    return consulta.order_by(RotaIA.nome).all()


def _colunas_retorno(db_dados: Session, rota: RotaIA) -> list[str]:
    """Colunas a devolver na busca (as configuradas ou todas as da tabela)."""
    if rota.colunas_retorno:
        pedidas = [c.strip() for c in rota.colunas_retorno.split(",") if c.strip()]
        return schema_service.validar_colunas(db_dados, rota.tabela, pedidas)
    return [c["nome"] for c in schema_service.listar_colunas(db_dados, rota.tabela)]


def executar_busca(db_dados: Session, rota: RotaIA, valor: str) -> list[dict]:
    """SELECT parametrizado no banco de trabalho, filtrando pela coluna configurada."""
    tabela = schema_service.validar_tabela(db_dados, rota.tabela)
    coluna = schema_service.validar_colunas(db_dados, tabela, [rota.coluna_filtro or ""])[0]
    colunas = _colunas_retorno(db_dados, rota)

    lista_colunas = ", ".join(f"`{c}`" for c in colunas)
    sql = text(
        f"SELECT {lista_colunas} FROM `{tabela}` WHERE `{coluna}` LIKE :valor LIMIT {LIMITE_RESULTADOS}"
    )
    linhas = db_dados.execute(sql, {"valor": f"%{valor}%"}).mappings().all()
    return [dict(linha) for linha in linhas]


def executar_insercao(db_dados: Session, rota: RotaIA, dados: dict) -> None:
    """INSERT parametrizado no banco de trabalho (colunas todas validadas)."""
    tabela = schema_service.validar_tabela(db_dados, rota.tabela)
    colunas = schema_service.validar_colunas(db_dados, tabela, list(dados.keys()))

    lista_colunas = ", ".join(f"`{c}`" for c in colunas)
    marcadores = ", ".join(f":{c}" for c in colunas)
    sql = text(f"INSERT INTO `{tabela}` ({lista_colunas}) VALUES ({marcadores})")
    db_dados.execute(sql, dados)
    db_dados.commit()


def executar_exclusao(db_dados: Session, rota: RotaIA, valor: str) -> int:
    """DELETE parametrizado no banco de trabalho. Devolve quantas linhas saíram."""
    tabela = schema_service.validar_tabela(db_dados, rota.tabela)
    coluna = schema_service.validar_colunas(db_dados, tabela, [rota.coluna_filtro or ""])[0]

    sql = text(f"DELETE FROM `{tabela}` WHERE `{coluna}` = :valor")
    resultado = db_dados.execute(sql, {"valor": valor})
    db_dados.commit()
    return resultado.rowcount or 0


def campos_para_inserir(db_dados: Session, rota: RotaIA) -> list[dict]:
    """Campos que o bot deve coletar numa inserção.

    Usa os campos configurados pelo aluno (lidos da **aplicação**, via `rota.campos`); se
    ele não configurou nenhum, cai para as colunas reais da tabela no **banco de
    trabalho** (marcando as obrigatórias e ignorando as geradas, como o id).
    """
    if rota.campos:
        return [
            {"coluna": c.coluna, "rotulo": c.rotulo, "obrigatorio": c.obrigatorio}
            for c in sorted(rota.campos, key=lambda c: (c.ordem, c.id))
        ]
    return [
        {"coluna": c["nome"], "rotulo": c["nome"], "obrigatorio": c["obrigatoria"]}
        for c in schema_service.listar_colunas(db_dados, rota.tabela)
        if not c["gerada"]
    ]


def formatar_resultados(linhas: list[dict]) -> str:
    """Transforma as linhas encontradas num texto amigável para o WhatsApp."""
    partes = []
    for i, linha in enumerate(linhas, start=1):
        campos = [f"{chave}: {valor}" for chave, valor in linha.items() if valor is not None]
        partes.append(f"{i}. " + " | ".join(campos))
    return "\n".join(partes)
