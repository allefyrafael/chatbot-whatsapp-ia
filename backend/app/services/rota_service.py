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
    colunas_reais = schema_service.listar_colunas(db_dados, rota.tabela)
    permitidas = {c["nome"] for c in colunas_reais if not c["segredo"]}
    if rota.colunas_retorno:
        pedidas = [c.strip() for c in rota.colunas_retorno.split(",") if c.strip()]
        validadas = schema_service.validar_colunas(db_dados, rota.tabela, pedidas)
        # Rotas antigas podem ter sido salvas antes da classificação de segredo. Nunca
        # deixe uma configuração histórica fazer senha, token ou hash sair no WhatsApp.
        return [coluna for coluna in validadas if coluna in permitidas]
    return [c["nome"] for c in colunas_reais if c["nome"] in permitidas]


def listar_todos(db_dados: Session, rota: RotaIA) -> list[dict]:
    """SELECT sem WHERE, para as rotas que devolvem a tabela inteira.

    Existe porque pedidos do tipo "quero ver as categorias" não têm termo de busca:
    antes eles caíam no filtro e voltavam vazios mesmo com a tabela cheia.
    """
    tabela = schema_service.validar_tabela(db_dados, rota.tabela)
    colunas = _colunas_retorno(db_dados, rota)

    lista_colunas = ", ".join(f"`{c}`" for c in colunas)
    sql = text(f"SELECT {lista_colunas} FROM `{tabela}` LIMIT {LIMITE_RESULTADOS}")
    return [dict(linha) for linha in db_dados.execute(sql).mappings().all()]


def colunas_filtraveis(db_dados: Session, rota: RotaIA) -> list[dict]:
    """Colunas que o usuário do chat pode escolher para filtrar.

    Ficam de fora as chaves (ninguém procura "a categoria 3" por escrito, e oferecer o id
    é justamente o que fazia toda busca voltar vazia) e os **segredos** (senha, hash).
    Dado pessoal continua filtrável: procurar pelo CPF de alguém é uso legítimo — o que
    não pode é o valor ser exibido sem querer, e isso quem decide é a lista de retorno.
    Se sobrar nada, devolvemos tudo em vez de travar.
    """
    colunas = schema_service.listar_colunas(db_dados, rota.tabela)
    uteis = [c for c in colunas if not c["chave"] and not c["segredo"]]
    return uteis or colunas


def colunas_para_excluir(db_dados: Session, rota: RotaIA) -> list[dict]:
    """Colunas que podem identificar o registro a excluir.

    Ao contrário de uma busca por texto, uma chave como ``id`` é útil e segura aqui:
    ela permite que a pessoa escolha exatamente o registro que acabou de ver. Segredos
    continuam fora do menu, pois nem devem ser expostos nem usados no chat.
    """
    return [
        coluna for coluna in schema_service.listar_colunas(db_dados, rota.tabela)
        if not coluna["segredo"]
    ]


def executar_busca_em(
    db_dados: Session, rota: RotaIA, coluna: str, valor: str
) -> list[dict]:
    """SELECT filtrando por uma coluna escolhida na hora, e não pela fixa da rota.

    É o que permite o filtro guiado: uma rota configurada com a coluna errada deixa de
    condenar toda busca ao vazio, porque quem conversa escolhe por onde filtrar.
    O nome da coluna passa pela mesma validação de sempre antes de virar SQL.
    """
    tabela = schema_service.validar_tabela(db_dados, rota.tabela)
    coluna_ok = schema_service.validar_colunas(db_dados, tabela, [coluna])[0]
    colunas = _colunas_retorno(db_dados, rota)

    lista_colunas = ", ".join(f"`{c}`" for c in colunas)
    sql = text(
        f"SELECT {lista_colunas} FROM `{tabela}` WHERE `{coluna_ok}` LIKE :valor "
        f"LIMIT {LIMITE_RESULTADOS}"
    )
    linhas = db_dados.execute(sql, {"valor": f"%{valor}%"}).mappings().all()
    return [dict(linha) for linha in linhas]


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


def executar_busca_exata_em(
    db_dados: Session, rota: RotaIA, coluna: str, valor: str
) -> list[dict]:
    """Mostra os registros que serão afetados antes de uma exclusão.

    A exclusão usa igualdade, não ``LIKE``. A prévia precisa obedecer à mesma regra,
    para que a confirmação nunca descreva um conjunto diferente do que será removido.
    """
    tabela = schema_service.validar_tabela(db_dados, rota.tabela)
    coluna_ok = schema_service.validar_colunas(db_dados, tabela, [coluna])[0]
    colunas = _colunas_retorno(db_dados, rota)
    lista_colunas = ", ".join(f"`{c}`" for c in colunas)
    sql = text(
        f"SELECT {lista_colunas} FROM `{tabela}` WHERE `{coluna_ok}` = :valor "
        f"LIMIT {LIMITE_RESULTADOS}"
    )
    linhas = db_dados.execute(sql, {"valor": valor}).mappings().all()
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


