from __future__ import annotations

import typing
from collections import OrderedDict
from collections.abc import Mapping as _Mapping
from enum import Enum, auto
from threading import RLock

if typing.TYPE_CHECKING:
    # We can only import Protocol if TYPE_CHECKING because it's a development
    # dependency, and is not available at runtime.
    from typing_extensions import Protocol

    class HasGettableStringKeys(Protocol):
        def keys(self) -> typing.Iterator[str]: ...

        def __getitem__(self, key: str) -> str: ...


__all__ = [
    "RecentlyUsedContainer",
    "HTTPHeaderDict",
    "GroupedDict",
]


# Key type
_KT = typing.TypeVar("_KT")
# Value type
_VT = typing.TypeVar("_VT")
# Default type
_DT = typing.TypeVar("_DT")

ValidHTTPHeaderSource = typing.Union[
    "HTTPHeaderDict",
    typing.Mapping[str, str],
    typing.Iterable[typing.Tuple[str, str]],
    "HasGettableStringKeys",
]


class _Sentinel(Enum):
    not_passed = auto()


def ensure_can_construct_http_header_dict(
    potential: object,
) -> ValidHTTPHeaderSource | None:
    if isinstance(potential, HTTPHeaderDict):
        return potential
    elif isinstance(potential, typing.Mapping):
        # Full runtime checking of the contents of a Mapping is expensive, so for the
        # purposes of typechecking, we assume that any Mapping is the right shape.
        return typing.cast(typing.Mapping[str, str], potential)
    elif isinstance(potential, typing.Iterable):
        # Similarly to Mapping, full runtime checking of the contents of an Iterable is
        # expensive, so for the purposes of typechecking, we assume that any Iterable
        # is the right shape.
        return typing.cast(typing.Iterable[typing.Tuple[str, str]], potential)
    elif hasattr(potential, "keys") and hasattr(potential, "__getitem__"):
        return typing.cast("HasGettableStringKeys", potential)
    else:
        return None


class RecentlyUsedContainer(typing.Generic[_KT, _VT], typing.MutableMapping[_KT, _VT]):
    """
    Provides a thread-safe dict-like container which maintains up to
    ``maxsize`` keys while throwing away the least-recently-used keys beyond
    ``maxsize``. Caution: RecentlyUsedContainer is deprecated and scheduled for
    removal in a next major of urllib3.future. It has been replaced by a more
    suitable implementation in ``urllib3.util.traffic_police``.

    :param maxsize:
        Maximum number of recent elements to retain.

    :param dispose_func:
        Every time an item is evicted from the container,
        ``dispose_func(value)`` is called.  Callback which will get called
    """

    _container: typing.OrderedDict[_KT, _VT]
    _maxsize: int
    dispose_func: typing.Callable[[_VT], None] | None
    lock: RLock

    def __init__(
        self,
        maxsize: int = 10,
        dispose_func: typing.Callable[[_VT], None] | None = None,
    ) -> None:
        super().__init__()
        self._maxsize = maxsize
        self.dispose_func = dispose_func
        self._container = OrderedDict()
        self.lock = RLock()

    def __getitem__(self, key: _KT) -> _VT:
        # Re-insert the item, moving it to the end of the eviction line.
        with self.lock:
            item = self._container.pop(key)
            self._container[key] = item
            return item

    def __setitem__(self, key: _KT, value: _VT) -> None:
        evicted_item = None
        with self.lock:
            # Possibly evict the existing value of 'key'
            try:
                # If the key exists, we'll overwrite it, which won't change the
                # size of the pool. Because accessing a key should move it to
                # the end of the eviction line, we pop it out first.
                evicted_item = key, self._container.pop(key)
                self._container[key] = value
            except KeyError:
                # When the key does not exist, we insert the value first so that
                # evicting works in all cases, including when self._maxsize is 0
                self._container[key] = value
                if len(self._container) > self._maxsize:
                    # If we didn't evict an existing value, and we've hit our maximum
                    # size, then we have to evict the least recently used item from
                    # the beginning of the container.
                    evicted_item = self._container.popitem(last=False)

        # After releasing the lock on the pool, dispose of any evicted value.
        if evicted_item is not None and self.dispose_func:
            _, evicted_value = evicted_item
            self.dispose_func(evicted_value)

    def __delitem__(self, key: _KT) -> None:
        with self.lock:
            value = self._container.pop(key)

        if self.dispose_func:
            self.dispose_func(value)

    def __len__(self) -> int:
        with self.lock:
            return len(self._container)

    def __iter__(self) -> typing.NoReturn:
        raise NotImplementedError(
            "Iteration over this class is unlikely to be threadsafe."
        )

    def clear(self) -> None:
        with self.lock:
            # Copy pointers to all values, then wipe the mapping
            values = list(self._container.values())
            self._container.clear()

        if self.dispose_func:
            for value in values:
                self.dispose_func(value)

    def keys(self) -> set[_KT]:  # type: ignore[override]
        with self.lock:  # Defensive: dead code
            return set(self._container.keys())  # Defensive: dead code


