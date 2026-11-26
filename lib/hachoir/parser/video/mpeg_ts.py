"""
MPEG-2 Transport Stream parser.

Documentation:
- MPEG-2 Transmission
  http://erg.abdn.ac.uk/research/future-net/digital-video/mpeg2-trans.html

Author: Victor Stinner
Creation date: 13 january 2007
"""

from hachoir.parser import Parser
from hachoir.field import (FieldSet, ParserError, MissingField,
                           UInt8, UInt16, UInt24, Enum, Bit, Bits, RawBytes, RawBits)
from hachoir.core.endian import BIG_ENDIAN
from hachoir.core.text_handler import textHandler, hexadecimal


TS_Elementary_stream_types = {
    0x00: 'Reserved',
    0x01: 'ISO/IEC 11172-2 (MPEG-1 video)',
    0x02: 'ITU-T Rec. H.262 and ISO/IEC 13818-2 (MPEG-2 higher rate interlaced video)',
    0x03: 'ISO/IEC 11172-3 (MPEG-1 audio)',
    0x04: 'ISO/IEC 13818-3 (MPEG-2 halved sample rate audio)',
    0x05: 'ITU-T Rec. H.222 and ISO/IEC 13818-1 (MPEG-2 tabled data)',
    0x06: 'ITU-T Rec. H.222 and ISO/IEC 13818-1 (MPEG-2 packetized data)',
    0x07: 'ISO/IEC 13522 (MHEG)',
    0x08: 'ITU-T Rec. H.222 and ISO/IEC 13818-1 DSM CC',
    0x09: 'ITU-T Rec. H.222 and ISO/IEC 13818-1/11172-1 auxiliary data',
    0x0A: 'ISO/IEC 13818-6 DSM CC multiprotocol encapsulation',
    0x0B: 'ISO/IEC 13818-6 DSM CC U-N messages',
    0x0C: 'ISO/IEC 13818-6 DSM CC stream descriptors',
    0x0D: 'ISO/IEC 13818-6 DSM CC tabled data',
    0x0E: 'ISO/IEC 13818-1 auxiliary data',
    0x0F: 'ISO/IEC 13818-7 ADTS AAC (MPEG-2 lower bit-rate audio)',
    0x10: 'ISO/IEC 14496-2 (MPEG-4 H.263 based video)',
    0x11: 'ISO/IEC 14496-3 (MPEG-4 LOAS multi-format framed audio)',
    0x12: 'ISO/IEC 14496-1 (MPEG-4 FlexMux)',
    0x13: 'ISO/IEC 14496-1 (MPEG-4 FlexMux)',
    0x14: 'ISO/IEC 13818-6 DSM CC synchronized download protocol',
    0x15: 'Packetized metadata',
    0x16: 'Sectioned metadata',
    0x17: 'ISO/IEC 13818-6 DSM CC Data Carousel metadata',
    0x18: 'ISO/IEC 13818-6 DSM CC Object Carousel metadata',
    0x19: 'ISO/IEC 13818-6 Synchronized Download Protocol metadata',
    0x1A: 'ISO/IEC 13818-11 IPMP',
    0x1B: 'ITU-T Rec. H.264 and ISO/IEC 14496-10 (lower bit-rate video)',
    0x1C: 'ISO/IEC 14496-3 (MPEG-4 raw audio)',
    0x1D: 'ISO/IEC 14496-17 (MPEG-4 text)',
    0x1E: 'ISO/IEC 23002-3 (MPEG-4 auxiliary video)',
    0x1F: 'ISO/IEC 14496-10 SVC (MPEG-4 AVC sub-bitstream)',
    0x20: 'ISO/IEC 14496-10 MVC (MPEG-4 AVC sub-bitstream)',
    0x21: 'ITU-T Rec. T.800 and ISO/IEC 15444 (JPEG 2000 video)',
    0x24: 'ITU-T Rec. H.265 and ISO/IEC 23008-2 (Ultra HD video)',
    0x33: 'ITU-T Rec. H.266 and ISO/IEC 23090-3 (VVC video)',
    0x42: 'Chinese Video Standard',
    0x7f: 'ISO/IEC 13818-11 IPMP (DRM)',
    0x80: 'ITU-T Rec. H.262 and ISO/IEC 13818-2 with DES-64-CBC encryption for DigiCipher II or PCM audio for Blu-ray',
    0x81: 'Dolby Digital (AC-3) up to six channel audio for ATSC and Blu-ray',
    0x82: 'SCTE subtitle or DTS 6 channel audio for Blu-ray',
    0x83: 'Dolby TrueHD lossless audio for Blu-ray',
    0x84: 'Dolby Digital Plus (enhanced AC-3) up to 16 channel audio for Blu-ray',
    0x85: 'DTS 8 channel audio for Blu-ray',
    0x86: 'SCTE-35[5] digital program insertion cue message or DTS 8 channel lossless audio for Blu-ray',
    0x87: 'Dolby Digital Plus (enhanced AC-3) up to 16 channel audio for ATSC',
    0x90: 'Blu-ray Presentation Graphic Stream (subtitling)',
    0x91: 'ATSC DSM CC Network Resources table',
    0xC0: 'DigiCipher II text',
    0xC1: 'Dolby Digital (AC-3) up to six channel audio with AES-128-CBC data encryption',
    0xC2: 'ATSC DSM CC synchronous data or Dolby Digital Plus up to 16 channel audio with AES-128-CBC data encryption',
    0xCF: 'ISO/IEC 13818-7 ADTS AAC with AES-128-CBC frame encryption',
    0xD0: 'Privately defined.',
    0xD1: 'BBC Dirac (Ultra HD video)',
    0xD2: 'Audio Video Standard AVS2 (Ultra HD video)',
    0xD3: 'Audio Video Standard AVS3 Audio',
    0xD4: 'Audio Video Standard AVS3 Video (Ultra HD video)',
    0xDB: 'ITU-T Rec. H.264 and ISO/IEC 14496-10 with AES-128-CBC slice encryption',
    0xEA: 'Microsoft Windows Media Video 9 (lower bit-rate video)',
}

