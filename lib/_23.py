# coding=utf-8
#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from collections import deque
from itertools import islice
from sys import version_info

from six import binary_type, moves

# noinspection PyUnresolvedReferences
from six.moves.urllib.parse import quote, quote_plus, unquote as six_unquote, unquote_plus as six_unquote_plus, \
    urlencode, urlsplit, urlunparse, urlunsplit
# noinspection PyUnreachableCode
if False:
    # ----------------------
    # resolve typing imports
    # ----------------------
    # noinspection PyUnresolvedReferences
    from typing import Any, AnyStr, Callable, Dict, Iterator, List, Optional, Tuple, Union
    # -------------------
    # resolve pyc imports
    # -------------------
    # noinspection PyTypeChecker
    quote = quote_plus = None  # type: Callable
    # noinspection PyTypeChecker
    urlencode = urlsplit = urlunparse = urlunsplit = None  # type: Callable

PY38 = version_info[0:2] >= (3, 8)

""" one off consumables (Iterators) """
filter_iter = moves.filter  # type: Callable[[], Iterator]
map_iter = moves.map  # type: Callable[[], Iterator]


def map_consume(*args):
    # type: (...) -> None
    """Run a lambda over elements without returning anything"""
    deque(moves.map(*args), maxlen=0)


def consume(iterator, n=None):
    # type: (Iterator, Optional[int]) -> None
    """Advance the iterator n-steps ahead. If n is None, consume entirely. Returns nothing.

    Useful if a method returns a Iterator but it's not used, but still all should be called,
    for example if each iter element calls a function that should be called for all or
    given amount of elements in Iterator

    examples:
    consume(filter_iter(...))  # consumes all elements of given function that returns a Iterator
    consume(filter_iter(...), 3)  # consumes next 3 elements of given function that returns a Iterator
    """
    # Use functions that consume iterators at C speed.
    if n is None:
        # feed the entire iterator into a zero-length deque
        deque(iterator, maxlen=0)
    else:
        # advance to the empty slice starting at position n
        next(islice(iterator, n, n), None)


def decode_str(s, encoding='utf-8', errors=None):
    # type: (...) -> AnyStr
    if isinstance(s, binary_type):
        if None is errors:
            return s.decode(encoding)
        return s.decode(encoding, errors)
    return s


def html_unescape(s):
    # type: (AnyStr) -> AnyStr
    """helper to remove special character quoting"""
    if (3, 4) > version_info:
        # noinspection PyUnresolvedReferences
        from six.moves.html_parser import HTMLParser
        # noinspection PyDeprecation
        return HTMLParser().unescape(s)

    # noinspection PyCompatibility,PyUnresolvedReferences
    from html import unescape
    return unescape(s)


def list_range(*args, **kwargs):
    # type: (...) -> List
    return list(moves.range(*args, **kwargs))


def urlparse(url, scheme='', allow_fragments=True):
    """return ParseResult where netloc is populated from path if required, no need to test .netloc anymore"""
    # noinspection PyUnresolvedReferences
    from six.moves.urllib.parse import urlparse as _urlparse, ParseResult
    parsed_url = _urlparse(url, scheme, allow_fragments)
    if '' != parsed_url.netloc:
        return parsed_url
    # fix occasional cases where '' == netloc and its data is in parsed_result.path
    # noinspection PyArgumentList
    fix = ParseResult(scheme=parsed_url.scheme, netloc=parsed_url.path, path=url,
                      params=parsed_url.params, query=parsed_url.query, fragment=parsed_url.fragment)
    return fix


def make_btih(s):
    from base64 import b16encode, b32decode
    return decode_str(b16encode(b32decode(s)))


def b64decodestring(s):
    # type: (Union[bytes, AnyStr]) -> AnyStr
    from base64 import b64decode
    return decode_str(b64decode(s))


def b64encodestring(s, keep_eol=False):
    # type: (AnyStr, Union[bool]) -> AnyStr
    data = decode_str(b64encodebytes(decode_bytes(s)))
    if keep_eol:
        return data
    return data.rstrip()


