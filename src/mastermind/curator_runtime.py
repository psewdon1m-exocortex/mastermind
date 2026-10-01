"""Compatibility import for the Bibliotekar local runtime."""
import sys

from . import bibliotekar_runtime as _implementation

sys.modules[__name__] = _implementation
