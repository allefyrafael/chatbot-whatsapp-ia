"""Validação e leitura da chave da API do Groq.

A chave é cadastrada pelo admin na tela de onboarding do painel e persistida em
configuracoes.groq_api_key. Este módulo isola o SDK do Groq do resto da aplicação —
a fase 5 (roteador de intenção) vai reaproveitar get_chave_groq()/carregar_cliente().
"""

from groq import AuthenticationError, Groq
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Configuracao

CONFIGURACAO_ID = 1


def get_configuracao(db: Session) -> Configuracao | None:
    return db.get(Configuracao, CONFIGURACAO_ID)


def get_chave_groq(db: Session) -> str | None:
    config = get_configuracao(db)
    if config is None:
        return None
    return config.groq_api_key


def validar_chave_groq(chave: str) -> tuple[bool, str]:
    """Confere se a chave é aceita pelo Groq fazendo uma chamada leve (listar modelos).

    Retorna (ok, mensagem). Se a chave for recusada, ok=False com motivo.
    Se houver falha de rede/outro erro, ok=False pedindo para tentar de novo —
    assim nunca salvamos uma chave que não conseguimos confirmar.
    """
    chave = (chave or "").strip()
    if not chave.startswith("gsk_"):
        return False, "A chave do Groq deve começar com 'gsk_'. Confira se copiou a chave inteira."

    try:
        cliente = Groq(api_key=chave)
        cliente.models.list()
        return True, "Chave validada com sucesso."
    except AuthenticationError:
        return False, "Chave recusada pelo Groq. Verifique se ela é válida e não foi revogada."
    except Exception as exc:  # noqa: BLE001 - queremos reportar qualquer falha ao admin
        return False, f"Não foi possível validar a chave agora ({type(exc).__name__}). Tente novamente."


def responder_com_ia(chave: str, system_prompt: str, mensagem_usuario: str) -> str:
    """Gera a resposta do bot para uma mensagem, usando o Groq (chat completion).

    `system_prompt` carrega as instruções (RAG) + o catálogo; `mensagem_usuario` é o texto
    recebido do cliente. Levanta exceção em caso de falha — quem chama trata o fallback.
    """
    cliente = Groq(api_key=chave)
    resposta = cliente.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": mensagem_usuario},
        ],
        temperature=0.4,
        max_tokens=400,
    )
    return (resposta.choices[0].message.content or "").strip()
