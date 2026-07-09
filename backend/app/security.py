"""Segurança: hashing de senha (bcrypt) e tokens de sessão (JWT).

`hash_senha`/`verificar_senha` guardam e conferem senhas com bcrypt. `criar_token_acesso`
emite um JWT assinado (HS256) com o id do usuário e expiração; `decodificar_token_acesso`
o valida e devolve o id, ou `None` se inválido/expirado. Usado por `app.routers.auth`
(emissão) e `app.deps` (validação).
"""

import datetime

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def hash_senha(senha_texto_puro: str) -> str:
    hash_bytes = bcrypt.hashpw(senha_texto_puro.encode("utf-8"), bcrypt.gensalt())
    return hash_bytes.decode("utf-8")


def verificar_senha(senha_texto_puro: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(senha_texto_puro.encode("utf-8"), senha_hash.encode("utf-8"))


def criar_token_acesso(usuario_id: int) -> str:
    expira_em = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=settings.jwt_expire_minutes
    )
    payload = {"sub": str(usuario_id), "exp": expira_em}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decodificar_token_acesso(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None
