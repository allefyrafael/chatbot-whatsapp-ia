"""Botão de ícone não pode herdar o padding do botão comum.

Na lista de rotas, o ícone de editar aparecia e os de ativar/excluir ficavam em branco.
Causa: `.btn-icone { padding: 0 }` é uma classe (0,1,0) e perde para a regra genérica
`button[type="submit"] { padding: 9px 16px }` (0,1,1). Dentro de 30px de largura, 32px
de padding horizontal espremem o SVG até sumir. O de editar escapava por ser um `<a>`.

Como o CSS não é executado nos testes, conferimos o contrato no arquivo: todo seletor
que zera o padding do ícone precisa alcançar `button` com especificidade suficiente.
"""

from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "style.css"


@pytest.fixture(scope="module")
def css() -> str:
    return CSS.read_text(encoding="utf-8")


def _bloco(css: str, seletor: str) -> str:
    """Texto do bloco de regras que começa no seletor informado."""
    i = css.index(seletor)
    return css[i:css.index("}", i)]


def test_regra_base_alcanca_button(css):
    bloco = _bloco(css, ".btn-icone,")
    assert "button.btn-icone" in bloco
    assert "padding: 0" in bloco


def test_hover_tambem_alcanca_button(css):
    """`button[type="submit"]:hover` (0,2,1) supera `.btn-icone:hover` (0,2,0)."""
    bloco = _bloco(css, ".btn-icone:hover,")
    assert "button.btn-icone:hover" in bloco


def test_svg_tem_tamanho_explicito(css):
    """SVG sem width/height no atributo depende do CSS para não colapsar."""
    bloco = _bloco(css, ".btn-icone svg")
    assert "width: 16px" in bloco and "height: 16px" in bloco


def test_lista_de_rotas_usa_button_para_acoes(admin_client, config_empresa, db_session):
    """Fixa o cenário: as ações são <button>, e é por isso que a regra precisa alcançá-los."""
    from app.models import RotaIA

    db_session.add(RotaIA(
        nome="R", descricao="d", operacao="buscar", tabela="categorias",
    ))
    db_session.commit()

    html = admin_client.get("/painel/rotas").text
    assert '<button type="submit" class="btn-icone' in html
    assert 'class="btn-icone"' in html  # o link de editar
