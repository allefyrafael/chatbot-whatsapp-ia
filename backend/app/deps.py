"""Dependências compartilhadas de rota — o guarda de autenticação do painel.

`get_current_admin` lê o cookie `access_token`, valida o JWT e carrega o usuário.
Se algo falhar, levanta `NaoAutenticado`, que `app.main` converte em redirect para
`/login` (uma página de painel não deve devolver 401 cru ao navegador).
"""

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario
from app.security import decodificar_token_acesso

COOKIE_NAME = "access_token"


class NaoAutenticado(Exception):
    """Levantada quando o painel exige um admin logado e o cookie é ausente/inválido.

    Tratada em main.py com um exception handler que redireciona para /login
    (uma página de painel não deve responder 401 cru para o navegador).
    """


def get_current_admin(
    access_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
) -> Usuario:
    if not access_token:
        raise NaoAutenticado()

    usuario_id = decodificar_token_acesso(access_token)
    if usuario_id is None:
        raise NaoAutenticado()

    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NaoAutenticado()

    return usuario
