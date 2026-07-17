# Tutorial de instalação e execução (para alunos)

Este guia leva você do zero até o chatbot rodando e conectado ao WhatsApp. São **2
programas para instalar** e **1 comando para rodar tudo**.

---

## 1. O que instalar na máquina

Instale os dois programas abaixo (Windows):

### a) Python 3.12
- Baixe em <https://www.python.org/downloads/release/python-3129/> (Windows installer 64-bit).
- **Importante:** na primeira tela do instalador, marque **"Add python.exe to PATH"**.
- Precisa ser a **versão 3.12** (a 3.13/3.14 quebram algumas bibliotecas).
- Confirir depois: abra o **PowerShell** e digite `py -3.12 --version` → deve mostrar `Python 3.12.x`.

### b) Docker Desktop
- Baixe em <https://www.docker.com/products/docker-desktop/> e instale.
- Abra o **Docker Desktop** e **espere** o ícone da baleia (canto inferior) ficar verde,
  escrito **"Engine running"**. Deixe-o aberto enquanto usar o chatbot.
- O Docker roda o banco de dados (MySQL) e o WhatsApp (Evolution API) pra você — você não
  precisa instalar mais nada.

> Você **não** precisa instalar MySQL, Node, nem a Evolution manualmente. O comando de
> execução cuida de tudo isso.

---

## 2. Pegar o projeto

Coloque a pasta do projeto num lugar fácil, por exemplo `C:\Projetos\ChatBotModelo`.
A estrutura é assim:

```
ChatBotModelo\
├── backend\        ← é AQUI que você roda o comando
├── evolution\      ← WhatsApp (sobe sozinho)
└── TUTORIAL.md     ← este arquivo
```

---

## 3. Rodar tudo (1 comando)

1. Confirme que o **Docker Desktop está aberto** e "Engine running".
2. Abra a pasta **`backend`** no Explorador de Arquivos.
3. Dê **duplo-clique em `run.bat`** (ou, no PowerShell dentro de `backend`, digite `.\run.bat`).

O `run.bat` faz tudo automaticamente:

| Passo | O que acontece |
|------|----------------|
| 1 | Cria o ambiente Python (venv) |
| 2 | Instala as bibliotecas |
| 3 | Cria o arquivo de configuração (`.env`) |
| 4 | Sobe o **MySQL** (banco de dados) no Docker |
| 5 | Sobe a **Evolution API** (WhatsApp) no Docker |
| 6 | Inicia o **painel** em <http://localhost:8000> |

Na primeira vez demora alguns minutos (baixa as imagens do Docker e instala as libs).
Quando aparecer `Uvicorn running on http://0.0.0.0:8000`, está no ar. **Deixe essa janela
aberta** — é o servidor rodando. Para parar, aperte `Ctrl + C`.

---

## 4. Primeiro acesso (configurar a empresa)

Com o servidor rodando, abra no navegador: <http://localhost:8000/setup>

1. **Cadastre a empresa**: nome + número de WhatsApp do bot (com DDI+DDD, só números,
   ex.: `5561999998888`) + seu nome, e-mail e senha de administrador.
2. Faça login em <http://localhost:8000/login>.

### Conectar a Inteligência Artificial (Groq) — gratuito
Ao logar, você cai na tela da **chave Groq** (é o "cérebro" do bot):
1. Acesse <https://console.groq.com> e crie uma conta grátis.
2. Em **API Keys** → **Create API Key**, copie a chave (começa com `gsk_`).
3. Cole no painel e clique em **Salvar e validar**.

### Conectar o WhatsApp (QR Code)
1. No menu, vá em **WhatsApp** → **Conectar WhatsApp**.
2. Vai aparecer um **QR Code**.
3. No celular do número do bot: **WhatsApp → Configurações → Aparelhos conectados →
   Conectar um aparelho** → aponte a câmera para o QR.
4. Quando conectar, **mande uma mensagem** para esse número de outro celular — o bot
   responde com IA.

### Cadastrar produtos e ensinar o bot
- **Produtos/Serviços**: cadastre o que a empresa vende (o bot usa isso para responder).
- **IA · RAG**: escreva regras do tipo "o que o bot DEVE / NÃO DEVE fazer".
- **Configurações → Zona de perigo**: "Apagar tudo" reinicia o sistema do zero (útil para
  refazer o teste do começo).

---

