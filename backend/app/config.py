"""Configuração central da aplicação, lida do arquivo `.env` (via pydantic-settings).

Um único objeto `settings` é importado pelos demais módulos. Cada atributo tem um
default seguro para desenvolvimento; em produção, sobrescreva pelo `.env`. A chave do
Groq NÃO fica aqui — é cadastrada pelo admin e salva no banco.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env fica na raiz do backend (backend/.env), independente de onde a app é iniciada.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    database_url: str = "mysql+pymysql://chatbot_app:chatbot_app_pass@localhost:3306/chatbot"
    jwt_secret_key: str = "troque-esta-chave-em-producao"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    redis_url: str = "redis://localhost:6379/0"
    groq_api_key: str = ""

    # Modelo do Groq usado para as respostas do bot (chat completion).
    groq_model: str = "llama-3.3-70b-versatile"

    # WhatsApp: 'evolution' (Evolution API via Docker, QR — real), 'baileys' (sidecar Node)
    # ou 'fake' (dublê para testes automatizados).
    whatsapp_provider: str = "evolution"
    whatsapp_service_url: str = "http://localhost:3001"  # usado só pelo provider 'baileys'
    whatsapp_webhook_secret: str = "troque-este-secret-do-webhook"
    # Tempo de vida (segundos) do código/QR exibido no painel.
    pairing_ttl_seconds: int = 60

    # Evolution API (provider 'evolution')
    evolution_api_url: str = "http://localhost:8080"
    evolution_api_key: str = "chatbot-evo-key-2026"
    evolution_instance: str = "chatbot"
    # URL que a Evolution (dentro do Docker) usa para chamar nosso webhook no host.
    # No Docker Desktop, o host é acessível por host.docker.internal.
    evolution_webhook_url: str = "http://host.docker.internal:8000/webhook/whatsapp"


settings = Settings()
