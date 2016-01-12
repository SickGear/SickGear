"""
Parser for AVCHD/Blu-ray formats

Notice: This parser is based off reverse-engineering efforts.
It is NOT based on official specifications, and is subject to change as
more information becomes available. There's a lot of guesswork here, so if you find
that something disagrees with an official specification, please change it.

Notice: This parser has NOT been tested on Blu-ray disc data, only on files
taken from AVCHD camcorders.

Author: Robert Xiao
Creation: December 30, 2010

References:
- Wikipedia: http://en.wikipedia.org/wiki/AVCHD
- European patent EP1821310: http://www.freepatentsonline.com/EP1821310.html
"""

"""
File structure:
Root (/PRIVATE/AVCHD, /AVCHD, /, etc.)
    AVCHDTN/: (AVCHD only)
        THUMB.TDT: Thumbnail Data: stored as a series of 16KiB pages, where each thumbnail starts on a page boundary
        THUMB.TID: Thumbnail Index (TIDX), unknown format
    BDMV/:
        INDEX.BDM|index.bdmv: Bluray Disc Metadata (INDX): Clip index file
        MOVIEOBJ.BDM|MovieObject.bdmv: Bluray Disc Metadata (MOBJ): Clip description file
        AUXDATA/: (Optional, Blu-ray only)
            sound.bdmv: Sound(s) associated with HDMV Interactive Graphic streams applications
            ?????.otf: Font(s) associated with Text subtitle applications
        BACKUP/: (Optional)
            [Copies of *.bdmv, CLIPINF/* and PLAYLIST/*]
        CLIPINF/:
            ?????.CPI/?????.clpi: Clip information (HDMV)
        PLAYLIST/:
            ?????.MPL/?????.mpls: Movie Playlist information (MPLS)
        STREAM/:
            ?????.MTS|?????.m2ts: BDAV MPEG-2 Transport Stream (video file)
            SSIF/: (Blu-ray 3D only)
                ?????.ssif: Stereoscopic Interleaved file
    IISVPL/: (Optional?, AVCHD only?)
        ?????.VPL: Virtual Playlist? (MPLS)
"""

from hachoir_parser import HachoirParser
from hachoir_core.field import (RootSeekableFieldSet, FieldSet,
    RawBytes, Bytes, String, Bits, UInt8, UInt16, UInt32, PascalString8, Enum)
from hachoir_core.endian import BIG_ENDIAN
from hachoir_core.iso639 import ISO639_2
from hachoir_core.text_handler import textHandler, hexadecimal
from datetime import datetime

def fromhex(field):
    return int('%x'%field.value)

class AVCHDTimestamp(FieldSet):
    static_size = 8*8
    def createFields(self):
        yield textHandler(UInt8(self, "unknown", description="0x1E"), hexadecimal)
        yield textHandler(UInt8(self, "century"), hexadecimal)
        yield textHandler(UInt8(self, "year"), hexadecimal)
        yield textHandler(UInt8(self, "month"), hexadecimal)
        yield textHandler(UInt8(self, "day"), hexadecimal)
        yield textHandler(UInt8(self, "hour"), hexadecimal)
        yield textHandler(UInt8(self, "minute"), hexadecimal)
        yield textHandler(UInt8(self, "second"), hexadecimal)

    def createValue(self):
        return datetime(fromhex(self['century'])*100 + fromhex(self['year']),
            fromhex(self['month']), fromhex(self['day']),
            fromhex(self['hour']), fromhex(self['minute']), fromhex(self['second']))

class AVCHDGenericChunk(FieldSet):
    def createFields(self):
        yield UInt32(self, "size")
        self._size = (self['size'].value+4)*8
        yield RawBytes(self, "raw[]", self['size'].value)

class AVCHDINDX_0(FieldSet):
    def createFields(self):
        yield UInt32(self, "size")
        self._size = (self['size'].value+4)*8
        yield RawBytes(self, "unknown[]", 22)
        yield UInt32(self, "count")
        for i in xrange(self['count'].value):
            yield RawBytes(self, "data[]", 12)

