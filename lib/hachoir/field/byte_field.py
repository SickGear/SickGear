"""
Very basic field: raw content with a size in byte. Use this class for
unknown content.
"""

from hachoir.field import Field, FieldError
from hachoir.core.tools import makePrintable
from hachoir.core import config

MAX_LENGTH = (2**64)


class RawBytes(Field):
    """
    Byte vector of unknown content

    @see: L{Bytes}
    """
    static_size = staticmethod(lambda *args, **kw: args[1] * 8)

    def __init__(self, parent, name, length, description="Raw data"):
        assert issubclass(parent.__class__, Field)
        if not(0 < length <= MAX_LENGTH):
            raise FieldError("Invalid RawBytes length (%s)!" % length)
        Field.__init__(self, parent, name, length * 8, description)
        self._display = None

    def _createDisplay(self, human):
        max_bytes = config.max_byte_length
        try:
            display = makePrintable(self.value[:max_bytes], "ASCII")
        except Exception:
            if self._display is None:
                address = self.absolute_address
                length = min(self._size // 8, max_bytes)
                self._display = self._parent.stream.readBytes(address, length)
            display = makePrintable(self._display, "ASCII")
        truncated = (8 * len(display) < self._size)
        if human:
            if truncated:
                display += "(...)"
            return makePrintable(display, "latin-1", quote='"')
        else:
            if truncated:
                return '"%s(...)"' % display
            else:
                return '"%s"' % display

    def createDisplay(self):
        return self._createDisplay(True)

    def createRawDisplay(self):
        return self._createDisplay(False)

    def hasValue(self):
        return True

    def createValue(self):
        assert (self._size % 8) == 0
        if self._display:
            self._display = None
        return self._parent.stream.readBytes(
            self.absolute_address, self._size // 8)


class Bytes(RawBytes):
    """
    Byte vector: can be used for magic number or GUID/UUID for example.

    @see: L{RawBytes}
    """
    pass
