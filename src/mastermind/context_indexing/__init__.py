"""Compatibility facade. New consumers use mastermind.weaver.Weaver."""
from ..weaver import Scope, Weaver

ContextIndexing = Weaver
__all__ = ["ContextIndexing", "Scope"]