TS_Audio_stream_types = {
    0x03,  # 'ISO/IEC 11172-3 (MPEG-1 audio)',
    0x04,  # 'ISO/IEC 13818-3 (MPEG-2 halved sample rate audio)',
    0x0F,  # 'ISO/IEC 13818-7 ADTS AAC (MPEG-2 lower bit-rate audio)',
    0x11,  # 'ISO/IEC 14496-3 (MPEG-4 LOAS multi-format framed audio)',
    0x1C,  # 'ISO/IEC 14496-3 (MPEG-4 raw audio)',
    0x81,  # 'Dolby Digital (AC-3) up to six channel audio for ATSC and Blu-ray',
    0x82,  # 'SCTE subtitle or DTS 6 channel audio for Blu-ray',
    0x83,  # 'Dolby TrueHD lossless audio for Blu-ray',
    0x84,  # 'Dolby Digital Plus (enhanced AC-3) up to 16 channel audio for Blu-ray',
    0x85,  # 'DTS 8 channel audio for Blu-ray',
    0x86,  # 'SCTE-35[5] digital program insertion cue message or DTS 8 channel lossless audio for Blu-ray',
    0x87,  # 'Dolby Digital Plus (enhanced AC-3) up to 16 channel audio for ATSC',
    0xC1,  # 'Dolby Digital (AC-3) up to six channel audio with AES-128-CBC data encryption',
    0xC2,  # 'ATSC DSM CC synchronous data or Dolby Digital Plus up to 16 channel audio with AES-128-CBC data encryption',
    0xCF,  # 'ISO/IEC 13818-7 ADTS AAC with AES-128-CBC frame encryption',
    0xD3,  # 'Audio Video Standard AVS3 Audio',
}

