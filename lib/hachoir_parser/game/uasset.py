"""
Unreal 4 .uasset file parser

Author: Robert Xiao
Creation date: 2015-01-17
"""

from hachoir_parser import Parser
from hachoir_core.field import (FieldSet, StaticFieldSet, SeekableFieldSet, Int32, UInt32,
    String, PascalString32, PaddingBytes, Bytes, RawBytes)
from hachoir_core.endian import LITTLE_ENDIAN

class StringTable(FieldSet):
    def __init__(self, parent, name, count, *args):
        FieldSet.__init__(self, parent, name, *args)
        self.count = count

    def createFields(self):
        for i in xrange(self.count):
            yield PascalString32(self, "string[]", strip='\0')

def getObject(self, val):
    if val == 0:
        return None
    elif val < 0:
        return self['/header/refs/ref[%d]' % (-val-1)]
    else:
        return self['/header/assets/asset[%d]' % (val-1)]


class AssetHeader(FieldSet):
    def createFields(self):
        yield Int32(self, "type1")
        yield Int32(self, "type2")
        yield Int32(self, "parent") # 0 = no parent
        yield Int32(self, "name_index")
        yield Int32(self, "unk[]")
        yield Int32(self, "unk[]")
        yield Int32(self, "size")
        yield Int32(self, "offset")
        yield Int32(self, "unk[]")
        yield Int32(self, "unk[]")
        yield Int32(self, "unk[]")
        yield Int32(self, "unk[]")
        yield Int32(self, "unk[]")
        yield Int32(self, "unk[]")
        yield Int32(self, "unk[]")
        yield Int32(self, "unk[]")
        yield Int32(self, "unk[]")

    @property
    def typeName(self):
        return getObject(self, self["type1"].value).objectName

    @property
    def objectName(self):
        name_index = self['name_index'].value
        return self['/header/strings/string[%d]' % name_index].value

    @property
    def fullObjectName(self):
        name = self.objectName
        if self['parent'].value:
            name = '%s.%s' % (getObject(self, self['parent'].value).fullObjectName, name)
        return name

    def createValue(self):
        return '<Asset %s of type %s, size %d>' % (
            self.fullObjectName, self.typeName, self['size'].value)

    def createDescription(self):
        return str([t.value for t in self.array('unk')])

class AssetTable(FieldSet):
    def __init__(self, parent, name, count, *args):
        FieldSet.__init__(self, parent, name, *args)
        self.count = count

    def createFields(self):
        for i in xrange(self.count):
            yield AssetHeader(self, "asset[]")

class ReferenceHeader(FieldSet):
    def createFields(self):
        yield Int32(self, "unk[]")
        yield Int32(self, "unk[]")
        yield Int32(self, "type_index")
        yield Int32(self, "unk[]")
        yield Int32(self, "parent")
        yield Int32(self, "name_index")
        yield Int32(self, "unk[]")

    @property
    def typeName(self):
        type_index = self['type_index'].value
        return self['/header/strings/string[%d]' % type_index].value

    @property
    def objectName(self):
        name_index = self['name_index'].value
        return self['/header/strings/string[%d]' % name_index].value

    @property
    def fullObjectName(self):
        name = self.objectName
        if self['parent'].value:
            name = '[%s].%s' % (getObject(self, self['parent'].value).fullObjectName, name)
        return name

    def createValue(self):
        return '<Reference %s of type %s>' % (self.fullObjectName, self.typeName)

    def createDescription(self):
        return str([t.value for t in self.array('unk')])

class ReferenceTable(FieldSet):
    def __init__(self, parent, name, count, *args):
        FieldSet.__init__(self, parent, name, *args)
        self.count = count

    def createFields(self):
        for i in xrange(self.count):
            yield ReferenceHeader(self, "ref[]")



class UAssetHeader(SeekableFieldSet):
    def __init__(self, *args):
        SeekableFieldSet.__init__(self, *args)
        self._size = self["header_size"].value * 8

    def createFields(self):
        yield UInt32(self, "magic")
        yield Int32(self, "version")
        yield RawBytes(self, "unk[]", 16)
        yield UInt32(self, "header_size")
        yield PascalString32(self, "none", strip='\0')
        yield RawBytes(self, "unk[]", 4)

        yield UInt32(self, "num_strings", "Number of strings in the header")
        yield UInt32(self, "offset_strings", "Offset to string table within the header")
        yield UInt32(self, "num_assets", "Number of assets described in the header")
        yield UInt32(self, "offset_assets", "Offset to asset table within the header")
        yield UInt32(self, "num_refs", "Number of references? described in the header")
        yield UInt32(self, "offset_refs", "Offset to reference table within the header")

        yield UInt32(self, "offset_unk[]", "Offset to something")
        yield UInt32(self, "unk[]")
        yield UInt32(self, "offset_unk[]", "Offset to some other thing")
        yield UInt32(self, "unk[]")

        yield RawBytes(self, "signature", 16, "Some kind of hash")

        yield UInt32(self, "unk[]")
        yield UInt32(self, "num_assets2", "num_assets again")
        assert self['num_assets'].value == self['num_assets2'].value
        yield UInt32(self, "num_strings2", "num_strings again")
        assert self['num_strings'].value == self['num_strings2'].value
        yield RawBytes(self, "unk[]", 34)
        yield UInt32(self, "unk[]")
        yield UInt32(self, "size_unk", "Size of something")
        yield RawBytes(self, "unk[]", 12)

        self.seekByte(self["offset_strings"].value)
        yield StringTable(self, "strings", self["num_strings"].value)

        self.seekByte(self["offset_assets"].value)
        yield AssetTable(self, "assets", self["num_assets"].value)

        self.seekByte(self["offset_refs"].value)
        yield ReferenceTable(self, "refs", self["num_refs"].value)

class Asset(FieldSet):
    def createFields(self):
        yield UInt32(self, "type")

class UAssetFile(Parser):
    MAGIC = "\xc1\x83\x2a\x9e"
    PARSER_TAGS = {
        "id": "uasset",
        "category": "game",
        "description": "Unreal .uasset file",
        "min_size": 32,
        "file_ext": (".uasset",),
        "magic": ((MAGIC, 0),),
    }
    endian = LITTLE_ENDIAN

    def validate(self):
        temp = self.stream.readBytes(0, 4)
        if temp != self.MAGIC:
            return "Wrong header"
        return True

    def createFields(self):
        yield UAssetHeader(self, "header")
        for asset in self['/header/assets'].array('asset'):
            self.seekByte(asset['offset'].value)
            yield RawBytes(self, "asset[]", asset['size'].value, description="Data for asset %s" % asset.fullObjectName)
