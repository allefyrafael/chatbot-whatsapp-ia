# ChatBotModelo

Chatbot de WhatsApp administrado por IA: o cliente conversa pelo WhatsApp, um roteador
com IA (Groq) interpreta a intenção e a traduz em operações sobre um banco MySQL
(consultar produtos, fazer pedido, gerar cobrança Pix). Um painel web administrativo
permite ao dono do negócio configurar a empresa, a chave da IA e o catálogo de produtos.

Projeto educacional, construído em fases.

> **É aluno / primeira vez?** Siga o **[TUTORIAL.md](TUTORIAL.md)** — passo a passo do
> que instalar e como rodar. **Documentação técnica:** [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

---

## Rodar tudo com um comando

Pré-requisitos: **Python 3.12**, **Docker Desktop** (aberto, "Engine running") e um
**banco MySQL no AWS RDS** já criado (com acesso público e o seu IP liberado no
Security Group).

```powershell
cd backend
.\run.bat
```

Na primeira execução o `run.bat` cria o arquivo `.env` e pede para você preencher a
`DATABASE_URL` com os dados do seu RDS — o próprio `.env` explica onde achar cada valor
(endpoint, porta, usuário, senha e nome do banco) no console da AWS.

Depois disso, o `run.bat` faz **tudo** sozinho: cria o venv (Python 3.12), instala as
dependências, testa a conexão com o RDS, sobe a **Evolution API (WhatsApp)** no Docker e
inicia a aplicação. **As tabelas são criadas automaticamente** no primeiro start.

- App / primeiro acesso: <http://localhost:8000/setup>
- **Swagger (documentação viva das rotas): <http://localhost:8000/docs>**

> O banco fica **sempre no AWS RDS** — o projeto não sobe MySQL local. O Docker é usado
> apenas para o WhatsApp (Evolution API).

> ⚠️ **Python 3.12, não 3.13/3.14.** As dependências (pydantic-core) ainda não suportam o
> 3.14. O `run.bat` já usa `py -3.12`. Nunca rode `python -m venv .venv` manualmente com o
> 3.14 — isso quebra o ambiente.

---

## O primeiro acesso

1. Abra <http://localhost:8000/setup> e cadastre a **empresa** (nome + número de WhatsApp
   do bot) e o **primeiro administrador** (nome, e-mail, senha).
2. Faça login em <http://localhost:8000/login>.
3. Como ainda não há chave de IA, você cai na **tela de onboarding do Groq**, com um
   tutorial passo a passo para gerar a chave gratuita em
   [console.groq.com](https://console.groq.com). A chave é validada na hora e salva no
   banco (nunca no `.env`).
4. Pronto: use a navegação do painel:
   - **Produtos/Serviços** — catálogo que o bot usa.
   - **WhatsApp** — conecte a linha do bot por código de pareamento (veja abaixo).
   - **IA · RAG** — configure, em blocos, o que o bot **deve** e **não deve** fazer.
   - **Chave Groq** — troque a chave da IA quando quiser.

---

## Conectar o WhatsApp

O painel conecta o WhatsApp por **código de pareamento** (sem API oficial). Há dois modos,
definidos por `WHATSAPP_PROVIDER` no `.env`:

- **`fake`** (padrão) — gera um código e **simula** a conexão. Serve para desenvolver e
  testar todo o fluxo sem um celular.
- **`baileys`** — conexão **real**. Requer subir o sidecar Node em
  [`whatsapp-service/`](whatsapp-service/README.md):

  ```bash
  cd whatsapp-service && npm install && npm start
  ```

  e, no `.env` do backend: `WHATSAPP_PROVIDER=baileys` (o `WHATSAPP_WEBHOOK_SECRET` precisa
  bater com o do sidecar).

Em ambos os modos, na tela **WhatsApp** você clica em *Solicitar código*, o painel mostra o
código com **contador de expiração** e as instruções para inseri-lo no celular
(WhatsApp → Aparelhos conectados → Conectar com número de telefone).

---

## Rodar os testes

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m pytest
```

Os testes usam SQLite em memória e um provedor de WhatsApp *fake* — não precisam de MySQL
nem de celular. Cobrem serviços (RAG, conexão, mensagens), rotas do painel, o webhook e o
provedor.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend/API | Python + FastAPI |
| Banco | MySQL 8 (local ou Docker; AWS RDS em produção) |
| ORM | SQLAlchemy 2 |
| Painel web | Jinja2 (renderizado no servidor) |
| Auth do painel | JWT (python-jose) em cookie httpOnly + bcrypt |
| IA | Groq (SDK oficial) — validação da chave já; roteador na fase 5 |
| Cache/sessão | Redis (reservado para a fase 9) |
| WhatsApp | Baileys via sidecar Node (`whatsapp-service/`) — código de pareamento |
| Testes | pytest (SQLite em memória + provedor fake) |

---

## Estrutura

```
ChatBotModelo/
├── README.md                     ← este arquivo (visão geral + como rodar)
├── docs/ARQUITETURA.md           ← documentação técnica detalhada
├── whatsapp-service/             ← sidecar Node (Baileys) — conexão real do WhatsApp
└── backend/
    ├── run.ps1 / run.bat / run.sh   ← "um comando para rodar tudo"
    ├── requirements.txt · pytest.ini · .env.example
    ├── tests/                    ← pytest (SQLite em memória + provedor fake)
    └── app/
        ├── main.py               ← app FastAPI, metadados do Swagger, lifespan
        ├── bootstrap.py          ← cria database + colunas novas no arranque
        ├── config.py · database.py · models.py · schemas.py · security.py
        ├── deps.py · catalogo.py · groq_service.py · templating.py
        ├── whatsapp/             ← abstração do WhatsApp (provider, fake, baileys, factory)
        ├── services/             ← regras: rag_service, conexao_service, mensagem_service
        ├── routers/              ← setup, auth, integracao, itens, rag, whatsapp, webhook, tools
        ├── templates/            ← HTML (Jinja2)
        └── static/               ← CSS (design-system)
```

---

## Status e roadmap

**Fase 1 (concluída):** setup, autenticação, onboarding Groq, CRUD de itens, catálogo +
`/tools/*` seguras.

**Fase 4 (concluída):** conexão do WhatsApp por código de pareamento (Baileys via sidecar,
com provedor fake para dev/testes), RAG por prompt em blocos, webhook do chatbot, suíte de
testes (pytest) e redesign do painel (100% da tela, sem scroll).

Próximas: **5** roteador Groq (function calling, usando o RAG) · **6** catálogo dinâmico ·
**7** upload de script SQL · **8** pedidos + Pix · **9** modo admin dentro do chat (Redis).
Detalhes em [docs/ARQUITETURA.md](docs/ARQUITETURA.md#roadmap-por-fases).
