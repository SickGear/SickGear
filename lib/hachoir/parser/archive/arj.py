"""
ARJ archive file parser

https://github.com/FarGroup/FarManager/blob/master/plugins/multiarc/arc.doc/arj.txt
"""

from hachoir.core.endian import LITTLE_ENDIAN
from hachoir.field import (FieldSet, ParserError,
                           CString, Enum, RawBytes,
                           UInt8, UInt16, UInt32,
                           Bytes)
from hachoir.parser import Parser

HOST_OS = {
    0: "MSDOS",
    1: "PRIMOS",
    2: "UNIX",
    3: "AMIGA",
    4: "MACDOS",
    5: "OS/2",
    6: "APPLE GS",
    7: "ATARI ST",
    8: "NEXT",
    9: "VAX VMS",
    10: "WIN95",
    11: "WIN32",
}

FILE_TYPE = {
    0: "BINARY",
    1: "TEXT",
    2: "COMMENT",
    3: "DIRECTORY",
    4: "VOLUME",
    5: "CHAPTER",
}

MAGIC = b"\x60\xEA"


class BaseBlock(FieldSet):
    @property
    def isEmpty(self):
        return self["basic_header_size"].value == 0

    def _header_start_fields(self):
        yield Bytes(self, "magic", len(MAGIC))
        if self["magic"].value != MAGIC:
            raise ParserError("Wrong header magic")
        yield UInt16(self, "basic_header_size", "zero if end of archive")
        if not self.isEmpty:
            yield UInt8(self, "first_hdr_size")
            yield UInt8(self, "archiver_version")
            yield UInt8(self, "min_archiver_version")
            yield Enum(UInt8(self, "host_os"), HOST_OS)
            yield UInt8(self, "arj_flags")

    def _header_end_fields(self):
        yield UInt8(self, "last_chapter")
        fhs = self["first_hdr_size"]
        name_position = fhs.address // 8 + fhs.value
        current_position = self["last_chapter"].address // 8 + 1
        if name_position > current_position:
            yield RawBytes(self, "reserved2", name_position - current_position)

        yield CString(self, "filename", "File name", charset="ASCII")
        yield CString(self, "comment", "Comment", charset="ASCII")
        yield UInt32(self, "crc", "Header CRC")

        i = 0
        while not self.eof:
            yield UInt16(self, f"extended_header_size_{i}")
            cur_size = self[f"extended_header_size_{i}"].value
            if cur_size == 0:
                break
            yield RawBytes(self, "extended_header_data", cur_size)
            yield UInt32(self, f"extended_header_crc_{i}")
            i += 1

    def validate(self):
        if self.stream.readBytes(0, 2) != MAGIC:
            return "Invalid magic"
        return True


class Header(BaseBlock):
    def createFields(self):
        yield from self._header_start_fields()
        if not self.isEmpty:
            yield UInt8(self, "security_version")
            yield Enum(UInt8(self, "file_type"), FILE_TYPE)
            yield UInt8(self, "reserved")
            yield UInt32(self, "date_time_created")
            yield UInt32(self, "date_time_modified")
            yield UInt32(self, "archive_size")
            yield UInt32(self, "security_envelope_file_position")
            yield UInt16(self, "filespec_position")
            yield UInt16(self, "security_envelope_data_len")
            yield UInt8(self, "encryption_version")
            yield from self._header_end_fields()

    def createDescription(self):
        if self.isEmpty:
            return "Empty main header"
        return "Main header of '%s'" % self["filename"].value


class Block(BaseBlock):
    def createFields(self):
        yield from self._header_start_fields()
        if not self.isEmpty:
            yield UInt8(self, "method")
            yield Enum(UInt8(self, "file_type"), FILE_TYPE)
            yield UInt8(self, "reserved")
            yield UInt32(self, "date_time_modified")
            yield UInt32(self, "compressed_size")
            yield UInt32(self, "original_size")
            yield UInt32(self, "original_file_crc")
            yield UInt16(self, "filespec_position")
            yield UInt16(self, "file_access_mode")
            yield UInt8(self, "first_chapter")
            yield from self._header_end_fields()
            compressed_size = self["compressed_size"].value
            if compressed_size > 0:
                yield RawBytes(self, "compressed_data", compressed_size)

    def createDescription(self):
        if self.isEmpty:
            return "Empty file header"
        return "File header of '%s'" % self["filename"].value


class ArjParser(Parser):
    endian = LITTLE_ENDIAN
    PARSER_TAGS = {
        "id": "arj",
        "category": "archive",
        "file_ext": ("arj",),
        "min_size": 4 * 8,
        "description": "ARJ archive"
    }

    def validate(self):
        if self.stream.readBytes(0, 2) != MAGIC:
            return "Invalid magic"
        return True

    def createFields(self):
        yield Header(self, "header")
        if not self["header"].isEmpty:
            while not self.eof:
                block = Block(self, "file_header[]")
                yield block
                if block.isEmpty:
                    break
