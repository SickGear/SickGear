"""
Apple BOMStorage parser.

Used for Assets.Bom files by Interface Builder, and for .bom files by Installer.app.

Documents:

Author: Robert Xiao
Created: 2015-05-14
"""

from hachoir.parser import HachoirParser
from hachoir.field import (RootSeekableFieldSet, FieldSet,
                           UInt32, Bytes, NullBytes, RawBytes)
from hachoir.core.endian import BIG_ENDIAN


class BomTrailerEntry(FieldSet):

    static_size = 64  # bits

    def createFields(self):
        yield UInt32(self, "offset")
        yield UInt32(self, "size")

    def createDescription(self):
        return "Object at offset %d, size %d" % (self['offset'].value, self['size'].value)


class BomTrailer(FieldSet):

    def createFields(self):
        yield UInt32(self, "num_spaces", "Total number of entries, including blank entries")
        nobj = self['/num_objects'].value
        nspace = self['num_spaces'].value
        for i in range(nobj + 1):
            yield BomTrailerEntry(self, "entry[]")
        yield NullBytes(self, "blank_entries", (nspace - nobj - 1) * (BomTrailerEntry.static_size // 8))
        yield UInt32(self, "num_trail")
        ntrail = self['num_trail'].value
        for i in range(ntrail):
            yield BomTrailerEntry(self, "trail[]")

    def createDescription(self):
        return "Bom file trailer"


class BomFile(HachoirParser, RootSeekableFieldSet):

    endian = BIG_ENDIAN
    MAGIC = b"BOMStore"
    PARSER_TAGS = {
        "id": "bom_store",
        "category": "archive",
        "file_ext": ("bom", "car"),
        "magic": ((MAGIC, 0),),
        "min_size": 32 * 8,  # 32-byte header
        "description": "Apple bill-of-materials file",
    }

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(self, None, "root", stream, None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        if self.stream.readBytes(0, len(self.MAGIC)) != self.MAGIC:
            return "Invalid magic"
        return True

    def createFields(self):
        yield Bytes(self, "magic", 8, "File magic (BOMStore)")
        yield UInt32(self, "version")  # ?
        yield UInt32(self, "num_objects")
        yield UInt32(self, "trailer_offset")
        yield UInt32(self, "trailer_size")
        yield UInt32(self, "header_offset")
        yield UInt32(self, "header_size")

        yield RawBytes(self, "object[]", 512 - 32, "Null object (size 0, offset 0)")

        self.seekByte(self['trailer_offset'].value)
        yield BomTrailer(self, "trailer")

        self.seekByte(self['header_offset'].value)
        yield RawBytes(self, "header", self['header_size'].value)

        for entry in self['trailer'].array('entry'):
            if entry['size'].value == 0:
                continue
            self.seekByte(entry['offset'].value)
            yield RawBytes(self, "object[]", entry['size'].value)

        for entry in self['trailer'].array('trail'):
            self.seekByte(entry['offset'].value)
            yield RawBytes(self, "trail[]", entry['size'].value)
