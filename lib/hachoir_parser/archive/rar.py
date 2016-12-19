"""
RAR parser

Status: can only read higher-level attructures
Author: Christophe Gisquet
"""

from hachoir_parser import Parser
from hachoir_core.field import (StaticFieldSet, FieldSet,
    Bit, Bits, Enum,
    UInt8, UInt16, UInt32, UInt64,
    String, TimeDateMSDOS32,
    NullBytes, NullBits, RawBytes)
from hachoir_core.text_handler import textHandler, filesizeHandler, hexadecimal
from hachoir_core.endian import LITTLE_ENDIAN
from hachoir_parser.common.msdos import MSDOSFileAttr32
from datetime import timedelta

MAX_FILESIZE = 1000 * 1024 * 1024

BLOCK_NAME = {
    0x72: "Marker",
    0x73: "Archive",
    0x74: "File",
    0x75: "Comment",
    0x76: "Extra info",
    0x77: "Subblock",
    0x78: "Recovery record",
    0x79: "Archive authenticity",
    0x7A: "New-format subblock",
    0x7B: "Archive end",
}

COMPRESSION_NAME = {
    0x30: "Storing",
    0x31: "Fastest compression",
    0x32: "Fast compression",
    0x33: "Normal compression",
    0x34: "Good compression",
    0x35: "Best compression"
}

OS_MSDOS = 0
OS_WIN32 = 2
OS_NAME = {
    0: "MS DOS",
    1: "OS/2",
    2: "Win32",
    3: "Unix",
}

DICTIONARY_SIZE = {
    0: "Dictionary size 64 Kb",
    1: "Dictionary size 128 Kb",
    2: "Dictionary size 256 Kb",
    3: "Dictionary size 512 Kb",
    4: "Dictionary size 1024 Kb",
    7: "File is a directory",
}

def formatRARVersion(field):
    """
    Decodes the RAR version stored on 1 byte
    """
    return "%u.%u" % divmod(field.value, 10)

def markerFlags(s):
    yield UInt16(s, "flags", "Marker flags, always 0x1a21")

commonFlags = (
    (Bit, "is_ignorable", "Old versions of RAR should ignore this block when copying data"),
    (Bit, "has_added_size", "Additional field indicating additional size"),
)

class ArchiveFlags(StaticFieldSet):
    format = (
        (Bit, "vol", "Archive volume"),
        (Bit, "has_comment", "Whether there is a comment"),
        (Bit, "is_locked", "Archive volume"),
        (Bit, "is_solid", "Whether files can be extracted separately"),
        (Bit, "new_numbering", "New numbering, or compressed comment"), # From unrar
        (Bit, "has_authenticity_information", "The integrity/authenticity of the archive can be checked"),
        (Bit, "is_protected", "The integrity/authenticity of the archive can be checked"),
        (Bit, "is_passworded", "Needs a password to be decrypted"),
        (Bit, "is_first_vol", "Whether it is the first volume"),
        (Bit, "is_encrypted", "Whether the encryption version is present"),
        (NullBits, "internal", 4, "Reserved for 'internal use'"),
    ) + commonFlags

def archiveFlags(s):
    yield ArchiveFlags(s, "flags", "Archiver block flags")

def archiveHeader(s):
    yield NullBytes(s, "reserved[]", 2, "Reserved word")
    yield NullBytes(s, "reserved[]", 4, "Reserved dword")

def commentHeader(s):
    yield filesizeHandler(UInt16(s, "total_size", "Comment header size + comment size"))
    yield filesizeHandler(UInt16(s, "uncompressed_size", "Uncompressed comment size"))
    yield UInt8(s, "required_version", "RAR version needed to extract comment")
    yield UInt8(s, "packing_method", "Comment packing method")
    yield UInt16(s, "comment_crc16", "Comment CRC")

def commentBody(s):
    size = s["total_size"].value - s.current_size
    if size > 0:
        yield RawBytes(s, "comment_data", size, "Compressed comment data")

def signatureHeader(s):
    yield TimeDateMSDOS32(s, "creation_time")
    yield filesizeHandler(UInt16(s, "arc_name_size"))
    yield filesizeHandler(UInt16(s, "user_name_size"))

def recoveryHeader(s):
    yield filesizeHandler(UInt32(s, "total_size"))
    yield textHandler(UInt8(s, "version"), hexadecimal)
    yield UInt16(s, "rec_sectors")
    yield UInt32(s, "total_blocks")
    yield RawBytes(s, "mark", 8)

def avInfoHeader(s):
    yield filesizeHandler(UInt16(s, "total_size", "Total block size"))
    yield UInt8(s, "version", "Version needed to decompress", handler=hexadecimal)
    yield UInt8(s, "method", "Compression method", handler=hexadecimal)
    yield UInt8(s, "av_version", "Version for AV", handler=hexadecimal)
    yield UInt32(s, "av_crc", "AV info CRC32", handler=hexadecimal)

def avInfoBody(s):
    size = s["total_size"].value - s.current_size
    if size > 0:
        yield RawBytes(s, "av_info_data", size, "AV info")

