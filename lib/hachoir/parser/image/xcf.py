"""
Gimp image parser (XCF file, ".xcf" extension).

You can find informations about XCF file in Gimp source code. URL to read
CVS online:
  http://cvs.gnome.org/viewcvs/gimp/app/xcf/
  files xcf-read.c and xcf-load.c

Author: Victor Stinner
"""

from hachoir.parser import Parser
from hachoir.field import (StaticFieldSet, FieldSet, ParserError,
                           UInt8, UInt32, Enum, Float32, String, PascalString32, RawBytes)
from hachoir.parser.image.common import RGBA
from hachoir.core.endian import NETWORK_ENDIAN


class XcfCompression(FieldSet):
    static_size = 8
    COMPRESSION_NAME = {
        0: "None",
        1: "RLE",
        2: "Zlib",
        3: "Fractal"
    }

    def createFields(self):
        yield Enum(UInt8(self, "compression", "Compression method"), self.COMPRESSION_NAME)


class XcfResolution(StaticFieldSet):
    format = (
        (Float32, "xres", "X resolution in DPI"),
        (Float32, "yres", "Y resolution in DPI")
    )


class XcfTattoo(StaticFieldSet):
    format = ((UInt32, "tattoo", "Tattoo"),)


class LayerOffsets(StaticFieldSet):
    format = (
        (UInt32, "ofst_x", "Offset X"),
        (UInt32, "ofst_y", "Offset Y")
    )


class LayerMode(FieldSet):
    static_size = 32
    MODE_NAME = {
        0: "Normal",
        1: "Dissolve",
        2: "Behind",
        3: "Multiply",
        4: "Screen",
        5: "Overlay",
        6: "Difference",
        7: "Addition",
        8: "Subtract",
        9: "Darken only",
        10: "Lighten only",
        11: "Hue",
        12: "Saturation",
        13: "Color",
        14: "Value",
        15: "Divide",
        16: "Dodge",
        17: "Burn",
        18: "Hard light",
        19: "Soft light",
        20: "Grain extract",
        21: "Grain merge",
        22: "Color erase"
    }

    def createFields(self):
        yield Enum(UInt32(self, "mode", "Layer mode"), self.MODE_NAME)


class GimpBoolean(UInt32):

    def __init__(self, parent, name):
        UInt32.__init__(self, parent, name)

    def createValue(self):
        return 1 == UInt32.createValue(self)


class XcfUnit(StaticFieldSet):
    format = ((UInt32, "unit", "Unit"),)


class XcfParasiteEntry(FieldSet):

    def createFields(self):
        yield PascalString32(self, "name", "Name", strip="\0", charset="UTF-8")
        yield UInt32(self, "flags", "Flags")
        yield PascalString32(self, "data", "Data", strip=" \0", charset="UTF-8")


class XcfLevel(FieldSet):

    def createFields(self):
        yield UInt32(self, "width", "Width in pixel")
        yield UInt32(self, "height", "Height in pixel")
        yield UInt32(self, "offset", "Offset")
        offset = self["offset"].value
        if offset == 0:
            return
        data_offsets = []
        while (self.absolute_address + self.current_size) // 8 < offset:
            chunk = UInt32(self, "data_offset[]", "Data offset")
            yield chunk
            if chunk.value == 0:
                break
            data_offsets.append(chunk)
        if (self.absolute_address + self.current_size) // 8 != offset:
            raise ParserError("Problem with level offset.")
        previous = offset
        for chunk in data_offsets:
            data_offset = chunk.value
            size = data_offset - previous
            yield RawBytes(self, "data[]", size, "Data content of %s" % chunk.name)
            previous = data_offset


class XcfHierarchy(FieldSet):

    def createFields(self):
        yield UInt32(self, "width", "Width")
        yield UInt32(self, "height", "Height")
        yield UInt32(self, "bpp", "Bits/pixel")

        offsets = []
        while True:
            chunk = UInt32(self, "offset[]", "Level offset")
            yield chunk
            if chunk.value == 0:
                break
            offsets.append(chunk.value)
        for offset in offsets:
            padding = self.seekByte(offset, relative=False)
            if padding is not None:
                yield padding
            yield XcfLevel(self, "level[]", "Level")
#        yield XcfChannel(self, "channel[]", "Channel"))


class XcfChannel(FieldSet):

    def createFields(self):
        yield UInt32(self, "width", "Channel width")
        yield UInt32(self, "height", "Channel height")
        yield PascalString32(self, "name", "Channel name", strip="\0", charset="UTF-8")
        yield from readProperties(self)
        yield UInt32(self, "hierarchy_ofs", "Hierarchy offset")
        yield XcfHierarchy(self, "hierarchy", "Hierarchy")

    def createDescription(self):
        return 'Channel "%s"' % self["name"].value


