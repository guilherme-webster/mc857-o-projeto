"""Copy and paste for the hand-drawn single-line text fields.

The seed fields of the tournament and grid screens are drawn by the views
themselves (not Arcade GUI widgets), so they only receive ``on_text`` and
``on_key_press``. This module adds the usual Ctrl+C / Ctrl+V shortcuts on top
of those events, using the system clipboard exposed by the pyglet window.

Seeds are the reason this exists: a tournament or grid is reproduced by typing
the same seed again (#105), so the value must travel between runs, saved
tournaments and other people without being retyped digit by digit.

Contract: copy never changes the field; paste *replaces* the whole field,
because a seed is a single value and appending to a previous one would
silently build a different seed. Validation stays where it already is
(``parse_optional_seed`` when the value is used).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import arcade


class ClipboardWindow(Protocol):
    """The part of ``pyglet.window.Window`` used here; tests pass a fake."""

    def get_clipboard_text(self) -> str: ...

    def set_clipboard_text(self, text: str) -> None: ...


@dataclass(frozen=True)
class ClipboardResult:
    """Outcome of a shortcut: the new field text and a status message."""

    text: str
    message: str
    ok: bool = True


def handle_clipboard_shortcut(
    window: ClipboardWindow, symbol: int, modifiers: int, text: str
) -> ClipboardResult | None:
    """Apply Ctrl+C / Ctrl+V (Cmd on macOS) to a focused field.

    Returns ``None`` when the key is not a clipboard shortcut, so the caller
    keeps its own handling (Backspace, Enter, ...). Clipboard failures (no
    clipboard owner, unsupported platform) are reported, never raised: the
    field is left unchanged.
    """

    if not modifiers & arcade.key.MOD_ACCEL:
        return None
    if symbol == arcade.key.C:
        if not text:
            return ClipboardResult(text, "Campo vazio: nada para copiar.", ok=False)
        try:
            window.set_clipboard_text(text)
        except Exception:  # noqa: BLE001 - system clipboard is an external boundary
            return ClipboardResult(text, "Não foi possível copiar.", ok=False)
        return ClipboardResult(text, f"Semente {text} copiada.")
    if symbol == arcade.key.V:
        try:
            pasted = window.get_clipboard_text() or ""
        except Exception:  # noqa: BLE001 - system clipboard is an external boundary
            return ClipboardResult(text, "Não foi possível colar.", ok=False)
        # Only the first line counts: copying from a terminal or document often
        # brings a trailing newline or surrounding spaces along with the seed.
        lines = pasted.strip().splitlines()
        value = lines[0].strip() if lines else ""
        if not value:
            return ClipboardResult(text, "Área de transferência vazia.", ok=False)
        return ClipboardResult(value, f"Semente {value} colada.")
    return None
