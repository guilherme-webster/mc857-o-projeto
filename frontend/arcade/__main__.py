"""Run the Arcade configuration-screen prototype."""

from __future__ import annotations

import arcade

from frontend.arcade.parameters_view import create_parameters_window


def main() -> None:
    """Open the configuration view and enter Arcade's event loop."""

    create_parameters_window()
    arcade.run()


if __name__ == "__main__":
    main()
