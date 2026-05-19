"""Core compatibility exports for LINZA.

`LinzaCore` now delegates to package modules while preserving the public import
path used by tests, scripts, and older local workflows.
"""

from .compat import LinzaCore, tokenize

__all__ = ["LinzaCore", "tokenize"]