class AVCHDIDEX_0(FieldSet):
    def createFields(self):
        yield UInt32(self, "size")
        self._size = (self['size'].value+4)*8
        yield RawBytes(self, "unknown[]", 40)
        yield AVCHDTimestamp(self, "last_modified")
        yield RawBytes(self, "unknown[]", self._size//8-52)

class AVCHDMOBJ_Chunk(FieldSet):
    def createFields(self):
        yield UInt32(self, "unknown[]")
        yield UInt32(self, "index")
        yield UInt32(self, "unknown[]")
        yield textHandler(UInt32(self, "unknown_id"), hexadecimal)
        yield UInt32(self, "unknown[]")
        yield textHandler(UInt32(self, "playlist_id"), lambda field: '%05d'%field.value)
        yield UInt32(self, "unknown[]")

class AVCHDMPLS_StreamEntry(FieldSet):
    ENTRYTYPE = {1:'PlayItem on disc',
                 2:'SubPath on disc',
                 3:'PlayItem in local storage',
                 4:'SubPath in local storage'}
    def createFields(self):
        yield UInt8(self, "size")
        self._size = (self['size'].value+1)*8
        yield Enum(UInt8(self, "type"), self.ENTRYTYPE)
        if self['type'].value in (1,3):
            yield textHandler(UInt16(self, "pid", "PID of item in clip stream m2ts file"), hexadecimal)
        else: # 2,4
            '''
            The patent says:
                ref_to_SubPath_id
                ref_to_SubClip_entry_id
                ref_to_Stream_PID_of_subClip
            Sizes aren't given, though, so I cannot determine the format without a sample.
            '''
            pass

class AVCHDMPLS_StreamAttribs(FieldSet):
    STREAMTYPE = {
        0x01: "V_MPEG1",
        0x02: "V_MPEG2",
        0x1B: "V_AVC",
        0xEA: "V_VC1",
        0x03: "A_MPEG1",
        0x04: "A_MPEG2",
        0x80: "A_LPCM",
        0x81: "A_AC3",
        0x84: "A_AC3_PLUS",
        0xA1: "A_AC3_PLUS_SEC",
        0x83: "A_TRUEHD",
        0x82: "A_DTS",
        0x85: "A_DTS-HD",
        0xA2: "A_DTS-HD_SEC",
        0x86: "A_DTS-MA",
        0x90: "S_PGS",
        0x91: "S_IGS",
        0x92: "T_SUBTITLE",
    }
    # Enumerations taken from "ClownBD's CLIPINF Editor". Values may not be accurate.
    def createFields(self):
        yield UInt8(self, "size")
        self._size = (self['size'].value+1)*8
        yield Enum(UInt8(self, "type"), self.STREAMTYPE)
        if self['type'].display.startswith('V'): # Video
            yield Enum(Bits(self, "resolution", 4), {1:'480i', 2:'576i', 3:'480p', 4:'1080i', 5:'720p', 6:'1080p', 7:'576p'})
            yield Enum(Bits(self, "fps", 4), {1:'24/1.001', 2:'24', 3:'25', 4:'30/1.001', 6:'50', 7:'60/1.001'})
            yield Enum(UInt8(self, "aspect_ratio"), {0x20:'4:3', 0x30:'16:9'})
        elif self['type'].display.startswith('A'): # Audio
            yield Enum(Bits(self, "channel_layout", 4), {1:'Mono', 3:'Stereo', 6:'Multi', 12:'Combi'})
            yield Enum(Bits(self, "sample_rate", 4), {1:'48KHz', 4:'96KHz', 5:'192KHz', 12:'48-192KHz', 14:'48-96KHz'})
            yield Enum(String(self, "language", 3), ISO639_2)
        elif self['type'].display.startswith('T'): # Text subtitle
            yield UInt8(self, "unknown[]")
            yield Enum(String(self, "language", 3), ISO639_2)
        elif self['type'].display.startswith('S'): # Graphics
            yield Enum(String(self, "language", 3), ISO639_2)
        else:
            pass

class AVCHDMPLS_Stream(FieldSet):
    def createFields(self):
        yield AVCHDMPLS_StreamEntry(self, "entry")
        yield AVCHDMPLS_StreamAttribs(self, "attribs")

class AVCHDMPLS_PlayItem(FieldSet):
    def createFields(self):
        yield UInt32(self, "size")
        self._size = (self['size'].value+4)*8
        yield UInt16(self, "unknown[]")
        yield UInt8(self, "video_count", "Number of video stream entries")
        yield UInt8(self, "audio_count", "Number of video stream entries")
        yield UInt8(self, "subtitle_count", "Number of presentation graphics/text subtitle entries")
        yield UInt8(self, "ig_count", "Number of interactive graphics entries")
        yield RawBytes(self, "unknown[]", 8)
        for i in xrange(self['video_count'].value):
            yield AVCHDMPLS_Stream(self, "video[]")
        for i in xrange(self['audio_count'].value):
            yield AVCHDMPLS_Stream(self, "audio[]")
        for i in xrange(self['subtitle_count'].value):
            yield AVCHDMPLS_Stream(self, "subtitle[]")
        for i in xrange(self['ig_count'].value):
            yield AVCHDMPLS_Stream(self, "ig[]")

class AVCHDMPLS_0_Chunk(FieldSet):
    def createFields(self):
        yield UInt16(self, "size")
        self._size = (self['size'].value+2)*8
        yield Bytes(self, "clip_id", 5)
        yield Bytes(self, "clip_type", 4)
        yield RawBytes(self, "unknown[]", 3)
        yield UInt32(self, "clip_start_time[]", "clip start time (units unknown)")
        yield UInt32(self, "clip_end_time[]", "clip end time (units unknown)")
        yield RawBytes(self, "unknown[]", 10)
        yield AVCHDMPLS_PlayItem(self, "playitem")

class AVCHDMPLS_0(FieldSet):
    def createFields(self):
        yield UInt32(self, "size")
        self._size = (self['size'].value+4)*8
        yield UInt32(self, "count")
        yield UInt16(self, "unknown[]")
        for i in xrange(self['count'].value):
            yield AVCHDMPLS_0_Chunk(self, "chunk[]")

class AVCHDMPLS_PlayItemMark(FieldSet):
    def createFields(self):
        yield UInt16(self, "unknown[]")
        yield UInt16(self, "playitem_idx", "Index of the associated PlayItem")
        yield UInt32(self, "mark_time", "Marker time in clip (units unknown)")
        yield RawBytes(self, "unknown", 6)

class AVCHDMPLS_1(FieldSet):
    def createFields(self):
        yield UInt32(self, "size")
        self._size = (self['size'].value+4)*8
        yield UInt16(self, "count")
        for i in xrange(self['count'].value):
            yield AVCHDMPLS_PlayItemMark(self, "chunk[]")

class AVCHDPLEX_1_Chunk(FieldSet):
    static_size = 66*8
    def createFields(self):
        yield RawBytes(self, "unknown[]", 10)
        yield AVCHDTimestamp(self, "date")
        yield RawBytes(self, "unknown[]", 1)
        yield PascalString8(self, "date")
    def createValue(self):
        return self['date'].value

class AVCHDPLEX_0(FieldSet):
    def createFields(self):
        yield UInt32(self, "size")
        self._size = (self['size'].value+4)*8
        yield RawBytes(self, "unknown[]", 10)
        yield AVCHDTimestamp(self, "last_modified")
        yield RawBytes(self, "unknown[]", 2)
        yield PascalString8(self, "date")

class AVCHDPLEX_1(FieldSet):
    def createFields(self):
        yield UInt32(self, "size")
        self._size = (self['size'].value+4)*8
        yield UInt16(self, "count")
        for i in xrange(self['count'].value):
            yield AVCHDPLEX_1_Chunk(self, "chunk[]")

class AVCHDCLPI_1(FieldSet):
    def createFields(self):
        yield UInt32(self, "size")
        self._size = (self['size'].value+4)*8
        yield RawBytes(self, "unknown[]", 10)
        yield textHandler(UInt16(self, "video_pid", "PID of video data in stream file"), hexadecimal)
        yield AVCHDMPLS_StreamAttribs(self, "video_attribs")
        yield textHandler(UInt16(self, "audio_pid", "PID of audio data in stream file"), hexadecimal)
        yield AVCHDMPLS_StreamAttribs(self, "audio_attribs")

def AVCHDIDEX(self):
    yield AVCHDIDEX_0(self, "chunk[]")
    yield AVCHDGenericChunk(self, "chunk[]")

def AVCHDPLEX(self):
    yield AVCHDPLEX_0(self, "chunk[]")
    yield AVCHDPLEX_1(self, "chunk[]")
    yield AVCHDGenericChunk(self, "chunk[]")

def AVCHDCLEX(self):
    yield AVCHDGenericChunk(self, "chunk[]")
    yield AVCHDGenericChunk(self, "chunk[]")

class AVCHDChunkWithHeader(FieldSet):
    TYPES = {'IDEX': AVCHDIDEX,
             'PLEX': AVCHDPLEX,
             'CLEX': AVCHDCLEX,}
    def createFields(self):
        yield UInt32(self, "size")
        self._size = (self['size'].value+4)*8
        yield UInt32(self, "unknown[]", "24")
        yield UInt32(self, "unknown[]", "1")
        yield UInt32(self, "unknown[]", "0x10000100")
        yield UInt32(self, "unknown[]", "24")
        yield UInt32(self, "size2")
        assert self['size'].value == self['size2'].value+20
        yield Bytes(self, "magic", 4)
        yield RawBytes(self, "unknown[]", 36)
        for field in self.TYPES[self['magic'].value](self):
            yield field

class AVCHDINDX(HachoirParser, RootSeekableFieldSet):
    endian = BIG_ENDIAN
    MAGIC = "INDX0"
    PARSER_TAGS = {
        "id": "bdmv_index",
        "category": "video",
        "file_ext": ("bdm","bdmv"),
        "magic": ((MAGIC, 0),),
        "min_size": 8, # INDX0?00
        "description": "INDEX.BDM",
    }

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(self, None, "root", stream, None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        if self.stream.readBytes(0, len(self.MAGIC)) != self.MAGIC:
            return "Invalid magic"
        return True

    def createFields(self):
        yield Bytes(self, "filetype", 4, "File type (INDX)")
        yield Bytes(self, "fileversion", 4, "File version (0?00)")
        yield UInt32(self, "offset[0]")
        yield UInt32(self, "offset[1]")
        self.seekByte(self['offset[0]'].value)
        yield AVCHDINDX_0(self, "chunk[]")
        self.seekByte(self['offset[1]'].value)
        yield AVCHDChunkWithHeader(self, "chunk[]")

class AVCHDMOBJ(HachoirParser, RootSeekableFieldSet):
    endian = BIG_ENDIAN
    MAGIC = "MOBJ0"
    PARSER_TAGS = {
        "id": "bdmv_mobj",
        "category": "video",
        "file_ext": ("bdm","bdmv"),
        "magic": ((MAGIC, 0),),
        "min_size": 8, # MOBJ0?00
        "description": "MOVIEOBJ.BDM",
    }

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(self, None, "root", stream, None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        if self.stream.readBytes(0, len(self.MAGIC)) != self.MAGIC:
            return "Invalid magic"
        return True

    def createFields(self):
        yield Bytes(self, "filetype", 4, "File type (MOBJ)")
        yield Bytes(self, "fileversion", 4, "File version (0?00)")
        yield RawBytes(self, "unknown[]", 32)
        yield UInt32(self, "size")
        yield UInt32(self, "unknown[]")
        yield UInt16(self, "count")
        yield textHandler(UInt32(self, "unknown_id"), hexadecimal)
        for i in xrange(1, self['count'].value):
            yield AVCHDMOBJ_Chunk(self, "movie_object[]")

class AVCHDMPLS(HachoirParser, RootSeekableFieldSet):
    endian = BIG_ENDIAN
    MAGIC = "MPLS0"
    PARSER_TAGS = {
        "id": "bdmv_mpls",
        "category": "video",
        "file_ext": ("mpl","mpls","vpl"),
        "magic": ((MAGIC, 0),),
        "min_size": 8, # MPLS0?00
        "description": "MPLS",
    }

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(self, None, "root", stream, None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        if self.stream.readBytes(0, len(self.MAGIC)) != self.MAGIC:
            return "Invalid magic"
        return True

    def createFields(self):
        yield Bytes(self, "filetype", 4, "File type (MPLS)")
        yield Bytes(self, "fileversion", 4, "File version (0?00)")
        yield UInt32(self, "offset[0]")
        yield UInt32(self, "offset[1]")
        yield UInt32(self, "offset[2]")
        self.seekByte(self['offset[0]'].value)
        yield AVCHDMPLS_0(self, "chunk[]")
        self.seekByte(self['offset[1]'].value)
        yield AVCHDMPLS_1(self, "chunk[]")
        self.seekByte(self['offset[2]'].value)
        yield AVCHDChunkWithHeader(self, "chunk[]")

class AVCHDCLPI(HachoirParser, RootSeekableFieldSet):
    endian = BIG_ENDIAN
    MAGIC = "HDMV0"
    PARSER_TAGS = {
        "id": "bdmv_clpi",
        "category": "video",
        "file_ext": ("cpi","clpi"),
        "magic": ((MAGIC, 0),),
        "min_size": 8, # HDMV0?00
        "description": "HDMV",
    }

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(self, None, "root", stream, None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        if self.stream.readBytes(0, len(self.MAGIC)) != self.MAGIC:
            return "Invalid magic"
        return True

    def createFields(self):
        yield Bytes(self, "filetype", 4, "File type (HDMV)")
        yield Bytes(self, "fileversion", 4, "File version (0?00)")
        yield UInt32(self, "offset[]")
        yield UInt32(self, "offset[]")
        yield UInt32(self, "offset[]")
        yield UInt32(self, "offset[]")
        yield UInt32(self, "offset[]")
        self.seekByte(self['offset[0]'].value)
        yield AVCHDGenericChunk(self, "chunk[]")
        self.seekByte(self['offset[1]'].value)
        yield AVCHDCLPI_1(self, "chunk[]")
        self.seekByte(self['offset[2]'].value)
        yield AVCHDGenericChunk(self, "chunk[]")
        self.seekByte(self['offset[3]'].value)
        yield AVCHDGenericChunk(self, "chunk[]")
        self.seekByte(self['offset[4]'].value)
        yield AVCHDChunkWithHeader(self, "chunk[]")
