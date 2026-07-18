"""Modelos SQLAlchemy — o mapa das tabelas do domínio.

Todas as tabelas da especificação já são declaradas aqui, mesmo as usadas só em fases
futuras (clientes, pedidos, itens_pedido, pagamentos, tabelas/colunas dinâmicas), para
evitar migração de schema no meio do projeto. Em uso na fase 1: `Configuracao`,
`Usuario` e `Item`.
"""

import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Boolean, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Configuracao(Base):
    """Singleton (linha única, id sempre 1) com os dados da empresa deste deploy."""

    __tablename__ = "configuracoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome_empresa: Mapped[str] = mapped_column(String(255))
    numero_whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    instance_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Estado da conexão do WhatsApp: 'desconectado' | 'aguardando_pareamento' | 'conectado'.
    status_conexao: Mapped[str] = mapped_column(String(30), default="desconectado")
    # Chave da API do Groq, cadastrada pelo admin na tela de onboarding do painel.
    groq_api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Código de pareamento atual do WhatsApp e quando ele expira (fluxo de conexão).
    pairing_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pairing_expira_em: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(String(30), default="admin")


class Item(Base):
    __tablename__ = "itens"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(255))
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Preço opcional: itens "sob consulta" ficam com preco = NULL.
    preco: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero_whatsapp: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    status: Mapped[str] = mapped_column(String(30), default="aguardando_pagamento")
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    itens_pedido: Mapped[list["ItemPedido"]] = relationship(back_populates="pedido")


class ItemPedido(Base):
    __tablename__ = "itens_pedido"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("itens.id"))
    quantidade: Mapped[int]
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    pedido: Mapped["Pedido"] = relationship(back_populates="itens_pedido")


class Pagamento(Base):
    __tablename__ = "pagamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"))
    provedor: Mapped[str | None] = mapped_column(String(50), nullable=True)
    qr_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pendente")


class TabelaDinamica(Base):
    __tablename__ = "tabelas_dinamicas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome_tabela: Mapped[str] = mapped_column(String(64), unique=True)
    nome_exibicao: Mapped[str] = mapped_column(String(255))

    colunas: Mapped[list["ColunaDinamica"]] = relationship(back_populates="tabela")


class ColunaDinamica(Base):
    __tablename__ = "colunas_dinamicas"

    id: Mapped[int] = mapped_column(primary_key=True)
    tabela_id: Mapped[int] = mapped_column(ForeignKey("tabelas_dinamicas.id"))
    nome: Mapped[str] = mapped_column(String(64))
    tipo: Mapped[str] = mapped_column(String(30))
    obrigatorio: Mapped[bool] = mapped_column(Boolean, default=False)

    tabela: Mapped["TabelaDinamica"] = relationship(back_populates="colunas")


class RagBloco(Base):
    """Bloco de instrução do RAG por prompt.

    Cada bloco é do tipo 'fazer' (o que o bot DEVE fazer) ou 'nao_fazer' (o que NÃO deve).
    O `rag_service` junta os blocos ativos, por tipo e ordem, para montar o system prompt
    enviado ao Groq (fase 5).
    """

    __tablename__ = "rag_blocos"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))  # 'fazer' | 'nao_fazer'
    titulo: Mapped[str] = mapped_column(String(255))
    conteudo: Mapped[str] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Mensagem(Base):
    """Histórico mínimo de mensagens do chatbot (recebidas via webhook / enviadas)."""

    __tablename__ = "mensagens"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), index=True)
    direcao: Mapped[str] = mapped_column(String(10))  # 'recebida' | 'enviada'
    conteudo: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class RotaIA(Base):
    """Ação que o chatbot pode executar no banco, montada pelo aluno no painel.

    A `descricao` em linguagem natural é o que a IA usa para decidir quando acionar a
    rota. Os nomes de tabela/coluna aqui são sempre revalidados contra a introspecção
    real do banco antes de qualquer execução (ver `services/schema_service`).
    """

    __tablename__ = "rotas_ia"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    descricao: Mapped[str] = mapped_column(Text)
    operacao: Mapped[str] = mapped_column(String(20))  # 'buscar' | 'inserir' | 'excluir'
    tabela: Mapped[str] = mapped_column(String(64))
    # Coluna usada no WHERE de buscar/excluir (nula em inserir).
    coluna_filtro: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Colunas devolvidas na busca, separadas por vírgula. Vazio = todas as liberadas.
    colunas_retorno: Mapped[str | None] = mapped_column(Text, nullable=True)
    # O que o bot pergunta ao usuário (ex.: "Qual o nome do usuário?").
    pergunta: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Resposta quando a busca não acha nada. Pode usar {valor} para repetir o termo.
    mensagem_vazio: Mapped[str | None] = mapped_column(Text, nullable=True)
    requer_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    campos: Mapped[list["RotaCampo"]] = relationship(
        back_populates="rota", cascade="all, delete-orphan"
    )


class RotaCampo(Base):
    """Campo que o bot coleta numa rota de inserção (define o que é obrigatório)."""

    __tablename__ = "rota_campos"

    id: Mapped[int] = mapped_column(primary_key=True)
    rota_id: Mapped[int] = mapped_column(ForeignKey("rotas_ia.id"))
    coluna: Mapped[str] = mapped_column(String(64))
    rotulo: Mapped[str] = mapped_column(String(255))  # como o bot pergunta por ele
    obrigatorio: Mapped[bool] = mapped_column(Boolean, default=True)
    ordem: Mapped[int] = mapped_column(default=0)

    rota: Mapped["RotaIA"] = relationship(back_populates="campos")


class SessaoChat(Base):
    """Estado da conversa de um número: rota em andamento e sessão de admin.

    Permite o diálogo em etapas (o bot pergunta, espera a resposta e só então executa)
    e guarda até quando aquele número está autenticado como administrador.
    """

    __tablename__ = "sessoes_chat"

    numero: Mapped[str] = mapped_column(String(20), primary_key=True)
    rota_id_pendente: Mapped[int | None] = mapped_column(nullable=True)
    # Onde a conversa parou: 'aguardando_valor', 'aguardando_email', 'aguardando_senha',
    # 'aguardando_campo', 'aguardando_confirmacao'.
    etapa: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Dados já coletados (JSON serializado) enquanto a rota não é executada.
    dados_parciais: Mapped[str | None] = mapped_column(Text, nullable=True)
    # E-mail informado enquanto autentica (antes de validar a senha).
    email_em_validacao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_autenticado_ate: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    atualizado_em: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
