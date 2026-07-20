# Arquitetura — ChatBotModelo (Fase 1)

Documento técnico da aplicação: o que cada módulo faz, como os dados fluem, o modelo de
dados, o esquema de autenticação/acessos e a referência completa das rotas (o que cada
uma recebe e retorna). Para subir o projeto, veja o [README](../README.md).

A referência de rotas **viva** (interativa, sempre em sincronia com o código) fica no
Swagger em `/docs`. Este documento explica o "porquê" e o contexto que o Swagger não dá.

---

## 1. Visão geral

O sistema tem dois públicos e, por isso, dois tipos de rota:

- **Painel administrativo (HTML)** — usado pelo dono do negócio no navegador. Renderizado
  no servidor com Jinja2. Protegido por sessão (cookie JWT).
- **Tools da IA (JSON)** — a ponte pela qual a camada de IA (fase 5) lê e escreve no
  banco. Não renderiza HTML; troca JSON. Protegida por um **catálogo** de tabelas/colunas
  liberadas, não por login.

```
                    ┌─────────────────────────────┐
  Navegador  ─────► │  Painel (HTML, Jinja2)       │
  (admin)          │  /setup /login /painel/**    │──┐
                    └─────────────────────────────┘  │
                                                      ▼
                    ┌─────────────────────────────┐  ┌──────────┐
  IA / bot   ─────► │  Tools (JSON)                │─►│  MySQL   │
  (fase 5)         │  /tools/consultar /inserir   │  └──────────┘
                    └─────────────────────────────┘       ▲
                       │ valida contra o catálogo ─────────┘
```

**Princípio de segurança central:** a IA nunca monta SQL. Ela chama `/tools/*` com um
nome de tabela e pares coluna→valor; o `catalogo.py` rejeita qualquer tabela/coluna fora
da lista liberada (HTTP 400), e o SQL é montado com SQLAlchemy Core **parametrizado**.

---

## 2. Módulos — o que cada um faz

Todos em `backend/app/`.

| Módulo | Responsabilidade |
|---|---|
| `main.py` | Cria o `app` FastAPI, define os metadados do Swagger, registra os routers, o `lifespan` (bootstrap do banco) e o handler que redireciona não-autenticados para `/login`. |
| `bootstrap.py` | No arranque: cria o **database** (`CREATE DATABASE IF NOT EXISTS`) e, via `garantir_colunas`, adiciona colunas novas em tabelas já existentes (migração idempotente, sem Alembic). É o que permite "rodar do zero". |
| `templating.py` | Instância única de `Jinja2Templates` (caminhos absolutos ao pacote), compartilhada pelos routers. |
| `config.py` | `Settings` (pydantic-settings) lidas do `.env`: `DATABASE_URL`, segredo/expiração do JWT, `REDIS_URL`. Exporta o objeto `settings`. |
| `database.py` | `engine`, `SessionLocal`, `Base` declarativa e a dependency `get_db()` (uma sessão por requisição, fechada ao fim). |
| `models.py` | Tabelas SQLAlchemy do domínio (ver §4). Já declara todas, inclusive as de fases futuras. |
| `schemas.py` | Contratos Pydantic das rotas JSON (`/tools/*`): `ConsultarIn/Out`, `InserirIn/Out`, `ItemOut`. Geram os "Schemas" e exemplos no Swagger. |
| `security.py` | Hash de senha (bcrypt) e JWT: `hash_senha`, `verificar_senha`, `criar_token_acesso`, `decodificar_token_acesso`. |
| `deps.py` | `get_current_admin`: guarda das rotas de painel. Lê o cookie, valida o JWT, carrega o usuário; se falhar, levanta `NaoAutenticado`. |
| `catalogo.py` | Fonte da verdade sobre o que a IA pode tocar. `validar_tabela`, `validar_campos_consulta`, `validar_campos_insercao`. Hoje estático; na fase 6 passa a ler do banco. |
| `groq_service.py` | Isola o SDK do Groq: `validar_chave_groq` (faz uma chamada de teste), `get_chave_groq`, `get_configuracao`. |
| `routers/setup.py` | Cadastro inicial da empresa + 1º admin. |
| `routers/auth.py` | Login/logout; emissão do cookie de sessão. |
| `routers/integracao.py` | Onboarding e troca da chave do Groq. |
| `routers/itens.py` | CRUD de produtos/serviços. |
| `routers/rag.py` | CRUD dos blocos de RAG + preview do prompt montado. |
| `routers/whatsapp.py` | Conexão do WhatsApp: solicitar código, status (JSON p/ polling), desconectar. |
| `routers/webhook.py` | `POST /webhook/whatsapp` — recebe mensagens do sidecar (valida secret). |
| `routers/tools.py` | Rotas de dados da IA, validadas pelo catálogo. |
| `whatsapp/` | Abstração do WhatsApp: `provider` (interface), `fake`, `baileys`, `factory`. O resto do código depende só da interface. |
| `services/rag_service.py` | Regras dos blocos de RAG + `montar_system_prompt(db)`. |
| `services/conexao_service.py` | Orquestra o provedor de WhatsApp e persiste código/expiração/status. |
| `services/mensagem_service.py` | Registra mensagens e trata as recebidas (ponto de entrada do bot; Groq entra na fase 5). |

