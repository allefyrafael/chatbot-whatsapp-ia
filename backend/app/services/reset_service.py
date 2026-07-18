"""Reset do sistema — apaga todos os dados para simular o primeiro acesso.

Uso: validar o fluxo de onboarding do zero (setup → login → Groq → WhatsApp → itens).
Operação destrutiva e irreversível; a rota que a chama exige admin e confirmação.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    ColunaDinamica,
    Cliente,
    Configuracao,
    Item,
    ItemPedido,
    Mensagem,
    Pagamento,
    Pedido,
    RagBloco,
    RotaCampo,
    RotaIA,
    SessaoChat,
    TabelaDinamica,
    Usuario,
)

# Ordem segura por chave estrangeira (filhos antes dos pais).
# IMPORTANTE: ao criar uma tabela nova de domínio, acrescente-a aqui — senão o
# "apagar tudo" deixa resíduo e o onboarding não recomeça de verdade.
_MODELOS_EM_ORDEM = [
    ItemPedido,
    Pagamento,
    Pedido,
    Mensagem,
    SessaoChat,
    RotaCampo,
    RotaIA,
    RagBloco,
    ColunaDinamica,
    TabelaDinamica,
    Item,
    Cliente,
    Usuario,
    Configuracao,
]


def resetar_tudo(db: Session) -> None:
    """Remove todas as linhas das tabelas de domínio (deixa o banco como recém-criado)."""
    for modelo in _MODELOS_EM_ORDEM:
        db.query(modelo).delete()
    db.commit()
