"""Rotulo de botao que cabe na caixa, mesmo em janela menor ou com outra fonte.

Os botoes tem largura fixa; sem ajuste, um rotulo mais largo que a caixa passa
da borda. A funcao reduz a fonte a partir do tamanho normal, ate caber ou ate
``MIN_BUTTON_FONT_SIZE``. Como parte sempre do tamanho base, o texto volta ao
tamanho normal quando ha espaco.
"""

from __future__ import annotations

import arcade

MIN_BUTTON_FONT_SIZE = 8


def fit_button_text(text: arcade.Text, max_width: float, base_size: float) -> None:
    """Ajuste o tamanho da fonte de ``text`` para que caiba em ``max_width`` px."""

    size = base_size
    text.font_size = size
    while text.content_width > max_width and size > MIN_BUTTON_FONT_SIZE:
        size -= 1
        text.font_size = size
