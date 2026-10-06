"""mapcan — YAML-карта сигналов как единственный источник правды."""

__version__ = "0.13.0"

from .loader import load, loads  # noqa: E402
from .model import MapCan  # noqa: E402
from .validate import check, validate_file, validate_text  # noqa: E402

__all__ = ["MapCan", "check", "load", "loads", "validate_file", "validate_text", "__version__"]