---

## 3. Fluxo de uma requisição

**Rota de painel** (ex.: `GET /painel/itens`):
1. FastAPI resolve as dependências: `get_db()` abre uma sessão; `get_current_admin` lê o
   cookie `access_token`, decodifica o JWT e busca o `Usuario`.
2. Se o cookie falta/expira → `NaoAutenticado` → handler em `main.py` → redirect `/login`.
3. Caso ok, a rota consulta o banco e devolve HTML (Jinja2).

**Rota de tool** (ex.: `POST /tools/inserir`):
1. O corpo JSON é validado pelo schema Pydantic (`InserirIn`).
2. `catalogo.py` confere tabela e colunas; se algo não está liberado → **400**.
3. O SQL é montado parametrizado (SQLAlchemy Core) e executado; retorna JSON.

### Rotas de IA no WhatsApp

As rotas cadastradas no painel usam `conversa_service` como máquina de estados e
`rota_service` para executar SQL parametrizado no banco de trabalho. Há dois cuidados que
evitam ações ambíguas ou vazamento de dados:

1. **Busca e apresentação:** cada resultado é formatado como um bloco de WhatsApp, com uma
   coluna por linha e ícones para chave, texto, número, data e booleano. Campos secretos
   (senha, hash, token e similares) são removidos inclusive de rotas antigas que os tenham
   gravado por engano.
2. **Cadastro:** a lista de campos da rota é persistida em `rota_campos`. A introspecção do
   banco é a fonte de verdade: `NOT NULL` sem valor padrão e sem geração automática é
   obrigatório. PK manual continua sendo pedida; apenas AUTO_INCREMENT/gerada é omitida.
   Se o banco rejeitar o INSERT, o estado da conversa permanece para tentar novamente ou
   refazer os dados.
3. **Exclusão:** o bot lista até 10 registros, pede que a pessoa escolha a coluna e o valor
   de filtro, mostra uma prévia com igualdade exata e só executa após `SIM`. A coluna é
   validada contra o schema e segredos não aparecem no menu.

Campos pessoais são sinalizados no painel para escolha consciente do administrador. Campos
secretos não podem ser exibidos, filtrados ou coletados pelo WhatsApp.

---

## 4. Modelo de dados

Em uso na Fase 1: **configuracoes**, **usuarios**, **itens**. As demais já existem para
evitar migração futura.

**`configuracoes`** — linha única (id=1) com os dados deste deploy.

| Coluna | Tipo | Notas |
|---|---|---|
| id | int PK | Sempre 1 (singleton). |
| nome_empresa | varchar(255) | |
| numero_whatsapp | varchar(20), nulo | Número do bot (só dígitos, DDI+DDD+número). |
| instance_name | varchar(100), nulo | Reservado para o nome da instância/sessão. |
| status_conexao | varchar(30) | `desconectado` \| `aguardando_pareamento` \| `conectado`. |
| groq_api_key | varchar(255), nulo | Chave do Groq (cadastrada no painel). |
| pairing_code | varchar(16), nulo | Código de pareamento atual do WhatsApp. |
| pairing_expira_em | datetime, nulo | Quando o código expira. |

**`usuarios`** — administradores do painel.

| Coluna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| nome | varchar(255) | |
| email | varchar(255) único | Login. |
| senha_hash | varchar(255) | bcrypt. |
| papel | varchar(30) | Default `admin`. |

**`itens`** — produtos/serviços.

| Coluna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| nome | varchar(255) | |
| descricao | text, nulo | |
| preco | decimal(10,2), **nulo** | Nulo = "sob consulta". |