def executar_exclusao(
    db_dados: Session, rota: RotaIA, valor: str, coluna: str | None = None
) -> int:
    """DELETE parametrizado no banco de trabalho. Devolve quantas linhas saíram.

    ``coluna`` é escolhida pela pessoa durante o fluxo de exclusão. O fallback mantém
    compatibilidade com rotas e testes antigos que ainda informam só ``coluna_filtro``.
    """
    tabela = schema_service.validar_tabela(db_dados, rota.tabela)
    coluna = schema_service.validar_colunas(
        db_dados, tabela, [coluna or rota.coluna_filtro or ""]
    )[0]

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
    colunas_reais = schema_service.listar_colunas(db_dados, rota.tabela)
    por_nome = {coluna["nome"]: coluna for coluna in colunas_reais}

    if rota.campos:
        campos = []
        for campo in sorted(rota.campos, key=lambda c: (c.ordem, c.id)):
            coluna = por_nome.get(campo.coluna)
            # Uma rota salva não pode transformar um NOT NULL em opcional. O esquema
            # real do banco é a fonte da verdade, inclusive após uma alteração de schema.
            if coluna and not coluna["gerada"] and not coluna["segredo"]:
                campos.append(
                    {
                        "coluna": campo.coluna,
                        "rotulo": campo.rotulo,
                        "obrigatorio": bool(coluna["obrigatoria"]),
                    }
                )
        return campos
    return [
        {"coluna": c["nome"], "rotulo": c["nome"], "obrigatorio": c["obrigatoria"]}
        for c in colunas_reais
        if not c["gerada"] and not c["segredo"]
    ]


def formatar_resultados_da_rota(
    db_dados: Session, rota: RotaIA, linhas: list[dict]
) -> str:
    """Formata resultados com os tipos reais das colunas da tabela.

    O formatador puro continua simples para testes e outros chamadores; este adaptador
    é o usado no chat, onde os ícones precisam refletir o schema real.
    """
    return formatar_resultados(linhas, schema_service.listar_colunas(db_dados, rota.tabela))


# Ícone por papel da coluna. O WhatsApp não tem tabela nem cor: o emoji é o único
# recurso de hierarquia visual disponível, então cada tipo de dado ganha o seu.
_ICONE_POR_PAPEL = {
    "texto": "📝",
    "numero": "🔢",
    "data": "📅",
    "booleano": "✅",
    "outro": "▪️",
}
_ICONE_CHAVE = "🆔"


def _formatar_valor(valor, papel: str) -> str:
    """Deixa o valor legível para quem lê no celular, não para quem lê SQL."""
    if valor is None or valor == "":
        return "—"
    if papel == "booleano" or (papel == "numero" and isinstance(valor, bool)):
        return "Sim" if valor else "Não"
    texto = str(valor).strip()
    # Descrições longas viram parágrafos ilegíveis numa bolha de conversa.
    return texto if len(texto) <= 160 else texto[:157] + "…"


def formatar_resultados(
    linhas: list[dict],
    colunas: list[dict] | None = None,
    total: int | None = None,
) -> str:
    """Monta a resposta do bot encaixando cada registro num modelo fixo.

    O formato antigo (`1. id: 1 | nome: X | descricao: Y`) virava uma linha só,
    interminável, em que nada se destacava. Aqui cada registro é um bloco, com *todas*
    as colunas em linhas próprias, ícone por tipo e espaço entre registros.

    `colunas` traz a classificação (papel/chave) para escolher o ícone e formatar
    booleano como Sim/Não; sem ela, o texto ainda sai, só que sem esses detalhes.
    """
    if not linhas:
        return ""

    info = {c["nome"]: c for c in (colunas or [])}

    def papel(nome: str) -> str:
        return info.get(nome, {}).get("papel", "outro")

    def e_chave(nome: str) -> bool:
        return bool(info.get(nome, {}).get("chave"))

    blocos = []
    for i, linha in enumerate(linhas, start=1):
        detalhes = []
        for nome, valor in linha.items():
            p = papel(nome)
            icone = _ICONE_CHAVE if e_chave(nome) else _ICONE_POR_PAPEL.get(p, "▪️")
            if p == "booleano":
                icone = "✅" if valor else "⛔"
            detalhes.append(f"{icone} _{nome}:_ {_formatar_valor(valor, p)}")

        blocos.append("\n".join([f"*Registro {i}*", *detalhes]))

    quantos = total if total is not None else len(linhas)
    plural = "registro encontrado" if quantos == 1 else "registros encontrados"
    cabecalho = f"📋 *{quantos} {plural}*"
    rodape = (
        f"\n\n_Mostrando os {len(linhas)} primeiros._"
        if total is not None and total > len(linhas)
        else ""
    )
    return cabecalho + "\n\n" + "\n\n".join(blocos) + rodape