TS_Video_stream_types = {
    0x01,  # 'ISO/IEC 11172-2 (MPEG-1 video)',
    0x02,  # 'ITU-T Rec. H.262 and ISO/IEC 13818-2 (MPEG-2 higher rate interlaced video)',
    0x10,  # 'ISO/IEC 14496-2 (MPEG-4 H.263 based video)',
    0x1B,  # 'ITU-T Rec. H.264 and ISO/IEC 14496-10 (lower bit-rate video)',
    0x1E,  # 'ISO/IEC 23002-3 (MPEG-4 auxiliary video)',
    0x1F,  # 'ISO/IEC 14496-10 SVC (MPEG-4 AVC sub-bitstream)',
    0x20,  # 'ISO/IEC 14496-10 MVC (MPEG-4 AVC sub-bitstream)',
    0x21,  # 'ITU-T Rec. T.800 and ISO/IEC 15444 (JPEG 2000 video)',
    0x24,  # 'ITU-T Rec. H.265 and ISO/IEC 23008-2 (Ultra HD video)',
    0x33,  # 'ITU-T Rec. H.266 and ISO/IEC 23090-3 (VVC video)',
    0x42,  # 'Chinese Video Standard',
    0x80,  # 'ITU-T Rec. H.262 and ISO/IEC 13818-2 with DES-64-CBC encryption for DigiCipher II or PCM audio for Blu-ray',
    0xD1,  # 'BBC Dirac (Ultra HD video)',
    0xD2,  # 'Audio Video Standard AVS2 (Ultra HD video)',
    0xD4,  # 'Audio Video Standard AVS3 Video (Ultra HD video)',
    0xDB,  # 'ITU-T Rec. H.264 and ISO/IEC 14496-10 with AES-128-CBC slice encryption',
    0xEA,  # 'Microsoft Windows Media Video 9 (lower bit-rate video)',
}


class AdaptationField(FieldSet):

    def createFields(self):
        yield UInt8(self, "length")

        yield Bit(self, "discontinuity_indicator")
        yield Bit(self, "random_access_indicator")
        yield Bit(self, "es_prio_indicator")
        yield Bit(self, "has_pcr")
        yield Bit(self, "has_opcr")
        yield Bit(self, "has_splice_point")
        yield Bit(self, "private_data")
        yield Bit(self, "has_extension")

        if self['has_pcr'].value:
            yield Bits(self, "pcr_base", 33)
            yield Bits(self, "pcr_ext", 9)

        if self['has_opcr'].value:
            yield Bits(self, "opcr_base", 33)
            yield Bits(self, "opcr_ext", 9)

        if self['has_splice_point'].value:
            yield Bits(self, "splice_countdown", 8)

        stuff_len = ((self['length'].value + 1) * 8) - self.current_size
        if self['length'].value and stuff_len:
            yield RawBits(self, 'stuffing', stuff_len)


