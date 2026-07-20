"""Toda ação precisa dizer ao usuário o que aconteceu.

Vários fluxos redirecionavam em silêncio: o admin clicava, a tela trocava e ele não
sabia se deu certo, se ainda estava processando ou se falhou. Estes testes fixam o
contrato: confirmação antes de ações destrutivas, e mensagem depois.
"""

import pytest

from app.models import Configuracao


@pytest.fixture
def config_com_numero(db_session, config_empresa):
    config = db_session.get(Configuracao, 1)
    config.numero_whatsapp = "5561999998888"
    db_session.commit()
    return config


class TestWhatsApp:
    def test_trocar_numero_pede_confirmacao(self, admin_client, config_empresa):
        """Trocar o número derruba a sessão ativa — não pode ser um clique solto."""
        html = admin_client.get("/painel/whatsapp").text
        assert 'action="/painel/whatsapp/numero"' in html
        assert "data-confirmar" in html

    def test_trocar_numero_sinaliza_sucesso(self, admin_client, config_com_numero):
        resp = admin_client.post(
            "/painel/whatsapp/numero",
            data={"numero_whatsapp": "5511988887777"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/painel/whatsapp?ok=numero"

    def test_mensagem_de_sucesso_chega_na_tela(self, admin_client, config_empresa):
        html = admin_client.get("/painel/whatsapp?ok=numero").text
        # `tojson` escapa acentos (Número), entao a comparacao usa trecho sem acento.
        assert "atualizado. Gere um novo QR" in html
        assert 'UI.aviso(' in html and '"ok")' in html

    def test_numero_invalido_explica_o_formato(self, admin_client, config_empresa):
        resp = admin_client.post(
            "/painel/whatsapp/numero", data={"numero_whatsapp": "abc"},
            follow_redirects=False,
        )
        assert resp.headers["location"] == "/painel/whatsapp?erro=numero"
        html = admin_client.get("/painel/whatsapp?erro=numero").text
        assert "10 a 15 d" in html and '"erro")' in html

    def test_pareamento_cancelado_explica_as_causas(self, admin_client, config_empresa):
        """Número inexistente gera QR e a sessão é cancelada — antes, em silêncio."""
        html = admin_client.get("/painel/whatsapp?erro=pareamento_cancelado").text
        # `tojson` escapa acentos e tags (`<b>` vira <b>): comparamos o que
        # sobra em ASCII puro.
        assert "no WhatsApp" in html
        assert "expirou" in html
        assert "gere um novo QR" in html

    def test_desconectar_pede_confirmacao(self):
        """O bloco "conectado" s\u00f3 \u00e9 renderizado com sess\u00e3o ativa de verdade.

        Montar esse estado exigiria um provedor falso conectado; como o que importa aqui
        \u00e9 o markup da confirma\u00e7\u00e3o, conferimos direto no template.
        """
        from pathlib import Path

        import app.templates as _  # noqa: F401 - s\u00f3 para localizar o pacote

        tpl = Path(__file__).resolve().parent.parent / "app" / "templates" / "whatsapp_connect.html"
        conteudo = tpl.read_text(encoding="utf-8")

        i = conteudo.index('action="/painel/whatsapp/desconectar"')
        trecho = conteudo[i:i + 400]
        assert "data-confirmar" in trecho
        assert "data-perigo" in trecho


class TestConfirmacoes:
    def test_zona_de_perigo_confirma_antes_de_apagar(self, admin_client, config_empresa):
        html = admin_client.get("/painel/config").text
        assert "data-confirmar" in html
        assert "data-perigo" in html
        assert "confirm(" not in html   # nao usa mais o dialogo do navegador

    def test_excluir_item_confirma(self, admin_client, config_empresa):
        html = admin_client.get("/painel/itens").text
        assert "confirm(" not in html


class TestGroq:
    def test_erro_da_chave_volta_em_json(self, admin_client, config_empresa, monkeypatch):
        """O formulário envia por fetch para mostrar 'validando…' e o resultado."""
        monkeypatch.setattr(
            "app.routers.integracao.validar_chave_groq",
            lambda chave: (False, "Chave recusada pelo Groq."),
        )
        resp = admin_client.post(
            "/painel/integracao/groq",
            data={"groq_api_key": "gsk_invalida"},
            headers={"X-Requested-With": "fetch"},
        )
        assert resp.status_code == 400
        assert resp.json()["erro"] == "Chave recusada pelo Groq."

    def test_sucesso_devolve_mensagem_e_destino(self, admin_client, config_empresa, monkeypatch):
        monkeypatch.setattr(
            "app.routers.integracao.validar_chave_groq", lambda chave: (True, "ok")
        )
        resp = admin_client.post(
            "/painel/integracao/groq",
            data={"groq_api_key": "gsk_valida"},
            headers={"X-Requested-With": "fetch"},
        )
        corpo = resp.json()
        assert corpo["ok"] is True
        assert "salva" in corpo["mensagem"]
        assert corpo["destino"] == "/painel/itens"


class TestCacheDeEstaticos:
    """Depois de um `git pull`, o navegador não pode servir o CSS antigo.

    Foi o que aconteceu com os ícones da lista de rotas: o HTML novo pedia
    `.btn-icone svg { width:16px }`, o navegador usava o CSS em cache sem essa regra, e
    o SVG aparecia sem tamanho. A versão no link muda junto com o arquivo.
    """

    def test_link_do_css_leva_versao(self, admin_client, config_empresa):
        html = admin_client.get("/painel/rotas").text
        assert "/static/style.css?v=" in html
        assert "/static/ui.js?v=" in html

    def test_versao_muda_quando_o_arquivo_muda(self, tmp_path, monkeypatch):
        """Sem isto o link ficaria fixo e o cache do navegador nunca seria invalidado."""
        import os

        from app import templating

        arquivo = tmp_path / "style.css"
        arquivo.write_text("a{}", encoding="utf-8")
        monkeypatch.setattr(templating, "STATIC_DIR", tmp_path)

        antes = templating.estatico("style.css")

        # mtime tem granularidade de 1s em alguns sistemas: fixamos um valor futuro em
        # vez de reescrever e torcer para o relógio ter avançado.
        os.utime(arquivo, (0, 1_700_000_000))
        depois = templating.estatico("style.css")

        assert antes != depois
        assert depois.endswith("?v=1700000000")

    def test_arquivo_inexistente_nao_quebra_a_pagina(self):
        from app.templating import estatico

        assert estatico("nao-existe.css") == "/static/nao-existe.css"
