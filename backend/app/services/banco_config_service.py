"""Configuração do banco pelo painel (assistente estilo MySQL Workbench).

Recebe host/porta/usuário/senha/banco, monta a `DATABASE_URL`, **testa a conexão de
verdade** e só então grava no `.env`. Se falhar, traduz o erro técnico do MySQL numa
mensagem que o aluno entende (Security Group, senha errada, banco inexistente...).
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote, unquote

from sqlalchemy import create_engine, text

from app.config import settings
from app.database import recarregar_engine

ARQUIVO_ENV = Path(__file__).resolve().parent.parent.parent / ".env"

# Schemas internos do MySQL: o RDS nao deixa a aplicacao criar tabelas neles.
SCHEMAS_RESERVADOS = {"mysql", "information_schema", "performance_schema", "sys"}


def validar_nome_banco(banco: str) -> str | None:
    """Recusa nomes de schema de sistema. Retorna a mensagem de erro, ou None se ok."""
    nome = (banco or "").strip().lower()
    if not nome:
        return "Informe o nome do banco de dados (ex.: <b>chatbot</b>)."
    if nome in SCHEMAS_RESERVADOS:
        return (
            f"<b>{nome}</b> é um banco interno do servidor MySQL (guarda usuários e "
            "permissões) e a AWS não permite criar tabelas nele. "
            "Use um nome próprio para a aplicação, por exemplo <b>chatbot</b> — "
            "se ele ainda não existir, eu crio automaticamente para você."
        )
    return None


def partes_da_url(url: str) -> dict:
    """Quebra a DATABASE_URL nos campos do formulário. **Nunca devolve a senha.**

    Usado para pré-preencher a tela de conexão no painel, mostrando ao admin em qual
    servidor/banco a aplicação está ligada agora.
    """
    vazio = {"host": "", "porta": "3306", "usuario": "", "banco": ""}
    if not url:
        return vazio
    padrao = re.match(r"^mysql\+pymysql://([^:]*):([^@]*)@([^:/]+):(\d+)/(.+)$", url.strip())
    if not padrao:
        return vazio
    return {
        "host": padrao.group(3),
        "porta": padrao.group(4),
        "usuario": unquote(padrao.group(1)),
        "banco": padrao.group(5).split("?")[0],
    }


def montar_url(host: str, porta: str, usuario: str, senha: str, banco: str) -> str:
    """Monta a DATABASE_URL escapando usuário/senha (senhas têm @, :, / com frequência)."""
    return (
        f"mysql+pymysql://{quote(usuario, safe='')}:{quote(senha, safe='')}"
        f"@{host.strip()}:{porta.strip()}/{banco.strip()}"
    )


def traduzir_erro(exc: Exception) -> str:
    """Converte a exceção do driver numa explicação acionável para o aluno."""
    texto = str(exc)

    if "1044" in texto:
        return (
            "O usuário e a senha estão corretos, mas ele não tem permissão nesse banco. "
            "Isso acontece quando se aponta para um banco interno do MySQL (como "
            "<code>mysql</code>, <code>sys</code> ou <code>information_schema</code>). "
            "Troque o campo <b>Banco de dados</b> por um nome da sua aplicação, "
            "por exemplo <b>chatbot</b> — eu crio automaticamente se não existir."
        )
    if "1045" in texto or "Access denied" in texto:
        return (
            "Usuário ou senha incorretos. Confira o <b>Master username</b> e a "
            "<b>Master password</b> que você definiu ao criar o banco no RDS."
        )
    if "1049" in texto or "Unknown database" in texto:
        return (
            "O usuário e a senha estão certos, mas esse <b>nome de banco</b> não existe "
            "no servidor. Confira o campo <b>DB name</b> na aba Configuration do RDS."
        )
    if "2005" in texto or "getaddrinfo" in texto or "Name or service not known" in texto:
        return (
            "Não encontrei esse servidor. O <b>endpoint</b> parece incorreto — copie-o "
            "inteiro do RDS (termina em <code>.rds.amazonaws.com</code>)."
        )
    if "2003" in texto or "timed out" in texto or "Can't connect" in texto:
        return (
            "O servidor não respondeu. Quase sempre é o <b>Security Group</b>: crie uma "
            "regra liberando a porta 3306 para o <b>seu IP atual</b>. Confira também se "
            "o banco está com <b>Public access = Yes</b> e status <b>Available</b>."
        )
    if "SSL" in texto or "certificate" in texto.lower():
        return (
            "Falha no TLS/SSL. Confira o caminho do certificado da AWS "
            "(<code>global-bundle.pem</code>) ou deixe o campo de certificado vazio."
        )
    return f"Não consegui conectar. Detalhe técnico: {texto[:300]}"


def testar_conexao(url: str, ssl_ca: str = "") -> tuple[bool, str]:
    """Tenta conectar de verdade. Retorna (ok, mensagem_amigavel)."""
    connect_args = {"ssl": {"ca": ssl_ca}} if ssl_ca else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "Conexão bem-sucedida."
    except Exception as exc:  # noqa: BLE001 - qualquer falha vira mensagem amigável
        return False, traduzir_erro(exc)
    finally:
        engine.dispose()


def _substituir_linha(conteudo: str, chave: str, valor: str) -> str:
    """Troca (ou acrescenta) `CHAVE=valor` no texto do .env."""
    padrao = re.compile(rf"^{re.escape(chave)}=.*$", re.MULTILINE)
    if padrao.search(conteudo):
        return padrao.sub(f"{chave}={valor}", conteudo)
    return conteudo.rstrip("\n") + f"\n{chave}={valor}\n"


def salvar_configuracao(url: str, ssl_ca: str = "") -> None:
    """Persiste no .env, atualiza as settings em memória e recarrega o engine."""
    conteudo = ARQUIVO_ENV.read_text(encoding="utf-8") if ARQUIVO_ENV.exists() else ""
    conteudo = _substituir_linha(conteudo, "DATABASE_URL", url)
    conteudo = _substituir_linha(conteudo, "DB_SSL_CA", ssl_ca)
    ARQUIVO_ENV.write_text(conteudo, encoding="utf-8")

    # Reflete a mudança sem exigir restart do servidor.
    settings.database_url = url
    settings.db_ssl_ca = ssl_ca
    recarregar_engine()
