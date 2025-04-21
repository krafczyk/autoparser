"""
Recursive dataclass → argparse bridge with type‑safe dispatch.
"""

from __future__ import annotations
import argparse, dataclasses as _dc
from dataclasses import MISSING
from typing import (Any, Callable, Generic, Protocol, ClassVar, overload,
                    TypeVar, Annotated, get_args, get_origin)

# Define a protocol capturing 'dataclass-ness'
class _DataclassType(Protocol):
    __dataclass_fields__: ClassVar[dict[str, _dc.Field[Any]]] # pyright: ignore[reportExplicitAny]

# --------------------------------------------------------------------------- #
T = TypeVar('T', bound=_DataclassType)
U = TypeVar('U', bound=_DataclassType)
Handler = Callable[[T], None]


class Result(Generic[T]):
    __slots__: tuple[str,...] = ('args', 'func')
    def __init__(self, args: T, func: Handler[T] | None=None):
        self.args: T = args
        self.func: Handler[T]|None = func


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


# --------------------------------------------------------------------------- #
class _Parser(Generic[T]):
    """Internal wrapper; users obtain it via the `ArgumentParser` factory."""

    _parser: argparse.ArgumentParser
    _root_cls: type[T] | None
    _names_left: set[str]

    # ---- construction ---------------------------------------------------- #
    def __init__(self, schema: type[T]|tuple[str],
                 *,
                 _parser: argparse.ArgumentParser | None = None, **kwargs: Any) -> None: # pyright: ignore[reportExplicitAny,reportAny]
        self._parser = _parser or argparse.ArgumentParser(**kwargs) # pyright: ignore[reportAny]
        self._subparsers: argparse._SubParsersAction[Any]|None = None # pyright: ignore[reportExplicitAny,reportPrivateUsage]

        if type(schema) is tuple:
            names: set[str] = set(schema)
            if not names:
                raise ValueError("tuple[str,...] must list at least one sub‑command")
            self._root_cls = None
            self._names_left = names
            self._subparsers = self._parser.add_subparsers(dest='_cmd', required=True)
        elif _is_dataclass(schema):
            self._root_cls = schema
            _add_dataclass_arguments(self._parser, schema)
        else:
            raise TypeError("schema must be dataclass or tuple[str,...]")

    # ---- API surface ----------------------------------------------------- #
    def add_subparser(self,
                      name: str,
                      schema: type[U],
                      func: Handler[U]|None = None) -> _Parser[U]:
        """Define a sub‑command.  Returns a *new* _Parser for further nesting."""
        if self._subparsers is None:
            raise RuntimeError("Cannot add subparsers when root is a dataclass")

        if name not in self._names_left:
            raise ValueError(f"Unknown subcommand '{name}' " + \
                             f"(expected one of {sorted(self._names_left)})")
        self._names_left.remove(name)

        sub: argparse.ArgumentParser = self._subparsers.add_parser(name)
        child = _Parser(schema, _parser=sub)

        # leaf? (dataclass + handler)
        if _is_dataclass(schema):
            if func is None:
                raise ValueError("Leaf subparser requires a handler")
            sub.set_defaults(_cls=schema, _handler=func)
        elif func is not None:
            raise ValueError("Handler can only be attached to a dataclass leaf")

        return child

    # ---- parsing --------------------------------------------------------- #
    def parse_args(self, argv: list[str]|None = None) -> Result[T]:
        ns = self._parser.parse_args(argv)

        # dataclass root without sub‑parsers
        if hasattr(ns, '_handler') is False and self._subparsers is None and self._root_cls is not None:
            args: _DataclassType = _namespace_to_dataclass(ns, self._root_cls)  # type: ignore[arg-type]
            return Result(args, None)

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


# --------------------------------------------------------------------------- #

# factory with overloads
@overload
def ArgumentParser(schema: type[T]) -> _Parser[T]: ...
@overload
def ArgumentParser(schema: tuple[str,...]) -> _Parser[_DataclassType]: ...
def ArgumentParser(schema) -> _Parser:  # noqa: N802 D401
    """Factory returning a parser builder."""
    return _Parser(schema)
