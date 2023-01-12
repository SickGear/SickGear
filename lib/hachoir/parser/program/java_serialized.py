'''
Java Object Serialization Stream parser.

References:
- http://docs.oracle.com/javase/7/docs/platform/serialization/spec/protocol.html
- http://www.javaworld.com/article/2072752/the-java-serialization-algorithm-revealed.html

Author: Robert Xiao <nneonneo@gmail.com>
Creation Date: Jun 18, 2015
Updated: Jan 12, 2017
'''

from hachoir.parser import Parser
from hachoir.field import (
    ParserError, FieldSet,
    Enum, RawBytes, String, PascalString16, Float32, Float64,
    Int8, UInt8, Int16, UInt16, Int32, UInt32, Int64,
    Bit, NullBits)
from hachoir.core.endian import BIG_ENDIAN
from hachoir.core.text_handler import textHandler, hexadecimal

from .java import parse_field_descriptor


class LongString(FieldSet):

    def createFields(self):
        yield Int64(self, "length")
        yield String(self, "value", charset="UTF-8")

    def createDescription(self):
        return self['value'].description

    def createValue(self):
        return self['value'].value


class UTF16Character(UInt16):

    def createDisplay(self):
        return repr(chr(self.value))


class JavaBool(UInt8):

    def createValue(self):
        val = UInt8.createValue(self)
        return (val != 0)


class SerializedNull(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)

    def createValue(self):
        return None

    def createDisplay(self):
        return 'null'