# unused and incomplete
class PESPayloadField(FieldSet):

    def __init__(self, *args, **kw):
        self._m2ts = kw.pop('m2ts', False)
        self._size = kw.pop('size', 0)
        FieldSet.__init__(self, *args, **kw)

    def createFields(self):
        yield UInt24(self, 'start code prefix', 3)
        yield UInt8(self, 'Stream id')
        yield UInt16(self, 'Packet length')
        size = 188 - 8*6
        if self['Stream id'].value not in (0xBE, 0xBF):
            size -= 8*2
            yield Bits(self, 'unknown', 2)
            yield Bits(self, 'scrambling control', 2)
            yield Bit(self, 'priority')
            yield Bit(self, 'alignment indicator')
            yield Bit(self, 'copyright')
            yield Bit(self, 'original')
            yield Bits(self, 'DTS flags', 2)
            yield Bit(self, 'ESCR flag')
            yield Bit(self, 'ES rate flag')
            yield Bit(self, 'DSM trick mode flag')
            yield Bit(self, 'additional copy info flag')
            yield Bit(self, 'CRC flag')
            yield Bit(self, 'extension flag')
            if self['extension flag'].value:
                size -= 8
                yield Bit(self, 'PES private data flag')
                yield Bit(self, 'pack header field flag')
                yield Bit(self, 'program packet sequence counter flag')
                yield Bit(self, 'P-STD buffer flag')
                yield Bits(self, 'unknown 111', 3)
                yield Bit(self, 'PES extension flag 2')
                # more data parsing needed
        if self._m2ts:
            size += 4
        size -= (self.current_size // 8)
        yield RawBytes(self, "data", size)


class PMTElementaryStream(FieldSet):

    def createFields(self):
        yield UInt8(self, 'stream type')
        yield Bits(self, 'Reserved bits', 3)
        yield Bits(self, 'Elementary PID', 13)
        yield Bits(self, 'Reserved bits', 4)
        yield Bits(self, 'ES Info length unused bits', 2)
        yield Bits(self, 'ES Info length', 10)
        if e_l := self['ES Info length'].value:
            yield RawBytes(self, 'Elementary stream descriptors', e_l)


class PATProgram(FieldSet):

    def createFields(self):
        yield UInt16(self, 'Program num')
        yield Bits(self, 'Reserved bits', 3)
        yield Bits(self, 'Program map PID', 13)


class PAT(FieldSet):

    def createFields(self):
        # the section length counts 5 bytes of section header before the programs, and 4 bytes of CRC after them
        # a packet holds 44 programs at most, and only PID 0 has this table, other payloads are read as one by mistake
        programs = 0 == self.parent.parent['pid'].value and (self.parent['Section length'].value - 9) // 4 or 1
        for program_counter in range(1, 1 + max(1, min(44, programs))):
            yield PATProgram(self, f'Program #{program_counter}')


class PMT(FieldSet):

    def createFields(self):
        yield Bits(self, 'Reserved bits', 3)
        yield Bits(self, 'PCR PID', 13)
        yield Bits(self, 'Reserved bits', 4)
        yield Bits(self, 'Program info length unused bits', 2)
        yield Bits(self, 'Program info length', 10)
        if p_l := self['Program info length'].value:
            yield RawBytes(self, 'Program descriptors', p_l)
        # Elementary stream specific data repeated until end of section length
        # the section length also counts 5 bytes of section header, the 4 bytes above, and 4 bytes of CRC at the end
        section_len = self.parent['Section length'].value - 13 - self['Program info length'].value
        stream_counter = 1
        while section_len > 0:
            yield PMTElementaryStream(self, f'Elementary Stream #{stream_counter}')
            section_len -= 5 + self[f'Elementary Stream #{stream_counter}']['ES Info length'].value
            stream_counter += 1


class PayloadField(FieldSet):

    def createFields(self):
        # Fixme: specific packet types don't have this
        if self.parent['payload_unit_start'].value:
            yield UInt8(self, 'Pointer field')
            if 0 != self['Pointer field'].value:
                yield RawBytes(self, 'Skipped byte', self['Pointer field'].value)
        yield UInt8(self, 'Table ID')
        yield Bit(self, 'Section syntax indicator')
        yield Bit(self, 'Private bit')
        yield Bits(self, 'Reserved bits', 2)
        yield Bits(self, 'Section length unused bits', 2)
        yield Bits(self, 'Section length', 10)
        if self['Section syntax indicator'].value:
            yield UInt16(self, 'Table ID extension')
            yield Bits(self, 'Reserved bits', 2)
            yield Bits(self, 'Version number', 5)
            yield Bit(self, 'Current/next indicator ')
            yield UInt8(self, 'Section number')
            yield UInt8(self, 'Last section number')
        # section data
        # PAT
        if 0x00 == self['Table ID'].value:
            yield PAT(self, 'PAT')
        # PMT
        elif 0x02 == self['Table ID'].value:
            yield PMT(self, name='PMT')

        # Fixme: parsing of all previous field required
        # yield UInt8(self, 'descriptor tag')
        # yield UInt8(self, 'descriptor length')
        # yield RawBytes(self, 'Descriptor data', self['descriptor length'].value)


class Packet(FieldSet):

    def __init__(self, *args, **kw):
        self._m2ts = kw.pop('m2ts', False)
        FieldSet.__init__(self, *args, **kw)
        if self._m2ts:
            size = 4
        else:
            size = 0
        size += 188
        if self["has_error"].value:
            size += 16
        self._size = size * 8

    PID = {
        0x0000: "Program Association Table (PAT)",
        0x0001: "Conditional Access Table (CAT)",
        # 0x0002..0x000f: reserved
        # 0x0010..0x1FFE: network PID, program map PID, elementary PID, etc.
        # TODO: Check above values
        # 0x0044: "video",
        # 0x0045: "audio",
        0x1FFF: "Null packet",
    }

    def createFields(self):
        if self._m2ts:
            yield Bits(self, "c", 2)
            yield Bits(self, "ats", 32 - 2)
        yield textHandler(UInt8(self, "sync", 8), hexadecimal)
        if self["sync"].value != 0x47:
            raise ParserError("MPEG-2 TS: Invalid synchronization byte")
        yield Bit(self, "has_error")
        yield Bit(self, "payload_unit_start")
        yield Bit(self, "priority")
        yield Enum(textHandler(Bits(self, "pid", 13, "Program identifier"), hexadecimal), self.PID)
        yield Bits(self, "scrambling_control", 2)
        yield Bit(self, "has_adaptation")
        yield Bit(self, "has_payload")
        yield Bits(self, "counter", 4)

        if self["has_adaptation"].value:
            # adaptation fields are unbound packets
            self._size = None
            yield AdaptationField(self, "adaptation_field")
        if self["has_payload"].value:
            # payloads are unbound packets
            self._size = None
            yield PayloadField(self, name='payload')
        if self["has_error"].value:
            yield RawBytes(self, "error_correction", 16)

    def createDescription(self):
        text = "Packet: PID %s" % self["pid"].display
        if self["payload_unit_start"].value:
            text += ", start of payload"
        if self["has_adaptation"].value:
            text += ", with adaptation field"
        return text

    def isValid(self):
        if not self["has_payload"].value and not self["has_adaptation"].value:
            return "No payload and no adaptation"
        pid = self["pid"].value
        if (0x0002 <= pid <= 0x000f) or (0x2000 <= pid):
            return "Invalid program identifier (%s)" % self["pid"].display
        return ""


# M2TS 4 bytes + 188 bytes payload + 4 errors
MAX_PACKET_SIZE = 208


class MPEG_TS(Parser):
    PARSER_TAGS = {
        "id": "mpeg_ts",
        "category": "video",
        "file_ext": ("ts", "m2ts", "mts"),
        "min_size": 188 * 8,
        "mime": ("video/MP2T",),
        "description": "MPEG-2 Transport Stream"
    }
    endian = BIG_ENDIAN

    def is_m2ts(self):
        # FIXME: detect using file content, not file name
        # maybe detect sync at offset+4 bytes?
        source = self.stream.source
        if not (source and source.startswith("file:")):
            return True
        filename = source[5:].lower()
        return filename.endswith((".m2ts", ".mts"))

    def validate(self):
        sync = self.stream.searchBytes(b"\x47", 0, MAX_PACKET_SIZE * 8)
        if sync is None:
            return "Unable to find synchronization byte"
        for index in range(5):
            try:
                packet = self["packet[%u]" % index]
            except (ParserError, MissingField):
                if index and self.eof:
                    return True
                else:
                    return "Unable to get packet #%u" % index
            err = packet.isValid()
            if err:
                return "Packet #%u is invalid: %s" % (index, err)
        return True

    def createFields(self):
        m2ts = self.is_m2ts()

        while not self.eof and MAX_PACKET_SIZE*8*5000 > self.current_size:
            current = self.current_size
            next_sync = current
            if m2ts:
                next_sync += 4 * 8
            sync = self.stream.searchBytes(b"\x47", current,
                                           current + MAX_PACKET_SIZE * 8)
            if sync is None:
                raise ParserError("Unable to find synchronization byte")
            elif sync > next_sync:
                yield RawBytes(self, "incomplete_packet[]",
                               (sync - current) // 8)
            yield Packet(self, "packet[]", m2ts=m2ts)
