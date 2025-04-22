"""
Recursive dataclass → argparse bridge with type‑safe dispatch.
"""

from __future__ import annotations
import argparse, dataclasses as _dc
from dataclasses import MISSING
from typing import (Any, Callable, Generic, Protocol, ClassVar,
                    TypeVar, Annotated, get_args, get_origin)

# Define a protocol capturing 'dataclass-ness'
class _DataclassType(Protocol):
    __dataclass_fields__: ClassVar[dict[str, _dc.Field[Any]]] # pyright: ignore[reportExplicitAny]


# --------------------------------------------------------------------------- #
T = TypeVar('T', bound=_DataclassType)
U = TypeVar('U', bound=_DataclassType)
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


def _add_dataclass_arguments(parser: argparse.ArgumentParser, cls: type) -> None:
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


def _namespace_to_dataclass(ns: argparse.Namespace, cls: type[T]) -> T:
    vals = {f.name: getattr(ns, f.name) for f in _dc.fields(cls)}
    return cls(**vals)  # type: ignore[arg-type]


class SubParsers(object):
    """Internal wrapper; users obtain it via the `ArgumentParser` factory."""
    _subparsers: argparse.Action

    # ---- construction ---------------------------------------------------- #
    def __init__(self, subparsers: argparse.Action) -> None:
        self._subparsers = subparsers

    # ---- API surface ----------------------------------------------------- #
    def add_parser(self,
                   name: str,
                   schema: type[_DataclassType],
                   handler: Handler[_DataclassType]|None=None) -> ArgumentParser:
        subparser = self._subparsers.add_parser(name)
        _add_dataclass_arguments(subparser, schema)
        if handler is not None:
            subparser.set_defaults(func=handler)
        return ArgumentParser(subparser)


# --------------------------------------------------------------------------- #
class ArgumentParser(object):
    """Internal wrapper; users obtain it via the `ArgumentParser` factory."""

    _parser: argparse.ArgumentParser

    # ---- construction ---------------------------------------------------- #
    def __init__(self,
                 _parser: argparse.ArgumentParser | None = None,
                 **kwargs: Any) -> None: # pyright: ignore[reportExplicitAny,reportAny]
        self._parser = _parser or argparse.ArgumentParser(**kwargs) # pyright: ignore[reportAny]

    # ---- API surface ----------------------------------------------------- #
    def add_arguments(self,
                      schema: type[_DataclassType],
                      handler: Handler[_DataclassType]|None=None) -> None:
        _add_dataclass_arguments(self._parser, schema)
        self._parser.set_defaults(_handler=handler, _schema=schema)

    def add_argument(self, # pyright: ignore[reportAny]
                     *args: Any, **kwargs: Any) -> Any: # pyright: ignore[reportExplicitAny,reportAny]
        return self._parser.add_argument(*args, **kwargs) # pyright: ignore[reportAny]

    def add_subparsers(self,
                       **kwargs: Any) -> SubParsers: # pyright: ignore[reportExplicitAny,reportAny]
        subparsers = self._parser.add_subparsers(**kwargs) # pyright: ignore[reportAny]
        return SubParsers(subparsers)

    # ---- parsing --------------------------------------------------------- #
    def parse_args(self, argv: list[str]|None = None) -> Result[_DataclassType]:
        ns: argparse.Namespace = self._parser.parse_args(argv)

        if not hasattr(ns, '_schema'):
            raise ValueError("No schema found in Namespace")

        args: _DataclassType = _namespace_to_dataclass(ns, ns._schema)

        return Result(args, ns, ns._handler)

        # dataclass root without sub‑parsers
        if hasattr(ns, '_handler') is False and self._subparsers is None and self._root_cls is not None:
            args: _DataclassType = _namespace_to_dataclass(ns, self._root_cls)  # type: ignore[arg-type]
            return Result(args, ns, None)

        # descend until the deepest leaf has stamped _cls/_handler
        if not hasattr(ns, '_cls'):
            self._parser.error("No valid sub‑command given")  # pragma: no cover

        cls: type[Generic[U]] = ns._cls               # set by leaf
        handler: Optional[Handler[Any]] = ns._handler  # type: ignore[attr-defined]
        # scrub helpers for clean Namespace → dataclass
        for x in ('_cls', '_handler', '_cmd'):
            if hasattr(ns, x):
                delattr(ns, x)

        args = _namespace_to_dataclass(ns, cls)
        return Result(args, handler)
