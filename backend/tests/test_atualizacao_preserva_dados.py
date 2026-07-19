"""Atualizar a versão não pode custar o trabalho já feito pelo aluno.

Quem está na versão anterior tem o banco do chatbot **na própria máquina**, com empresa,
chave do Groq, produtos/serviços e o treinamento da IA (blocos de RAG) já cadastrados.
A versão nova só acrescenta as tabelas das rotas de IA — nada pode ser recriado nem
apagado no caminho.
"""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.bootstrap import garantir_colunas
from app.database import Base
from app.models import Configuracao, Item, RagBloco, Usuario

# Tabelas que a versão nova acrescenta. O aluno não tem nenhuma delas.
TABELAS_NOVAS = {"rotas_ia", "rota_campos", "sessoes_chat"}


@pytest.fixture
def banco_da_versao_anterior(tmp_path):
    """Banco como ele existe na máquina do aluno hoje: sem as tabelas das rotas de IA."""
    engine = create_engine(f"sqlite:///{tmp_path}/aluno.db")

    antigas = [t for t in Base.metadata.sorted_tables if t.name not in TABELAS_NOVAS]
    Base.metadata.create_all(bind=engine, tables=antigas)

    with Session(engine) as s:
        s.add(Configuracao(id=1, nome_empresa="Pizzaria do Aluno",
                           numero_whatsapp="5561999998888", groq_api_key="gsk_ja_cadastrada"))
        s.add(Usuario(nome="Aluno", email="aluno@escola.br", senha_hash="hash", papel="admin"))
        s.add(Item(nome="Pizza Calabresa", descricao="grande", preco=45))
        s.add(Item(nome="Refrigerante", descricao="2L", preco=12))
        s.add(RagBloco(tipo="fazer", titulo="Tom", conteudo="ser simpatico e objetivo"))
        s.add(RagBloco(tipo="nao_fazer", titulo="Precos", conteudo="nunca inventar preco"))
        s.commit()
    return engine


def _atualizar(engine):
    """Exatamente o que o arranque da versão nova faz."""
    Base.metadata.create_all(bind=engine)
    garantir_colunas(engine)


def test_tabelas_novas_sao_criadas(banco_da_versao_anterior):
    antes = set(inspect(banco_da_versao_anterior).get_table_names())
    assert not (TABELAS_NOVAS & antes)

    _atualizar(banco_da_versao_anterior)

    assert TABELAS_NOVAS <= set(inspect(banco_da_versao_anterior).get_table_names())


def test_nada_do_aluno_se_perde(banco_da_versao_anterior):
    _atualizar(banco_da_versao_anterior)

    with Session(banco_da_versao_anterior) as s:
        config = s.get(Configuracao, 1)
        assert config.nome_empresa == "Pizzaria do Aluno"
        assert config.groq_api_key == "gsk_ja_cadastrada"   # não precisa recadastrar
        assert s.query(Item).count() == 2                    # produtos intactos
        assert s.query(RagBloco).count() == 2                # treinamento da IA intacto
        assert s.query(Usuario).count() == 1                 # continua logando


def test_atualizar_de_novo_nao_mexe_em_nada(banco_da_versao_anterior):
    """`run.bat` roda toda vez; a segunda passagem tem de ser inofensiva."""
    _atualizar(banco_da_versao_anterior)
    _atualizar(banco_da_versao_anterior)

    with Session(banco_da_versao_anterior) as s:
        assert s.query(Item).count() == 2
        assert s.query(RagBloco).count() == 2
