"""O handler de OperationalError não pode disfarçar erro de schema de "perdi a conexão".

Quando disfarça, o usuário é devolvido ao assistente de conexão; ele reconecta, o erro
acontece de novo e o cadastro nunca conclui — o loop infinito relatado em produção.
Só código de conexão de verdade (servidor inacessível) justifica esse desvio.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import banco_fora_do_ar


def _erro(codigo: int, mensagem: str) -> OperationalError:
    """OperationalError com o `orig` do pymysql, que é de onde o código é lido."""
    original = Exception(codigo, mensagem)
    original.args = (codigo, mensagem)
    return OperationalError("SELECT 1", {}, original)


@pytest.fixture
def app_com_handler():
    app = FastAPI()
    app.add_exception_handler(OperationalError, banco_fora_do_ar)

    @app.get("/coluna-faltando")
    def coluna_faltando():
        raise _erro(1054, "Unknown column 'papel' in 'field list'")

    @app.get("/servidor-fora")
    def servidor_fora():
        raise _erro(2003, "Can't connect to MySQL server on 'localhost'")

    return app


def test_erro_de_schema_nao_devolve_o_assistente(app_com_handler):
    """1054 é bug de schema: deve estourar como erro real, não virar tela de conexão."""
    cliente = TestClient(app_com_handler, raise_server_exceptions=False)
    resposta = cliente.get("/coluna-faltando")

    assert resposta.status_code == 500
    assert "Conectar o banco" not in resposta.text


def test_servidor_inacessivel_ainda_devolve_o_assistente(app_com_handler):
    """2003 é conexão de verdade: aí sim vale reabrir o assistente com orientação."""
    cliente = TestClient(app_com_handler, raise_server_exceptions=False)
    resposta = cliente.get("/servidor-fora")

    assert resposta.status_code == 503
    assert "Docker" in resposta.text  # localhost -> orienta sobre o container local
