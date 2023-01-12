"""
TIFF image parser.

Authors: Victor Stinner, Sebastien Ponce, Robert Xiao
Creation date: 30 september 2006
"""

from hachoir.parser import Parser
from hachoir.field import SeekableFieldSet, RootSeekableFieldSet, Bytes
from hachoir.core.endian import LITTLE_ENDIAN, BIG_ENDIAN
from hachoir.parser.image.exif import TIFF, IFD


def getStrips(ifd):
    data = {}
    for i, entry in enumerate(ifd.array('entry')):
        data[entry['tag'].display] = entry
    # image data
    if "StripOffsets" in data and "StripByteCounts" in data:
        offs = ifd.getEntryValues(data["StripOffsets"])
        bytes = ifd.getEntryValues(data["StripByteCounts"])
        for off, byte in zip(offs, bytes):
            yield off.value, byte.value

    # image data
    if "TileOffsets" in data and "TileByteCounts" in data:
        offs = ifd.getEntryValues(data["TileOffsets"])
        bytes = ifd.getEntryValues(data["TileByteCounts"])
        for off, byte in zip(offs, bytes):
            yield off.value, byte.value


class ImageFile(SeekableFieldSet):

    def __init__(self, parent, name, description, ifd):
        SeekableFieldSet.__init__(self, parent, name, description, None)
        self._ifd = ifd

    def createFields(self):
        for off, byte in getStrips(self._ifd):
            self.seekByte(off, relative=False)
            field = Bytes(self, "strip[]", byte)
            yield field


class TiffFile(RootSeekableFieldSet, Parser):
    PARSER_TAGS = {
        "id": "tiff",
        "category": "image",
        "file_ext": ("tif", "tiff"),
        "mime": ("image/tiff",),
        "min_size": 8 * 8,
        "magic": ((b"II\x2A\0", 0), (b"MM\0\x2A", 0)),
        "description": "TIFF picture"
    }

    # Correct endian is set in constructor
    endian = LITTLE_ENDIAN

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(
            self, None, "root", stream, None, stream.askSize(self))
        if self.stream.readBytes(0, 2) == b"MM":
            self.endian = BIG_ENDIAN
        Parser.__init__(self, stream, **args)

    def validate(self):
        endian = self.stream.readBytes(0, 2)
        if endian not in (b"MM", b"II"):
            return "Invalid endian (%r)" % endian
        if self["version"].value != 42:
            return "Unknown TIFF version"
        return True

    def createFields(self):
        yield from TIFF(self)

        for ifd in self:
            if not isinstance(ifd, IFD):
                continue
            offs = (off for off, byte in getStrips(ifd))
            self.seekByte(min(offs), relative=False)
            image = ImageFile(self, "image[]", "Image File", ifd)
            yield image
