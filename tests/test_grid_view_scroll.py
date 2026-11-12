"""Rolagem da tabela de pilotos da tela de grid, sem janela.

A janela e substituida por um objeto com largura e altura: a logica de quantas
linhas cabem, de manter o piloto selecionado visivel e de mapear o clique para
a linha certa depende so dessas medidas.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    import arcade

    from frontend.arcade.grid_editor import ATTRIBUTES
    from frontend.arcade.grid_view import _TABLE_COLUMNS, ROW_HEIGHT, GridView
except ModuleNotFoundError as error:
    if error.name != "arcade":
        raise
    GridView = None  # type: ignore[assignment,misc]


class _FakeClient:
    def fetch_current_grid(self):
        return None

    def fetch_history_races(self, season):
        return {"races": []}


class _FakeWindow:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height


def _view(height: int, drivers: int) -> GridView:
    window = _FakeWindow(1280, height)
    with patch("arcade.get_window", return_value=window):
        view = GridView(client=_FakeClient())
    view.window = window
    view._draft = SimpleNamespace(
        entries=[{"driver_id": f"driver:{i}"} for i in range(drivers)],
        disclaimer=None,
    )
    return view


@unittest.skipIf(GridView is None, "requires arcade")
class GridScrollTest(unittest.TestCase):
    def test_visible_rows_follow_the_window_height(self) -> None:
        self.assertEqual(_view(900, 0)._visible_count(), 23)
        self.assertEqual(_view(600, 0)._visible_count(), 12)

    def test_small_window_still_shows_one_row(self) -> None:
        self.assertEqual(_view(200, 5)._visible_count(), 1)

    def test_scroll_is_clamped_to_the_last_page(self) -> None:
        view = _view(720, 30)
        view._scroll = 999
        view._clamp_scroll()
        self.assertEqual(view._scroll, 30 - view._visible_count())

    def test_selecting_below_the_page_scrolls_it_into_view(self) -> None:
        view = _view(720, 30)
        visible = view._visible_count()
        view._selected = "driver:25"
        view._ensure_selected_visible()
        self.assertLess(view._scroll, 26)
        self.assertGreaterEqual(view._scroll + visible, 26)

    def test_selecting_above_the_page_scrolls_back(self) -> None:
        view = _view(720, 30)
        view._scroll = 10
        view._selected = "driver:3"
        view._ensure_selected_visible()
        self.assertEqual(view._scroll, 3)

    def test_click_maps_to_the_row_under_the_scroll(self) -> None:
        view = _view(720, 30)
        view._scroll = 10
        top = view._table_top()
        # Centro da primeira linha visivel.
        self.assertEqual(
            view._row_at(100, top - ROW_HEIGHT / 2 + 1),
            "driver:10",
        )

    def test_side_box_controls_stay_inside_it_and_clear_the_table(self) -> None:
        view = _view(900, 3)
        view.window.width = 1280
        left = view._panel_left()
        box_right = view.window.width - 40
        for key, (x, _y, w, _h) in view._buttons().items():
            if key.startswith(("minus:", "plus:", "move-")):
                self.assertGreaterEqual(x, left, msg=key)
                self.assertLessEqual(x + w, box_right, msg=key)
        # Ultima coluna da tabela (texto alinhado a direita) termina em x=820.
        last_column = max(40 + x for _label, x, _anchor in _TABLE_COLUMNS)
        self.assertGreaterEqual(left, last_column + 10)

    def test_side_box_scrolls_and_hides_controls_outside_its_area(self) -> None:
        first = ATTRIBUTES[0].name
        last = ATTRIBUTES[-1].name
        view = _view(720, 3)
        view._panel_scroll = 0
        self.assertIn(f"minus:{first}", view._buttons())
        view._panel_scroll = 10_000
        view._clamp_panel_scroll()
        self.assertNotIn(f"minus:{first}", view._buttons())
        self.assertIn(f"minus:{last}", view._buttons())

    def test_wheel_over_the_side_box_scrolls_it_not_the_table(self) -> None:
        view = _view(720, 30)
        left = view._panel_left()
        view.on_mouse_scroll(left + 40, 300, 0, -3)
        self.assertEqual(view._panel_scroll, 3 * 32)
        self.assertEqual(view._scroll, 0)



    def test_wheel_scrolls_the_table_and_respects_bounds(self) -> None:
        view = _view(720, 30)
        view.on_mouse_scroll(100, 300, 0, -3)
        self.assertEqual(view._scroll, 3)
        view.on_mouse_scroll(100, 300, 0, 50)
        self.assertEqual(view._scroll, 0)
        # Fora da tabela (sobre o painel lateral) a roda nao rola a lista.
        view.on_mouse_scroll(1200, 300, 0, -3)
        self.assertEqual(view._scroll, 0)


if __name__ == "__main__":
    unittest.main()
