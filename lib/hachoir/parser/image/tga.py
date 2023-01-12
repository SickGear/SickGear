"""
Truevision Targa Graphic (TGA) picture parser.

Author: Victor Stinner
Creation: 18 december 2006
"""

from hachoir.parser import Parser
from hachoir.field import FieldSet, UInt8, UInt16, Enum, RawBytes, Bit, Bits, RawBits
from hachoir.core.endian import LITTLE_ENDIAN
from hachoir.parser.image.common import PaletteRGB
from hachoir.core.text_handler import textHandler, hexadecimal


class Line(FieldSet):

    def __init__(self, *args):
        FieldSet.__init__(self, *args)
        self._size = self["/width"].value * self.root.getBpp()

    def createFields(self):
        bpp = self.root.getBpp()
        for x in range(self["/width"].value):
            yield textHandler(Bits(self, "pixel[]", bpp), hexadecimal)


class Pixels(FieldSet):

    def __init__(self, *args):
        FieldSet.__init__(self, *args)
        self._size = self["/width"].value * \
            self["/height"].value * self.root.getBpp()

    def createFields(self):
        if self["/y_flip"].value:
            RANGE = range(self["/height"].value)
        else:
            RANGE = reversed(range(self["/height"].value))
        for y in RANGE:
            yield Line(self, "line[%u]" % y)


class TargaFile(Parser):
    PARSER_TAGS = {
        "id": "targa",
        "category": "image",
        "file_ext": ("tga",),
        "mime": ("image/targa", "image/tga", "image/x-tga"),
        "min_size": 18 * 8,
        "description": "Truevision Targa Graphic (TGA)"
    }
    CODEC_NAME = {
        0: "No image data",
        1: "Palette uncompressed",
        2: "True-color uncompressed",
        3: "Grayscale uncompressed",
        9: "Palette RLE",
        10: "True-color RLE",
        11: "Grayscale RLE",
    }
    endian = LITTLE_ENDIAN

    def validate(self):
        if self["codec"].value not in self.CODEC_NAME:
            return "Unknown codec"
        if self["palette_type"].value not in (0, 1):
            return "Unknown palette type %d" % self["palette_type"].value
        if self["bpp"].value not in (8, 15, 16, 24, 32):
            return "Unknown bits/pixel value %d" % self["bpp"].value
        return True

    def getBpp(self):
        bpp = self['bpp'].value
        if bpp == 15:
            bpp = 16
        return bpp

    def createFields(self):
        yield UInt8(self, "id_length", "Length of the image ID field")
        yield UInt8(self, "palette_type", "Colormap present?")
        yield Enum(UInt8(self, "codec", "Pixels encoding"), self.CODEC_NAME)
        yield UInt16(self, "palette_ofs", "Palette absolute file offset")
        yield UInt16(self, "nb_color", "Number of colors in the palette")
        yield UInt8(self, "color_map_size", "Size of each palette entry")
        yield UInt16(self, "x_min")
        yield UInt16(self, "y_min")
        yield UInt16(self, "width")
        yield UInt16(self, "height")
        yield UInt8(self, "bpp", "Bits per pixel")
        yield Bits(self, "alpha_depth", 4, "Alpha channel depth")
        yield Bit(self, "x_flip", "Flip across the X-axis? (If set, columns run right-to-left)")
        yield Bit(self, "y_flip", "Flip across the Y-axis? (If set, rows run top-to-bottom)")
        yield RawBits(self, "reserved_flags", 2)

        if self["id_length"].value:
            yield RawBytes(self, "image_id", self["id_length"].value)

        if self["palette_type"].value == 1:
            yield PaletteRGB(self, "palette", 1 << self["bpp"].value)

        if self["codec"] in (1, 2, 3):
            yield Pixels(self, "pixels")
        else:
            size = (self.size - self.current_size) // 8
            if size:
                yield RawBytes(self, "raw_pixels", size)
