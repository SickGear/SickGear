"""
7zip file parser

Informations:
- File 7zformat.txt of 7-zip SDK:
  http://www.7-zip.org/sdk.html

Author: Olivier SCHWAB
Creation date: 6 december 2006

Updated by: Robert Xiao
Date: February 26 2011
"""

from hachoir_parser import Parser
from hachoir_core.field import (Field, FieldSet, ParserError,
    CompressedField, CString,
    Enum, Bit, Bits, UInt8, UInt32, UInt64,
    Bytes, RawBytes, TimestampWin64)
from hachoir_core.stream import StringInputStream
from hachoir_core.endian import LITTLE_ENDIAN
from hachoir_core.text_handler import textHandler, hexadecimal, filesizeHandler
from hachoir_core.tools import createDict, alignValue
from hachoir_parser.common.msdos import MSDOSFileAttr32

try:
    from pylzma import decompress as lzmadecompress
    has_lzma = True
except ImportError:
    has_lzma = False

class SZUInt64(Field):
    """
    Variable length UInt64, where the first byte gives both the number of bytes
    needed and the upper byte value.
    """
    def __init__(self, parent, name, max_size=None, description=None):
        Field.__init__(self, parent, name, size=8, description=description)
        value = 0
        addr = self.absolute_address
        mask = 0x80
        firstByte = parent.stream.readBits(addr, 8, LITTLE_ENDIAN)
        for i in xrange(8):
            addr += 8
            if not (firstByte & mask):
                value += ((firstByte & (mask-1)) << (8*i))
                break
            value |= (parent.stream.readBits(addr, 8, LITTLE_ENDIAN) << (8*i))
            mask >>= 1
            self._size += 8
        self.createValue = lambda: value

PROP_INFO = {
    0x00: ('kEnd', 'End-of-header marker'),

    0x01: ('kHeader', 'Archive header'),

    0x02: ('kArchiveProperties', 'Archive properties'),

    0x03: ('kAdditionalStreamsInfo', 'AdditionalStreamsInfo'),
    0x04: ('kMainStreamsInfo', 'MainStreamsInfo'),
    0x05: ('kFilesInfo', 'FilesInfo'),

    0x06: ('kPackInfo', 'PackInfo'),
    0x07: ('kUnPackInfo', 'UnPackInfo'),
    0x08: ('kSubStreamsInfo', 'SubStreamsInfo'),

    0x09: ('kSize', 'Size'),
    0x0A: ('kCRC', 'CRC'),

    0x0B: ('kFolder', 'Folder'),

    0x0C: ('kCodersUnPackSize', 'CodersUnPackSize'),
    0x0D: ('kNumUnPackStream', 'NumUnPackStream'),

    0x0E: ('kEmptyStream', 'EmptyStream'),
    0x0F: ('kEmptyFile', 'EmptyFile'),
    0x10: ('kAnti', 'Anti'),

    0x11: ('kName', 'Name'),
    0x12: ('kCreationTime', 'CreationTime'),
    0x13: ('kLastAccessTime', 'LastAccessTime'),
    0x14: ('kLastWriteTime', 'LastWriteTime'),
    0x15: ('kWinAttributes', 'WinAttributes'),
    0x16: ('kComment', 'Comment'),

    0x17: ('kEncodedHeader', 'Encoded archive header'),
}
PROP_IDS = createDict(PROP_INFO, 0)
PROP_DESC = createDict(PROP_INFO, 1)
# create k* constants
for k in PROP_IDS:
    globals()[PROP_IDS[k]] = k

def ReadNextByte(self):
    return self.stream.readBits(self.absolute_address + self.current_size, 8, self.endian)

def PropID(self, name):
    return Enum(UInt8(self, name), PROP_IDS)

class SevenZipBitVector(FieldSet):
    def __init__(self, parent, name, num, has_all_byte=False, **args):
        FieldSet.__init__(self, parent, name, **args)
        self.has_all_byte=has_all_byte
        self.num = num
    def createFields(self):
        if self.has_all_byte:
            yield Enum(UInt8(self, "all_defined"), {0:'False', 1:'True'})
            if self['all_defined'].value:
                return
        nbytes = alignValue(self.num, 8)//8
        ctr = 0
        for i in xrange(nbytes):
            for j in reversed(xrange(8)):
                yield Bit(self, "bit[%d]"%(ctr+j))
            ctr += 8
    def isAllDefined(self):
        return self.has_all_byte and self['all_defined'].value
    def isDefined(self, index):
        if self.isAllDefined():
            return True
        return self['bit[%d]'%index].value
    def createValue(self):
        if self.isAllDefined():
            return range(self.num)
        return [i for i in xrange(self.num) if self['bit[%d]'%i].value]
    def createDisplay(self):
        if self.isAllDefined():
            return 'all'
        return ','.join(str(i) for i in self.value)

