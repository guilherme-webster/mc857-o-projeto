"""Atalhos de copiar e colar dos campos de semente (#105), sem janela."""

from __future__ import annotations

import unittest

try:
    import arcade

    from frontend.arcade.clipboard import handle_clipboard_shortcut
except ModuleNotFoundError as error:
    if error.name != "arcade":
        raise
    arcade = None  # type: ignore[assignment]


class FakeClipboardWindow:
    """Stand-in for the pyglet window: stores the clipboard in memory."""

    def __init__(self, content: str = "", *, broken: bool = False) -> None:
        self.content = content
        self.broken = broken

    def get_clipboard_text(self) -> str:
        if self.broken:
            raise RuntimeError("no clipboard owner")
        return self.content

    def set_clipboard_text(self, text: str) -> None:
        if self.broken:
            raise RuntimeError("no clipboard owner")
        self.content = text


@unittest.skipIf(arcade is None, "requires Arcade")
class ClipboardShortcutTest(unittest.TestCase):
    def test_ctrl_c_copies_without_changing_the_field(self) -> None:
        window = FakeClipboardWindow()

        result = handle_clipboard_shortcut(
            window, arcade.key.C, arcade.key.MOD_ACCEL, "12345"
        )

        self.assertEqual(window.content, "12345")
        self.assertEqual(result.text, "12345")
        self.assertTrue(result.ok)

    def test_ctrl_v_replaces_the_field_with_the_first_trimmed_line(self) -> None:
        window = FakeClipboardWindow("  987654321\nresto da linha\n")

        result = handle_clipboard_shortcut(
            window, arcade.key.V, arcade.key.MOD_ACCEL, "111"
        )

        self.assertEqual(result.text, "987654321")
        self.assertTrue(result.ok)

    def test_plain_keys_and_other_shortcuts_are_left_to_the_caller(self) -> None:
        window = FakeClipboardWindow("42")

        self.assertIsNone(handle_clipboard_shortcut(window, arcade.key.V, 0, "1"))
        self.assertIsNone(
            handle_clipboard_shortcut(
                window, arcade.key.BACKSPACE, arcade.key.MOD_ACCEL, "1"
            )
        )

    def test_empty_field_or_clipboard_and_failures_keep_the_field(self) -> None:
        empty_copy = handle_clipboard_shortcut(
            FakeClipboardWindow(), arcade.key.C, arcade.key.MOD_ACCEL, ""
        )
        empty_paste = handle_clipboard_shortcut(
            FakeClipboardWindow("   \n"), arcade.key.V, arcade.key.MOD_ACCEL, "7"
        )
        broken = handle_clipboard_shortcut(
            FakeClipboardWindow(broken=True),
            arcade.key.V,
            arcade.key.MOD_ACCEL,
            "7",
        )

        self.assertFalse(empty_copy.ok)
        self.assertEqual((empty_paste.text, empty_paste.ok), ("7", False))
        self.assertEqual((broken.text, broken.ok), ("7", False))


if __name__ == "__main__":
    unittest.main()