class HTTPHeaderDictItemView(typing.Set[typing.Tuple[str, str]]):
    """
    HTTPHeaderDict is unusual for a Mapping[str, str] in that it has two modes of
    address.

    If we directly try to get an item with a particular name, we will get a string
    back that is the concatenated version of all the values:

    >>> d['X-Header-Name']
    'Value1, Value2, Value3'

    However, if we iterate over an HTTPHeaderDict's items, we will optionally combine
    these values based on whether combine=True was called when building up the dictionary

    >>> d = HTTPHeaderDict({"A": "1", "B": "foo"})
    >>> d.add("A", "2", combine=True)
    >>> d.add("B", "bar")
    >>> list(d.items())
    [
        ('A', '1, 2'),
        ('B', 'foo'),
        ('B', 'bar'),
    ]

    This class conforms to the interface required by the MutableMapping ABC while
    also giving us the nonstandard iteration behavior we want; items with duplicate
    keys, ordered by time of first insertion.
    """

    _headers: HTTPHeaderDict

    def __init__(self, headers: HTTPHeaderDict) -> None:
        self._headers = headers

    def __len__(self) -> int:
        return len(list(self._headers.iteritems()))

    def __iter__(self) -> typing.Iterator[tuple[str, str]]:
        return self._headers.iteritems()

    def __contains__(self, item: object) -> bool:
        if isinstance(item, tuple) and len(item) == 2:
            passed_key, passed_val = item
            if isinstance(passed_key, str) and isinstance(passed_val, str):
                return self._headers._has_value_for_header(passed_key, passed_val)
        return False


