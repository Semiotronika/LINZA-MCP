"""Console entry points for LINZA."""

from __future__ import annotations

import argparse

import anyio

from .compat import __version__
from .server import main as server_main


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="linza-mcp",
        description="Run the LINZA MCP stdio server.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"linza-mcp {__version__}",
    )
    parser.parse_args(argv)
    anyio.run(server_main)
