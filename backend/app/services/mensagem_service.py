"""Regras de mensagens do chatbot — registro e resposta às mensagens recebidas.

`registrar` persiste uma mensagem (recebida/enviada). `tratar_mensagem_recebida` é o
cérebro do bot: registra a mensagem, monta o system prompt (instruções do RAG + catálogo
de produtos) e pede a resposta ao Groq. Falhas nunca quebram o webhook — há sempre um
texto de fallback. Isolar tudo aqui mantém o webhook fino e testável.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import groq_service
from app.models import Item, Mensagem, RotaIA
from app.services import conversa_service, rag_service, rota_service

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


def tratar_mensagem_recebida(
    db: Session, numero: str, texto: str, db_dados: Session | None = None
) -> str:
    """Ponto de entrada do bot: continua um fluxo, aciona uma rota ou conversa.

    `db` é o banco da aplicação; `db_dados` é o banco de trabalho do aluno (onde as rotas
    de IA agem). Quando `db_dados` não é informado, usa-se o próprio `db` — é o modo
    fallback, em que os dois bancos são o mesmo.

    Ordem: (1) se há uma conversa em andamento, ela tem prioridade; (2) senão a IA decide
    se alguma rota cadastrada atende o pedido; (3) senão é papo comum (RAG + catálogo).
    """
    dados = db_dados if db_dados is not None else db

    # SECURITY: se o bot está esperando a senha do admin, ela NÃO vai para o histórico.
    conteudo_para_log = "[senha omitida]" if conversa_service.deve_mascarar(db, numero) else texto
    registrar(db, numero=numero, direcao="recebida", conteudo=conteudo_para_log)

    resposta = _gerar_resposta(db, dados, numero, texto)

    registrar(db, numero=numero, direcao="enviada", conteudo=resposta)
    return resposta


def _gerar_resposta(db: Session, db_dados: Session, numero: str, texto: str) -> str:
    # 1) Conversa em andamento (o bot já havia perguntado algo).
    try:
        em_andamento = conversa_service.continuar_fluxo(db, db_dados, numero, texto)
        if em_andamento is not None:
            return em_andamento
    except Exception:  # noqa: BLE001 - erro numa rota não pode derrubar o atendimento
        return "Tive um problema ao executar essa ação. Pode tentar de novo?"

    chave = groq_service.get_chave_groq(db)
    if not chave:
        return _FALLBACK_SEM_IA

    # 2) A IA decide se alguma rota cadastrada atende o pedido.
    try:
        rotas = rota_service.listar_rotas(db, apenas_ativas=True)
        rota_id, valor = groq_service.escolher_acao(chave, texto, rotas)
        if rota_id:
            rota = db.get(RotaIA, rota_id)
            if rota is not None and rota.ativo:
                return conversa_service.iniciar_rota(db, db_dados, numero, rota, valor)
    except Exception:  # noqa: BLE001 - se o roteamento falhar, cai na conversa normal
        pass

    # 3) Conversa comum (instruções do RAG + catálogo de produtos).
    try:
        resposta = groq_service.responder_com_ia(chave, montar_system_prompt(db), texto)
        return resposta or _FALLBACK_ERRO
    except Exception:  # noqa: BLE001 - nunca deixar o webhook quebrar por causa da IA
        return _FALLBACK_ERRO