## 5. Opcional: usar um banco de dados na nuvem (AWS RDS)

Por padrão o banco roda na sua máquina (no Docker). Se quiser um **MySQL gerenciado na
AWS (RDS)** — por exemplo, para a turma inteira acessar o mesmo banco pela internet —
siga os passos abaixo. Quando o `.env` aponta para um endereço remoto, o `run.bat`
detecta isso e **não** sobe o MySQL local.

### 5.1 Criar a instância no RDS
1. Acesse o **console da AWS** → serviço **RDS** → **Create database**.
2. Método: **Standard create**. Engine: **MySQL**.
3. Templates: **Free tier** (evita cobrança).
4. **Settings**:
   - DB instance identifier: `chatbot`
   - Master username: `admin`
   - Master password: escolha uma senha forte e **anote**.
5. **Instance configuration**: `db.t3.micro` (ou o que o free tier oferecer).
6. **Connectivity**:
   - Public access: **Yes** (para conseguir acessar da sua máquina).
   - VPC security group: **Create new** (dê um nome, ex.: `chatbot-sg`).
7. **Additional configuration** → Initial database name: `chatbot`.
8. Clique em **Create database** e espere ~5 minutos até o status ficar **Available**.

### 5.2 Liberar o acesso (Security Group)
1. Abra a instância → aba **Connectivity & security** → clique no **VPC security group**.
2. **Inbound rules** → **Edit inbound rules** → **Add rule**:
   - Type: **MySQL/Aurora** (porta **3306**)
   - Source: **My IP** (ou o IP/faixa da turma)
3. Salve. (Sem isso, a conexão fica "travada"/timeout.)

### 5.3 Pegar o endpoint
Na página da instância, copie o **Endpoint** — algo como
`chatbot.xxxxxxxx.us-east-1.rds.amazonaws.com`.

### 5.4 Apontar o app para o RDS
Abra o arquivo **`backend/.env`** e troque a linha `DATABASE_URL` pelo endpoint do RDS:

```
DATABASE_URL=mysql+pymysql://admin:SUA_SENHA@SEU_ENDPOINT:3306/chatbot
```

**TLS (recomendado pela AWS):** baixe o certificado da AWS em
<https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem>, salve num lugar
fácil, e no `.env` preencha (use barras normais `/`):

```
DB_SSL_CA=C:/Users/voce/certs/global-bundle.pem
```

### 5.5 Rodar
Rode o **`run.bat`** normalmente. Ele vai:
- detectar que o banco é remoto e **não** subir o MySQL do Docker;
- conectar no RDS e **criar as tabelas sozinho** no primeiro start.

Pronto: o painel funciona igual, mas os dados agora ficam no banco da AWS. Para voltar ao
banco local, é só recolocar a `DATABASE_URL` original no `.env`.

> Dica de custo: o RDS free tier tem limite de horas/mês. Quando não estiver usando,
> **pare (Stop)** a instância no console para não gastar as horas à toa.

---

## 6. Nas próximas vezes

Só precisa: abrir o **Docker Desktop** (esperar "Engine running") e rodar o **`run.bat`**
de novo. Ele reaproveita tudo o que já foi instalado e sobe rápido.

---

## 7. Se algo der errado

| Problema | Solução |
|---------|---------|
| "Python 3.12 nao encontrado" | Instale o Python **3.12** e marque "Add to PATH". Reabra o PowerShell. |
| "o Docker esta fora" / WhatsApp não conecta | Abra o Docker Desktop e espere **"Engine running"**. Rode o `run.bat` de novo. |
| WhatsApp "sumiu"/caiu | É o Docker que parou. No PowerShell: `wsl --shutdown`, reabra o Docker Desktop, e rode o `run.bat`. |
| Porta 8000 ocupada | Feche outro programa que use a porta 8000 (ou outro servidor rodando). |
| QR Code não aparece | Confirme que o Docker está "Engine running" e clique em **Gerar novo QR**. |
| RDS: conexão trava/timeout | Confira o **Security Group** (regra MySQL 3306 para o seu IP) e se "Public access" está **Yes**. |
| RDS: erro de SSL/TLS | Baixe o `global-bundle.pem` da AWS e aponte o `DB_SSL_CA` para ele no `.env` (barras `/`). |

Documentação técnica detalhada (para quem quer entender o código):
[docs/ARQUITETURA.md](docs/ARQUITETURA.md).
