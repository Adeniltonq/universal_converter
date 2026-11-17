#!/usr/bin/env python3
"""Universal Converter — iniciador que funciona sem instalar o pacote."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from universal_converter.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
