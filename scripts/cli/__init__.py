"""PurrCat CLI package"""

from .cmd_setup import run_setup
from .cmd_start import run_start

__all__ = ["run_setup", "run_start"]
