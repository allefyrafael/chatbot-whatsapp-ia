"""Regras de mensagens do chatbot — registro e resposta às mensagens recebidas.

`registrar` persiste uma mensagem (recebida/enviada). `tratar_mensagem_recebida` é o
cérebro do bot: registra a mensagem, monta o system prompt (instruções do RAG + catálogo
de produtos) e pede a resposta ao Groq. Falhas nunca quebram o webhook — há sempre um
texto de fallback. Isolar tudo aqui mantém o webhook fino e testável.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import groq_service
from app.models import Item, Mensagem
from app.services import rag_service

_BASE = (
    "Você é o atendente virtual de uma empresa, conversando com clientes pelo WhatsApp. "
    "Responda em português do Brasil, de forma curta, simpática e objetiva. "
    "Use apenas as informações do catálogo abaixo para falar de produtos e preços; "
    "se não souber, diga que vai verificar com um atendente."
)

_FALLBACK_SEM_IA = (
    "Olá! 👋 Recebemos sua mensagem. Nosso atendimento automático ainda está sendo "
    "configurado, mas já vamos te responder."
)
_FALLBACK_ERRO = (
    "Desculpe, tive um probleminha para responder agora. Pode tentar de novo em instantes?"
)


def registrar(db: Session, numero: str, direcao: str, conteudo: str) -> Mensagem:
    mensagem = Mensagem(numero=numero, direcao=direcao, conteudo=conteudo)
    db.add(mensagem)
    db.commit()
    return mensagem


def montar_system_prompt(db: Session) -> str:
    """Junta a instrução base, os blocos do RAG e o catálogo de produtos."""
    partes = [_BASE]

    rag = rag_service.montar_system_prompt(db)
    if rag:
        partes.append(rag)

    itens = db.query(Item).order_by(Item.nome).all()
    if itens:
        linhas = ["# CATÁLOGO (produtos/serviços disponíveis):"]
        for item in itens:
            preco = f"R$ {item.preco:.2f}" if item.preco is not None else "sob consulta"
            desc = f" — {item.descricao}" if item.descricao else ""
            linhas.append(f"- {item.nome}{desc} ({preco})")
        partes.append("\n".join(linhas))

    return "\n\n".join(partes)


def tratar_mensagem_recebida(db: Session, numero: str, texto: str) -> str:
    """Registra a mensagem recebida, gera a resposta do bot e a registra também."""
    registrar(db, numero=numero, direcao="recebida", conteudo=texto)

    chave = groq_service.get_chave_groq(db)
    if not chave:
        resposta = _FALLBACK_SEM_IA
    else:
        try:
            system_prompt = montar_system_prompt(db)
            resposta = groq_service.responder_com_ia(chave, system_prompt, texto)
            if not resposta:
                resposta = _FALLBACK_ERRO
        except Exception:  # noqa: BLE001 - nunca deixar o webhook quebrar por causa da IA
            resposta = _FALLBACK_ERRO

    registrar(db, numero=numero, direcao="enviada", conteudo=resposta)
    return resposta
