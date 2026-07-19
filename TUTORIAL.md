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
- Ele roda o **WhatsApp** (Evolution API) e o **banco de configuração** do chatbot. O banco
  do **seu projeto** fica na AWS.

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

## 4. Rodar tudo (1 comando)

1. Confirme que o **Docker Desktop está aberto** e "Engine running".
2. Abra a pasta **`backend`**.
3. Dê **duplo-clique em `run.bat`** (ou `.\run.bat` no PowerShell).

O `run.bat` faz tudo:

| Passo | O que acontece |
|------|----------------|
| 1 | Cria o ambiente Python (venv) |
| 2 | Instala as bibliotecas |
| 3 | Cria o arquivo de configuração |
| 4 | Sobe no Docker o **banco de configuração** do chatbot e a **Evolution API** (WhatsApp) |
| 5 | Inicia o **painel** em <http://localhost:8000> |

Na primeira vez demora alguns minutos. Quando aparecer
`Uvicorn running on http://0.0.0.0:8000`, está no ar. **Deixe essa janela aberta** — é o
servidor rodando. Para parar, `Ctrl + C`.

---

## 5. Conectar o banco do SEU projeto (pela tela)

Abra <http://localhost:8000> no navegador. Você cai direto na tela **"Conectar o banco do
seu projeto"**, com campos parecidos com os do MySQL Workbench. É aqui que você informa o
**banco que criou no AWS RDS** — o banco do seu restaurante, loja, escola…

A própria tela mostra, ao lado, **onde achar cada dado** no console da AWS:

| Campo | Onde achar (RDS → Databases → seu banco) |
|---|---|
| **Hostname** | aba **Connectivity & security** → campo **Endpoint** |
| **Porta** | mesma aba → **Port** (normalmente `3306`) |
| **Username** | o **Master username** definido ao criar o banco |
| **Password** | a **Master password** definida ao criar o banco |
| **Database** | aba **Configuration** → campo **DB name** |

Clique em **"Testar conexão e continuar"**:

- **Deu certo** → a configuração é salva e você segue para o cadastro da empresa. Você não
  precisa editar nenhum arquivo. As **tabelas do seu projeto** são suas: crie-as como
  aprendeu na aula (Workbench ou SQL) — o chatbot só lê e escreve nelas.
- **Deu errado** → aparece um aviso explicando **exatamente** o que corrigir (por exemplo:
  senha incorreta, banco inexistente, endpoint errado ou o Security Group bloqueando o
  seu IP). É só corrigir e testar de novo.

> Não precisa se preocupar com senha que tenha `@`, `:` ou `/` — a tela cuida disso.
>
> Em **Opções avançadas** dá para informar o certificado TLS da AWS
> (<https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem>), se quiser
> conexão criptografada. É opcional.

---

## 5.1 Entendendo os DOIS bancos

O sistema usa **dois bancos separados**. Entender isso evita muita confusão:

| | **Banco do SEU projeto** | **Banco de configuração** |
|---|---|---|
| **O que guarda** | **as tabelas que você cria** (restaurante, loja, escola…) | dados internos do chatbot: empresa, administradores, rotas, conversas |
| **Onde fica** | **AWS RDS** (o que você criou na aula) | **Docker, na sua máquina** |
| **Quem usa** | as **rotas de IA** — é aqui que o bot busca e cadastra | só o painel |
| **Você configura?** | **Sim** — é a tela do primeiro acesso | **Não** — sobe sozinho com o `run.bat` |

Ou seja: **você só se preocupa com o banco da AWS**. O de configuração é automático.

**Por que separar?**

1. **Segurança** — as tabelas internas do chatbot guardam senhas e a chave da IA. Com os
   bancos separados, uma rota de IA **não consegue nem enxergar** essas tabelas.
2. **Clareza** — o "Apagar tudo" (Configurações) zera o chatbot, mas **nunca apaga as suas
   tabelas** do banco da AWS. Seu projeto fica preservado.

Para trocar depois: **Configurações → Banco do meu projeto (AWS) → Alterar conexão**.

---

## 6. Primeiro acesso (empresa, IA e WhatsApp)

Logo após conectar o banco você já cai em <http://localhost:8000/setup>

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

## 6.1 Já usava a versão anterior? (atualização)

Se você já tinha o chatbot rodando e fez o treinamento da IA, **não perde nada**. Basta
baixar a versão nova e rodar o `run.bat` como sempre.

O que acontece:

| | |
|---|---|
| Seu banco na máquina | **continua o mesmo** — o `.env` não é sobrescrito |
| Empresa, chave do Groq, produtos, treinamento da IA | **preservados**, nada é recriado |
| O que muda | são **acrescentadas** 3 tabelas novas (`rotas_ia`, `rota_campos`, `sessoes_chat`), usadas pelas rotas de IA |

A novidade da versão é o **banco do seu projeto no AWS RDS** (seção 5) e as **rotas de IA**.
Enquanto você não conectar o RDS, tudo o que já funcionava continua funcionando — só o
construtor de rotas fica esperando a conexão.

> Não rode "Apagar tudo" achando que é necessário para atualizar: **não é**, e isso sim
> apagaria o seu treinamento.

---

## 7. Nas próximas vezes

Abra o **Docker Desktop** (esperar "Engine running") e rode o **`run.bat`**. Ele
reaproveita tudo o que já foi instalado e sobe rápido.

---

## 8. Se algo der errado

| Problema | Solução |
|---------|---------|
| "Python 3.12 nao encontrado" | Instale o Python **3.12** e marque "Add to PATH". Reabra o PowerShell. |
| Aviso "Não foi possível conectar" na tela do banco | O próprio aviso diz o que corrigir. Os motivos mais comuns: Security Group não libera o **seu IP atual**, "Public access" não está como **Yes**, ou usuário/senha/nome do banco errados. |
| Trocou de rede/Wi-Fi e o banco parou | Seu IP mudou. Atualize a regra do **Security Group** no RDS com o novo IP ("My IP"). |
| "o Docker esta fora" / WhatsApp não conecta | Abra o Docker Desktop e espere **"Engine running"**. Rode o `run.bat` de novo. |
| WhatsApp "sumiu"/caiu | É o Docker que parou. No PowerShell: `wsl --shutdown`, reabra o Docker Desktop e rode o `run.bat`. |
| Porta 8000 ocupada | Feche outro programa que use a porta 8000. |
| QR Code não aparece | Confirme o Docker "Engine running" e clique em **Gerar novo QR**. |

Documentação técnica (para quem quer entender o código):
[docs/ARQUITETURA.md](docs/ARQUITETURA.md).
