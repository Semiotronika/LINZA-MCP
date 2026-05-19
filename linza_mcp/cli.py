"""Console entry points for LINZA."""

from __future__ import annotations

import anyio

from .server import main as server_main


def main() -> None:
    anyio.run(server_main)