class FileFlags(FieldSet):
    static_size = 16
    def createFields(self):
        yield Bit(self, "continued_from", "File continued from previous volume")
        yield Bit(self, "continued_in", "File continued in next volume")
        yield Bit(self, "is_encrypted", "File encrypted with password")
        yield Bit(self, "has_comment", "File comment present")
        yield Bit(self, "is_solid", "Information from previous files is used (solid flag)")
        # The 3 following lines are what blocks more staticity
        yield Enum(Bits(self, "dictionary_size", 3, "Dictionary size"), DICTIONARY_SIZE)
        yield Bit(self, "is_large", "file64 operations needed")
        yield Bit(self, "is_unicode", "Filename also encoded using Unicode")
        yield Bit(self, "has_salt", "Has salt for encryption")
        yield Bit(self, "uses_file_version", "File versioning is used")
        yield Bit(self, "has_ext_time", "Extra time info present")
        yield Bit(self, "has_ext_flags", "Extra flag ??")
        for field in commonFlags:
            yield field[0](self, *field[1:])

def fileFlags(s):
    yield FileFlags(s, "flags", "File block flags")

class ExtTimeFlags(FieldSet):
    static_size = 16
    def createFields(self):
        for name in ['arctime', 'atime', 'ctime', 'mtime']:
            yield Bits(self, "%s_count" % name, 2, "Number of %s bytes" % name)
            yield Bit(self, "%s_onesec" % name, "Add one second to the timestamp?")
            yield Bit(self, "%s_present" % name, "Is %s extra time present?" % name)

class ExtTime(FieldSet):
    def createFields(self):
        yield ExtTimeFlags(self, "time_flags")
        for name in ['mtime', 'ctime', 'atime', 'arctime']:
            if self['time_flags/%s_present' % name].value:
                if name != 'mtime':
                    yield TimeDateMSDOS32(self, "%s" % name, "%s DOS timestamp" % name)
                count = self['time_flags/%s_count' % name].value
                if count:
                    yield Bits(self, "%s_remainder" % name, 8 * count, "%s extra precision time (in 100ns increments)" % name)

    def createDescription(self):
        out = 'Time extension'
        pieces = []
        for name in ['mtime', 'ctime', 'atime', 'arctime']:
            if not self['time_flags/%s_present' % name].value:
                continue

            if name == 'mtime':
                basetime = self['../ftime'].value
            else:
                basetime = self['%s' % name].value
            delta = timedelta()
            if self['time_flags/%s_onesec' % name].value:
                delta += timedelta(seconds=1)
            if '%s_remainder'%name in self:
                delta += timedelta(microseconds=self['%s_remainder' % name].value / 10.0)
            pieces.append('%s=%s' % (name, basetime + delta))
        if pieces:
            out += ': ' + ', '.join(pieces)
        return out

def specialHeader(s, is_file):
    yield filesizeHandler(UInt32(s, "compressed_size", "Compressed size (bytes)"))
    yield filesizeHandler(UInt32(s, "uncompressed_size", "Uncompressed size (bytes)"))
    yield Enum(UInt8(s, "host_os", "Operating system used for archiving"), OS_NAME)
    yield textHandler(UInt32(s, "crc32", "File CRC32"), hexadecimal)
    yield TimeDateMSDOS32(s, "ftime", "Date and time (MS DOS format)")
    yield textHandler(UInt8(s, "version", "RAR version needed to extract file"), formatRARVersion)
    yield Enum(UInt8(s, "method", "Packing method"), COMPRESSION_NAME)
    yield filesizeHandler(UInt16(s, "filename_length", "File name size"))
    if s["host_os"].value in (OS_MSDOS, OS_WIN32):
        yield MSDOSFileAttr32(s, "file_attr", "File attributes")
    else:
        yield textHandler(UInt32(s, "file_attr", "File attributes"), hexadecimal)

    # Start additional field from unrar
    if s["flags/is_large"].value:
        yield filesizeHandler(UInt64(s, "large_size", "Extended 64bits filesize"))

    # End additional field
    size = s["filename_length"].value
    if size > 0:
        if s["flags/is_unicode"].value:
            charset = "UTF-8"
        else:
            charset = "ISO-8859-15"
        yield String(s, "filename", size, "Filename", charset=charset)
    # Start additional fields from unrar - file only
    if is_file:
        if s["flags/has_salt"].value:
            yield RawBytes(s, "salt", 8, "Encryption salt to increase security")
        if s["flags/has_ext_time"].value:
            yield ExtTime(s, "extra_time")

def fileHeader(s):
    return specialHeader(s, True)

def fileBody(s):
    # File compressed data
    size = s["compressed_size"].value
    if s["flags/is_large"].value:
        size += s["large_size"].value
    if size > 0:
        yield RawBytes(s, "compressed_data", size, "File compressed data")

def fileDescription(tag):
    def _fileDescription(s):
        return "%s: %s (%s)" % \
               (tag, s["filename"].display, s["compressed_size"].display)
    return _fileDescription

