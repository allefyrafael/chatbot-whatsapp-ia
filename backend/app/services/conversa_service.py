"""Diálogo em etapas do chatbot — o bot pergunta, espera a resposta e só então executa.

Uma rota de IA raramente é resolvida numa mensagem só: o bot precisa perguntar o que
buscar, coletar campos de um cadastro ou confirmar uma exclusão. Este módulo guarda esse
estado por número (`SessaoChat`) e implementa a máquina de estados:

    (sem fluxo)
        -> iniciar_rota()
             |-- rota restrita? -> pede e-mail -> pede senha -> autentica
             |-- buscar/excluir sem valor? -> faz a pergunta configurada
             |-- inserir? -> coleta campo a campo (avisando o que e obrigatorio)
        -> executa e responde

Segurança: a senha digitada no chat é validada com `app.security.verificar_senha`, nunca
é registrada no histórico (ver `deve_mascarar`) e a sessão de admin expira.

**Duas conexões:** `db` é o banco da aplicação (estado da conversa, rotas, usuários) e
`db_dados` é o banco de trabalho do aluno (onde a ação realmente acontece). Como são
bancos distintos, não há transação comum entre eles — por isso a ordem é sempre
**executar no banco do aluno primeiro e só então limpar o estado da conversa**. Se a
operação falhar, o fluxo continua de pé e o usuário pode tentar de novo.
"""

from __future__ import annotations

import datetime
import json
import re
import unicodedata

from sqlalchemy.orm import Session

from app.models import RotaIA, SessaoChat, Usuario
from app.security import verificar_senha
from app.services import rota_service

# Quanto tempo o número permanece autenticado como admin depois de acertar a senha.
TTL_ADMIN_MINUTOS = 10

AGUARDANDO_EMAIL = "aguardando_email"
AGUARDANDO_SENHA = "aguardando_senha"
AGUARDANDO_VALOR = "aguardando_valor"
AGUARDANDO_CAMPO = "aguardando_campo"
AGUARDANDO_CONFIRMACAO = "aguardando_confirmacao"
# Filtro guiado: o usuário escolhe a coluna e depois o valor. Existe porque uma coluna
# de filtro fixa e mal escolhida (um id, por exemplo) condena toda busca ao vazio.
AGUARDANDO_COLUNA_FILTRO = "aguardando_coluna_filtro"
AGUARDANDO_VALOR_FILTRO = "aguardando_valor_filtro"
AGUARDANDO_COLUNA_EXCLUSAO = "aguardando_coluna_exclusao"
AGUARDANDO_VALOR_EXCLUSAO = "aguardando_valor_exclusao"
AGUARDANDO_REPETIR_INSERCAO = "aguardando_repetir_insercao"

_CANCELAR = {"cancelar", "cancela", "sair", "parar"}
_CONFIRMAR = {"sim", "s", "confirmo", "confirmar", "pode"}
_PULAR = {"pular", "pula", "nao", "não", "-"}


def _agora() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def obter_sessao(db: Session, numero: str) -> SessaoChat:
    sessao = db.get(SessaoChat, numero)
    if sessao is None:
        sessao = SessaoChat(numero=numero)
        db.add(sessao)
        db.commit()
    return sessao


def limpar_fluxo(db: Session, sessao: SessaoChat) -> None:
    """Encerra a conversa em andamento (mantém a autenticação de admin)."""
    sessao.rota_id_pendente = None
    sessao.etapa = None
    sessao.dados_parciais = None
    sessao.email_em_validacao = None
    db.commit()


def admin_autenticado(sessao: SessaoChat) -> bool:
    return bool(sessao.admin_autenticado_ate and sessao.admin_autenticado_ate > _agora())


def deve_mascarar(db: Session, numero: str) -> bool:
    """A próxima mensagem é a senha do admin? (para não gravá-la no histórico)"""
    sessao = db.get(SessaoChat, numero)
    return bool(sessao and sessao.etapa == AGUARDANDO_SENHA)


