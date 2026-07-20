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

    return _prosseguir(db, db_dados, sessao, rota, valor)


def _prosseguir(
    db: Session, db_dados: Session, sessao: SessaoChat, rota: RotaIA, valor: str | None
) -> str:
    """Executa a rota ou pergunta o que falta."""
    if rota.operacao == "inserir":
        return _proximo_campo(db, db_dados, sessao, rota)

    # Rota que devolve a tabela inteira não tem o que perguntar.
    if rota.operacao == "buscar" and rota.modo_busca == "todos":
        return _listar_tudo(db, db_dados, sessao, rota)

    if valor and rota.operacao == "buscar" and _valor_e_generico(valor, rota):
        # A IA costuma preencher o "valor" com o objeto da frase ("quero ver as
        # categorias" -> "categorias"). Isso pulava a pergunta e filtrava por um termo
        # que não existe em nenhum registro. Nesse caso tratamos como se nada tivesse
        # sido informado, e perguntamos.
        valor = None

    if not valor:
        sessao.etapa = AGUARDANDO_VALOR
        db.commit()
        return _pergunta_de(rota)

    if rota.operacao == "excluir":
        dados = _dados(sessao)
        dados["__valor__"] = valor
        _salvar_dados(db, sessao, dados)
        sessao.etapa = AGUARDANDO_CONFIRMACAO
        db.commit()
        return f'Confirma excluir "{valor}"? Responda *SIM* para confirmar ou *cancelar*.'

    return _executar_busca(db, db_dados, sessao, rota, valor)


# Respostas que significam "não quero filtrar, me traga tudo".
_PEDIDOS_DE_TUDO = {
    "todas", "todos", "tudo", "todas elas", "todos eles",
    "qualquer", "qualquer uma", "geral", "listar", "listar tudo", "all",
}


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


def _listar_tudo(
    db: Session, db_dados: Session, sessao: SessaoChat, rota: RotaIA
) -> str:
    linhas = rota_service.listar_todos(db_dados, rota)
    limpar_fluxo(db, sessao)
    if not linhas:
        return rota.mensagem_vazio or "Essa tabela ainda não tem registros."
    return rota_service.formatar_resultados(linhas)


def _executar_busca(
    db: Session, db_dados: Session, sessao: SessaoChat, rota: RotaIA, valor: str
) -> str:
    # Busca no banco do aluno primeiro; só limpa o estado se ela funcionou.
    linhas = rota_service.executar_busca(db_dados, rota, valor)
    limpar_fluxo(db, sessao)
    if not linhas:
        modelo = rota.mensagem_vazio or "Não encontrei {valor}."
        return modelo.replace("{valor}", valor)
    return rota_service.formatar_resultados(linhas)


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
    rota_service.executar_insercao(db_dados, rota, valores)
    limpar_fluxo(db, sessao)
    resumo = ", ".join(f"{c}: {v}" for c, v in valores.items())
    return f"Pronto! Cadastrei com sucesso.\n{resumo}"


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
        return f"Autenticado, {usuario.nome}. " + _prosseguir(
            db, db_dados, sessao, rota, dados.get("__valor__")
        )

    if etapa == AGUARDANDO_VALOR:
        # "todas" só vale onde a rota foi configurada para aceitar; nas demais o texto
        # segue como termo de busca normal.
        if rota.modo_busca == "perguntar_ou_todos" and _quer_tudo(resposta_limpa):
            return _listar_tudo(db, db_dados, sessao, rota)
        return _prosseguir(db, db_dados, sessao, rota, resposta_limpa)

    if etapa == AGUARDANDO_CAMPO:
        dados = _dados(sessao)
        coluna = dados.pop("__campo__", None)
        if coluna:
            if resposta_limpa.lower() not in _PULAR:
                dados[coluna] = resposta_limpa
            else:
                dados[coluna] = None
        _salvar_dados(db, sessao, dados)
        return _proximo_campo(db, db_dados, sessao, rota)

    if etapa == AGUARDANDO_CONFIRMACAO:
        if resposta_limpa.lower() not in _CONFIRMAR:
            limpar_fluxo(db, sessao)
            return "Ok, não excluí nada."
        valor = _dados(sessao).get("__valor__", "")
        # Exclui no banco do aluno primeiro; se falhar, o fluxo permanece.
        removidos = rota_service.executar_exclusao(db_dados, rota, valor)
        limpar_fluxo(db, sessao)
        if removidos:
            return f'Pronto, excluí "{valor}".'
        return f'Não encontrei "{valor}" para excluir.'

    limpar_fluxo(db, sessao)
    return None
