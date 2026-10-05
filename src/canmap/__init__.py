"""canmap — YAML-карта сигналов как единственный источник правды."""

__version__ = "0.1.0"

from .loader import load, loads  # noqa: E402
from .model import CanMap  # noqa: E402
from .validate import check, validate_file, validate_text  # noqa: E402

__all__ = ["CanMap", "check", "load", "loads", "validate_file", "validate_text", "__version__"]