def _dados(sessao: SessaoChat) -> dict:
    return json.loads(sessao.dados_parciais) if sessao.dados_parciais else {}


def _salvar_dados(db: Session, sessao: SessaoChat, dados: dict) -> None:
    sessao.dados_parciais = json.dumps(dados, ensure_ascii=False)
    db.commit()


# --------------------------------------------------------------------------- iniciar
def iniciar_rota(
    db: Session, db_dados: Session, numero: str, rota: RotaIA, valor: str | None = None
) -> str:
    """Começa uma rota. Pede autenticação antes, se ela for restrita."""
    sessao = obter_sessao(db, numero)
    sessao.rota_id_pendente = rota.id

    if rota.requer_admin and not admin_autenticado(sessao):
        sessao.etapa = AGUARDANDO_EMAIL
        if valor:
            _salvar_dados(db, sessao, {"__valor__": valor})
        db.commit()
        return (
            "Essa ação é restrita a administradores. "
            "Qual o seu *e-mail* de administrador?"
        )

    # Aqui o valor veio da IA (extraído da frase do usuário), não digitado em resposta.
    return _prosseguir(db, db_dados, sessao, rota, valor, valor_veio_da_ia=True)


def _prosseguir(
    db: Session,
    db_dados: Session,
    sessao: SessaoChat,
    rota: RotaIA,
    valor: str | None,
    valor_veio_da_ia: bool = False,
) -> str:
    """Executa a rota ou pergunta o que falta.

    `valor_veio_da_ia` distingue as duas origens do valor, que precisam de tratamento
    oposto: o que a IA extrai da frase inicial pode ser só o assunto e deve ser
    descartado; o que a pessoa digita em resposta à pergunta é sempre a resposta dela e
    **nunca** pode ser descartado — descartar fazia o bot repetir a pergunta para sempre.
    """
    if rota.operacao == "inserir":
        return _proximo_campo(db, db_dados, sessao, rota)

    # Exclusão nunca confia no valor extraído pela IA nem na coluna salva na rota. A
    # pessoa vê os registros, escolhe a coluna e confere o conjunto afetado antes do SIM.
    if rota.operacao == "excluir":
        return _iniciar_exclusao(db, db_dados, sessao, rota)

    # Rota que devolve a tabela inteira não tem o que perguntar.
    if rota.operacao == "buscar" and rota.modo_busca == "todos":
        return _listar_tudo(db, db_dados, sessao, rota)

    if (
        valor_veio_da_ia
        and valor
        and rota.operacao == "buscar"
        and _valor_e_generico(valor, rota)
    ):
        # A IA costuma preencher o "valor" com o objeto da frase ("quero ver as
        # categorias" -> "categorias"). Isso pulava a pergunta e filtrava por um termo
        # que não existe em nenhum registro. Nesse caso perguntamos.
        valor = None

    if not valor:
        sessao.etapa = AGUARDANDO_VALOR
        db.commit()
        return _pergunta_de(rota)

    # "Deixar escolher" nunca usa a coluna fixa da rota: o texto (venha da IA ou da
    # pessoa) e sempre interpretado, para a coluna errada nao condenar a busca.
    if rota.operacao == "buscar" and rota.modo_busca == "perguntar_ou_todos":
        return _interpretar_busca(db, db_dados, sessao, rota, valor)

    return _executar_busca(db, db_dados, sessao, rota, valor)


# Respostas que significam "não quero filtrar, me traga tudo".
_PEDIDOS_DE_TUDO = {
    "todas", "todos", "tudo", "todas elas", "todos eles",
    "qualquer", "qualquer uma", "geral", "listar", "listar tudo", "all",
}


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _normalizar(texto: str) -> str:
    return " ".join((texto or "").strip().lower().split())


def _quer_tudo(texto: str) -> bool:
    return _normalizar(texto) in _PEDIDOS_DE_TUDO


