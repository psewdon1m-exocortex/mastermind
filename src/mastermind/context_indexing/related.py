"""Compatibility import for pre-Weaver clients and durable job tooling."""
import sys

from ..weaver import related as _implementation

sys.modules[__name__] = _implementation
