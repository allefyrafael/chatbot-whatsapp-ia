"""Introspecção do banco do aluno — descobre tabelas e colunas reais.

Além de alimentar o construtor de rotas no painel, este módulo é a **fronteira de
segurança** do recurso: nenhum nome de tabela ou coluna chega ao SQL sem ter sido
confirmado aqui. Assim, mesmo que a IA (ou o usuário do chat) invente um nome, ele é
rejeitado antes de qualquer execução.

Tabelas internas da aplicação ficam de fora: guardam segredos (hash de senha, chave do
Groq), estado de autenticação ou o histórico privado de conversas.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# Nomes exclusivos desta aplicação: nunca são tabelas legítimas de um aluno, e guardam
# segredos ou o estado interno do bot. Ficam bloqueados em qualquer banco — inclusive no
# do aluno, porque uma cópia pode ter ido parar lá (foi o que aconteceu quando a
# configuração apontou para a AWS por engano). Ao criar uma tabela interna, inclua-a aqui.
TABELAS_INTERNAS = {
    "configuracoes",      # chave do Groq, código de pareamento
    "sessoes_chat",       # estado de autenticação do chat
    "rotas_ia",           # a própria configuração das rotas
    "rota_campos",
    "mensagens",          # histórico privado de conversas
    "rag_blocos",         # as regras de comportamento do próprio bot
    "tabelas_dinamicas",  # metadados internos do catálogo
    "colunas_dinamicas",
}

# Nome genérico demais para bloquear sempre: quase todo projeto de aluno tem o seu
# `usuarios` (um sistema de denúncias, por exemplo). No banco da aplicação ele guarda
# hashes de senha, então só é bloqueado quando o banco em uso É o da aplicação.
TABELAS_INTERNAS_SO_NA_APLICACAO = {"usuarios"}

TABELAS_BLOQUEADAS = TABELAS_INTERNAS | TABELAS_INTERNAS_SO_NA_APLICACAO


def _engine_de(origem: Engine | Session) -> Engine:
    """Aceita Engine ou Session e devolve sempre o Engine.

    A introspecção só precisa do Engine; aceitar `Session` mantém compatibilidade com os
    chamadores que já têm uma sessão em mãos.
    """
    return origem if isinstance(origem, Engine) else origem.get_bind()


class TabelaNaoPermitida(Exception):
    """Tabela inexistente ou bloqueada para uso pelas rotas de IA."""


class ColunaNaoPermitida(Exception):
    """Coluna inexistente na tabela informada."""


def _colunas_dos_modelos() -> dict[str, set[str]]:
    """Assinatura (nome -> colunas) de cada tabela que ESTA aplicação define."""
    import app.models  # noqa: F401 - registra as tabelas no metadata
    from app.database import Base

    return {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}


def _bloqueadas_para(engine: Engine) -> set[str]:
    """Quais nomes esconder neste engine.

    No banco da **aplicação**, tudo o que é interno — inclusive `usuarios`, que ali guarda
    hashes de senha.

    No banco do **aluno**, o projeto dele aparece inteiro. A única exceção são os nomes que
    carregam segredo (`configuracoes` tem a chave do Groq, `sessoes_chat` tem estado de
    autenticação): versões anteriores gravavam essas tabelas no RDS por engano, e expor uma
    sobra dessas a uma rota de IA seria vazamento. São nomes desta aplicação, não de um
    projeto de aula.
    """
    from app.database import get_engine

    if str(engine.url) == str(get_engine().url):
        return TABELAS_BLOQUEADAS
    return TABELAS_INTERNAS


def listar_tabelas(origem: Engine | Session) -> list[str]:
    """Tabelas do banco do projeto disponíveis para montar rotas."""
    engine = _engine_de(origem)
    inspetor = inspect(engine)
    bloqueadas = _bloqueadas_para(engine)
    return sorted(t for t in inspetor.get_table_names() if t not in bloqueadas)


# ---------------------------------------------------------------- classificação
# Radicais que indicam segredo ou documento pessoal. Sem acento e sem separadores: a
# comparação normaliza o nome da coluna antes, então `senha_hash`, `senhaHash`,
# `SENHA`, `nr_documento` e `numeroCartao` caem todos aqui.
_RADICAIS_SENSIVEIS = (
    "senha", "password", "passwd", "pwd", "hash", "salt",
    "token", "secret", "segredo", "apikey", "chaveapi", "credencial",
    "cpf", "cnpj", "rg", "documento", "passaporte", "identidade",
    "cartao", "card", "cvv", "ccv", "pin", "iban", "agencia", "conta",
    "biometria", "digital",
)
# Tamanhos classicos de hash em coluna de largura fixa (md5, sha1, bcrypt, sha256).
_TAMANHOS_DE_HASH = {32, 40, 60, 64, 128}


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _normalizar_nome(nome: str) -> str:
    """`Senha_Hash` -> `senhahash`, para comparar por radical sem depender do estilo."""
    return re.sub(r"[^a-z0-9]", "", _sem_acento(nome).lower())


def _estrutura(inspetor, tabela: str) -> dict:
    """Chaves e índices declarados na tabela — os sinais que não dependem do nome."""
    def _tentar(fn, padrao):
        try:
            return fn()
        except Exception:  # noqa: BLE001 - bancos variam no que expõem
            return padrao

    pk = set(_tentar(
        lambda: inspetor.get_pk_constraint(tabela).get("constrained_columns") or [], []
    ))
    fks = set()
    for fk in _tentar(lambda: inspetor.get_foreign_keys(tabela), []):
        fks.update(fk.get("constrained_columns") or [])

    unicas = set()
    for idx in _tentar(lambda: inspetor.get_indexes(tabela), []):
        if idx.get("unique"):
            unicas.update(c for c in (idx.get("column_names") or []) if c)
    for uc in _tentar(lambda: inspetor.get_unique_constraints(tabela), []):
        unicas.update(uc.get("column_names") or [])

    return {"pk": pk, "fks": fks, "unicas": unicas}


def _papel(tipo: str) -> str:
    """Família do tipo, para a tela mostrar o ícone certo e sugerir filtros."""
    t = tipo.upper()
    if any(x in t for x in ("CHAR", "TEXT", "STRING", "ENUM")):
        return "texto"
    if any(x in t for x in ("DATE", "TIME")):
        return "data"
    if "BOOL" in t or t.startswith("BIT"):
        return "booleano"
    if any(x in t for x in ("INT", "DEC", "NUMERIC", "FLOAT", "DOUBLE", "REAL")):
        return "numero"
    return "outro"


def _e_chave(nome: str, autoincremento: bool, estrutura: dict) -> bool:
    """Identificador: chave primária, estrangeira, autoincremento ou nome de id.

    A estrutura tem prioridade sobre o nome — é o que funciona em qualquer banco,
    inclusive quando a coluna se chama `codigo` ou `matricula`.
    """
    if nome in estrutura["pk"] or nome in estrutura["fks"] or autoincremento:
        return True
    n = _normalizar_nome(nome)
    return n == "id" or n.startswith("id") and len(n) > 2 or n.endswith("id")


def _largura(tipo: str) -> int | None:
    achado = re.search(r"\((\d+)", tipo)
    return int(achado.group(1)) if achado else None


def _avaliar_sensibilidade(nome: str, tipo: str, estrutura: dict) -> tuple[bool, str]:
    """A coluna deve ficar fora da resposta do bot por padrão? E por quê?

    Não existe sinal infalível para "dado sensível" — o schema não carrega essa
    semântica. Então combinamos pistas independentes de idioma e de banco, e devolvemos
    o motivo para a tela poder justificar a marcação ao aluno, que decide no fim.
    """
    n = _normalizar_nome(nome)

    for radical in _RADICAIS_SENSIVEIS:
        if radical in n:
            return True, f"o nome contém “{radical}”"

    # Largura fixa típica de hash: bcrypt (60), sha256 (64), md5 (32)...
    if _papel(tipo) == "texto":
        largura = _largura(tipo)
        if largura in _TAMANHOS_DE_HASH and "CHAR" in tipo.upper():
            return True, f"texto de {largura} caracteres — tamanho típico de hash"

    # Texto único e obrigatório costuma ser credencial de acesso (login, e-mail, CPF).
    if nome in estrutura["unicas"] and _papel(tipo) == "texto":
        return True, "valor único — costuma identificar uma pessoa"

    return False, ""


def listar_colunas(origem: Engine | Session, tabela: str) -> list[dict]:
    """Colunas da tabela, com o que o construtor precisa saber.

    `obrigatoria` indica que a coluna precisa de valor ao inserir (NOT NULL, sem default
    e sem autoincremento) — é o que permite o bot avisar o que é obrigatório.
    """
    validar_tabela(origem, tabela)
    engine = _engine_de(origem)
    inspetor = inspect(engine)

    estrutura = _estrutura(inspetor, tabela)

    colunas = []
    for col in inspetor.get_columns(tabela):
        nome = col["name"]
        tipo = str(col["type"])
        autoincremento = bool(col.get("autoincrement")) or nome == "id"
        obrigatoria = (
            not col.get("nullable", True)
            and col.get("default") is None
            and not autoincremento
        )
        sensivel, motivo = _avaliar_sensibilidade(nome, tipo, estrutura)
        colunas.append(
            {
                "nome": nome,
                "tipo": tipo,
                "obrigatoria": obrigatoria,
                "gerada": autoincremento,
                "papel": _papel(tipo),
                # `chave` evita sugerir um id como filtro: filtrar id por texto
                # devolve sempre vazio.
                "chave": _e_chave(nome, autoincremento, estrutura),
                "texto": _papel(tipo) == "texto",
                "unica": nome in estrutura["unicas"],
                # `motivo` vai para a tela: o aluno vê POR QUE a coluna foi marcada e
                # decide. A heuristica orienta, quem manda e ele.
                "sensivel": sensivel,
                "motivo_sensivel": motivo,
            }
        )
    return colunas


def validar_tabela(origem: Engine | Session, tabela: str) -> str:
    """Confirma que a tabela existe e não é bloqueada. Devolve o nome validado."""
    nome = (tabela or "").strip()
    if nome not in listar_tabelas(origem):
        raise TabelaNaoPermitida(f"Tabela '{tabela}' não existe ou não é permitida.")
    return nome


def validar_colunas(origem: Engine | Session, tabela: str, colunas: list[str]) -> list[str]:
    """Confirma que todas as colunas existem na tabela. Devolve a lista validada."""
    existentes = {c["nome"] for c in listar_colunas(origem, tabela)}
    invalidas = [c for c in colunas if c not in existentes]
    if invalidas:
        raise ColunaNaoPermitida(f"Coluna(s) inexistente(s) em '{tabela}': {invalidas}")
    return list(colunas)