def _valor_e_generico(valor: str, rota: RotaIA) -> bool:
    """O "valor" extraído pela IA é só o assunto da frase, não um termo de busca?

    "quero ver as categorias" faz a IA preencher valor="categorias". Filtrar por isso
    devolve vazio numa tabela cheia — o sintoma que apareceu em produção. Comparamos com
    o nome da tabela e o nome da rota, que é de onde essa confusão sempre vem.
    """
    v = _normalizar(valor)
    if not v or _quer_tudo(v):
        return True
    alvos = {_normalizar(rota.tabela), _normalizar(rota.nome)}
    alvos.update(a.rstrip("s") for a in list(alvos))
    return v in alvos or v.rstrip("s") in alvos


def _pergunta_de(rota: RotaIA) -> str:
    """Pergunta configurada, avisando sobre "todas" quando a rota aceita."""
    base = rota.pergunta or "O que você quer procurar?"
    if rota.modo_busca == "perguntar_ou_todos":
        return f'{base}\n_(responda *todas* para ver a lista completa)_'
    return base


# "filtrar por nome = Corrupção", "coluna nome valor Corrupção", "nome: Corrupção"
_UMA_FRASE = re.compile(
    r"(?:filtrar\s+)?(?:pel[ao]\s+|por\s+)?(?P<coluna>[\w\sà-ú]+?)\s*"
    r"(?:=|:|\bcom\s+(?:o\s+)?valor\b|\bigual\s+a\b|\bcomo\b)\s*"
    r"(?P<valor>.+)$",
    re.IGNORECASE,
)


def _achar_coluna(texto: str, colunas: list[dict]) -> str | None:
    """Casa o que a pessoa escreveu com uma coluna real. Aceita o número da lista.

    Comparação sem acento e sem separadores, porque ninguém digita `data_cadastro` —
    digita "data cadastro" ou "Data de Cadastro".
    """
    alvo = _normalizar(texto)
    if not alvo:
        return None

    if alvo.isdigit():
        indice = int(alvo) - 1
        if 0 <= indice < len(colunas):
            return colunas[indice]["nome"]

    def simplificar(t: str) -> str:
        return re.sub(r"[^a-z0-9]", "", _sem_acento(t).lower())

    simples = simplificar(alvo)
    for coluna in colunas:                       # nome exato
        if simplificar(coluna["nome"]) == simples:
            return coluna["nome"]
    for coluna in colunas:                       # a pessoa citou a coluna na frase
        if simplificar(coluna["nome"]) in simples:
            return coluna["nome"]
    return None


def _menu_de_colunas(colunas: list[dict], introducao: str = "Você pode filtrar por estas colunas:") -> str:
    linhas = "\n".join(
        f"{i}. *{c['nome']}*" for i, c in enumerate(colunas, start=1)
    )
    return (
        introducao + "\n" + linhas +
        "\n\nResponda o *nome* ou o *número* da coluna."
    )


def _pedir_coluna(
    db: Session, sessao: SessaoChat, colunas: list[dict]
) -> str:
    sessao.etapa = AGUARDANDO_COLUNA_FILTRO
    db.commit()
    return _menu_de_colunas(colunas)


def _filtrar_por(
    db: Session, db_dados: Session, sessao: SessaoChat, rota: RotaIA,
    coluna: str, valor: str,
) -> str:
    linhas = rota_service.executar_busca_em(db_dados, rota, coluna, valor)
    limpar_fluxo(db, sessao)
    if not linhas:
        modelo = rota.mensagem_vazio or "Não encontrei nada com {valor} em {coluna}."
        return modelo.replace("{valor}", valor).replace("{coluna}", coluna)
    return rota_service.formatar_resultados_da_rota(db_dados, rota, linhas)


