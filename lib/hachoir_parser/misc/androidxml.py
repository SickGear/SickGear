'''
AndroidManifest.xml parser

References:
- http://code.google.com/p/androguard/source/browse/core/bytecodes/apk.py

Author: Robert Xiao
Creation Date: May 29, 2011
'''

from hachoir_parser import Parser
from hachoir_core.field import (FieldSet, ParserError,
    String, Enum, GenericVector,
    UInt8, UInt16, UInt32, Int32,
    Float32, Bits,)
from hachoir_core.text_handler import textHandler, hexadecimal, filesizeHandler
from hachoir_core.tools import createDict
from hachoir_core.endian import LITTLE_ENDIAN


class PascalCString16(FieldSet):
    def createFields(self):
        yield UInt16(self, "size")
        self._size = (self['size'].value+2)*16
        yield String(self, "string", (self['size'].value+1)*2, strip='\0', charset="UTF-16-LE")
    def createValue(self):
        return self['string'].value

class StringTable(FieldSet):
    def createFields(self):
        for field in self['../offsets']:
            pad = self.seekByte(field.value)
            if pad:
                yield pad
            yield PascalCString16(self, "string[]")

def Top(self):
    while not self.eof:
        yield Chunk(self, "chunk[]")

def StringChunk(self):
    # TODO: styles
    yield UInt32(self, "string_count")
    yield UInt32(self, "style_count")
    yield UInt32(self, "reserved[]")
    yield UInt32(self, "string_offset")
    yield UInt32(self, "style_offset")
    yield GenericVector(self, "offsets", self['string_count'].value, UInt32,
            description="Offsets for string table")
    pad = self.seekByte(self['string_offset'].value)
    if pad:
        yield pad
    yield StringTable(self, "table")

def ResourceIDs(self):
    while self._current_size < self._size:
        yield textHandler(UInt32(self, "resource_id[]"), hexadecimal)

def stringIndex(field):
    if field.value == -1:
        return ''
    return field['/xml_file/string_table/table/string[%d]'%field.value].display

def NamespaceTag(self):
    yield UInt32(self, "lineno", "Line number from original XML file")
    yield Int32(self, "unk[]", "Always -1")
    yield textHandler(Int32(self, "prefix"), stringIndex)
    yield textHandler(Int32(self, "uri"), stringIndex)
def NamespaceStartValue(self):
    return "xmlns:%s='%s'"%(self['prefix'].display, self['uri'].display)
def NamespaceEndValue(self):
    return "/%s"%self['prefix'].display

def IntTextHandler(func):
    return lambda *args, **kwargs: textHandler(Int32(*args, **kwargs), func)
def booleanText(field):
    if field.value == 0:
        return 'false'
    return 'true'
class XMLUnitFloat(FieldSet):
    static_size = 32
    UNIT_MAP = {}
    RADIX_MAP = {
        0: 0,
        1: 7,
        2: 15,
        3: 23,
    }
    def createFields(self):
        yield Enum(Bits(self, "unit", 4), self.UNIT_MAP)
        yield Enum(Bits(self, "exponent", 2), self.RADIX_MAP)
        yield Bits(self, "reserved[]", 2)
        yield Bits(self, "mantissa", 24)
    def createValue(self):
        return float(self['mantissa'].value) >> self.RADIX_MAP[self['exponent'].value]
    def createDisplay(self):
        return '%f%s'%(self.value, self.UNIT_MAP.get(self['unit'].value, ''))
class XMLDimensionFloat(XMLUnitFloat):
    UNIT_MAP = dict(enumerate(["px","dip","sp","pt","in","mm"]))
class XMLFractionFloat(XMLUnitFloat):
    UNIT_MAP = {0: '%', 1: '%p'}
