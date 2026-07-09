# Evolution API — gateway real do WhatsApp (QR Code)

Sobe a [Evolution API](https://doc.evolution-api.com) em Docker (API + Postgres + Redis).
É o provedor **real** de WhatsApp do projeto (`WHATSAPP_PROVIDER=evolution`): o backend
Python fala com ela por HTTP (`EvolutionWhatsAppProvider`), mostra o QR Code no painel e
recebe as mensagens de volta pelo webhook.

## Subir

Requer **Docker Desktop rodando** (ícone da baleia = "Engine running").

```bash
cd evolution
docker compose up -d
```

Confira: <http://localhost:8080> deve responder "Evolution API ... it is working!".
Painel próprio da Evolution (opcional): <http://localhost:8080/manager> (use a API key).

A `EVOLUTION_API_KEY` está em `evolution/.env` (troque em produção). Ela precisa bater com
`EVOLUTION_API_KEY` do `backend/.env`.

## Como conectar o WhatsApp (no painel do chatbot)

1. Suba a Evolution (acima) e o backend (`cd backend && run.bat`) na **porta 8000**.
2. No painel → **WhatsApp** → **Conectar WhatsApp**.
3. Escaneie o **QR Code** com o WhatsApp do número do bot
   (Configurações → Aparelhos conectados → Conectar um aparelho).
4. Ao conectar, mande uma mensagem para o número — o bot responde com IA (Groq + RAG).

> O webhook aponta para `host.docker.internal:8000` (o backend no host, visto de dentro do
> Docker). Por isso o backend precisa estar na **porta 8000** para receber as mensagens.

## Parar / limpar

```bash
docker compose down          # para os containers (mantém os dados)
docker compose down -v       # para e apaga os volumes (Postgres/instâncias)
```
