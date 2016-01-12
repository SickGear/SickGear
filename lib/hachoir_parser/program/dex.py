'''
Dalvik Executable (dex) parser.

References:
- http://www.dalvikvm.com/
- http://code.google.com/p/androguard/source/browse/core/bytecodes/dvm.py
- http://androguard.googlecode.com/hg/specs/dalvik/dex-format.html

Author: Robert Xiao
Creation Date: May 29, 2011
'''

from hachoir_parser import HachoirParser
from hachoir_core.field import (SeekableFieldSet, RootSeekableFieldSet, FieldSet, ParserError,
    String, RawBytes, GenericVector,
    UInt8, UInt16, UInt32, NullBits, Bit)
from hachoir_core.text_handler import textHandler, hexadecimal, filesizeHandler
from hachoir_core.endian import LITTLE_ENDIAN
from hachoir_parser.program.java import eat_descriptor

class DexHeader(FieldSet):
    def createFields(self):
        yield String(self, "magic", 4)
        yield String(self, "version", 4, strip='\0')
        yield textHandler(UInt32(self, "checksum"), hexadecimal)
        yield RawBytes(self, "signature", 20, description="SHA1 sum over all subsequent data")
        yield filesizeHandler(UInt32(self, "filesize"))
        yield UInt32(self, "size", description="Header size")
        self._size = self['size'].value*8
        yield textHandler(UInt32(self, "endian"), hexadecimal)
        yield UInt32(self, "link_count")
        yield UInt32(self, "link_offset")
        yield UInt32(self, "map_offset", description="offset to map footer")
        yield UInt32(self, "string_count", description="number of entries in string table")
        yield UInt32(self, "string_offset", description="offset to string table")
        yield UInt32(self, "type_desc_count", description="number of entries in type descriptor table")
        yield UInt32(self, "type_desc_offset", description="offset to type descriptor table")
        yield UInt32(self, "meth_desc_count", description="number of entries in method descriptor table")
        yield UInt32(self, "meth_desc_offset", description="offset to method descriptor table")
        yield UInt32(self, "field_count", description="number of entries in field table")
        yield UInt32(self, "field_offset", description="offset to field table")
        yield UInt32(self, "method_count", description="number of entries in method table")
        yield UInt32(self, "method_offset", description="offset to method table")
        yield UInt32(self, "class_count", description="number of entries in class table")
        yield UInt32(self, "class_offset", description="offset to class table")
        yield UInt32(self, "data_size", description="size of data region")
        yield UInt32(self, "data_offset", description="offset to data region")

def stringIndex(field):
    return field['/string_table/item[%d]'%field.value].display

def classDisplay(field):
    disp, tail = eat_descriptor(stringIndex(field))
    return disp

def classIndex(field):
    return field['/type_desc_table/item[%d]'%field.value].display

# modified from java.py
code_to_type_name = {
    'B': "byte",
    'C': "char",
    'D': "double",
    'F': "float",
    'I': "int",
    'J': "long",
    'L': "object",
    'S': "short",
    'Z': "boolean",
}

def argumentDisplay(field):
    # parse "shorty" descriptors (these start with the return code, which is redundant)
    text = stringIndex(field)[1:]
    return [code_to_type_name.get(c,c) for c in text]

def signatureIndex(field):
    return field['/meth_desc_table/item[%d]'%field.value].display

class PascalCString(FieldSet):
    def createFields(self):
        yield UInt8(self, "size")
        self._size = (self['size'].value+2)*8
        yield String(self, "string", self['size'].value+1, strip='\0')
    def createValue(self):
        return self['string'].value

class StringTable(SeekableFieldSet):
    def createFields(self):
        for item in self['/string_offsets'].array('item'):
            self.seekByte(item.value, relative=False)
            yield PascalCString(self, "item[]")

class TypeDescriptorEntry(FieldSet):
    static_size = 32
    def createFields(self):
        yield textHandler(UInt32(self, "desc", description="Type descriptor"), classDisplay)
    def createValue(self):
        return (self['desc'].value,)
    def createDisplay(self):
        return self['desc'].display

class MethodDescriptorEntry(FieldSet):
    static_size = 96
    def createFields(self):
        yield textHandler(UInt32(self, "args", description="Argument type"), argumentDisplay)
        yield textHandler(UInt32(self, "return", description="Return type"), classIndex)
        yield UInt32(self, "param_offset", "Offset to parameter detail list")
    def createValue(self):
        return (self['args'].value, self['return'].value)
    def createDisplay(self):
        return "%s (%s)"%(self['return'].display, ', '.join(self['args'].display))