def newSubHeader(s):
    return specialHeader(s, False)

class EndFlags(StaticFieldSet):
    format = (
        (Bit, "has_next_vol", "Whether there is another next volume"),
        (Bit, "has_data_crc", "Whether a CRC value is present"),
        (Bit, "rev_space"),
        (Bit, "has_vol_number", "Whether the volume number is present"),
        (NullBits, "unused[]", 10),
    ) + commonFlags

def endFlags(s):
    yield EndFlags(s, "flags", "End block flags")

class BlockFlags(StaticFieldSet):
    static_size = 16

    format = (
        (NullBits, "unused[]", 14),
    ) + commonFlags

class Block(FieldSet):
    BLOCK_INFO = {
        # None means 'use default function'
        0x72: ("marker", "File format marker", markerFlags, None, None),
        0x73: ("archive_start", "Archive info", archiveFlags, archiveHeader, None),
        0x74: ("file[]", fileDescription("File entry"), fileFlags, fileHeader, fileBody),
        0x75: ("comment[]", "Comment", None, commentHeader, commentBody),
        0x76: ("av_info[]", "Extra information", None, avInfoHeader, avInfoBody),
        0x77: ("sub_block[]", fileDescription("Subblock"), None, newSubHeader, fileBody),
        0x78: ("recovery[]", "Recovery block", None, recoveryHeader, None),
        0x79: ("signature", "Signature block", None, signatureHeader, None),
        0x7A: ("sub_block[]", fileDescription("New-format subblock"), fileFlags,
               newSubHeader, fileBody),
        0x7B: ("archive_end", "Archive end block", endFlags, None, None),
    }

    def __init__(self, parent, name):
        FieldSet.__init__(self, parent, name)
        t = self["block_type"].value
        if t in self.BLOCK_INFO:
            self._name, desc, parseFlags, parseHeader, parseBody = self.BLOCK_INFO[t]
            if callable(desc):
                self.createDescription = lambda: desc(self)
            elif desc:
                self._description = desc
            if parseFlags    : self.parseFlags     = lambda: parseFlags(self)
            if parseHeader   : self.parseHeader    = lambda: parseHeader(self)
            if parseBody     : self.parseBody      = lambda: parseBody(self)
        else:
            self.info("Processing as unknown block block of type %u" % type)

        self._size = 8*self["block_size"].value
        if t == 0x74 or t == 0x7A:
            self._size += 8*self["compressed_size"].value
            if "is_large" in self["flags"] and self["flags/is_large"].value:
                self._size += 8*self["large_size"].value
        elif "has_added_size" in self:
            self._size += 8*self["added_size"].value
        # TODO: check if any other member is needed here

    def createFields(self):
        yield textHandler(UInt16(self, "crc16", "Block CRC16"), hexadecimal)
        yield textHandler(UInt8(self, "block_type", "Block type"), hexadecimal)

        # Parse flags
        for field in self.parseFlags():
            yield field

        # Get block size
        yield filesizeHandler(UInt16(self, "block_size", "Block size"))

        # Parse remaining header
        for field in self.parseHeader():
            yield field

        # Finish header with stuff of unknow size
        size = self["block_size"].value - (self.current_size//8)
        if size > 0:
            yield RawBytes(self, "unknown", size, "Unknow data (UInt32 probably)")

        # Parse body
        for field in self.parseBody():
            yield field

    def createDescription(self):
        return "Block entry: %s" % self["type"].display

    def parseFlags(self):
        yield BlockFlags(self, "flags", "Block header flags")

    def parseHeader(self):
        if "has_added_size" in self["flags"] and \
           self["flags/has_added_size"].value:
            yield filesizeHandler(UInt32(self, "added_size",
                "Supplementary block size"))

    def parseBody(self):
        """
        Parse what is left of the block
        """
        size = self["block_size"].value - (self.current_size//8)
        if "has_added_size" in self["flags"] and self["flags/has_added_size"].value:
            size += self["added_size"].value
        if size > 0:
            yield RawBytes(self, "body", size, "Body data")

class RarFile(Parser):
    MAGIC = "Rar!\x1A\x07\x00"
    PARSER_TAGS = {
        "id": "rar",
        "category": "archive",
        "file_ext": ("rar",),
        "mime": (u"application/x-rar-compressed", ),
        "min_size": 7*8,
        "magic": ((MAGIC, 0),),
        "description": "Roshal archive (RAR)",
    }
    endian = LITTLE_ENDIAN

    def validate(self):
        magic = self.MAGIC
        if self.stream.readBytes(0, len(magic)) != magic:
            return "Invalid magic"
        return True

    def createFields(self):
        while not self.eof:
            yield Block(self, "block[]")

    def createContentSize(self):
        start = 0
        end = MAX_FILESIZE * 8
        pos = self.stream.searchBytes("\xC4\x3D\x7B\x00\x40\x07\x00", start, end)
        if pos is not None:
            return pos + 7*8
        return None

