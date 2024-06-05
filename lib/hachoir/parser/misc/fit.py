"""
Garmin fit file Format parser.

Author: Sebastien Ponce <sebastien.ponce@cern.ch>
"""

from hachoir.parser import Parser
from hachoir.field import FieldSet, Int8, UInt8, Int16, UInt16, Int32, UInt32, Int64, UInt64, RawBytes, Bit, Bits, Bytes, String, Float32, Float64
from hachoir.core.endian import BIG_ENDIAN, LITTLE_ENDIAN

field_types = {
    0: UInt8,      # enum
    1: Int8,       # signed int of 8 bits
    2: UInt8,      # unsigned int of 8 bits
    131: Int16,    # signed int of 16 bits
    132: UInt16,   # unsigned int of 16 bits
    133: Int32,    # signed int of 32 bits
    134: UInt32,   # unsigned int of 32 bits
    7: String,     # string
    136: Float32,  # float
    137: Float64,  # double
    10: UInt8,     # unsigned int of 8 bits with 0 as invalid value
    139: UInt16,   # unsigned int of 16 bits with 0 as invalid value
    140: UInt32,   # unsigned int of 32 bits with 0 as invalid value
    13: Bytes,     # bytes
    142: Int64,    # signed int of 64 bits
    143: UInt64,   # unsigned int of 64 bits
    144: UInt64    # unsigned int of 64 bits with 0 as invalid value
}


class Header(FieldSet):
    endian = LITTLE_ENDIAN

    def createFields(self):
        yield UInt8(self, "size", "Header size")
        yield UInt8(self, "protocol", "Protocol version")
        yield UInt16(self, "profile", "Profile version")
        yield UInt32(self, "datasize", "Data size")
        yield RawBytes(self, "datatype", 4)
        yield UInt16(self, "crc", "CRC of first 11 bytes or 0x0")

    def createDescription(self):
        return "Header of fit file. Data size is %d" % (self["datasize"].value)


class NormalRecordHeader(FieldSet):

    def createFields(self):
        yield Bit(self, "normal", "Normal header (0)")
        yield Bit(self, "type", "Message type (0 data, 1 definition")
        yield Bit(self, "typespecific", "0")
        yield Bit(self, "reserved", "0")
        yield Bits(self, "msgType", 4, description="Message type")

    def createDescription(self):
        return "Record header, this is a %s message" % ("definition" if self["type"].value else "data")


class FieldDefinition(FieldSet):

    def createFields(self):
        yield UInt8(self, "number", "Field definition number")
        yield UInt8(self, "size", "Size in bytes")
        yield UInt8(self, "type", "Base type")

    def createDescription(self):
        return "Field Definition. Number %d, Size %d" % (self["number"].value, self["size"].value)


class DefinitionMessage(FieldSet):

    def createFields(self):
        yield NormalRecordHeader(self, "RecordHeader")
        yield UInt8(self, "reserved", "Reserved (0)")
        yield UInt8(self, "architecture", "Architecture (0 little, 1 big endian")
        self.endian = BIG_ENDIAN if self["architecture"].value else LITTLE_ENDIAN
        yield UInt16(self, "msgNumber", "Message Number")
        yield UInt8(self, "nbFields", "Number of fields")
        for n in range(self["nbFields"].value):
            yield FieldDefinition(self, "fieldDefinition[]")

    def createDescription(self):
        return "Definition Message. Contains %d fields" % (self["nbFields"].value)


class DataMessage(FieldSet):

    def createFields(self):
        hdr = NormalRecordHeader(self, "RecordHeader")
        yield hdr
        msgType = self["RecordHeader"]["msgType"].value
        msgDef = self.parent.msgDefs[msgType]
        for n in range(msgDef["nbFields"].value):
            desc = msgDef["fieldDefinition[%d]" % n]
            typ = field_types[desc["type"].value]
            self.endian = BIG_ENDIAN if msgDef["architecture"].value else LITTLE_ENDIAN
            if typ == String or typ == Bytes:
                yield typ(self, "field%d" % n, desc["size"].value)
            else:
                if typ.static_size // 8 == desc["size"].value:
                    yield typ(self, "field%d" % n, desc["size"].value)
                else:
                    for p in range(desc["size"].value * 8 // typ.static_size):
                        yield typ(self, "field%d[]" % n)

    def createDescription(self):
        return "Data Message"


class TimeStamp(FieldSet):

    def createFields(self):
        yield Bit(self, "timestamp", "TimeStamp (1)")
        yield Bits(self, "msgType", 3, description="Message type")
        yield Bits(self, "time", 4, description="TimeOffset")

    def createDescription(self):
        return "TimeStamp"


class CRC(FieldSet):

    def createFields(self):
        yield UInt16(self, "crc", "CRC")

    def createDescription(self):
        return "CRC"


class FITFile(Parser):
    endian = BIG_ENDIAN
    PARSER_TAGS = {
        "id": "fit",
        "category": "misc",
        "file_ext": ("fit",),
        "mime": ("application/fit",),
        "min_size": 14 * 8,
        "description": "Garmin binary fit format"
    }

    def __init__(self, *args, **kwargs):
        Parser.__init__(self, *args, **kwargs)
        self.msgDefs = {}

    def validate(self):
        s = self.stream.readBytes(0, 12)
        if s[8:12] != b'.FIT':
            return "Invalid header %d %d %d %d" % tuple([int(b) for b in s[8:12]])
        return True

    def createFields(self):
        yield Header(self, "header")
        while self.current_size < self["header"]["datasize"].value * 8:
            b = self.stream.readBits(self.absolute_address + self.current_size, 2, self.endian)
            if b == 1:
                defMsg = DefinitionMessage(self, "definition[]")
                msgType = defMsg["RecordHeader"]["msgType"].value
                sizes = ''
                ts = 0
                for n in range(defMsg["nbFields"].value):
                    fname = "fieldDefinition[%d]" % n
                    size = defMsg[fname]["size"].value
                    ts += size
                    sizes += "%d/" % size
                sizes += "%d" % ts
                self.msgDefs[msgType] = defMsg
                yield defMsg
            elif b == 0:
                yield DataMessage(self, "data[]")
            else:
                yield TimeStamp(self, "timestamp[]")
        yield CRC(self, "crc")