class FieldEntry(FieldSet):
    static_size = 64
    def createFields(self):
        yield textHandler(UInt16(self, "class", description="Class containing this field"), classIndex)
        yield textHandler(UInt16(self, "type", description="Field type"), classIndex)
        yield textHandler(UInt32(self, "name", description="Field name"), stringIndex)
    def createValue(self):
        return (self['class'].value, self['type'].value, self['name'].value)
    def createDisplay(self):
        return "%s %s.%s"%(self['type'].display, self['class'].display, self['name'].display)

class MethodEntry(FieldSet):
    static_size = 64
    def createFields(self):
        yield textHandler(UInt16(self, "class", description="Class containing this method"), classIndex)
        yield textHandler(UInt16(self, "sig", description="Method signature"), signatureIndex)
        yield textHandler(UInt32(self, "name", description="Method name"), stringIndex)
    def createValue(self):
        return (self['class'].value, self['sig'].value, self['name'].value)
    def createDisplay(self):
        sig = self['/meth_desc_table/item[%d]'%self['sig'].value]
        return "%s %s.%s(%s)"%(sig['return'].display, self['class'].display, self['name'].display, ', '.join(sig['args'].display))

class AccessFlags(FieldSet):
    static_size = 32
    def createFields(self):
        yield Bit(self, "public")
        yield Bit(self, "private")
        yield Bit(self, "protected")
        yield Bit(self, "static")
        yield Bit(self, "final")
        yield Bit(self, "synchronized")
        yield Bit(self, "volatile")
        yield Bit(self, "transient")
        yield Bit(self, "native")
        yield Bit(self, "interface")
        yield Bit(self, "abstract")
        yield Bit(self, "strictfp")
        yield Bit(self, "synthetic")
        yield Bit(self, "annotation")
        yield Bit(self, "enum")
        yield NullBits(self, "reserved[]", 1)
        yield Bit(self, "constructor")
        yield NullBits(self, "reserved[]", 15)
    def createValue(self):
        return tuple(f for f in self if f.value is True)
    def createDisplay(self):
        return ' '.join(f.name for f in self if f.value is True)

class ClassEntry(FieldSet):
    static_size = 8*32
    def createFields(self):
        yield textHandler(UInt32(self, "class", description="Class being described"), classIndex)
        yield AccessFlags(self, "flags")
        yield textHandler(UInt32(self, "superclass", description="Superclass"), classIndex)
        yield UInt32(self, "interfaces_offset", description="Offset to interface list")
        yield textHandler(UInt32(self, "filename", description="Filename"), stringIndex)
        yield UInt32(self, "annotations_offset")
        yield UInt32(self, "class_data_offset")
        yield UInt32(self, "static_values_offset")
    def createValue(self):
        return tuple(f.value for f in self)
    def createDisplay(self):
        disp = self['flags'].display
        if not self['flags/interface'].value:
            if disp:
                disp += ' '
            disp += 'class'
        disp += ' '+self['class'].display
        if self['superclass'].display != 'java.lang.Object':
            disp += ' extends '+self['superclass'].display
        return disp

class DexFile(HachoirParser, RootSeekableFieldSet):
    MAGIC = "dex\n"
    PARSER_TAGS = {
        "id": "dex",
        "category": "program",
        "file_ext": ("dex",),
        "min_size": 80*8,
        "magic": ((MAGIC, 0),),
        "description": "Dalvik VM Executable",
    }
    endian = LITTLE_ENDIAN

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(self, None, "root", stream, None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        if self.stream.readBytes(0, len(self.MAGIC)) != self.MAGIC:
            return "Invalid magic"
        if self['header/version'].value != '035':
            return "Unknown version"
        return True

    def createFields(self):
        yield DexHeader(self, "header")

        self.seekByte(self['header/string_offset'].value)
        yield GenericVector(self, "string_offsets", self['header/string_count'].value, UInt32,
            description="Offsets for string table")
        self.seekByte(self['string_offsets/item[0]'].value)
        yield StringTable(self, "string_table",
            description="String table")

        self.seekByte(self['header/type_desc_offset'].value)
        yield GenericVector(self, "type_desc_table", self['header/type_desc_count'].value, TypeDescriptorEntry,
            description="Type descriptor table")

        self.seekByte(self['header/meth_desc_offset'].value)
        yield GenericVector(self, "meth_desc_table", self['header/meth_desc_count'].value, MethodDescriptorEntry,
            description="Method descriptor table")

        self.seekByte(self['header/field_offset'].value)
        yield GenericVector(self, "field_table", self['header/field_count'].value, FieldEntry,
            description="Field definition table")

        self.seekByte(self['header/method_offset'].value)
        yield GenericVector(self, "method_table", self['header/method_count'].value, MethodEntry,
            description="Method definition table")

        self.seekByte(self['header/class_offset'].value)
        yield GenericVector(self, "class_table", self['header/class_count'].value, ClassEntry,
            description="Class definition table")
