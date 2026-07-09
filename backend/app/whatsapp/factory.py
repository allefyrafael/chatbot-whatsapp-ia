"""Seleção do provedor de WhatsApp conforme a configuração.

`get_whatsapp_provider()` devolve uma instância única (cacheada) do provedor escolhido em
`settings.whatsapp_provider`. As rotas dependem de `provedor_whatsapp` (via FastAPI
`Depends`), o que permite os testes substituírem o provedor por um dublê com
`app.dependency_overrides`.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.whatsapp.baileys import BaileysWhatsAppProvider
from app.whatsapp.evolution import EvolutionWhatsAppProvider
from app.whatsapp.fake import FakeWhatsAppProvider
from app.whatsapp.provider import WhatsAppProvider


@lru_cache
def get_whatsapp_provider() -> WhatsAppProvider:
    if settings.whatsapp_provider == "evolution":
        return EvolutionWhatsAppProvider()
    if settings.whatsapp_provider == "baileys":
        return BaileysWhatsAppProvider(settings.whatsapp_service_url)
    return FakeWhatsAppProvider(ttl_seconds=settings.pairing_ttl_seconds)


def provedor_whatsapp() -> WhatsAppProvider:
    """Dependency de rota — resolve o provedor atual (substituível em testes)."""
    return get_whatsapp_provider()