**`rag_blocos`** — instruções do RAG por prompt.

| Coluna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| tipo | varchar(20) | `fazer` \| `nao_fazer`. |
| titulo | varchar(255) | |
| conteudo | text | |
| ordem | int | Ordena os blocos dentro do tipo. |
| ativo | bool | Só blocos ativos entram no prompt. |

**`mensagens`** — histórico do chatbot.

| Coluna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| numero | varchar(20) | Número do cliente. |
| direcao | varchar(10) | `recebida` \| `enviada`. |
| conteudo | text | |
| criado_em | datetime | Preenchido pelo banco. |

**Fases futuras (já criadas):** `clientes`, `pedidos`, `itens_pedido`, `pagamentos`,
`tabelas_dinamicas`, `colunas_dinamicas`.

---

## 5. Autenticação e acessos

**Quem acessa o quê:**

| Rota | Acesso | Como é protegida |
|---|---|---|
| `/setup` | Público (só antes de configurar) | Some após a empresa existir. |
| `/login`, `/logout` | Público | — |
| `/painel/**` (itens, rag, whatsapp, integracao) | Só administrador logado | Cookie JWT via `get_current_admin`. |
| `/tools/**` | Backend do bot (fase 5) | Catálogo (não login). |
| `/webhook/whatsapp` | Sidecar do WhatsApp | Header `X-Webhook-Secret`. |
| `/`, `/docs`, `/redoc`, `/static/**` | Público | — |

**Mecanismo de sessão:**
- No login, `security.criar_token_acesso(usuario_id)` gera um JWT HS256 com `sub` = id e
  expiração (`JWT_EXPIRE_MINUTES`, default 8h).
- É gravado no cookie **`access_token`** (`httponly=True`, `samesite=lax`).
- Cada rota de painel depende de `get_current_admin`, que decodifica o cookie e carrega o
  usuário. Falha → redirect para `/login` (nunca 401 cru no navegador).
- `/logout` apaga o cookie.

Senhas nunca são guardadas em texto puro — só o hash bcrypt.

---

## 6. Referência de rotas

> Todos os corpos de formulário são `application/x-www-form-urlencoded`; os de tools são
> `application/json`. Fonte viva e testável: **`/docs`**.

### Setup
| Método/Rota | Recebe | Retorna |
|---|---|---|
| `GET /setup` | — | HTML do form; ou redireciona a `/login` se já configurado. |
| `POST /setup` | `nome_empresa`, `numero_whatsapp`, `admin_nome`, `admin_email`, `admin_senha` | Redirect `/login`; 400 reexibindo o form se o número for inválido. |

### Autenticação
| Método/Rota | Recebe | Retorna |
|---|---|---|
| `GET /login` | — | HTML do form; redireciona a `/setup` se não há empresa. |
| `POST /login` | `email`, `senha` | Cookie `access_token` + redirect (`/painel/itens` ou onboarding Groq); 401 reexibindo o form se inválido. |
| `GET /logout` | — | Apaga o cookie, redirect `/login`. |

### Integração IA
| Método/Rota | Recebe | Retorna |
|---|---|---|
| `GET /painel/integracao/groq` | query `forcar` (0/1) | HTML do tutorial se não há chave/há problema; redirect `/painel/itens` se a chave é válida (a menos que `forcar=1`). |
| `POST /painel/integracao/groq` | `groq_api_key` | Salva e redireciona `/painel/itens`; 400 reexibindo o form se a chave for recusada. |

### Painel — Itens (exigem admin logado)
| Método/Rota | Recebe | Retorna |
|---|---|---|
| `GET /painel/itens` | — | HTML da lista. |
| `GET /painel/itens/novo` | — | HTML do form vazio. |
| `POST /painel/itens/novo` | `nome`, `descricao?`, `preco?`, `sem_preco?` | Redirect para a lista. |
| `GET /painel/itens/{id}/editar` | — | HTML do form preenchido; 404 se não existe. |
| `POST /painel/itens/{id}/editar` | `nome`, `descricao?`, `preco?`, `sem_preco?` | Redirect para a lista; 404 se não existe. |
| `POST /painel/itens/{id}/excluir` | — | Redirect para a lista (idempotente). |