class SerializedReference(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        yield Int32(self, "handle")

    @property
    def referent(self):
        return self.root.handles[self['handle'].value]

    def createValue(self):
        return self['handle'].value

    def createDisplay(self):
        return "-> " + str(self.referent.display)


class FieldDesc(FieldSet):

    def createFields(self):
        yield String(self, "typecode", 1)
        yield PascalString16(self, "fieldName", charset="UTF-8")
        if self['typecode'].value in ('[', 'L'):
            yield SerializedContent(self, "className")

    @property
    def typeDescriptor(self):
        typecode = self['typecode'].value
        if typecode in ('[', 'L'):
            return self['className'].value
        else:
            return typecode

    @property
    def typeName(self):
        return parse_field_descriptor(self.typeDescriptor)

    @property
    def fieldName(self):
        return self['fieldName'].value

    def createValue(self):
        return (self.typeDescriptor, self.fieldName)

    def createDisplay(self):
        return '%s %s' % (self.typeName, self.fieldName)


class ClassAnnotation(FieldSet):

    def createFields(self):
        while 1:
            obj = SerializedContent(self, "contents[]")
            yield obj
            if isinstance(obj, EndBlockData):
                break


class SerializedClassDesc(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        yield PascalString16(self, "className", charset="UTF-8")
        yield Int64(self, "serialVersionUID")
        self.root.newHandle(self)
        yield NullBits(self, "classDescFlags_reserved", 3)
        yield Bit(self, "classDescFlags_enum", "Is the class an Enum?")
        yield Bit(self, "classDescFlags_block_data", "Was the externalizable's block data written using stream version 2?")
        yield Bit(self, "classDescFlags_externalizable", "Does the class implement java.io.Externalizable?")
        yield Bit(self, "classDescFlags_serializable", "Does the class implement java.io.Serializable?")
        yield Bit(self, "classDescFlags_write_method", "Does the class have a writeObject method?")
        yield Int16(self, "fieldDesc_count")
        for i in range(self['fieldDesc_count'].value):
            yield FieldDesc(self, "fieldDesc[]")
        yield ClassAnnotation(self, "classAnnotation")
        yield SerializedContent(self, "superClassDesc")

    @property
    def className(self):
        return self['className'].value

    def createValue(self):
        return self.className


class ObjectValue(FieldSet):

    def gen_values(self, classDesc):
        if isinstance(classDesc, SerializedReference):
            classDesc = classDesc.referent
        if isinstance(classDesc, SerializedNull):
            return

        for field in self.gen_values(classDesc['superClassDesc']):
            yield field

        if isinstance(classDesc, SerializedProxyClassDesc):
            return

        if classDesc['classDescFlags_externalizable'].value:
            yield WriteObjectContents(self, "external[]", "%s.writeExternal() output" % classDesc['className'].value)
            return

        for fieldDesc in classDesc.array('fieldDesc'):
            tc = fieldDesc['typecode'].value
            klass = VALUE_CLASS_MAP[tc]
            field = klass(self, "field[]", description="%s.%s" %
                          (classDesc.className, fieldDesc.fieldName))
            field.fieldName = fieldDesc.fieldName
            yield field

        if classDesc['classDescFlags_write_method'].value:
            yield WriteObjectContents(self, "extra[]", "%s.writeObject() output" % classDesc['className'].value)

    def createFields(self):
        for field in self.gen_values(self.parent.classDesc):
            yield field


class WriteObjectContents(FieldSet):

    def createFields(self):
        while 1:
            obj = SerializedContent(self, "extra[]")
            yield obj
            if isinstance(obj, EndBlockData):
                break


class SerializedObject(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        yield SerializedContent(self, "classDesc")
        self.root.newHandle(self)

        yield ObjectValue(self, "value")

    @property
    def classDesc(self):
        classDesc = self['classDesc']
        if isinstance(classDesc, SerializedReference):
            classDesc = classDesc.referent
        return classDesc

    def createValue(self):
        return tuple(field.value for field in self['value'].array('field'))

    def createDisplay(self):
        out = []
        for field in self['value'].array('field'):
            if isinstance(field, SerializedReference) and not isinstance(field.referent, SerializedString):
                # Avoid recursive references
                out.append('%s=#<REF:%s>' % (field.fieldName,
                                             field.referent.classDesc.className))
            else:
                out.append('%s=%s' % (field.fieldName, field.display))
        return '%s(%s)' % (self.classDesc.className, ', '.join(out))


class SerializedString(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        self.root.newHandle(self)
        yield PascalString16(self, "value", charset="UTF-8")

    def createValue(self):
        return self['value'].value

    def createDisplay(self):
        return self['value'].display


class SerializedArray(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        yield SerializedContent(self, "classDesc")
        self.root.newHandle(self)

        yield Int32(self, "size")
        klass = VALUE_CLASS_MAP[self.classDesc.className[
            1]]  # className is [<elementType>
        for i in range(self['size'].value):
            yield klass(self, "value[]")

    @property
    def classDesc(self):
        classDesc = self['classDesc']
        if isinstance(classDesc, SerializedReference):
            classDesc = classDesc.referent
        return classDesc

    def createValue(self):
        return [v.value for v in self.array('value')]

    def createDisplay(self):
        out = []
        for field in self.array('value'):
            if isinstance(field, SerializedReference) and not isinstance(field.referent, SerializedString):
                # Avoid recursive references
                out.append('#<REF:%s>' % (field.referent.classDesc.className,))
            else:
                out.append('%s' % (field.display,))
        return '[%s]' % ', '.join(out)


class SerializedClass(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        yield SerializedContent(self, "classDesc")
        self.root.newHandle(self)


class BlockData(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        yield UInt8(self, "size")
        if self['size'].value:
            yield RawBytes(self, "data", self['size'].value)


class EndBlockData(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)


class StreamReset(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        self.root.resetHandles()


class BlockDataLong(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        yield UInt32(self, "size")
        if self['size'].value:
            yield RawBytes(self, "data", self['size'].value)


class SerializedException(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        self.root.resetHandles()
        yield SerializedObject(self, "object")
        self.root.resetHandles()


class SerializedLongString(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        self.root.newHandle(self)
        yield LongString(self, "value")

    def createValue(self):
        return self['value'].value


class SerializedProxyClassDesc(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)

        self.root.newHandle(self)
        yield Int32(self, "proxyInterfaceName_count")
        for i in range(self['proxyInterfaceName_count'].value):
            yield PascalString16(self, "proxyInterfaceName[]", charset="UTF-8")
        yield ClassAnnotation(self, "classAnnotation")
        yield SerializedContent(self, "superClassDesc")

    @property
    def className(self):
        return '<Proxy implements %s>' % (', '.join(v.value for v in self.array('proxyInterfaceName')))


class SerializedEnum(FieldSet):

    def createFields(self):
        yield Enum(UInt8(self, "typecode"), TYPECODE_NAMES)
        yield SerializedContent(self, "classDesc")
        self.root.newHandle(self)
        yield SerializedContent(self, "enumConstantName")

    @property
    def classDesc(self):
        classDesc = self['classDesc']
        if isinstance(classDesc, SerializedReference):
            classDesc = classDesc.referent
        return classDesc

    def createValue(self):
        return self['enumConstantName'].value

    def createDisplay(self):
        return '%s.%s' % (self.classDesc.className, self.value)


TYPECODE_NAMES = {
    0x70: "NULL",
    0x71: "REFERENCE",
    0x72: "CLASSDESC",
    0x73: "OBJECT",
    0x74: "STRING",
    0x75: "ARRAY",
    0x76: "CLASS",
    0x77: "BLOCKDATA",
    0x78: "ENDBLOCKDATA",
    0x79: "RESET",
    0x7A: "BLOCKDATALONG",
    0x7B: "EXCEPTION",
    0x7C: "LONGSTRING",
    0x7D: "PROXYCLASSDESC",
    0x7E: "ENUM",
}

TYPECODE_TABLE = {
    0x70: SerializedNull,
    0x71: SerializedReference,
    0x72: SerializedClassDesc,
    0x73: SerializedObject,
    0x74: SerializedString,
    0x75: SerializedArray,
    0x76: SerializedClass,
    0x77: BlockData,
    0x78: EndBlockData,
    0x79: StreamReset,
    0x7a: BlockDataLong,
    0x7b: SerializedException,
    0x7c: SerializedLongString,
    0x7d: SerializedProxyClassDesc,
    0x7e: SerializedEnum,
}


def SerializedContent(parent, name, description=None):
    tc = parent.stream.readBits(
        parent.absolute_address + parent.current_size, 8, parent.endian)
    klass = TYPECODE_TABLE.get(tc, None)
    if klass is None:
        raise ParserError("Unknown typecode 0x%02x" % tc)
    return klass(parent, name, description)


VALUE_CLASS_MAP = {
    'B': Int8,
    'C': UTF16Character,
    'D': Float64,
    'F': Float32,
    'I': Int32,
    'J': Int64,
    'S': Int16,
    'Z': JavaBool,
    '[': SerializedContent,  # SerializedArray or reference
    'L': SerializedContent,  # SerializedObject or reference
}


class JavaSerializedFile(Parser):
    endian = BIG_ENDIAN

    MAGIC = 0xaced
    KNOWN_VERSIONS = (5,)

    PARSER_TAGS = {
        "id": "java_serialized",
        "category": "program",
        "file_ext": ("ser",),
        "mime": ("application/java-serialized-object",),
        "min_size": 4 * 4,
        "magic": ((b"\xac\xed", 0),),
        "description": "Serialized Java object",
    }

    def validate(self):
        if self["magic"].value != self.MAGIC:
            return "Wrong magic signature!"
        if self["version"].value not in self.KNOWN_VERSIONS:
            return "Unknown version (%d)" % self["version"].value
        return True

    def createDescription(self):
        return "Serialized Java object, version %s" % self["version"].value

    def resetHandles(self):
        self.handles = {}
        self.nextHandleNum = 0x7E0000

    def newHandle(self, obj):
        self.handles[self.nextHandleNum] = obj
        self.nextHandleNum += 1

    def createFields(self):
        self.resetHandles()

        yield textHandler(UInt16(self, "magic", "Java serialized object signature"),
                          hexadecimal)
        yield UInt16(self, "version", "Stream version")

        while not self.eof:
            yield SerializedContent(self, "object[]")