def _interpretar_busca(
    db: Session,
    db_dados: Session,
    sessao: SessaoChat,
    rota: RotaIA,
    texto: str,
    ja_ofereceu_colunas: bool = False,
) -> str:
    """Entende o que a pessoa quer, no modo "Deixar escolher".

    Ponto único de interpretação: seja o texto extraído pela IA da primeira frase ou a
    resposta digitada depois, tudo passa por aqui. Assim a `coluna_filtro` gravada na
    rota nunca é usada às cegas — era o que fazia uma rota mal configurada (filtro num
    id) responder "não encontrei" para qualquer busca.

    Ordem: quer tudo? -> "coluna = valor" numa frase? -> citou uma coluna? -> oferece a
    lista de colunas.
    """
    if _quer_tudo(texto):
        return _listar_tudo(db, db_dados, sessao, rota)

    colunas = rota_service.colunas_filtraveis(db_dados, rota)

    casou = _UMA_FRASE.match(texto)
    if casou:
        coluna = _achar_coluna(casou.group("coluna"), colunas)
        if coluna:
            return _filtrar_por(
                db, db_dados, sessao, rota, coluna, casou.group("valor").strip()
            )

    coluna = _achar_coluna(texto, colunas)
    if coluna:
        _salvar_dados(db, sessao, {**_dados(sessao), "__coluna__": coluna})
        sessao.etapa = AGUARDANDO_VALOR_FILTRO
        db.commit()
        return f"Qual valor você procura em *{coluna}*?"

    # Não é nome de coluna: é um valor. Se a rota tem uma coluna de filtro que serve,
    # usamos ela — quem digita "Assédio" quer o resultado, não um menu. O menu fica
    # para quando a coluna configurada é inútil (um id) ou nem existe.
    if not ja_ofereceu_colunas:
        padrao = next((c["nome"] for c in colunas if c["nome"] == rota.coluna_filtro), None)
        if padrao:
            return _filtrar_por(db, db_dados, sessao, rota, padrao, texto)

    prefixo = "Não reconheci essa coluna.\n\n" if ja_ofereceu_colunas else ""
    return prefixo + _pedir_coluna(db, sessao, colunas)


def _listar_tudo(
    db: Session, db_dados: Session, sessao: SessaoChat, rota: RotaIA
) -> str:
    linhas = rota_service.listar_todos(db_dados, rota)
    limpar_fluxo(db, sessao)
    if not linhas:
        return rota.mensagem_vazio or "Essa tabela ainda não tem registros."
    return rota_service.formatar_resultados_da_rota(db_dados, rota, linhas)


def _executar_busca(
    db: Session, db_dados: Session, sessao: SessaoChat, rota: RotaIA, valor: str
) -> str:
    # Busca no banco do aluno primeiro; só limpa o estado se ela funcionou.
    linhas = rota_service.executar_busca(db_dados, rota, valor)
    limpar_fluxo(db, sessao)
    if not linhas:
        modelo = rota.mensagem_vazio or "Não encontrei {valor}."
        return modelo.replace("{valor}", valor)
    return rota_service.formatar_resultados_da_rota(db_dados, rota, linhas)


# ----------------------------------------------------------------------- exclusão
def _iniciar_exclusao(
    db: Session, db_dados: Session, sessao: SessaoChat, rota: RotaIA
) -> str:
    """Exibe os registros e só então pergunta como a pessoa quer identificá-los."""
    linhas = rota_service.listar_todos(db_dados, rota)
    if not linhas:
        limpar_fluxo(db, sessao)
        return rota.mensagem_vazio or "Não há registros para excluir."

    colunas = rota_service.colunas_para_excluir(db_dados, rota)
    sessao.etapa = AGUARDANDO_COLUNA_EXCLUSAO
    sessao.dados_parciais = None
    db.commit()
    lista = rota_service.formatar_resultados_da_rota(db_dados, rota, linhas)
    menu = _menu_de_colunas(
        colunas,
        "🗑️ *Para excluir, escolha a coluna que identifica o registro:*",
    )
    return f"{lista}\n\n{menu}"


