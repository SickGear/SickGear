"""
Character field class: a 8-bit character
"""

from hachoir.field import Bits
from hachoir.core.tools import makePrintable


class Character(Bits):
    """
    A 8-bit character using ASCII charset for display attribute.
    """
    static_size = 8

    def __init__(self, parent, name, description=None):
        Bits.__init__(self, parent, name, self.static_size, description=description)

    def createValue(self):
        return chr(self._parent.stream.readBits(
            self.absolute_address, self.static_size, self.parent.endian))

    def createRawDisplay(self):
        return str(Bits.createValue(self))

    def createDisplay(self):
        return makePrintable(self.value, "ASCII", quote="'")