class XMLAttribute(FieldSet):
    TYPE_INFO = {
        0: ('Null', IntTextHandler(lambda field: '')),
        1: ('Reference', IntTextHandler(lambda field: '@%08x'%field.value)),
        2: ('Attribute', IntTextHandler(lambda field: '?%08x'%field.value)),
        3: ('String', IntTextHandler(stringIndex)),
        4: ('Float', Float32),
        5: ('Dimension', XMLDimensionFloat),
        6: ('Fraction', XMLFractionFloat),
        16: ('Int_Dec', Int32),
        17: ('Int_Hex', IntTextHandler(hexadecimal)),
        18: ('Int_Boolean', IntTextHandler(booleanText)),
        28: ('Int_Color_Argb8', IntTextHandler(lambda field: '#%08x'%field.value)),
        29: ('Int_Color_Rgb8', IntTextHandler(lambda field: '#%08x'%field.value)),
        30: ('Int_Color_Argb4', IntTextHandler(lambda field: '#%08x'%field.value)),
        31: ('Int_Color_Rgb4', IntTextHandler(lambda field: '#%08x'%field.value)),
    }
    TYPE_NAME = createDict(TYPE_INFO, 0)
    TYPE_FUNC = createDict(TYPE_INFO, 1)
    static_size = 5*32
    def createFields(self):
        yield textHandler(Int32(self, "ns"), stringIndex)
        yield textHandler(Int32(self, "name"), stringIndex)
        yield textHandler(Int32(self, "value_string"), stringIndex)
        yield UInt16(self, "unk[]")
        yield UInt8(self, "unk[]")
        yield Enum(UInt8(self, "value_type"), self.TYPE_NAME)
        func = self.TYPE_FUNC.get(self['value_type'].value, None)
        if not func:
            func = UInt32
        yield func(self, "value_data")
    def createValue(self):
        return (self['name'].display, self['value_data'].value)
    def createDisplay(self):
        return '%s="%s"'%(self['name'].display, self['value_data'].display)

def TagStart(self):
    yield UInt32(self, "lineno", "Line number from original XML file")
    yield Int32(self, "unk[]", "Always -1")
    yield textHandler(Int32(self, "ns"), stringIndex)
    yield textHandler(Int32(self, "name"), stringIndex)
    yield UInt32(self, "flags")
    yield UInt16(self, "attrib_count")
    yield UInt16(self, "attrib_id")
    yield UInt16(self, "attrib_class")
    yield UInt16(self, "attrib_style")
    for i in xrange(self['attrib_count'].value):
        yield XMLAttribute(self, "attrib[]")
def TagStartValue(self):
    attrstr = ' '.join(attr.display for attr in self.array('attrib'))
    if attrstr: attrstr = ' '+attrstr
    if not self['ns'].display:
        return '<%s%s>'%(self['name'].display, attrstr)
    return "<%s:%s%s>"%(self['ns'].display, self['name'].display, attrstr)

def TagEnd(self):
    yield UInt32(self, "lineno", "Line number from original XML file")
    yield Int32(self, "unk[]", "Always -1")
    yield textHandler(Int32(self, "ns"), stringIndex)
    yield textHandler(Int32(self, "name"), stringIndex)
def TagEndValue(self):
    if not self['ns'].display:
        return '</%s>'%self['name'].display
    return "</%s:%s>"%(self['ns'].display, self['name'].display)

def TextChunk(self):
    # TODO
    yield UInt32(self, "lineno", "Line number from original XML file")
    yield Int32(self, "unk[]", "Always -1")

class Chunk(FieldSet):
    CHUNK_INFO = {
        0x0001: ("string_table", "String Table", StringChunk, None),
        0x0003: ("xml_file", "XML File", Top, None),
        0x0100: ("namespace_start[]", "Start Namespace", NamespaceTag, NamespaceStartValue),
        0x0101: ("namespace_end[]", "End Namespace", NamespaceTag, NamespaceEndValue),
        0x0102: ("tag_start[]", "Start Tag", TagStart, TagStartValue),
        0x0103: ("tag_end[]", "End Tag", TagEnd, TagEndValue),
        0x0104: ("text[]", "Text", TextChunk, None),
        0x0180: ("resource_ids", "Resource IDs", ResourceIDs, None),
    }
    CHUNK_DESC = createDict(CHUNK_INFO, 1)
    def __init__(self, parent, name, description=None):
        FieldSet.__init__(self, parent, name, description)
        self._size = self['chunk_size'].value* 8
        type = self['type'].value
        self.parse_func = None
        if type in self.CHUNK_INFO:
            self._name, self._description, self.parse_func, value_func = self.CHUNK_INFO[type]
            if value_func:
                self.createValue = lambda: value_func(self)

    def createFields(self):
        yield Enum(UInt16(self, "type"), self.CHUNK_DESC)
        yield UInt16(self, "header_size")
        yield UInt32(self, "chunk_size")
        if self.parse_func:
            for field in self.parse_func(self):
                yield field

class AndroidXMLFile(Parser):
    MAGIC = "\x03\x00\x08\x00"
    PARSER_TAGS = {
        "id": "axml",
        "category": "misc",
        "file_ext": ("xml",),
        "min_size": 32*8,
        "magic": ((MAGIC, 0),),
        "description": "Android binary XML format",
    }
    endian = LITTLE_ENDIAN

    def validate(self):
        if self.stream.readBytes(0, len(self.MAGIC)) != self.MAGIC:
            return "Invalid magic"
        return True

    def createFields(self):
        yield Chunk(self, "xml_file")
