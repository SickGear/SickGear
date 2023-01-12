"""
Microsoft Archive parser

Author: Victor Stinner
Creation date: 2007-03-04
"""

from hachoir.parser import Parser
from hachoir.field import FieldSet, String, UInt32, SubFile
from hachoir.core.endian import LITTLE_ENDIAN
from hachoir.core.text_handler import textHandler, filesizeHandler, hexadecimal

MAX_NB_FILE = 100000


class FileIndex(FieldSet):
    static_size = 68 * 8

    def createFields(self):
        yield String(self, "filename", 56, truncate="\0", charset="ASCII")
        yield filesizeHandler(UInt32(self, "filesize"))
        yield textHandler(UInt32(self, "crc32"), hexadecimal)
        yield UInt32(self, "offset")

    def createDescription(self):
        return "File %s (%s) at %s" % (
            self["filename"].value, self["filesize"].display, self["offset"].value)


class MarFile(Parser):
    MAGIC = b"MARC"
    PARSER_TAGS = {
        "id": "mar",
        "category": "archive",
        "file_ext": ("mar",),
        "min_size": 80 * 8,  # At least one file index
        "magic": ((MAGIC, 0),),
        "description": "Microsoft Archive",
    }
    endian = LITTLE_ENDIAN

    def validate(self):
        if self.stream.readBytes(0, 4) != self.MAGIC:
            return "Invalid magic"
        if self["version"].value != 3:
            return "Invalid version"
        if not(1 <= self["nb_file"].value <= MAX_NB_FILE):
            return "Invalid number of file"
        return True

    def createFields(self):
        yield String(self, "magic", 4, "File signature (MARC)", charset="ASCII")
        yield UInt32(self, "version")
        yield UInt32(self, "nb_file")
        files = []
        for index in range(self["nb_file"].value):
            item = FileIndex(self, "file[]")
            yield item
            if item["filesize"].value:
                files.append(item)
        files.sort(key=lambda item: item["offset"].value)
        for index in files:
            padding = self.seekByte(index["offset"].value)
            if padding:
                yield padding
            size = index["filesize"].value
            desc = "File %s" % index["filename"].value
            yield SubFile(self, "data[]", size, desc, filename=index["filename"].value)