### IA — RAG (exigem admin logado)
| Método/Rota | Recebe | Retorna |
|---|---|---|
| `GET /painel/rag` | — | HTML das duas colunas (Fazer / Não fazer). |
| `POST /painel/rag/novo` | `tipo`, `titulo`, `conteudo` | Redirect; **400** se `tipo` inválido. |
| `POST /painel/rag/{id}/editar` | `titulo`, `conteudo`, `ativo?` | Redirect; 404 se não existe. |
| `POST /painel/rag/{id}/excluir` | — | Redirect (idempotente). |
| `GET /painel/rag/preview` | — | Texto puro: o system prompt montado. |

### WhatsApp (exigem admin logado)
| Método/Rota | Recebe | Retorna |
|---|---|---|
| `GET /painel/whatsapp` | — | HTML: status, código+contador (se pareando) e instruções. |
| `POST /painel/whatsapp/parear` | — | Solicita código ao provedor; redirect para a tela. |
| `GET /painel/whatsapp/status` | — | `{ status }` — usado pelo front no polling. |
| `POST /painel/whatsapp/desconectar` | — | Encerra a sessão; redirect. |

### Webhook (bot)
| Método/Rota | Recebe (JSON) | Retorna |
|---|---|---|
| `POST /webhook/whatsapp` | `{ numero, texto }` + header `X-Webhook-Secret` | `{ ok: true }`; **401** sem/errado o secret; ignora payload sem texto. |

### Tools (IA)
| Método/Rota | Recebe (JSON) | Retorna |
|---|---|---|
| `POST /tools/consultar` | `{ tabela, filtros{}, campos[]? }` | `{ resultados: [ {...} ] }`; **400** se tabela/coluna fora do catálogo. |
| `POST /tools/inserir` | `{ tabela, dados{} }` | `{ registro: {...} }`; **400** se coluna inválida ou obrigatória ausente. |

Exemplo:
```bash
curl -X POST http://localhost:8000/tools/consultar \
  -H "Content-Type: application/json" \
  -d '{"tabela":"itens","filtros":{},"campos":["id","nome","preco"]}'
```

---

## 7. O catálogo (coração da segurança das tools)

`catalogo.py` mantém `TABELAS_LIBERADAS`: para cada tabela liberada, quais colunas podem
ser lidas, quais podem ser inseridas e quais são obrigatórias. As funções de validação
levantam **HTTP 400** antes de qualquer acesso ao banco quando:
- a tabela não está liberada;
- há coluna de filtro/retorno/inserção fora da lista;
- falta uma coluna obrigatória na inserção.

Hoje o catálogo é um dicionário estático (só `itens`). Na **fase 6**, a fonte passa a ser
as tabelas `tabelas_dinamicas`/`colunas_dinamicas` — as assinaturas das funções foram
pensadas para não mudar, então os routers de tools não precisarão ser alterados.

---

## 8. Execução manual (passo a passo)

O `run.bat`/`run.ps1`/`run.sh` automatiza tudo isto. Manualmente (Windows, dentro de
`backend/`):

```powershell
py -3.12 -m venv .venv           # Python 3.12 obrigatório (não 3.14)
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env           # ajuste a DATABASE_URL
python -m uvicorn app.main:app --reload
```

As tabelas são criadas no arranque (`app.bootstrap` + `create_all`). O banco em si é o
**MySQL no AWS RDS** apontado pela `DATABASE_URL` do `.env` — o projeto não sobe MySQL
local. O `run.bat` testa essa conexão antes de iniciar a aplicação.

---

## 9. WhatsApp — arquitetura da conexão (Fase 4)

A conexão é desenhada com o **padrão provider (porta/adaptador)** para não acoplar o
backend a uma tecnologia de WhatsApp:

```
Painel ─► conexao_service ─► WhatsAppProvider (interface)
                                 ├── FakeWhatsAppProvider   (dev/testes: gera código, simula conexão)
                                 └── BaileysWhatsAppProvider (HTTP ─► sidecar Node ─► WhatsApp)
```

- O provedor é escolhido em `whatsapp/factory.py` por `WHATSAPP_PROVIDER` e injetado nas
  rotas via `Depends(provedor_whatsapp)` — o que permite os testes trocarem por um dublê.
- **Fluxo de pareamento**: painel → `POST /parear` → `conexao_service.iniciar_conexao`
  chama `provider.iniciar_pareamento(numero)`, que devolve `código + expiração`; isso é
  gravado em `configuracoes` e exibido com contador. O front faz *polling* em
  `/painel/whatsapp/status`; quando o provedor reporta `conectado`, a tela atualiza.