class XcfLayer(FieldSet):

    def createFields(self):
        yield UInt32(self, "width", "Layer width in pixels")
        yield UInt32(self, "height", "Layer height in pixels")
        yield Enum(UInt32(self, "type", "Layer type"), XcfFile.IMAGE_TYPE_NAME)
        yield PascalString32(self, "name", "Layer name", strip="\0", charset="UTF-8")
        for prop in readProperties(self):
            yield prop

        # --
        # TODO: Hack for Gimp 1.2 files
        # --

        yield UInt32(self, "hierarchy_ofs", "Hierarchy offset")
        yield UInt32(self, "mask_ofs", "Layer mask offset")
        padding = self.seekByte(self["hierarchy_ofs"].value, relative=False)
        if padding is not None:
            yield padding
        yield XcfHierarchy(self, "hierarchy", "Hierarchy")
        # TODO: Read layer mask if needed: self["mask_ofs"].value != 0

    def createDescription(self):
        return 'Layer "%s"' % self["name"].value


class XcfParasites(FieldSet):

    def createFields(self):
        size = self["../size"].value * 8
        while self.current_size < size:
            yield XcfParasiteEntry(self, "parasite[]", "Parasite")


class XcfProperty(FieldSet):
    PROP_COMPRESSION = 17
    PROP_RESOLUTION = 19
    PROP_PARASITES = 21
    TYPE_NAME = {
        0: "End",
        1: "Colormap",
        2: "Active layer",
        3: "Active channel",
        4: "Selection",
        5: "Floating selection",
        6: "Opacity",
        7: "Mode",
        8: "Visible",
        9: "Linked",
        10: "Lock alpha",
        11: "Apply mask",
        12: "Edit mask",
        13: "Show mask",
        14: "Show masked",
        15: "Offsets",
        16: "Color",
        17: "Compression",
        18: "Guides",
        19: "Resolution",
        20: "Tattoo",
        21: "Parasites",
        22: "Unit",
        23: "Paths",
        24: "User unit",
        25: "Vectors",
        26: "Text layer flags",
    }

    handler = {
        6: RGBA,
        7: LayerMode,
        8: GimpBoolean,
        9: GimpBoolean,
        10: GimpBoolean,
        11: GimpBoolean,
        12: GimpBoolean,
        13: GimpBoolean,
        15: LayerOffsets,
        17: XcfCompression,
        19: XcfResolution,
        20: XcfTattoo,
        21: XcfParasites,
        22: XcfUnit
    }

    def __init__(self, *args, **kw):
        FieldSet.__init__(self, *args, **kw)
        self._size = (8 + self["size"].value) * 8

    def createFields(self):
        yield Enum(UInt32(self, "type", "Property type"), self.TYPE_NAME)
        yield UInt32(self, "size", "Property size")

        size = self["size"].value
        if 0 < size:
            cls = self.handler.get(self["type"].value, None)
            if cls:
                yield cls(self, "data", size=size * 8)
            else:
                yield RawBytes(self, "data", size, "Data")

    def createDescription(self):
        return "Property: %s" % self["type"].display


def readProperties(parser):
    while True:
        prop = XcfProperty(parser, "property[]")
        yield prop
        if prop["type"].value == 0:
            return


class XcfFile(Parser):
    PARSER_TAGS = {
        "id": "xcf",
        "category": "image",
        "file_ext": ("xcf",),
        "mime": ("image/x-xcf", "application/x-gimp-image"),
        # header+empty property+layer offset+channel offset
        "min_size": (26 + 8 + 4 + 4) * 8,
        "magic": (
            (b'gimp xcf file\0', 0),
            (b'gimp xcf v002\0', 0),
        ),
        "description": "Gimp (XCF) picture"
    }
    endian = NETWORK_ENDIAN
    IMAGE_TYPE_NAME = {
        0: "RGB",
        1: "Gray",
        2: "Indexed"
    }

    def validate(self):
        if self.stream.readBytes(0, 14) not in (b'gimp xcf file\0', b'gimp xcf v002\0'):
            return "Wrong signature"
        return True

    def createFields(self):
        # Read signature
        yield String(self, "signature", 14, "Gimp picture signature (ends with nul byte)", charset="ASCII")

        # Read image general informations (width, height, type)
        yield UInt32(self, "width", "Image width")
        yield UInt32(self, "height", "Image height")
        yield Enum(UInt32(self, "type", "Image type"), self.IMAGE_TYPE_NAME)
        for prop in readProperties(self):
            yield prop

        # Read layer offsets
        layer_offsets = []
        while True:
            chunk = UInt32(self, "layer_offset[]", "Layer offset")
            yield chunk
            if chunk.value == 0:
                break
            layer_offsets.append(chunk.value)

        # Read channel offsets
        channel_offsets = []
        while True:
            chunk = UInt32(self, "channel_offset[]", "Channel offset")
            yield chunk
            if chunk.value == 0:
                break
            channel_offsets.append(chunk.value)

        # Read layers
        for index, offset in enumerate(layer_offsets):
            if index + 1 < len(layer_offsets):
                size = (layer_offsets[index + 1] - offset) * 8
            else:
                size = None
            padding = self.seekByte(offset, relative=False)
            if padding:
                yield padding
            yield XcfLayer(self, "layer[]", size=size)

        # Read channels
        for index, offset in enumerate(channel_offsets):
            if index + 1 < len(channel_offsets):
                size = (channel_offsets[index + 1] - offset) * 8
            else:
                size = None
            padding = self.seekByte(offset, relative=False)
            if padding is not None:
                yield padding
            yield XcfChannel(self, "channel[]", "Channel", size=size)
