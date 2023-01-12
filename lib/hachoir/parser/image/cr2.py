"""
Canon CR2 raw image data, version 2.0 image parser.

Authors: Fernando Crespo
Creation date: 21 february 2017
"""

from hachoir.parser import Parser
from hachoir.field import SeekableFieldSet, RootSeekableFieldSet, Bytes, String, UInt8, UInt16, UInt32
from hachoir.core.endian import LITTLE_ENDIAN, BIG_ENDIAN
from hachoir.core.text_handler import textHandler, hexadecimal
from hachoir.parser.image.exif import IFD, IFD_TAGS


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


class ImageFile(SeekableFieldSet):

    def __init__(self, parent, name, description, ifd):
        SeekableFieldSet.__init__(self, parent, name, description, None)
        self._ifd = ifd

    def createFields(self):
        for off, byte in getStrips(self._ifd):
            self.seekByte(off, relative=False)
            yield Bytes(self, "strip[]", byte)


class CR2File(RootSeekableFieldSet, Parser):
    PARSER_TAGS = {
        "id": "cr2",
        "category": "image",
        "file_ext": ("cr2",),
        "mime": ("image/x-canon-cr2",),
        "min_size": 15,
        "magic": ((b"CR", 8),),
        "description": "Canon CR2 raw image data, version 2.0"
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
            return "Unknown Canon TIFF version - " + str(self["version"].value)
        if self["cr_identifier"].value != "CR":
            return "Unknown Canon Raw File"
        return True

    def createFields(self):
        iff_start = self.absolute_address
        yield String(self, "endian", 2, "Endian ('II' or 'MM')", charset="ASCII")
        if self["endian"].value == "II":
            self.endian = LITTLE_ENDIAN
        else:
            self.endian = BIG_ENDIAN

        yield UInt16(self, "version", "TIFF version number")
        yield UInt32(self, "img_dir_ofs", "Next image directory offset")

        yield String(self, "cr_identifier", 2, "Canon Raw marker", charset="ASCII")
        yield UInt8(self, "cr_major_version", "Canon Raw major version number")
        yield UInt8(self, "cr_minor_version", "Canon Raw minor version number")

        yield textHandler(UInt32(self, "cr_raw_ifd_offset", "Offset to Raw IFD"), hexadecimal)

        offsets = [(self['img_dir_ofs'].value, 'ifd[]', IFD)]

        while offsets:
            offset, name, klass = offsets.pop(0)
            self.seekByte(offset + iff_start // 8, relative=False)
            ifd = klass(self, name, iff_start)

            yield ifd
            for entry in ifd.array('entry'):
                tag = entry['tag'].value
                if tag in IFD_TAGS:
                    name, klass = IFD_TAGS[tag]
                    offsets.append((ifd.getEntryValues(entry)[
                                   0].value, name + '[]', klass))
            if ifd['next'].value != 0:
                offsets.append((ifd['next'].value, 'ifd[]', IFD))

        for ifd in self.array('ifd'):
            offs = (off for off, byte in getStrips(ifd))
            self.seekByte(min(offs), relative=False)
            image = ImageFile(self, "image[]", "Image File", ifd)
            yield image
