# Tutorial de instalação e execução (para alunos)

Este guia leva você do zero até o chatbot rodando e conectado ao WhatsApp.

**Visão geral:** você instala 2 programas, cria seu banco de dados na AWS (RDS), preenche
1 arquivo de configuração e roda 1 comando.

---

## 1. O que instalar na máquina

### a) Python 3.12
- Baixe em <https://www.python.org/downloads/release/python-3129/> (Windows installer 64-bit).
- **Importante:** na primeira tela do instalador, marque **"Add python.exe to PATH"**.
- Precisa ser a **versão 3.12** (a 3.13/3.14 quebram algumas bibliotecas).
- Para conferir: abra o **PowerShell** e digite `py -3.12 --version` → deve mostrar `Python 3.12.x`.

### b) Docker Desktop
- Baixe em <https://www.docker.com/products/docker-desktop/> e instale.
- Abra o **Docker Desktop** e **espere** o ícone da baleia ficar verde, escrito
  **"Engine running"**. Deixe-o aberto enquanto usar o chatbot.
- Ele é usado apenas para o **WhatsApp** (Evolution API). O banco de dados fica na AWS.

---

## 2. Criar o banco de dados no AWS RDS

Siga o tutorial da aula para criar a instância **MySQL** no **AWS RDS**. Ao criar, garanta:

- **Public access: Yes** (senão sua máquina não alcança o banco)
- **Security Group** com uma regra de entrada liberando a porta **3306** para o **seu IP**
- **Initial database name** preenchido (ex.: `chatbot`) — anote esse nome
- Anote também o **Master username** e a **Master password** que você definiu

Espere o status da instância ficar **Available** antes de continuar.

> Atenção: se a sua internet trocar de IP (reiniciar o roteador, mudar de rede/Wi-Fi),
> a regra do Security Group para de valer e o banco fica inacessível. Nesse caso, é só
> editar a regra e colocar o novo IP ("My IP").

---

## 3. Pegar o projeto

Coloque a pasta do projeto num lugar fácil, por exemplo `C:\Projetos\ChatBotModelo`:

```
ChatBotModelo\
├── backend\        ← é AQUI que você roda o comando
├── evolution\      ← WhatsApp (sobe sozinho)
└── TUTORIAL.md     ← este arquivo
```

---

## 4. Configurar o acesso ao banco (arquivo `.env`)

1. Na pasta `backend`, rode o `run.bat` **uma vez**. Ele vai criar o arquivo `.env` e
   avisar que falta configurar o banco. (Ou copie `.env.example` para `.env` na mão.)
2. Abra o arquivo **`backend\.env`** no Bloco de Notas.
3. Preencha a linha `DATABASE_URL`. O próprio arquivo explica onde achar cada valor:

| Valor | Onde achar no console da AWS (RDS → Databases → seu banco) |
|---|---|
| **ENDPOINT** | aba **Connectivity & security** → campo **Endpoint** |
| **PORTA** | mesma aba → campo **Port** (normalmente `3306`) |
| **USUARIO** | o **Master username** que você definiu ao criar |
| **SENHA** | a **Master password** que você definiu ao criar |
| **BANCO** | aba **Configuration** → campo **DB name** |

O formato é este (troque os valores em MAIÚSCULO):

```
DATABASE_URL=mysql+pymysql://USUARIO:SENHA@ENDPOINT:3306/BANCO
```

Ficando parecido com:

```
DATABASE_URL=mysql+pymysql://admin:MinhaSenha123@chatbot.c9xyzabc.us-east-1.rds.amazonaws.com:3306/chatbot
```

> **Senha com caractere especial?** Substitua dentro da URL:
> `@` → `%40` · `:` → `%3A` · `/` → `%2F` · `?` → `%3F` · `#` → `%23`

**TLS (opcional, recomendado pela AWS):** baixe o certificado
<https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem>, salve num lugar
simples e preencha no `.env` (use barras normais `/`):

```
DB_SSL_CA=C:/Users/voce/Downloads/global-bundle.pem
```