def _preparar_exclusao(
    db: Session,
    db_dados: Session,
    sessao: SessaoChat,
    rota: RotaIA,
    coluna: str,
    valor: str,
) -> str:
    """Mostra a prévia exata da exclusão e guarda a confirmação pendente."""
    linhas = rota_service.executar_busca_exata_em(db_dados, rota, coluna, valor)
    if not linhas:
        sessao.etapa = AGUARDANDO_VALOR_EXCLUSAO
        _salvar_dados(db, sessao, {"__coluna_exclusao__": coluna})
        return (
            f'Não encontrei registro com *{coluna}* igual a "{valor}". '
            "Informe outro valor ou responda *cancelar*."
        )

    _salvar_dados(
        db,
        sessao,
        {"__coluna_exclusao__": coluna, "__valor_exclusao__": valor},
    )
    sessao.etapa = AGUARDANDO_CONFIRMACAO
    db.commit()
    previa = rota_service.formatar_resultados_da_rota(db_dados, rota, linhas)
    quantos = "registro" if len(linhas) == 1 else "registros"
    return (
        f"Encontrei estes {len(linhas)} {quantos} para excluir:\n\n{previa}"
        "\n\n⚠️ *Confirma a exclusão?* Responda *SIM* para confirmar ou *cancelar*."
    )


# ----------------------------------------------------------------------- inserção
def _proximo_campo(db: Session, db_dados: Session, sessao: SessaoChat, rota: RotaIA) -> str:
    """Pergunta o próximo campo pendente do cadastro, ou executa a inserção."""
    campos = rota_service.campos_para_inserir(db_dados, rota)
    dados = _dados(sessao)

    for campo in campos:
        if campo["coluna"] in dados:
            continue
        sessao.etapa = AGUARDANDO_CAMPO
        sessao.dados_parciais = json.dumps({**dados, "__campo__": campo["coluna"]}, ensure_ascii=False)
        db.commit()
        if campo["obrigatorio"]:
            return f'Informe *{campo["rotulo"]}* (obrigatório):'
        return f'Informe *{campo["rotulo"]}* (opcional — responda "pular" para deixar em branco):'

    valores = {c: v for c, v in dados.items() if not c.startswith("__")}
    # Grava no banco do aluno primeiro; se falhar, o fluxo continua para nova tentativa.
    try:
        rota_service.executar_insercao(db_dados, rota, valores)
    except Exception as erro:  # noqa: BLE001 - o banco do aluno pode recusar a inserção
        # Depois de uma falha SQLAlchemy a sessão fica em estado de erro até rollback.
        # O estado da conversa mora no outro banco e continua intacto para permitir retry.
        db_dados.rollback()
        sessao.etapa = AGUARDANDO_REPETIR_INSERCAO
        db.commit()
        return (
            "Não consegui cadastrar este registro. "
            f"*Motivo:* {_explicar_erro_insercao(erro)}\n\n"
            "Responda *tentar novamente* para repetir com estes dados, "
            "*refazer* para informar os campos de novo ou *cancelar*."
        )
    limpar_fluxo(db, sessao)
    resumo = ", ".join(f"{c}: {v}" for c, v in valores.items())
    return f"Pronto! Cadastrei com sucesso.\n{resumo}"


def _explicar_erro_insercao(erro: Exception) -> str:
    """Traduz os erros mais comuns do banco sem despejar SQL no WhatsApp."""
    detalhe = str(getattr(erro, "orig", erro))
    normalizado = detalhe.lower()
    if "not null" in normalizado or "cannot be null" in normalizado:
        return "um campo obrigatório ficou sem valor."
    if "unique" in normalizado or "duplicate" in normalizado:
        return "já existe um registro com um valor que precisa ser único."
    if "foreign key" in normalizado or "constraint failed" in normalizado:
        return "uma referência informada não existe ou não pode ser usada."
    if "too long" in normalizado or "data truncation" in normalizado:
        return "um dos valores é maior do que o permitido para esse campo."
    # A classe mantém a mensagem útil para quem administra sem expor comandos SQL nem
    # detalhes de conexão (host, usuário, senha).
    return f"o banco recusou os dados ({type(erro).__name__})."


