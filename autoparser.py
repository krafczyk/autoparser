"""
Recursive dataclass → argparse bridge with type‑safe dispatch.
"""

from __future__ import annotations
import argparse, dataclasses as _dc
from dataclasses import MISSING
from typing import (Any, Callable, Protocol, ClassVar,
                    TypeVar, Annotated, get_args, get_origin)

# Define a protocol capturing 'dataclass-ness'
class _DataclassType(Protocol):
    __dataclass_fields__: ClassVar[dict[str, _dc.Field[Any]]] # pyright: ignore[reportExplicitAny]


# --------------------------------------------------------------------------- #
T = TypeVar('T', bound=_DataclassType)
Handler = Callable[[T], None]


class Arg:
    """Attach argparse options to a dataclass field via `Annotated[..., Arg(...)]`."""
    __slots__: tuple[str, ...] = ('flags', 'kwargs')
    # declare types for slot attributes
    flags: tuple[str,...]
    kwargs: dict[str, object]

    def __init__(self, *flags: str, **kwargs: object):
        self.flags = flags
        self.kwargs = kwargs


# --------------------------------------------------------------------------- #
def _is_dataclass(cls: type) -> bool:
    return _dc.is_dataclass(cls)


def _extract_field_options(ann: object) -> tuple[object, tuple[str, ...], dict[str, Any]]: # pyright: ignore[reportExplicitAny]
    """Return (base_type, flags, argparse_kwargs)."""
    if get_origin(ann) is Annotated:
        base, *meta = get_args(ann) # pyright: ignore[reportAny]
        arg_meta = next((m for m in meta if isinstance(m, Arg)), None) # pyright: ignore[reportAny]
        flags = arg_meta.flags if arg_meta and arg_meta.flags else ()
        kwargs = dict(arg_meta.kwargs) if arg_meta else {}
        return base, flags, kwargs
    return ann, (), {}


def AddDataclassArguments(parser: argparse.ArgumentParser, cls: type) -> None:
    if not _is_dataclass(cls):
        raise TypeError(f"Expected dataclass, got {cls}")

    for f in _dc.fields(cls):
        typ, flags, kw = _extract_field_options(f.type)

        # Positional if we have a single flag
        positional = False
        if len(flags) == 0:
            positional = True

        # default flags: positional if none given
        if positional:
            if typ is bool:  # positional bool is useless – force option
                flags = (f"--{f.name.replace('_', '-')}",)
            else:
                flags = (f.name,)

        # implicit behaviour for bool
        if typ is bool:
            if 'action' not in kw:
                kw['action'] = 'store_false' if f.default is True else 'store_true'
        else:
            _ = kw.setdefault('type', typ) # pyright: ignore[reportAny]

        # required vs optional
        if f.default is not MISSING or f.default_factory is not MISSING:
            _ = kw.setdefault('default', f.default) # pyright: ignore[reportAny]

        if positional:
            _ = parser.add_argument(*flags, **kw) # pyright: ignore[reportAny]
        else:
            _ = parser.add_argument(*flags, dest=f.name, **kw) # pyright: ignore[reportAny]


def NamespaceToDataclass(ns: argparse.Namespace, cls: type[T]) -> T:
    vals = {f.name: getattr(ns, f.name) for f in _dc.fields(cls)}
    return cls(**vals)  # type: ignore[arg-type]
