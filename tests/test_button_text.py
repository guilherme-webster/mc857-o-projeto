"""Rotulos de botao reduzem a fonte para caber na caixa, sem janela."""

from __future__ import annotations

import unittest

from frontend.arcade.button_text import MIN_BUTTON_FONT_SIZE, fit_button_text


class FakeText:
    """Mede como um texto real: largura proporcional ao tamanho da fonte.

    ``arcade.Text`` so mede com uma janela aberta, entao o teste usa esta
    aproximacao linear.
    """

    def __init__(self, text: str, font_size: float) -> None:
        self.text = text
        self.font_size = font_size

    @property
    def content_width(self) -> float:
        return len(self.text) * self.font_size * 0.6


class FitButtonTextTest(unittest.TestCase):
    def test_short_label_keeps_the_base_size(self) -> None:
        text = FakeText("Abrir", 13)

        fit_button_text(text, 300, 13)

        self.assertEqual(text.font_size, 13)

    def test_long_label_shrinks_until_it_fits(self) -> None:
        text = FakeText("Resultado do torneio", 13)

        fit_button_text(text, 100, 13)

        self.assertLess(text.font_size, 13)
        self.assertLessEqual(text.content_width, 100)

    def test_never_goes_below_the_minimum_size(self) -> None:
        text = FakeText("Resultado do torneio", 13)

        fit_button_text(text, 1, 13)

        self.assertEqual(text.font_size, MIN_BUTTON_FONT_SIZE)

    def test_grows_back_to_the_base_size_when_there_is_room(self) -> None:
        text = FakeText("Resultado do torneio", 13)
        fit_button_text(text, 1, 13)

        fit_button_text(text, 1000, 13)

        self.assertEqual(text.font_size, 13)


if __name__ == "__main__":
    unittest.main()
