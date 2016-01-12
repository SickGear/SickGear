"""
Parallel Realities Starfighter .pak file parser

See http://www.parallelrealities.co.uk/projects/starfighter.php
or svn://svn.debian.org/svn/pkg-games/packages/trunk/starfighter/

Author: Oliver Gerlich
"""

from hachoir_parser import Parser
from hachoir_core.field import (ParserError,
    UInt32, String, SubFile, FieldSet)
from hachoir_core.endian import LITTLE_ENDIAN
from hachoir_core.text_handler import filesizeHandler

class FileEntry(FieldSet):
    def createFields(self):
        yield String(self, "filename", 56, truncate="\0")
        yield filesizeHandler(UInt32(self, "size"))
        yield SubFile(self, "data", self["size"].value, filename=self["filename"].value)

    def createDescription(self):
        return self["filename"].value

class PRSPakFile(Parser):
    PARSER_TAGS = {
        "id": "prs_pak",
        "category": "archive",
        "file_ext": ("pak",),
        "mime": (u"application/octet-stream",),
        "min_size": 4*8, # just the identifier
        "magic": (('PACK', 0),),
        "description": "Parallel Realities Starfighter .pak archive",
    }

    endian = LITTLE_ENDIAN

    def validate(self):
        return (self.stream.readBytes(0, 4) == 'PACK'
          and self["file[0]/size"].value >= 0
          and len(self["file[0]/filename"].value) > 0)

    def createFields(self):
        yield String(self, "magic", 4)

        # all remaining data must be file entries:
        while self.current_size < self._size:
            yield FileEntry(self, "file[]")
