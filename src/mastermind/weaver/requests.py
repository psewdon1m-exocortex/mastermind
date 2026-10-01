"""Typed internal work orders. HTTP/Bridge adapters retain their own authentication."""
from dataclasses import dataclass, field
from typing import Literal

from .graph import Scope


@dataclass(frozen=True)
class Lookup:
    query: str
    scope: Scope = field(default_factory=lambda: Scope('owner'))
    filters: dict = field(default_factory=dict)
    deadline: float | None = None
    limit: int = 20


@dataclass(frozen=True)
class Similar:
    path: str
    text: str
    focus: str = ''
    scope: Scope = field(default_factory=lambda: Scope('owner'))


@dataclass(frozen=True)
class Walk:
    path: str
    scope: Scope = field(default_factory=lambda: Scope('owner'))
    direction: Literal['outgoing', 'incoming', 'both'] = 'both'
    depth: int = 2
    limit: int = 64


@dataclass(frozen=True)
class Placement:
    understanding: dict
    text: str
    snapshot: dict
    profile: Literal['crusher'] = 'crusher'
    operation_id: str | None = None
    deadline: float | None = None


@dataclass(frozen=True)
class ExecutePlacement:
    job: object
    content: dict
    plan: dict
    profile: Literal['crusher'] = 'crusher'