class HTTPHeaderDict(typing.MutableMapping[str, str]):
    """
    :param headers:
        An iterable of field-value pairs. Must not contain multiple field names
        when compared case-insensitively.

    :param kwargs:
        Additional field-value pairs to pass in to ``dict.update``.

    A ``dict`` like container for storing HTTP Headers.

    Field names are stored and compared case-insensitively in compliance with
    RFC 7230. Iteration provides the first case-sensitive key seen for each
    case-insensitive pair.

    Using ``__setitem__`` syntax overwrites fields that compare equal
    case-insensitively in order to maintain ``dict``'s api. For fields that
    compare equal, instead create a new ``HTTPHeaderDict`` and use ``.add``
    in a loop.

    If multiple fields that are equal case-insensitively are passed to the
    constructor or ``.update``, the behavior is undefined and some will be
    lost.

    >>> headers = HTTPHeaderDict()
    >>> headers.add('Set-Cookie', 'foo=bar')
    >>> headers.add('set-cookie', 'baz=quxx')
    >>> headers['content-length'] = '7'
    >>> headers['SET-cookie']
    'foo=bar, baz=quxx'
    >>> headers['Content-Length']
    '7'
    """

    _container: typing.MutableMapping[str, list[str]]

    def __init__(self, headers: ValidHTTPHeaderSource | None = None, **kwargs: str):
        super().__init__()
        self._container = {}  # 'dict' is insert-ordered in Python 3.7+
        if headers is not None:
            if isinstance(headers, HTTPHeaderDict):
                self._copy_from(headers)
            else:
                self.extend(headers)
        if kwargs:
            self.extend(kwargs)

    def __setitem__(self, key: str, val: str) -> None:
        # avoid a bytes/str comparison by decoding before httplib
        self._container[key.lower()] = [key, val]

    def __getitem__(self, key: str) -> str:
        if isinstance(key, bytes):
            key = key.decode("latin-1")
        val = self._container[key.lower()]
        return ", ".join(val[1:])

    def __delitem__(self, key: str) -> None:
        if isinstance(key, bytes):
            key = key.decode("latin-1")
        del self._container[key.lower()]

    def __contains__(self, key: object) -> bool:
        if isinstance(key, bytes):
            key = key.decode("latin-1")
        if isinstance(key, str):
            return key.lower() in self._container
        return False

    def setdefault(self, key: str, default: str = "") -> str:
        return super().setdefault(key, default)

    def __eq__(self, other: object) -> bool:
        maybe_constructable = ensure_can_construct_http_header_dict(other)
        if maybe_constructable is None:
            return False
        else:
            other_as_http_header_dict = type(self)(maybe_constructable)

        return {k.lower(): v for k, v in self.itermerged()} == {
            k.lower(): v for k, v in other_as_http_header_dict.itermerged()
        }

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __len__(self) -> int:
        return len(self._container)

    def __iter__(self) -> typing.Iterator[str]:
        # Only provide the originally cased names
        for vals in self._container.values():
            yield vals[0]

    def discard(self, key: str) -> None:
        try:
            del self[key]
        except KeyError:
            pass

    def add(self, key: str, val: str, *, combine: bool = False) -> None:
        """Adds a (name, value) pair, doesn't overwrite the value if it already
        exists.

        If this is called with combine=True, instead of adding a new header value
        as a distinct item during iteration, this will instead append the value to
        any existing header value with a comma. If no existing header value exists
        for the key, then the value will simply be added, ignoring the combine parameter.

        >>> headers = HTTPHeaderDict(foo='bar')
        >>> headers.add('Foo', 'baz')
        >>> headers['foo']
        'bar, baz'
        >>> list(headers.items())
        [('foo', 'bar'), ('foo', 'baz')]
        >>> headers.add('foo', 'quz', combine=True)
        >>> list(headers.items())
        [('foo', 'bar, baz, quz')]
        """
        key_lower = key.lower()
        new_vals = [key, val]
        # Keep the common case aka no item present as fast as possible
        vals = self._container.setdefault(key_lower, new_vals)
        if new_vals is not vals:
            # if there are values here, then there is at least the initial
            # key/value pair
            if combine:
                vals[-1] = vals[-1] + ", " + val
            else:
                vals.append(val)

    def extend(self, *args: ValidHTTPHeaderSource, **kwargs: str) -> None:
        """Generic import function for any type of header-like object.
        Adapted version of MutableMapping.update in order to insert items
        with self.add instead of self.__setitem__
        """
        if len(args) > 1:
            raise TypeError(
                f"extend() takes at most 1 positional arguments ({len(args)} given)"
            )
        other = args[0] if len(args) >= 1 else ()

        if isinstance(other, HTTPHeaderDict):
            for key, val in other.iteritems():
                self.add(key, val)
        elif isinstance(other, typing.Mapping):
            for key, val in other.items():
                self.add(key, val)
        elif isinstance(other, typing.Iterable):
            for key, value in other:
                self.add(key, value)
        elif hasattr(other, "keys") and hasattr(other, "__getitem__"):
            # THIS IS NOT A TYPESAFE BRANCH
            # In this branch, the object has a `keys` attr but is not a Mapping or any of
            # the other types indicated in the method signature. We do some stuff with
            # it as though it partially implements the Mapping interface, but we're not
            # doing that stuff safely AT ALL.
            for key in other.keys():
                self.add(key, other[key])

        for key, value in kwargs.items():
            self.add(key, value)

    @typing.overload
    def getlist(self, key: str) -> list[str]: ...

    @typing.overload
    def getlist(self, key: str, default: _DT) -> list[str] | _DT: ...

    def getlist(
        self, key: str, default: _Sentinel | _DT = _Sentinel.not_passed
    ) -> list[str] | _DT:
        """Returns a list of all the values for the named field. Returns an
        empty list if the key doesn't exist."""
        if isinstance(key, bytes):
            key = key.decode("latin-1")
        try:
            vals = self._container[key.lower()]
        except KeyError:
            if default is _Sentinel.not_passed:
                # _DT is unbound; empty list is instance of List[str]
                return []
            # _DT is bound; default is instance of _DT
            return default
        else:
            # _DT may or may not be bound; vals[1:] is instance of List[str], which
            # meets our external interface requirement of `Union[List[str], _DT]`.
            return vals[1:]

    # Backwards compatibility for httplib
    getheaders = getlist
    getallmatchingheaders = getlist
    iget = getlist

    # Backwards compatibility for http.cookiejar
    get_all = getlist

    def __repr__(self) -> str:
        return f"{type(self).__name__}({dict(self.itermerged())})"

    def _copy_from(self, other: HTTPHeaderDict) -> None:
        for key, val in other._container.items():
            self._container[key] = val.copy()

    def copy(self) -> HTTPHeaderDict:
        clone = type(self)()
        clone._copy_from(self)
        return clone

    def iteritems(self) -> typing.Iterator[tuple[str, str]]:
        """Iterate over all header lines, including duplicate ones."""
        for vals in self._container.values():
            for val in vals[1:]:
                yield vals[0], val

    def itermerged(self) -> typing.Iterator[tuple[str, str]]:
        """Iterate over all headers, merging duplicate ones together."""
        for val in self._container.values():
            yield val[0], ", ".join(val[1:])

    def items(self) -> HTTPHeaderDictItemView:  # type: ignore[override]
        return HTTPHeaderDictItemView(self)

    def _has_value_for_header(self, header_name: str, potential_value: str) -> bool:
        if header_name in self:
            return potential_value in self._container[header_name.lower()][1:]
        return False