- **Mensagens recebidas**: o sidecar faz `POST /webhook/whatsapp` (com `X-Webhook-Secret`);
  `mensagem_service.tratar_mensagem_recebida` registra e (na fase 5) chamará o Groq usando
  `rag_service.montar_system_prompt(db)` como system prompt.

O sidecar Node (Baileys) fica em `whatsapp-service/` e só é necessário para a conexão real.

## 10. RAG por prompt (Fase 4)

Os blocos de `rag_blocos` (tipo `fazer`/`nao_fazer`, ativos, ordenados) são montados por
`rag_service.montar_system_prompt(db)` num único texto — o *system prompt* do bot. A tela
`/painel/rag` gerencia os blocos em duas colunas e `/painel/rag/preview` mostra o prompt
resultante. Assim, o comportamento do bot é configurável sem tocar em código.

## 10.1 As duas conexões de banco

O sistema mantém **dois engines independentes** (`app/database.py`):

| | Banco da **aplicação** | Banco de **trabalho** |
|---|---|---|
| Variáveis | `DATABASE_URL`, `DB_SSL_CA` | `DADOS_DATABASE_URL`, `DADOS_DB_SSL_CA` |
| Acesso | `get_engine()` / `get_db()` | `get_engine_dados()` / `get_db_dados()` |
| Conteúdo | tabelas internas (models do SQLAlchemy) | tabelas arbitrárias do aluno |
| Migrações | `create_all` + `garantir_colunas` no arranque | **nenhuma** — o schema é do aluno |

**Fallback:** se `DADOS_DATABASE_URL` estiver vazia, `get_engine_dados()` devolve o engine
da aplicação. Instalações antigas continuam funcionando sem qualquer mudança.

**Quem usa qual.** Praticamente todo o painel usa só a aplicação. Vão para o banco de
trabalho apenas: `schema_service` (introspecção), `rota_service` (execução do
SELECT/INSERT/DELETE) e, no painel, o construtor em `routers/rotas.py`. O
`conversa_service`/`mensagem_service` recebem **as duas** sessões: estado da conversa na
aplicação, dados do aluno no banco de trabalho.

**Fronteira de segurança.** Com bancos distintos, a IA não alcança fisicamente as tabelas
internas. No modo fallback, quem protege é `schema_service.TABELAS_BLOQUEADAS` — que
inclui `usuarios` (hashes), `configuracoes` (chave do Groq), `mensagens` (histórico),
`sessoes_chat`, `rotas_ia`/`rota_campos` e `rag_blocos` (as regras do próprio bot).
Ao criar uma tabela interna nova, **acrescente-a a essa lista**.

**Transações.** Bancos distintos não compartilham transação. Por isso a ordem é sempre
*executar no banco do aluno primeiro, limpar o estado da conversa depois*: se a operação
falhar, o fluxo permanece e o usuário pode tentar de novo.

**Reset.** `reset_service.resetar_tudo` roda apenas na sessão da aplicação — os dados do
aluno nunca são apagados.

## 11. Testes

`pytest`, em `backend/tests/`, com **SQLite em memória** e o **provedor fake** (nada de
MySQL nem celular). O `conftest.py` substitui `get_db` e `provedor_whatsapp`, e oferece um
`admin_client` já autenticado. Cobrem: `rag_service`, `conexao_service`, provedor fake,
rotas de RAG e de WhatsApp, e o webhook. Rode com `python -m pytest`.

---

## 12. Roadmap por fases

| Fase | Escopo | Status |
|---|---|---|
| 1 | Setup, auth, onboarding Groq, itens, catálogo + tools | ✅ concluída |
| 4 | WhatsApp por pareamento (Baileys/sidecar + fake), RAG por prompt, webhook, testes, redesign | ✅ concluída |
| 5 | Roteador Groq (function calling sobre `itens`/`clientes`, usando o RAG) | pendente |
| 6 | Catálogo dinâmico (introspecção do `INFORMATION_SCHEMA`) | pendente |
| 7 | Upload de script SQL com parser/validador (`sqlparse`) | pendente |
| 8 | Fluxo de pedido + pagamento Pix (webhook) | pendente |
| 9 | Modo admin autenticado dentro do chat (sessão Redis) | pendente |

O código de pareamento coletado no setup já é usado na conexão (fase 4); a chave do Groq +
os blocos de RAG passam a rotear mensagens na fase 5.
