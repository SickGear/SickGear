from .exceptions import CharacterEncodingOverride as CharacterEncodingOverride, CharacterEncodingUnknown as CharacterEncodingUnknown, NonXMLContentType as NonXMLContentType
from typing import Any

lazy_chardet_encoding: Any
bytes_: Any
unicode_: Any
EBCDIC_MARKER: bytes
UTF16BE_MARKER: bytes
UTF16LE_MARKER: bytes
UTF32BE_MARKER: bytes
UTF32LE_MARKER: bytes
ZERO_BYTES: str
RE_XML_DECLARATION: Any
RE_XML_PI_ENCODING: Any

def convert_to_utf8(http_headers: Any, data: Any, result: Any): ...