if 2 != version_info[0]:
    # ---------
    # Python 3+
    # ---------
    # noinspection PyUnresolvedReferences,PyProtectedMember
    from base64 import decodebytes, encodebytes
    b64decodebytes = decodebytes
    b64encodebytes = encodebytes
    # noinspection PyUnresolvedReferences,PyCompatibility
    from configparser import ConfigParser
    # noinspection PyUnresolvedReferences
    from os import scandir, DirEntry
    # noinspection PyUnresolvedReferences
    from itertools import zip_longest
    # noinspection PyUnresolvedReferences
    from inspect import getfullargspec as getargspec

    def unquote(string, encoding='utf-8', errors='replace'):
        return decode_str(six_unquote(decode_str(string, encoding, errors), encoding=encoding, errors=errors),
                          encoding, errors)

    def unquote_plus(string, encoding='utf-8', errors='replace'):
        return decode_str(six_unquote_plus(decode_str(string, encoding, errors), encoding=encoding, errors=errors),
                          encoding, errors)

    def decode_bytes(d, encoding='utf-8', errors='replace'):
        if not isinstance(d, binary_type):
            # noinspection PyArgumentList
            return bytes(d, encoding=encoding, errors=errors)
        return d

    def filter_list(*args):
        # type: (...) -> List
        return list(filter(*args))

    def list_items(d):
        # type: (Dict) -> List[Tuple[Any, Any]]
        """
        equivalent to python 2 .items()
        """
        return list(d.items())

    def list_keys(d):
        # type: (Dict) -> List
        """
        equivalent to python 2 .keys()
        """
        return list(d)

    def list_values(d):
        # type: (Dict) -> List
        """
        equivalent to python 2 .values()
        """
        return list(d.values())

    def map_list(*args):
        # type: (...) -> List
        return list(map(*args))

    def map_none(*args):
        # type: (...) -> List
        return list(zip_longest(*args))

    def unidecode(data):
        # type: (AnyStr) -> AnyStr
        return data

else:
    # ---------
    # Python 2
    # ---------
    from lib.unidecode import unidecode as unicode_decode
    # noinspection PyProtectedMember,PyDeprecation
    from base64 import decodestring, encodestring
    # noinspection PyDeprecation
    b64decodebytes = decodestring
    # noinspection PyDeprecation
    b64encodebytes = encodestring
    # noinspection PyUnresolvedReferences
    from lib.backports.configparser import ConfigParser
    # noinspection PyProtectedMember,PyUnresolvedReferences
    from lib.scandir.scandir import scandir, GenericDirEntry as DirEntry
    # noinspection PyUnresolvedReferences,PyDeprecation
    from inspect import getargspec

    def unquote(string, encoding='utf-8', errors='replace'):
        return decode_str(six_unquote(decode_str(string, encoding, errors)), encoding, errors)

    def unquote_plus(string, encoding='utf-8', errors='replace'):
        return decode_str(six_unquote_plus(decode_str(string, encoding, errors)), encoding, errors)

    # noinspection PyUnusedLocal
    def decode_bytes(d, encoding='utf-8', errors='replace'):
        if not isinstance(d, binary_type):
            return bytes(d)
        return d

    def filter_list(*args):
        # type: (...) -> List
        # noinspection PyTypeChecker
        return filter(*args)

    def list_items(d):
        # type: (Dict) -> List[Tuple[Any, Any]]
        # noinspection PyTypeChecker
        return d.items()

    def list_keys(d):
        # type: (Dict) -> List
        # noinspection PyTypeChecker
        return d.keys()

    def list_values(d):
        # type: (Dict) -> List
        # noinspection PyTypeChecker
        return d.values()

    def map_list(*args):
        # type: (...) -> List
        # noinspection PyTypeChecker
        return map(*args)

    def map_none(*args):
        # type: (...) -> List
        # noinspection PyTypeChecker
        return map(None, *args)

    def unidecode(data):
        # type: (AnyStr) -> AnyStr
        # noinspection PyUnresolvedReferences
        return isinstance(data, unicode) and unicode_decode(data) or data