class ArchiveProperty(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        size = SZUInt64(self, "size")
        yield size
        yield RawBytes(self, "data", size.value)
    def createDescription(self):
        return self['id'].display

class ArchiveProperties(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        while not self.eof:
            uid = ReadNextByte(self)
            if uid == kEnd:
                yield PropID(self, "end_marker")
                break
            yield ArchiveProperty(self, "prop[]")

class Digests(FieldSet):
    def __init__(self, parent, name, num_digests, digest_desc=None, desc=None):
        FieldSet.__init__(self, parent, name, desc)
        self.num_digests = num_digests
        if digest_desc is None:
            self.digest_desc = ['stream %d'%i for i in xrange(num_digests)]
        else:
            self.digest_desc = digest_desc
    def createFields(self):
        yield PropID(self, "id")
        definearr = SevenZipBitVector(self, "defined", self.num_digests, has_all_byte=True)
        yield definearr
        for index in definearr.value:
            yield textHandler(UInt32(self, "digest[]",
                "Digest for %s" % self.digest_desc[index]), hexadecimal)

class PackInfo(FieldSet):
    def createFields(self):
        yield PropID(self, "id")

        yield SZUInt64(self, "pack_pos", "File offset to the packed data")
        num = SZUInt64(self, "num_pack_streams", "Number of packed streams")
        yield num

        while not self.eof:
            uid = ReadNextByte(self)
            if uid == kEnd:
                yield PropID(self, "end_marker")
                break
            elif uid == kSize:
                yield PropID(self, "size_marker")
                for index in xrange(num.value):
                    yield SZUInt64(self, "pack_size[]")
            elif uid == kCRC:
                yield Digests(self, "digests", num.value)
            else:
                raise ParserError("Unexpected ID (%i)" % uid)

METHODS = {
    "\0": "Copy",
    "\3": "Delta",
    "\4": "x86_BCJ",
    "\5": "PowerPC",
    "\6": "IA64",
    "\7": "ARM_LE",
    "\8": "ARMT_LE", # thumb
    "\9": "SPARC",
    "\x21": "LZMA2",
    "\2\3\2": "Common-Swap-2",
    "\2\3\4": "Common-Swap-4",
    "\3\1\1": "7z-LZMA",
    "\3\3\1\3": "7z-Branch-x86-BCJ",
    "\3\3\1\x1b": "7z-Branch-x86-BCJ2",
    "\3\3\2\5": "7z-Branch-PowerPC-BE",
    "\3\3\3\1": "7z-Branch-Alpha-LE",
    "\3\3\4\1": "7z-Branch-IA64-LE",
    "\3\3\5\1": "7z-Branch-ARM-LE",
    "\3\3\6\5": "7z-Branch-M68-BE",
    "\3\3\7\1": "7z-Branch-ARMT-LE",
    "\3\3\8\5": "7z-Branch-SPARC-BE",
    "\3\4\1": "7z-PPMD",
    "\3\x7f\1": "7z-Experimental",
    "\4\0": "Reserved",
    "\4\1\0": "Zip-Copy",
    "\4\1\1": "Zip-Shrink",
    "\4\1\6": "Zip-Implode",
    "\4\1\x08": "Zip-Deflate",
    "\4\1\x09": "Zip-Deflate64",
    "\4\1\x10": "Zip-BZip2",
    "\4\1\x14": "Zip-LZMA",
    "\4\1\x60": "Zip-JPEG",
    "\4\1\x61": "Zip-WavPack",
    "\4\1\x62": "Zip-PPMD",
    "\4\1\x63": "Zip-wzAES",
    "\4\2\2": "BZip2",
    "\4\3\1": "RAR-15",
    "\4\3\2": "RAR-20",
    "\4\3\3": "RAR-29",
    "\4\4\1": "Arj3",
    "\4\4\2": "Arj4",
    "\4\5": "Z",
    "\4\6": "LZH",
    "\4\7": "7z-Reserved",
    "\4\8": "CAB",
    "\4\9\1": "NSIS-Deflate",
    "\4\9\1": "NSIS-BZip2",
    "\6\0": "Crypto-Reserved",
    "\6\1\x00": "Crypto-AES128-ECB",
    "\6\1\x01": "Crypto-AES128-CBC",
    "\6\1\x02": "Crypto-AES128-CFB",
    "\6\1\x03": "Crypto-AES128-OFB",
    "\6\1\x40": "Crypto-AES192-ECB",
    "\6\1\x41": "Crypto-AES192-CBC",
    "\6\1\x42": "Crypto-AES192-CFB",
    "\6\1\x43": "Crypto-AES192-OFB",
    "\6\1\x80": "Crypto-AES256-ECB",
    "\6\1\x81": "Crypto-AES256-CBC",
    "\6\1\x82": "Crypto-AES256-CFB",
    "\6\1\x83": "Crypto-AES256-OFB",
    "\6\1\xc0": "Crypto-AES-ECB",
    "\6\1\xc1": "Crypto-AES-CBC",
    "\6\1\xc2": "Crypto-AES-CFB",
    "\6\1\xc3": "Crypto-AES-OFB",
    "\6\7": "Crypto-Reserved",
    "\6\x0f": "Crypto-Reserved",
    "\6\xf0": "Crypto-Misc",
    "\6\xf1\1\1": "Crypto-Zip",
    "\6\xf1\3\2": "Crypto-RAR-Unknown",
    "\6\xf1\3\3": "Crypto-RAR-29", # AES128
    "\6\xf1\7\1": "Crypto-7z", # AES256
    "\7\0": "Hash-None",
    "\7\1": "Hash-CRC",
    "\7\2": "Hash-SHA1",
    "\7\3": "Hash-SHA256",
    "\7\4": "Hash-SHA384",
    "\7\5": "Hash-SHA512",
    "\7\xf0": "Hash-Misc",
    "\7\xf1\3\3": "Hash-RAR-29", # modified SHA1
    "\7\xf1\7\1": "Hash-7z", # SHA256
}

class Coder(FieldSet):
    def createFields(self):
        yield Bits(self, "id_size", 4)
        yield Bit(self, "is_not_simple", "If unset, stream setup is simple")
        yield Bit(self, "has_attribs", "Are there compression properties attached?")
        yield Bit(self, "unused[]")
        yield Bit(self, "is_not_last_method", "Are there more methods after this one in the alternative method list?")
        size = self['id_size'].value
        if size > 0:
            yield Enum(RawBytes(self, "id", size), METHODS)
        if self['is_not_simple'].value:
            yield SZUInt64(self, "num_stream_in")
            yield SZUInt64(self, "num_stream_out")
            self.info("Streams: IN=%u    OUT=%u" % \
                      (self["num_stream_in"].value, self["num_stream_out"].value))
        if self['has_attribs'].value:
            size = SZUInt64(self, "properties_size")
            yield size
            yield RawBytes(self, "properties", size.value)
    def _get_num_streams(self, direction):
        if self['is_not_simple'].value:
            return self['num_stream_%s'%direction].value
        return 1
    in_streams = property(lambda self: self._get_num_streams('in'))
    out_streams = property(lambda self: self._get_num_streams('out'))

class CoderList(FieldSet):
    def createFields(self):
        while not self.eof:
            field = Coder(self, "coder[]")
            yield field
            if not field['is_not_last_method'].value:
                break

class BindPairInfo(FieldSet):
    def createFields(self):
        # 64 bits values then cast to 32 in fact
        yield SZUInt64(self, "in_index")
        yield SZUInt64(self, "out_index")
        self.info("Indexes: IN=%u   OUT=%u" % \
                  (self["in_index"].value, self["out_index"].value))

class Folder(FieldSet):
    def createFields(self):
        yield SZUInt64(self, "num_coders")
        num = self["num_coders"].value
        self.info("Folder: %u codecs" % num)

        in_streams = out_streams = 0

        # Coder info
        for index in xrange(num):
            ci = CoderList(self, "coders[]")
            yield ci
            in_streams += ci['coder[0]'].in_streams
            out_streams += ci['coder[0]'].out_streams
        self._in_streams = in_streams
        self._out_streams = out_streams

        # Bind pairs
        self.info("out streams: %u" % out_streams)
        for index in xrange(out_streams-1):
            yield BindPairInfo(self, "bind_pair[]")

        # Packed streams
        # @todo: Actually find mapping
        packed_streams = in_streams - out_streams + 1
        if packed_streams > 1:
            for index in xrange(packed_streams):
                yield SZUInt64(self, "pack_stream[]")
    def _get_num_streams(self, direction):
        list(self)
        return getattr(self, '_'+direction+'_streams')
    in_streams = property(lambda self: self._get_num_streams('in'))
    out_streams = property(lambda self: self._get_num_streams('out'))

class UnpackInfo(FieldSet):
    def createFields(self):
        yield PropID(self, "id")

        yield PropID(self, "folder_marker")
        assert self['folder_marker'].value == kFolder
        yield SZUInt64(self, "num_folders")

        # Get generic info
        num = self["num_folders"].value
        self.info("%u folders" % num)
        yield UInt8(self, "is_external")

        if self['is_external'].value:
            yield SZUInt64(self, "folder_data_offset", "Offset to folder data within data stream")
        else:
            # Read folder items
            for folder_index in xrange(num):
                yield Folder(self, "folder[]")

        yield PropID(self, "unpacksize_marker")
        assert self['unpacksize_marker'].value == kCodersUnPackSize
        for folder_index in xrange(num):
            folder = self["folder[%u]" % folder_index]
            for index in xrange(folder.out_streams):
                yield SZUInt64(self, "unpack_size[%d][%d]"%(folder_index,index))

        # Extract digests
        while not self.eof:
            uid = ReadNextByte(self)
            if uid == kEnd:
                yield PropID(self, "end_marker")
                break
            elif uid == kCRC:
                yield Digests(self, "digests", num)
            else:
                raise ParserError("Unexpected ID (%i)" % uid)

class SubStreamInfo(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        num_folders = self['../unpack_info/num_folders'].value
        num_unpackstreams = [1]*num_folders
        while not self.eof:
            uid = ReadNextByte(self)
            if uid == kEnd:
                yield PropID(self, "end_marker")
                break
            elif uid == kNumUnPackStream:
                yield PropID(self, "num_unpackstream_marker")
                for i in xrange(num_folders):
                    field = SZUInt64(self, "num_unpackstreams[]")
                    yield field
                    num_unpackstreams[i] = field.value
            elif uid == kSize:
                yield PropID(self, "size_marker")
                for i in xrange(num_folders):
                    # The last substream's size is the stream size minus the other substreams.
                    for j in xrange(num_unpackstreams[i]-1):
                        yield SZUInt64(self, "unpack_size[%d][%d]"%(i,j))
            elif uid == kCRC:
                digests = []
                for i in xrange(num_folders):
                    if num_unpackstreams[i] == 1 and 'digests' in self['../unpack_info']:
                        continue
                    for j in xrange(num_unpackstreams[i]):
                        digests.append('folder %i, stream %i'%(i, j))
                yield Digests(self, "digests", len(digests), digests)
            else:
                raise ParserError("Unexpected ID (%i)" % uid)

class StreamsInfo(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        while not self.eof:
            uid = ReadNextByte(self)
            if uid == kEnd:
                yield PropID(self, "end")
                break
            elif uid == kPackInfo:
                yield PackInfo(self, "pack_info", PROP_DESC[uid])
            elif uid == kUnPackInfo:
                yield UnpackInfo(self, "unpack_info", PROP_DESC[uid])
            elif uid == kSubStreamsInfo:
                yield SubStreamInfo(self, "substreams_info", PROP_DESC[uid])
            else:
                raise ParserError("Unexpected ID (%i)" % uid)

class EncodedHeader(StreamsInfo):
    pass

class EmptyStreamProperty(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        yield SZUInt64(self, "size")
        yield SevenZipBitVector(self, "vec", self['../num_files'].value)
    def createValue(self):
        return self['vec'].value
    def createDisplay(self):
        return self['vec'].display

class EmptyFileProperty(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        yield SZUInt64(self, "size")
        empty_streams = self['../empty_streams/vec'].value
        yield SevenZipBitVector(self, "vec", len(empty_streams))
    def createValue(self):
        empty_streams = self['../empty_streams/vec'].value
        return [empty_streams[i] for i in self['vec'].value]
    def createDisplay(self):
        return ','.join(str(i) for i in self.value)

class FileTimeProperty(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        yield SZUInt64(self, "size")
        definearr = SevenZipBitVector(self, "defined", self['../num_files'].value, has_all_byte=True)
        yield definearr
        yield UInt8(self, "is_external")
        if self['is_external'].value:
            yield SZUInt64(self, "folder_data_offset", "Offset to folder data within data stream")
        else:
            for index in definearr.value:
                yield TimestampWin64(self, "timestamp[%d]"%index)

class FileNames(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        yield SZUInt64(self, "size")
        yield UInt8(self, "is_external")
        if self['is_external'].value:
            yield SZUInt64(self, "folder_data_offset", "Offset to folder data within data stream")
        else:
            for index in xrange(self['../num_files'].value):
                yield CString(self, "name[%d]"%index, charset="UTF-16-LE")

class FileAttributes(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        yield SZUInt64(self, "size")
        definearr = SevenZipBitVector(self, "defined", self['../num_files'].value, has_all_byte=True)
        yield definearr
        yield UInt8(self, "is_external")
        if self['is_external'].value:
            yield SZUInt64(self, "folder_data_offset", "Offset to folder data within data stream")
        else:
            for index in definearr.value:
                yield MSDOSFileAttr32(self, "attributes[%d]"%index)

class FilesInfo(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        yield SZUInt64(self, "num_files")
        while not self.eof:
            uid = ReadNextByte(self)
            if uid == kEnd:
                yield PropID(self, "end_marker")
                break
            elif uid == kEmptyStream:
                yield EmptyStreamProperty(self, "empty_streams")
            elif uid == kEmptyFile:
                yield EmptyFileProperty(self, "empty_files")
            elif uid == kAnti:
                yield EmptyFileProperty(self, "anti_files")
            elif uid == kCreationTime:
                yield FileTimeProperty(self, "creation_time")
            elif uid == kLastAccessTime:
                yield FileTimeProperty(self, "access_time")
            elif uid == kLastWriteTime:
                yield FileTimeProperty(self, "modified_time")
            elif uid == kName:
                yield FileNames(self, "filenames")
            elif uid == kWinAttributes:
                yield FileAttributes(self, "attributes")
            else:
                yield ArchiveProperty(self, "prop[]")

class Header(FieldSet):
    def createFields(self):
        yield PropID(self, "id")
        while not self.eof:
            uid = ReadNextByte(self)
            if uid == kEnd:
                yield PropID(self, "end")
                break
            elif uid == kArchiveProperties:
                yield ArchiveProperties(self, "props", PROP_DESC[uid])
            elif uid == kAdditionalStreamsInfo:
                yield StreamsInfo(self, "additional_streams", PROP_DESC[uid])
            elif uid == kMainStreamsInfo:
                yield StreamsInfo(self, "main_streams", PROP_DESC[uid])
            elif uid == kFilesInfo:
                yield FilesInfo(self, "files_info", PROP_DESC[uid])
            else:
                raise ParserError("Unexpected ID %u" % uid)

class NextHeader(FieldSet):
    def __init__(self, parent, name, desc="Next header"):
        FieldSet.__init__(self, parent, name, desc)
        self._size = 8*self["/signature/start_hdr/next_hdr_size"].value
    def createFields(self):
        uid = ReadNextByte(self)
        if uid == kHeader:
            yield Header(self, "header", PROP_DESC[uid])
        elif uid == kEncodedHeader:
            yield EncodedHeader(self, "encoded_hdr", PROP_DESC[uid])
        else:
            raise ParserError("Unexpected ID %u" % uid)

class NextHeaderParser(Parser):
    PARSER_TAGS = {
    }
    endian = LITTLE_ENDIAN

    def createFields(self):
        uid = ReadNextByte(self)
        if uid == kHeader:
            yield Header(self, "header", PROP_DESC[uid])
        elif uid == kEncodedHeader:
            yield EncodedHeader(self, "encoded_hdr", PROP_DESC[uid])
        else:
            raise ParserError("Unexpected ID %u" % uid)

    def validate(self):
        return True

class CompressedData(Bytes):
    def __init__(self, parent, name, length, decompressor, description=None,
      parser=None, filename=None, mime_type=None, parser_class=None):
        if filename:
            if not isinstance(filename, unicode):
                filename = makePrintable(filename, "ISO-8859-1")
            if not description:
                description = 'File "%s" (%s)' % (filename, humanFilesize(length))
        Bytes.__init__(self, parent, name, length, description)
        self.setupInputStream(decompressor, parser, filename, mime_type, parser_class)

    def setupInputStream(self, decompressor, parser, filename, mime_type, parser_class):
        def createInputStream(cis, **args):
            tags = args.setdefault("tags",[])
            if parser_class:
                tags.append(( "class", parser_class ))
            if parser is not None:
                tags.append(( "id", parser.PARSER_TAGS["id"] ))
            if mime_type:
                tags.append(( "mime", mime_type ))
            if filename:
                tags.append(( "filename", filename ))
            print args
            return StringInputStream(decompressor(self.value), **args)
        self.setSubIStream(createInputStream)

def get_header_decompressor(self):
    unpack_info = self['/next_hdr/encoded_hdr/unpack_info']
    assert unpack_info['num_folders'].value == 1
    coder = unpack_info['folder[0]/coders[0]/coder[0]']
    method = METHODS[coder['id'].value]
    if method == 'Copy':
        return lambda data: data
    elif method == '7z-LZMA':
        props = coder['properties'].value
        length = unpack_info['unpack_size[0][0]'].value
        return lambda data: lzmadecompress(props+data, maxlength=length)

def get_header_field(self, name, size, description=None):
    decompressor = get_header_decompressor(self)
    if decompressor is None:
        return RawBytes(self, name, size, description=description)
    return CompressedData(self, name, size, decompressor, description=description, parser_class=NextHeaderParser)
    
class Body(FieldSet):
    def __init__(self, parent, name, desc="Body data"):
        FieldSet.__init__(self, parent, name, desc)
        self._size = 8*self["/signature/start_hdr/next_hdr_offset"].value
    def createFields(self):
        if "encoded_hdr" in self["/next_hdr"]:
            pack_size = sum([s.value for s in self.array("/next_hdr/encoded_hdr/pack_info/pack_size")])
            body_size = self["/next_hdr/encoded_hdr/pack_info/pack_pos"].value
            if body_size:
                yield RawBytes(self, "compressed_data", body_size, "Compressed data")
            # Here we could check if copy method was used to "compress" it,
            # but this never happens, so just output "compressed file info"
            yield get_header_field(self, "compressed_file_info", pack_size,
                           "Compressed file information")
            size = (self._size//8) - pack_size - body_size
            if size > 0:
                yield RawBytes(self, "unknown_data", size)
        elif "header" in self["/next_hdr"]:
            yield RawBytes(self, "compressed_data", self._size//8, "Compressed data")

class StartHeader(FieldSet):
    static_size = 160
    def createFields(self):
        yield textHandler(UInt64(self, "next_hdr_offset",
            "Next header offset"), hexadecimal)
        yield UInt64(self, "next_hdr_size", "Next header size")
        yield textHandler(UInt32(self, "next_hdr_crc",
            "Next header CRC"), hexadecimal)

class SignatureHeader(FieldSet):
    static_size = 96 + StartHeader.static_size
    def createFields(self):
        yield Bytes(self, "signature", 6, "Signature Header")
        yield UInt8(self, "major_ver", "Archive major version")
        yield UInt8(self, "minor_ver", "Archive minor version")
        yield textHandler(UInt32(self, "start_hdr_crc",
            "Start header CRC"), hexadecimal)
        yield StartHeader(self, "start_hdr", "Start header")

class SevenZipParser(Parser):
    MAGIC = "7z\xbc\xaf\x27\x1c"
    PARSER_TAGS = {
        "id": "7zip",
        "category": "archive",
        "file_ext": ("7z",),
        "mime": (u"application/x-7z-compressed",),
        "min_size": 32*8,
        "magic": ((MAGIC, 0),),
        "description": "Compressed archive in 7z format"
    }
    endian = LITTLE_ENDIAN

    def createFields(self):
        yield SignatureHeader(self, "signature", "Signature Header")
        yield Body(self, "body_data")
        yield NextHeader(self, "next_hdr")

    def validate(self):
        if self.stream.readBytes(0,len(self.MAGIC)) != self.MAGIC:
            return "Invalid signature"
        return True

    def createContentSize(self):
        size = self["/signature/start_hdr/next_hdr_offset"].value*8
        size += self["/signature/start_hdr/next_hdr_size"].value*8
        size += SignatureHeader.static_size
        return size