_GK = typing.TypeVar("_GK", bound=typing.Hashable)
_GV = typing.TypeVar("_GV")


class ReverseKeysView(typing.KeysView[_GK]):
    """A read-only ``KeysView`` over the keys mapped to a single value.

    Returned by :meth:`GroupedDict.keys_for`. Backed by reference to an
    internal bucket so the view is live (mirrors ``dict.keys()`` semantics):
    subsequent mutations of the parent :class:`GroupedDict` are reflected on
    next iteration / membership test.
    """

    __slots__ = ("_bucket",)

    def __init__(self, bucket: typing.Optional[typing.Set[_GK]]) -> None:
        # We intentionally do NOT call super().__init__: the parent KeysView
        # expects a Mapping, but we wrap a raw set bucket instead.
        self._bucket: typing.Optional[typing.Set[_GK]] = bucket

    def __iter__(self) -> typing.Iterator[_GK]:
        if self._bucket is None:
            return iter(())
        return iter(self._bucket)

    def __len__(self) -> int:
        if self._bucket is None:
            return 0
        return len(self._bucket)

    def __contains__(self, key: object) -> bool:
        if self._bucket is None:
            return False
        return key in self._bucket

    def __repr__(self) -> str:
        return f"ReverseKeysView({set(self) if self._bucket else set()!r})"


