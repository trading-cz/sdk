"""Top-level `tradingcz` namespace for the trading-model repo.

The generated models live under `generated/tradingcz/...`.

When installing from a built wheel, Hatch packages `generated/tradingcz` directly,
so `import tradingcz.model` works normally.

When installing in editable mode from a local checkout, the project root is on
`sys.path`, but `generated/` is not necessarily on `sys.path`. This shim ensures
that `generated/tradingcz` is discoverable, making `import tradingcz.model...`
work consistently for local development.
"""

from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path

# Allow `tradingcz.*` portions from multiple distributions.
__path__ = extend_path(__path__, __name__)

_generated_tradingcz = Path(__file__).resolve().parents[1] / "generated" / "tradingcz"
if _generated_tradingcz.is_dir():
    __path__.append(str(_generated_tradingcz))