---

## 5. Rodar tudo (1 comando)

1. Confirme que o **Docker Desktop está aberto** e "Engine running".
2. Abra a pasta **`backend`**.
3. Dê **duplo-clique em `run.bat`** (ou `.\run.bat` no PowerShell).

O `run.bat` faz tudo:

| Passo | O que acontece |
|------|----------------|
| 1 | Cria o ambiente Python (venv) |
| 2 | Instala as bibliotecas |
| 3 | Cria o `.env` (se faltar) |
| 4 | **Testa a conexão com o seu banco no RDS** |
| 5 | Sobe a **Evolution API** (WhatsApp) no Docker |
| 6 | Inicia o **painel** em <http://localhost:8000> |

Na primeira vez demora alguns minutos. Quando aparecer
`Uvicorn running on http://0.0.0.0:8000`, está no ar. **Deixe essa janela aberta** — é o
servidor rodando. Para parar, `Ctrl + C`.

As tabelas do banco são criadas **automaticamente** no primeiro start. Você não precisa
rodar nenhum SQL na mão.

---

## 6. Primeiro acesso

Com o servidor rodando, abra: <http://localhost:8000/setup>

1. **Cadastre a empresa**: nome + número de WhatsApp do bot (DDI+DDD, só números,
   ex.: `5561999998888`) + seu nome, e-mail e senha de administrador.
2. Faça login em <http://localhost:8000/login>.

### Conectar a Inteligência Artificial (Groq) — gratuito
1. Acesse <https://console.groq.com> e crie uma conta grátis.
2. Em **API Keys** → **Create API Key**, copie a chave (começa com `gsk_`).
3. Cole no painel e clique em **Salvar e validar**.

### Conectar o WhatsApp (QR Code)
1. No menu, vá em **WhatsApp** → **Conectar WhatsApp**.
2. Vai aparecer um **QR Code**.
3. No celular do número do bot: **WhatsApp → Configurações → Aparelhos conectados →
   Conectar um aparelho** → aponte a câmera para o QR.
4. Conectado, **mande uma mensagem** para esse número de outro celular — o bot responde
   com IA.

### Cadastrar produtos e ensinar o bot
- **Produtos/Serviços**: cadastre o que a empresa vende (o bot usa isso para responder).
- **IA · RAG**: escreva regras do tipo "o que o bot DEVE / NÃO DEVE fazer".
- **Configurações → Zona de perigo**: "Apagar tudo" reinicia o sistema do zero.

---

## 7. Nas próximas vezes

Abra o **Docker Desktop** (esperar "Engine running") e rode o **`run.bat`**. Ele
reaproveita tudo o que já foi instalado e sobe rápido.

---

## 8. Se algo der errado

| Problema | Solução |
|---------|---------|
| "Python 3.12 nao encontrado" | Instale o Python **3.12** e marque "Add to PATH". Reabra o PowerShell. |
| "Falta configurar o banco de dados" | Preencha a linha `DATABASE_URL` no `backend\.env` (seção 4 acima). |
| "Nao consegui conectar no banco" | 1) Security Group liberando 3306 para o **seu IP atual**; 2) "Public access = Yes"; 3) usuário/senha/nome do banco corretos; 4) endpoint copiado inteiro. |
| Senha do banco não funciona | Tem caractere especial? Troque na URL: `@`→`%40`, `:`→`%3A`, `/`→`%2F`. |
| "o Docker esta fora" / WhatsApp não conecta | Abra o Docker Desktop e espere **"Engine running"**. Rode o `run.bat` de novo. |
| WhatsApp "sumiu"/caiu | É o Docker que parou. No PowerShell: `wsl --shutdown`, reabra o Docker Desktop e rode o `run.bat`. |
| Porta 8000 ocupada | Feche outro programa que use a porta 8000. |
| QR Code não aparece | Confirme o Docker "Engine running" e clique em **Gerar novo QR**. |

Documentação técnica (para quem quer entender o código):
[docs/ARQUITETURA.md](docs/ARQUITETURA.md).
