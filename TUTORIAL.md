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

## 5. Nas próximas vezes

Só precisa: abrir o **Docker Desktop** (esperar "Engine running") e rodar o **`run.bat`**
de novo. Ele reaproveita tudo o que já foi instalado e sobe rápido.

---

## 6. Se algo der errado

| Problema | Solução |
|---------|---------|
| "Python 3.12 nao encontrado" | Instale o Python **3.12** e marque "Add to PATH". Reabra o PowerShell. |
| "o Docker esta fora" / WhatsApp não conecta | Abra o Docker Desktop e espere **"Engine running"**. Rode o `run.bat` de novo. |
| WhatsApp "sumiu"/caiu | É o Docker que parou. No PowerShell: `wsl --shutdown`, reabra o Docker Desktop, e rode o `run.bat`. |
| Porta 8000 ocupada | Feche outro programa que use a porta 8000 (ou outro servidor rodando). |
| QR Code não aparece | Confirme que o Docker está "Engine running" e clique em **Gerar novo QR**. |

Documentação técnica detalhada (para quem quer entender o código):
[docs/ARQUITETURA.md](docs/ARQUITETURA.md).
