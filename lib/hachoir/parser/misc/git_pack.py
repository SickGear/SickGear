"""
Git pack file parser

See https://git-scm.com/docs/gitformat-pack

FIXME: there are probably still some endianness bugs in this parser.
"""

from hachoir.parser import Parser
from hachoir.field import (UInt8, UInt32, String, SubFile, FieldSet, Bit, Bits, RawBytes, Enum, GenericInteger)
from hachoir.core.endian import LITTLE_ENDIAN, BIG_ENDIAN
from hachoir.core.text_handler import textHandler, hexadecimal
from hachoir.parser.common.deflate import Deflate
import zlib


class ObjCommitParser(Parser):
    PARSER_TAGS = {
        "id": "git_pack_obj_commit",
        "min_size": (5 + 40 + 1) * 8,  # size of the "tree" line
        "description": "Git pack file: commit object",
    }

    endian = LITTLE_ENDIAN  # should not actually matter here, since this data should only contain text

    def validate(self):
        return True

    def createFields(self):
        yield String(self, "keyword_tree", 5)
        yield String(self, "tree_id", 40)
        yield String(self, "newline[]", 1)
        yield String(self, "remaining_text", (self.size - self.current_size) // 8)
        # FIXME: parse more fields. Is the order static?


class ObjOfsDeltaParser(Parser):
    PARSER_TAGS = {
        "id": "git_pack_obj_ofs_delta",
        "min_size": 2 * 8,  # at least source and target length, with at least one byte each
        "description": "Git pack file: ofs-delta object",
    }

    endian = BIG_ENDIAN

    def validate(self):
        return True

    def createFields(self):
        yield VarLengthInt(self, "source_length")
        yield VarLengthInt(self, "target_length")

        while self.current_size < self._size:
            yield DeltaInstruction(self, "instruction[]")


class DeltaInstruction(FieldSet):
    "See https://git-scm.com/docs/gitformat-pack#_deltified_representation"

    COPY_OR_ADD = {
        0: "ADD",
        1: "COPY",
    }

    def createFields(self):
        self.desc = ""
        yield Enum(Bit(self, "copy_or_add"), self.COPY_OR_ADD)

        if self["copy_or_add"].value:
            yield Bit(self, "size1_set")
            yield Bit(self, "size2_set")
            yield Bit(self, "size3_set")
            yield Bit(self, "offset1_set")
            yield Bit(self, "offset2_set")
            yield Bit(self, "offset3_set")
            yield Bit(self, "offset4_set")

            offset = 0
            if self["offset1_set"].value:
                yield UInt8(self, "offset1")
                offset |= (self["offset1"].value << 24)
            if self["offset2_set"].value:
                yield UInt8(self, "offset2")
                offset |= (self["offset2"].value << 16)
            if self["offset3_set"].value:
                yield UInt8(self, "offset3")
                offset |= (self["offset3"].value << 8)
            if self["offset4_set"].value:
                yield UInt8(self, "offset4")
                offset |= self["offset4"].value

            size = 0
            if self["size1_set"].value:
                yield UInt8(self, "size1")
                size |= (self["size1"].value << 16)
            if self["size2_set"].value:
                yield UInt8(self, "size2")
                size |= (self["size2"].value << 8)
            if self["size3_set"].value:
                yield UInt8(self, "size3")
                size |= self["size3"].value

            self.desc = f"copy {size} B from offset {offset}"

        else:
            data_size = Bits(self, "data_size", 7)
            yield data_size
            yield RawBytes(self, "data", data_size.value)
            self.desc = f"add {len(self['data'].value)} B"

    def createDescription(self):
        return self.desc


class VarLengthInt(FieldSet):
    "Variable-length integer; see https://git-scm.com/docs/gitformat-pack#_size_encoding"

    endian = BIG_ENDIAN

    def createFields(self):
        self.decoded_value = 0
        num_decoded_size_bits = 0
        while True:
            msb_field = Bit(self, "msb[]")
            yield msb_field
            value_field = Bits(self, "value[]", 7)
            yield value_field
            self.decoded_value |= (value_field.value << num_decoded_size_bits)
            num_decoded_size_bits += 7
            if not msb_field.value:
                break

    def createDescription(self):
        return f"value={self.decoded_value}"


class TypeAndSize(FieldSet):
    "Variable-length integer, with preceding type information."

    OBJECT_TYPES = {
        1: "OBJ_COMMIT",
        2: "OBJ_TREE",
        3: "OBJ_BLOB",
        4: "OBJ_TAG",
        6: "OBJ_OFS_DELTA",
        7: "OBJ_REF_DELTA",
    }

    def createFields(self):
        yield Bit(self, "msb[]")
        yield Enum(Bits(self, "typ", 3), self.OBJECT_TYPES)
        yield Bits(self, "size[]", 4)

        self.decoded_size = self["size[0]"].value
        num_decoded_size_bits = 4
        latest_msb = self["msb[0]"].value
        while latest_msb:
            msb_field = Bit(self, "msb[]")
            yield msb_field
            size_field = Bits(self, "size[]", 7)
            yield size_field
            self.decoded_size |= (size_field.value << num_decoded_size_bits)
            num_decoded_size_bits += 7
            latest_msb = msb_field.value

    def createDescription(self):
        return f"type={self['typ']}, decompressed size={self.decoded_size}"


class ObjectEntry(FieldSet):

    def createFields(self):
        type_and_size = TypeAndSize(self, "type_and_size")
        yield type_and_size

        if type_and_size["typ"].value == 6:
            yield VarLengthInt(self, "offset")
        # FIXME: for OBJ_REF_DELTA objects the parser needs to add another field; but I haven't been able to create such test files yet.

        parser_for_sub_field = None
        if type_and_size["typ"].value == 1:
            parser_for_sub_field = ObjCommitParser
        elif type_and_size["typ"].value == 6:
            parser_for_sub_field = ObjOfsDeltaParser
        # FIXME: add parsers for other object types

        num_compressed_bytes = self._determine_zlib_data_size(self.stream, self.absolute_address + self.current_size)
        yield Deflate(SubFile(self, "compressed_data", num_compressed_bytes, parser_class=parser_for_sub_field), False)

    def createDescription(self):
        return self["type_and_size"].description

    def _determine_zlib_data_size(self, stream, start_addr_in_bits):
        # This file format does not store the size of the compressed data.
        # Workaround: try to parse the compressed data until the parser has reached an end, to find the size of the compressed section.
        # The parsed data is thrown away.
        decompressor = zlib.decompressobj()
        read_addr_in_bits = start_addr_in_bits
        total_bytes_read = 0
        while not decompressor.eof:
            max_remaining_bytes = (stream.size - read_addr_in_bits) // 8
            num_bytes_to_read = min(1000, max_remaining_bytes)
            bytes_read = stream.readBytes(read_addr_in_bits, num_bytes_to_read)
            total_bytes_read += len(bytes_read)
            read_addr_in_bits += (len(bytes_read) * 8)
            decompressor.decompress(bytes_read)

        return total_bytes_read - len(decompressor.unused_data)


class GitPackFile(Parser):

    PARSER_TAGS = {
        "id": "git_pack",
        "category": "misc",
        "file_ext": (".pack",),
        "mime": (u"application/octet-stream",),
        "min_size": (4 + 4 + 4) * 8,  # just the header
        "magic": ((b'PACK',),),
        "description": "Git pack file",
    }

    endian = BIG_ENDIAN

    def validate(self):
        return (self.stream.readBytes(0, 4) == b"PACK"
                and self["version"].value in (2, 3))

    def createFields(self):
        yield String(self, "magic", 4)
        yield UInt32(self, "version")
        yield UInt32(self, "num_objects")

        for i in range(self["num_objects"].value):
            yield ObjectEntry(self, "object[]")

        yield textHandler(GenericInteger(self, "checksum", False, 20 * 8, "SHA1 checksum of all previous data"), hexadecimal)
