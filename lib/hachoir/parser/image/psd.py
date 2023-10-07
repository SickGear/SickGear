"""
Photoshop parser (.psd file).

Creation date: 8 january 2006
Author: Victor Stinner
"""

from hachoir.parser import Parser
from hachoir.field import (FieldSet,
                           UInt16, UInt32, String, NullBytes, Enum, RawBytes)
from hachoir.core.endian import BIG_ENDIAN
from hachoir.parser.image.photoshop_metadata import Photoshop8BIM


class Config(FieldSet):

    def __init__(self, *args):
        FieldSet.__init__(self, *args)
        self._size = (4 + self["size"].value) * 8

    def createFields(self):
        yield UInt32(self, "size")
        while not self.eof:
            yield Photoshop8BIM(self, "item[]")


class PsdFile(Parser):
    endian = BIG_ENDIAN
    PARSER_TAGS = {
        "id": "psd",
        "category": "image",
        "file_ext": ("psd",),
        "mime": ("image/psd", "image/photoshop", "image/x-photoshop"),
        "min_size": 4 * 8,
        "magic": ((b"8BPS\0\1", 0),),
        "description": "Photoshop (PSD) picture",
    }
    COLOR_MODE = {
        0: "Bitmap",
        1: "Grayscale",
        2: "Indexed",
        3: "RGB color",
        4: "CMYK color",
        7: "Multichannel",
        8: "Duotone",
        9: "Lab Color",
    }
    COMPRESSION_NAME = {
        0: "Raw data",
        1: "RLE",
    }

    def validate(self):
        if self.stream.readBytes(0, 4) != b"8BPS":
            return "Invalid signature"
        return True

    def createFields(self):
        yield String(self, "signature", 4, "PSD signature (8BPS)", charset="ASCII")
        yield UInt16(self, "version")
        yield NullBytes(self, "reserved[]", 6)
        yield UInt16(self, "nb_channels")
        yield UInt32(self, "width")
        yield UInt32(self, "height")
        yield UInt16(self, "depth")
        yield Enum(UInt16(self, "color_mode"), self.COLOR_MODE)

        # Mode data
        yield UInt32(self, "mode_data_size")
        size = self["mode_data_size"].value
        if size:
            yield RawBytes(self, "mode_data", size)

        # Resources
        yield Config(self, "config")

        # Reserved
        yield UInt32(self, "reserved_data_size")
        size = self["reserved_data_size"].value
        if size:
            yield RawBytes(self, "reserved_data", size)

        yield Enum(UInt16(self, "compression"), self.COMPRESSION_NAME)

        size = (self.size - self.current_size) // 8
        if size:
            yield RawBytes(self, "end", size)
