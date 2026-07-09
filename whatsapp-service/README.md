# whatsapp-service (sidecar Baileys)

Serviço Node que conecta o WhatsApp **por código de pareamento** (sem API oficial, via
[Baileys](https://github.com/WhiskeySockets/Baileys)) e repassa as mensagens recebidas ao
backend FastAPI. O painel Python fala com este serviço por HTTP (`BaileysWhatsAppProvider`).

Use este serviço apenas para a **conexão real**. Para desenvolver/testar o fluxo sem um
celular, o backend usa o provedor `fake` por padrão (`WHATSAPP_PROVIDER=fake`).

## Rodar

Requer **Node 18+** (usa o `fetch` global).

```bash
cd whatsapp-service
npm install
# variáveis (opcionais; valores default entre parênteses):
#   PORT (3001)
#   WEBHOOK_URL (http://localhost:8000/webhook/whatsapp)
#   WEBHOOK_SECRET (precisa bater com WHATSAPP_WEBHOOK_SECRET do backend)
npm start
```

Depois, no backend, defina no `.env`:

```
WHATSAPP_PROVIDER=baileys
WHATSAPP_SERVICE_URL=http://localhost:3001
WHATSAPP_WEBHOOK_SECRET=<o mesmo WEBHOOK_SECRET acima>
```

## Fluxo

1. No painel (`/painel/whatsapp`), clique em **Solicitar código de pareamento**.
2. O backend chama `POST /connect { numero }` deste serviço, que chama
   `sock.requestPairingCode(numero)` do Baileys e devolve `{ code, expiresIn }`.
3. Digite o código no WhatsApp: **Configurações → Aparelhos conectados → Conectar um
   aparelho → Conectar com número de telefone**.
4. Ao conectar, `GET /status` passa a devolver `conectado` e o painel atualiza sozinho.
5. Cada mensagem recebida vira um `POST` para `WEBHOOK_URL` com o header
   `X-Webhook-Secret`.

## Endpoints

| Método | Rota | Corpo | Resposta |
|---|---|---|---|
| POST | `/connect` | `{ numero }` | `{ code, expiresIn }` |
| GET | `/status` | — | `{ status }` |
| POST | `/send` | `{ numero, texto }` | `{ ok }` |
| POST | `/disconnect` | — | `{ ok }` |

A sessão fica salva em `auth/` (não versionar). Apague essa pasta para desparear.
