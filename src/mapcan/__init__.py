"""mapcan: a YAML signal map as the single source of truth."""

__version__ = "0.23.2"

from .loader import load, loads  # noqa: E402
from .model import MapCan  # noqa: E402
from .validate import check, validate_file, validate_text  # noqa: E402

__all__ = ["MapCan", "check", "load", "loads", "validate_file", "validate_text", "__version__"]