# ------------------------------------------------------------------------ continuar
def continuar_fluxo(db: Session, db_dados: Session, numero: str, texto: str) -> str | None:
    """Avança a conversa em andamento. Devolve None se não houver fluxo pendente."""
    sessao = db.get(SessaoChat, numero)
    if sessao is None or not sessao.etapa:
        return None

    resposta_limpa = texto.strip()
    if resposta_limpa.lower() in _CANCELAR:
        limpar_fluxo(db, sessao)
        return "Tudo bem, cancelei. Posso ajudar em algo mais?"

    rota = db.get(RotaIA, sessao.rota_id_pendente) if sessao.rota_id_pendente else None
    if rota is None:
        limpar_fluxo(db, sessao)
        return None

    etapa = sessao.etapa

    if etapa == AGUARDANDO_EMAIL:
        sessao.email_em_validacao = resposta_limpa
        sessao.etapa = AGUARDANDO_SENHA
        db.commit()
        return "Agora informe a sua *senha* de administrador:"

    if etapa == AGUARDANDO_SENHA:
        usuario = (
            db.query(Usuario).filter(Usuario.email == (sessao.email_em_validacao or "")).first()
        )
        if usuario is None or not verificar_senha(resposta_limpa, usuario.senha_hash):
            limpar_fluxo(db, sessao)
            return "E-mail ou senha incorretos. Ação cancelada por segurança."
        sessao.admin_autenticado_ate = _agora() + datetime.timedelta(minutes=TTL_ADMIN_MINUTOS)
        sessao.email_em_validacao = None
        sessao.etapa = None
        db.commit()
        dados = _dados(sessao)
        # `__valor__` foi guardado no início da rota: é o valor da IA, não uma resposta.
        return f"Autenticado, {usuario.nome}. " + _prosseguir(
            db, db_dados, sessao, rota, dados.get("__valor__"), valor_veio_da_ia=True
        )

    if etapa == AGUARDANDO_COLUNA_FILTRO:
        colunas = rota_service.colunas_filtraveis(db_dados, rota)
        if _quer_tudo(resposta_limpa):
            return _listar_tudo(db, db_dados, sessao, rota)
        # Aceita "nome = Corrupção" já nesta etapa, sem obrigar a ida e volta.
        casou = _UMA_FRASE.match(resposta_limpa)
        if casou:
            coluna = _achar_coluna(casou.group("coluna"), colunas)
            if coluna:
                return _filtrar_por(
                    db, db_dados, sessao, rota, coluna, casou.group("valor").strip()
                )
        coluna = _achar_coluna(resposta_limpa, colunas)
        if not coluna:
            return "Não reconheci essa coluna.\n\n" + _menu_de_colunas(colunas)
        _salvar_dados(db, sessao, {**_dados(sessao), "__coluna__": coluna})
        sessao.etapa = AGUARDANDO_VALOR_FILTRO
        db.commit()
        return f"Qual valor você procura em *{coluna}*?"

    if etapa == AGUARDANDO_VALOR_FILTRO:
        coluna = _dados(sessao).get("__coluna__")
        if not coluna:  # estado inconsistente: recomeça o filtro em vez de travar
            return _pedir_coluna(db, sessao, rota_service.colunas_filtraveis(db_dados, rota))
        return _filtrar_por(db, db_dados, sessao, rota, coluna, resposta_limpa)

    if etapa == AGUARDANDO_COLUNA_EXCLUSAO:
        colunas = rota_service.colunas_para_excluir(db_dados, rota)
        # Quem escreve "nome: Maria" não precisa responder duas vezes.
        casou = _UMA_FRASE.match(resposta_limpa)
        if casou:
            coluna = _achar_coluna(casou.group("coluna"), colunas)
            if coluna:
                return _preparar_exclusao(
                    db, db_dados, sessao, rota, coluna, casou.group("valor").strip()
                )
        coluna = _achar_coluna(resposta_limpa, colunas)
        if not coluna:
            return "Não reconheci essa coluna.\n\n" + _menu_de_colunas(
                colunas,
                "🗑️ *Escolha a coluna que identifica o registro:*",
            )
        _salvar_dados(db, sessao, {"__coluna_exclusao__": coluna})
        sessao.etapa = AGUARDANDO_VALOR_EXCLUSAO
        db.commit()
        return f"Qual valor você quer usar em *{coluna}*?"

    if etapa == AGUARDANDO_VALOR_EXCLUSAO:
        coluna = _dados(sessao).get("__coluna_exclusao__")
        if not coluna:
            return _iniciar_exclusao(db, db_dados, sessao, rota)
        return _preparar_exclusao(db, db_dados, sessao, rota, coluna, resposta_limpa)

    if etapa == AGUARDANDO_VALOR:
        if _quer_tudo(resposta_limpa):
            if rota.modo_busca == "perguntar_ou_todos":
                return _listar_tudo(db, db_dados, sessao, rota)
            # Buscar literalmente por "todas" devolveria "não encontrei todas", o que
            # não ajuda ninguém: a pessoa pediu a lista inteira e esta rota não oferece
            # essa opção. Dizemos isso, e seguimos esperando um termo.
            return (
                "Esta busca precisa de um termo específico — não consigo trazer a "
                "lista inteira por aqui.\n" + (rota.pergunta or "O que você procura?")
            )

        if rota.modo_busca == "perguntar_ou_todos":
            return _interpretar_busca(db, db_dados, sessao, rota, resposta_limpa)

        return _prosseguir(db, db_dados, sessao, rota, resposta_limpa)

    if etapa == AGUARDANDO_CAMPO:
        dados = _dados(sessao)
        coluna = dados.pop("__campo__", None)
        if coluna:
            campos = {campo["coluna"]: campo for campo in rota_service.campos_para_inserir(db_dados, rota)}
            campo = campos.get(coluna, {})
            if resposta_limpa.lower() in _PULAR:
                if campo.get("obrigatorio"):
                    dados["__campo__"] = coluna
                    _salvar_dados(db, sessao, dados)
                    return f'*{campo.get("rotulo", coluna)}* é obrigatório e não pode ficar em branco.'
                dados[coluna] = None
            else:
                dados[coluna] = resposta_limpa
        _salvar_dados(db, sessao, dados)
        return _proximo_campo(db, db_dados, sessao, rota)

    if etapa == AGUARDANDO_REPETIR_INSERCAO:
        resposta_normalizada = _normalizar(resposta_limpa)
        if resposta_normalizada in {"refazer", "refaz", "corrigir"}:
            _salvar_dados(db, sessao, {})
            return _proximo_campo(db, db_dados, sessao, rota)
        if resposta_normalizada in {"tentar", "tentar novamente", "sim", "s"}:
            return _proximo_campo(db, db_dados, sessao, rota)
        return "Responda *tentar novamente*, *refazer* ou *cancelar*."

    if etapa == AGUARDANDO_CONFIRMACAO:
        if resposta_limpa.lower() not in _CONFIRMAR:
            limpar_fluxo(db, sessao)
            return "Ok, não excluí nada."
        dados = _dados(sessao)
        valor = dados.get("__valor_exclusao__", dados.get("__valor__", ""))
        coluna = dados.get("__coluna_exclusao__")
        # Exclui no banco do aluno primeiro; se falhar, o fluxo permanece.
        removidos = rota_service.executar_exclusao(db_dados, rota, valor, coluna)
        limpar_fluxo(db, sessao)
        if removidos:
            return f'Pronto, excluí {removidos} registro(s) com *{coluna or rota.coluna_filtro}* igual a "{valor}".'
        return f'Não encontrei "{valor}" para excluir.'

    limpar_fluxo(db, sessao)
    return None