class GroupedDict(typing.Dict[_GK, _GV]):
    """A ``dict`` subclass that maintains a reverse "value to keys" index.

    Optimized for the case where many keys share a small number of distinct
    values. Reverse lookups via :meth:`keys_for` are O(1) average time and
    return a live :class:`ReverseKeysView`.

    A ``key_fn`` may be supplied to control how values are hashed for the
    reverse index. By default, the value itself is used (identity over
    equality). Pass ``key_fn=id`` to index by object identity instead — this
    is the right choice when values may override ``__eq__`` / ``__hash__``
    in ways you don't want to collapse buckets on, or when values are not
    hashable themselves.

    All standard ``dict`` mutation entry points are overridden to keep the
    reverse index coherent. Empty buckets are pruned eagerly so that
    long-lived instances do not accumulate stale entries on value churn.
    """

    __slots__ = ("_index", "_key_fn")

    def __init__(
        self,
        *args: typing.Any,
        key_fn: typing.Callable[[_GV], typing.Hashable] | None = None,
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._key_fn: typing.Callable[[_GV], typing.Hashable] = (
            key_fn if key_fn is not None else lambda x: x
        )
        self._index: dict[typing.Hashable, set[_GK]] = {}
        for k, v in super().items():
            self._index.setdefault(self._key_fn(v), set()).add(k)

    def __setitem__(self, key: _GK, value: _GV) -> None:
        old = dict.get(self, key, _Sentinel.not_passed)
        if old is not _Sentinel.not_passed:
            old_h = self._key_fn(old)
            new_h = self._key_fn(value)
            if old_h == new_h:
                dict.__setitem__(self, key, value)
                return
            bucket = self._index.get(old_h)
            if bucket is not None:
                bucket.discard(key)
                if not bucket:
                    del self._index[old_h]
            dict.__setitem__(self, key, value)
            bucket = self._index.get(new_h)
            if bucket is None:
                self._index[new_h] = {key}
            else:
                bucket.add(key)
            return
        dict.__setitem__(self, key, value)
        value_h = self._key_fn(value)
        bucket = self._index.get(value_h)
        if bucket is None:
            self._index[value_h] = {key}
        else:
            bucket.add(key)

    def __delitem__(self, key: _GK) -> None:
        old = dict.pop(self, key)
        old_h = self._key_fn(old)
        bucket = self._index.get(old_h)
        if bucket is not None:
            bucket.discard(key)
            if not bucket:
                del self._index[old_h]

    def pop(self, key: _GK, *args: typing.Any) -> typing.Any:
        if len(args) > 1:
            raise TypeError(f"pop expected at most 2 arguments, got {1 + len(args)}")
        if key not in self:
            if args:
                return args[0]
            raise KeyError(key)
        value = super().pop(key)
        h = self._key_fn(value)
        bucket = self._index.get(h)
        if bucket is not None:
            bucket.discard(key)
            if not bucket:
                del self._index[h]
        return value

    def popitem(self) -> tuple[_GK, _GV]:
        key, value = super().popitem()
        h = self._key_fn(value)
        bucket = self._index.get(h)
        if bucket is not None:
            bucket.discard(key)
            if not bucket:
                del self._index[h]
        return key, value

    def clear(self) -> None:
        super().clear()
        self._index.clear()

    def setdefault(self, key: _GK, default: typing.Any = None) -> typing.Any:
        if key in self:
            return super().__getitem__(key)
        # Route through __setitem__ to keep the reverse index coherent.
        self[key] = default
        return default

    def update(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        if len(args) > 1:
            raise TypeError(
                f"update expected at most 1 positional argument, got {len(args)}"
            )
        if args:
            other = args[0]
            if isinstance(other, _Mapping):
                for k in other:
                    self[k] = other[k]
            elif hasattr(other, "keys"):
                # Mapping-like protocol (duck-typed).
                for k in other.keys():
                    self[k] = other[k]
            else:
                for k, v in other:  # iterable of pairs
                    self[k] = v
        for k, v in kwargs.items():
            self[k] = v  # type: ignore[index]

    def keys_for(self, value: _GV) -> ReverseKeysView[_GK]:
        """Return a live read-only view over all keys mapped to ``value``.

        Lookup is O(1) average time. The returned :class:`ReverseKeysView`
        reflects the current bucket contents and updates as the parent
        :class:`GroupedDict` is mutated. Returns an empty view if no key
        maps to ``value``.
        """
        bucket = self._index.get(self._key_fn(value))
        return ReverseKeysView(bucket)

    def copy(self) -> GroupedDict[_GK, _GV]:
        # We pass key_fn through so the copy behaves identically.
        new: GroupedDict[_GK, _GV] = GroupedDict(self, key_fn=self._key_fn)
        return new

    def __copy__(self) -> GroupedDict[_GK, _GV]:
        return self.copy()

    @classmethod
    def fromkeys(  # type: ignore[override]
        cls,
        iterable: typing.Iterable[_GK],
        value: typing.Any = None,
    ) -> GroupedDict[_GK, typing.Any]:
        return cls({k: value for k in iterable})
