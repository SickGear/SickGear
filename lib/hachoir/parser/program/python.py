"""
Python compiled source code parser.

Informations:
- Python 2.4.2 source code:
  files Python/marshal.c and Python/import.c

Author: Victor Stinner
Creation: 25 march 2005
"""

from hachoir.parser import Parser
from hachoir.field import (
    Field, FieldSet, UInt8,
    UInt16, Int32, UInt32, Int64, UInt64,
    ParserError, Float64,
    Character, RawBytes, PascalString8, TimestampUnix32,
    Bit, String, NullBits)
from hachoir.core.endian import LITTLE_ENDIAN
from hachoir.core.bits import long2raw
from hachoir.core.text_handler import textHandler, hexadecimal
from hachoir.core import config

DISASSEMBLE = False

if DISASSEMBLE:
    from dis import dis

    def disassembleBytecode(field):
        bytecode = field.value
        dis(bytecode)

# --- String and string reference ---


def parseString(parent):
    yield UInt32(parent, "length", "Length")
    length = parent["length"].value
    if parent.name == "lnotab":
        bytecode_offset = 0
        line_number = parent['../firstlineno'].value
        for i in range(0, length, 2):
            bc_off_delta = UInt8(parent, 'bytecode_offset_delta[]')
            yield bc_off_delta
            bytecode_offset += bc_off_delta.value
            bc_off_delta._description = 'Bytecode Offset %i' % bytecode_offset
            line_number_delta = UInt8(parent, 'line_number_delta[]')
            yield line_number_delta
            line_number += line_number_delta.value
            line_number_delta._description = 'Line Number %i' % line_number
    elif 0 < length:
        yield RawBytes(parent, "text", length, "Content")
    if DISASSEMBLE and parent.name == "compiled_code":
        disassembleBytecode(parent["text"])


def createStringValue(parent):
    if parent.name == "lnotab":
        return "<lnotab>"
    return parent["text"]


def parseStringRef(parent):
    yield textHandler(UInt32(parent, "ref"), hexadecimal)


def createStringRefDesc(parent):
    return "String ref: %s" % parent["ref"].display


def createStringRefValue(parent):
    value = parent["ref"].value
    if hasattr(parent.root, 'string_table') and 0 <= value < len(parent.root.string_table):
        return parent.root.string_table[value]
    return None

# --- Integers ---


def parseInt32(parent):
    yield Int32(parent, "value")


def parseInt64(parent):
    yield Int64(parent, "value")


def createIntValue(parent):
    return parent["value"]


def parseLong(parent):
    yield Int32(parent, "digit_count")
    for index in range(abs(parent["digit_count"].value)):
        yield UInt16(parent, "digit[]")


def createLongValue(parent):
    is_negative = parent["digit_count"].value < 0
    count = abs(parent["digit_count"].value)
    total = 0
    for index in range(count - 1, -1, -1):
        total <<= 15
        total += parent["digit[%u]" % index].value
    if is_negative:
        total = -total
    return total


# --- Float and complex ---
def parseFloat(parent):
    yield PascalString8(parent, "value")


def createFloatValue(parent):
    return float(parent["value"].value)


def parseBinaryFloat(parent):
    yield Float64(parent, "value")


def parseComplex(parent):
    yield PascalString8(parent, "real")
    yield PascalString8(parent, "complex")


def parseBinaryComplex(parent):
    yield Float64(parent, "real")
    yield Float64(parent, "complex")


def createComplexValue(parent):
    return complex(
        float(parent["real"].value),
        float(parent["complex"].value))


# --- Tuple and list ---
def parseTuple(parent):
    yield UInt32(parent, "count", "Item count")
    count = parent["count"].value
    if count < 0:
        raise ParserError("Invalid tuple/list count")
    for index in range(count):
        yield Object(parent, "item[]")


def parseSmallTuple(parent):
    yield UInt8(parent, "count", "Item count")
    count = parent["count"].value
    if count < 0:
        raise ParserError("Invalid tuple/list count")
    for index in range(count):
        yield Object(parent, "item[]")


def createTupleDesc(parent):
    count = parent["count"].value
    items = "%s items" % count
    return "%s: %s" % (parent.code_info[2], items)


def tupleValueCreator(constructor):
    def createTupleValue(parent):
        return constructor([v.value for v in parent.array("item")])
    return createTupleValue


# --- Dict ---
def parseDict(parent):
    """
    Format is: (key1, value1, key2, value2, ..., keyn, valuen, NULL)
    where each keyi and valuei is an object.
    """
    parent.count = 0
    while True:
        key = Object(parent, "key[]")
        yield key
        if key["bytecode"].value == "0":
            break
        yield Object(parent, "value[]")
        parent.count += 1


def createDictDesc(parent):
    return "Dict: %s" % ("%s keys" % parent.count)


def createDictValue(parent):
    return {k.value: v.value for k, v in zip(parent.array("key"), parent.array("value"))}


def parseRef(parent):
    yield UInt32(parent, "n", "Reference")


def createRefDesc(parent):
    value = parent["n"].value
    if hasattr(parent.root, 'object_table') and 0 <= value < len(parent.root.object_table):
        return 'Reference: %s' % parent.root.object_table[value].description
    else:
        return 'Reference: %d' % value


def createRefValue(parent):
    value = parent["n"].value
    if hasattr(parent.root, 'object_table') and 0 <= value < len(parent.root.object_table):
        return parent.root.object_table[value]
    else:
        return None


def parseASCII(parent):
    size = UInt32(parent, "len", "Number of ASCII characters")
    yield size
    if size.value:
        yield String(parent, "text", size.value, "String content", charset="ASCII")


def parseShortASCII(parent):
    size = UInt8(parent, "len", "Number of ASCII characters")
    yield size
    if size.value:
        yield String(parent, "text", size.value, "String content", charset="ASCII")

# --- Code ---


def parseCode(parent):
    version = parent.root.getVersion()
    if 0x3000000 <= version:
        yield UInt32(parent, "arg_count", "Argument count")
        if 0x3080000 <= version:
            yield UInt32(parent, "posonlyargcount", "Positional only argument count")
        yield UInt32(parent, "kwonlyargcount", "Keyword only argument count")
        if version < 0x30B0000:
            yield UInt32(parent, "nb_locals", "Number of local variables")
        yield UInt32(parent, "stack_size", "Stack size")
        yield UInt32(parent, "flags")
    elif 0x2030000 <= version:
        yield UInt32(parent, "arg_count", "Argument count")
        yield UInt32(parent, "nb_locals", "Number of local variables")
        yield UInt32(parent, "stack_size", "Stack size")
        yield UInt32(parent, "flags")
    else:
        yield UInt16(parent, "arg_count", "Argument count")
        yield UInt16(parent, "nb_locals", "Number of local variables")
        yield UInt16(parent, "stack_size", "Stack size")
        yield UInt16(parent, "flags")

    yield Object(parent, "compiled_code")
    yield Object(parent, "consts")
    yield Object(parent, "names")
    if 0x30B0000 <= version:
        yield Object(parent, "co_localsplusnames")
        yield Object(parent, "co_localspluskinds")
    else:
        yield Object(parent, "varnames")
        if 0x2000000 <= version:
            yield Object(parent, "freevars")
            yield Object(parent, "cellvars")

    yield Object(parent, "filename")
    yield Object(parent, "name")
    if 0x30B0000 <= version:
        yield Object(parent, "qualname")

    if 0x2030000 <= version:
        yield UInt32(parent, "firstlineno", "First line number")
    else:
        yield UInt16(parent, "firstlineno", "First line number")
    if 0x30A0000 <= version:
        yield Object(parent, "linetable")
        if 0x30B0000 <= version:
            yield Object(parent, "exceptiontable")
    else:
        yield Object(parent, "lnotab")


class Object(FieldSet):
    bytecode_info = {
        # Don't contains any data
        '0': ("null", None, "NULL", None, None),
        'N': ("none", None, "None", None, lambda parent: None),
        'F': ("false", None, "False", None, lambda parent: False),
        'T': ("true", None, "True", None, lambda parent: True),
        'S': ("stop_iter", None, "StopIter", None, None),
        '.': ("ellipsis", None, "ELLIPSIS", None, lambda parent: ...),
        '?': ("unknown", None, "Unknown", None, None),

        'i': ("int32", parseInt32, "Int32", None, createIntValue),
        'I': ("int64", parseInt64, "Int64", None, createIntValue),
        'f': ("float", parseFloat, "Float", None, createFloatValue),
        'g': ("bin_float", parseBinaryFloat, "Binary float", None, createFloatValue),
        'x': ("complex", parseComplex, "Complex", None, createComplexValue),
        'y': ("bin_complex", parseBinaryComplex, "Binary complex", None, createComplexValue),
        'l': ("long", parseLong, "Long", None, createLongValue),
        's': ("string", parseString, "String", None, createStringValue),
        't': ("interned", parseString, "Interned", None, createStringValue),
        'u': ("unicode", parseString, "Unicode", None, createStringValue),
        'R': ("string_ref", parseStringRef, "String ref", createStringRefDesc, createStringRefValue),
        '(': ("tuple", parseTuple, "Tuple", createTupleDesc, tupleValueCreator(tuple)),
        ')': ("small_tuple", parseSmallTuple, "Tuple", createTupleDesc, tupleValueCreator(tuple)),
        '[': ("list", parseTuple, "List", createTupleDesc, tupleValueCreator(list)),
        '<': ("set", parseTuple, "Set", createTupleDesc, tupleValueCreator(set)),
        '>': ("frozenset", parseTuple, "Frozen set", createTupleDesc, tupleValueCreator(frozenset)),
        '{': ("dict", parseDict, "Dict", createDictDesc, createDictValue),
        'c': ("code", parseCode, "Code", None, None),
        'r': ("ref", parseRef, "Reference", createRefDesc, createRefValue),
        'a': ("ascii", parseASCII, "ASCII", None, createStringValue),
        'A': ("ascii_interned", parseASCII, "ASCII interned", None, createStringValue),
        'z': ("short_ascii", parseShortASCII, "Short ASCII", None, createStringValue),
        'Z': ("short_ascii_interned", parseShortASCII, "Short ASCII interned", None, createStringValue),
    }

    def __init__(self, parent, name, **kw):
        FieldSet.__init__(self, parent, name, **kw)
        code = self["bytecode"].value
        if code not in self.bytecode_info:
            raise ParserError('Unknown bytecode %r at position %s'
                              % (code, self.absolute_address // 8))
        self.code_info = self.bytecode_info[code]
        if not name:
            self._name = self.code_info[0]
        if code in ("t", "A", "Z"):
            if not hasattr(self.root, 'string_table'):
                self.root.string_table = []
            self.root.string_table.append(self)

    def createValue(self):
        create = self.code_info[4]
        if create:
            res = create(self)
            if isinstance(res, Field):
                return res.value
            else:
                return res
        return None

    def createDisplay(self):
        create = self.code_info[4]
        if create:
            res = create(self)
            if isinstance(res, Field):
                return res.display
            res = repr(res)
            if len(res) >= config.max_string_length:
                res = res[:config.max_string_length] + "..."
            return res
        return None

    def createFields(self):
        yield BytecodeChar(self, "bytecode", "Bytecode")
        yield Bit(self, "flag_ref", "Is a reference?")
        if self["flag_ref"].value:
            if not hasattr(self.root, 'object_table'):
                self.root.object_table = []
            self.root.object_table.append(self)
        parser = self.code_info[1]
        if parser:
            yield from parser(self)

    def createDescription(self):
        create = self.code_info[3]
        if create:
            return create(self)
        else:
            return self.code_info[2]


class BytecodeChar(Character):
    static_size = 7


PY_RELEASE_LEVEL_ALPHA = 0xA
PY_RELEASE_LEVEL_FINAL = 0xF


def VERSION(major, minor, release_level=PY_RELEASE_LEVEL_FINAL, serial=0):
    micro = 0
    return ((major << 24) + (minor << 16) + (micro << 8)
            + (release_level << 4) + (serial << 0))


class PythonCompiledFile(Parser):
    PARSER_TAGS = {
        "id": "python",
        "category": "program",
        "file_ext": ("pyc", "pyo"),
        "min_size": 9 * 8,
        "description": "Compiled Python script (.pyc/.pyo files)"
    }
    endian = LITTLE_ENDIAN

    # Dictionnary which associate the pyc signature (32-bit integer)
    # to a Python version string (eg. "m\xf2\r\n" => "Python 2.4b1").
    # This list comes from CPython source code, see MAGIC_NUMBER
    # in file Lib/importlib/_bootstrap_external.py
    MAGIC = {
        # Python 1.x
        20121: ("1.5", 0x1050000),
        50428: ("1.6", 0x1060000),

        # Python 2.x
        50823: ("2.0", 0x2000000),
        60202: ("2.1", 0x2010000),
        60717: ("2.2", 0x2020000),
        62011: ("2.3a0", 0x2030000),
        62021: ("2.3a0", 0x2030000),
        62041: ("2.4a0", 0x2040000),
        62051: ("2.4a3", 0x2040000),
        62061: ("2.4b1", 0x2040000),
        62071: ("2.5a0", 0x2050000),
        62081: ("2.5a0 (ast-branch)", 0x2050000),
        62091: ("2.5a0 (with)", 0x2050000),
        62092: ("2.5a0 (WITH_CLEANUP opcode)", 0x2050000),
        62101: ("2.5b3", 0x2050000),
        62111: ("2.5b3", 0x2050000),
        62121: ("2.5c1", 0x2050000),
        62131: ("2.5c2", 0x2050000),
        62151: ("2.6a0", 0x2070000),
        62161: ("2.6a1", 0x2070000),
        62171: ("2.7a0", 0x2070000),
        62181: ("2.7a0", 0x2070000),
        62191: ("2.7a0", 0x2070000),
        62201: ("2.7a0", 0x2070000),
        62211: ("2.7a0", 0x2070000),

        # Python 3.x
        3000: ("3.0 (3000)", 0x3000000),
        3010: ("3.0 (3010)", 0x3000000),
        3020: ("3.0 (3020)", 0x3000000),
        3030: ("3.0 (3030)", 0x3000000),
        3040: ("3.0 (3040)", 0x3000000),
        3050: ("3.0 (3050)", 0x3000000),
        3060: ("3.0 (3060)", 0x3000000),
        3061: ("3.0 (3061)", 0x3000000),
        3071: ("3.0 (3071)", 0x3000000),
        3081: ("3.0 (3081)", 0x3000000),
        3091: ("3.0 (3091)", 0x3000000),
        3101: ("3.0 (3101)", 0x3000000),
        3103: ("3.0 (3103)", 0x3000000),
        3111: ("3.0a4", 0x3000000),
        3131: ("3.0a5", 0x3000000),
        3141: ("3.1a0", 0x3010000),
        3151: ("3.1a0", 0x3010000),
        3160: ("3.2a0", 0x3020000),
        3170: ("3.2a1", 0x3020000),
        3180: ("3.2a2", 0x3020000),
        3190: ("Python 3.3a0", 0x3030000),
        3200: ("Python 3.3a0 ", 0x3030000),
        3210: ("Python 3.3a0 ", 0x3030000),
        3220: ("Python 3.3a1 ", 0x3030000),
        3230: ("Python 3.3a4 ", 0x3030000),
        3250: ("Python 3.4a1 ", 0x3040000),
        3260: ("Python 3.4a1 ", 0x3040000),
        3270: ("Python 3.4a1 ", 0x3040000),
        3280: ("Python 3.4a1 ", 0x3040000),
        3290: ("Python 3.4a4 ", 0x3040000),
        3300: ("Python 3.4a4 ", 0x3040000),
        3310: ("Python 3.4rc2", 0x3040000),
        3320: ("Python 3.5a0 ", 0x3050000),
        3330: ("Python 3.5b1 ", 0x3050000),
        3340: ("Python 3.5b2 ", 0x3050000),
        3350: ("Python 3.5b2 ", 0x3050000),
        3351: ("Python 3.5.2 ", 0x3050000),
        3360: ("Python 3.6a0 ", 0x3060000),
        3361: ("Python 3.6a0 ", 0x3060000),
        3370: ("Python 3.6a1 ", 0x3060000),
        3371: ("Python 3.6a1 ", 0x3060000),
        3372: ("Python 3.6a1 ", 0x3060000),
        3373: ("Python 3.6b1 ", 0x3060000),
        3375: ("Python 3.6b1 ", 0x3060000),
        3376: ("Python 3.6b1 ", 0x3060000),
        3377: ("Python 3.6b1 ", 0x3060000),
        3378: ("Python 3.6b2 ", 0x3060000),
        3379: ("Python 3.6rc1", 0x3060000),
        3390: ("Python 3.7a1", 0x30700A1),
        3391: ("Python 3.7a2", 0x30700A2),
        3392: ("Python 3.7a4", 0x30700A4),
        3393: ("Python 3.7b1", 0x30700B1),
        3394: ("Python 3.7b5", 0x30700B5),
        3400: ("Python 3.8a1", VERSION(3, 8)),
        3401: ("Python 3.8a1", VERSION(3, 8)),
        3410: ("Python 3.8a1", VERSION(3, 8)),
        3411: ("Python 3.8b2", VERSION(3, 8)),
        3412: ("Python 3.8b2", VERSION(3, 8)),
        3413: ("Python 3.8b4", VERSION(3, 8)),
        3420: ("Python 3.9a0", VERSION(3, 9)),
        3421: ("Python 3.9a0", VERSION(3, 9)),
        3422: ("Python 3.9a0", VERSION(3, 9)),
        3423: ("Python 3.9a2", VERSION(3, 9)),
        3424: ("Python 3.9a2", VERSION(3, 9)),
        3425: ("Python 3.9a2", VERSION(3, 9)),
        3430: ("Python 3.10a1", VERSION(3, 10)),
        3431: ("Python 3.10a1", VERSION(3, 10)),
        3432: ("Python 3.10a2", VERSION(3, 10)),
        3433: ("Python 3.10a2", VERSION(3, 10)),
        3434: ("Python 3.10a6", VERSION(3, 10)),
        3435: ("Python 3.10a7", VERSION(3, 10)),
        3436: ("Python 3.10b1", VERSION(3, 10)),
        3437: ("Python 3.10b1", VERSION(3, 10)),
        3438: ("Python 3.10b1", VERSION(3, 10)),
        3439: ("Python 3.10b1", VERSION(3, 10)),
        3450: ("Python 3.11a1", VERSION(3, 11)),
        3451: ("Python 3.11a1", VERSION(3, 11)),
        3452: ("Python 3.11a1", VERSION(3, 11)),
        3453: ("Python 3.11a1", VERSION(3, 11)),
        3454: ("Python 3.11a1", VERSION(3, 11)),
        3455: ("Python 3.11a1", VERSION(3, 11)),
        3456: ("Python 3.11a1", VERSION(3, 11)),
        3457: ("Python 3.11a1", VERSION(3, 11)),
        3458: ("Python 3.11a1", VERSION(3, 11)),
        3459: ("Python 3.11a1", VERSION(3, 11)),
        3460: ("Python 3.11a1", VERSION(3, 11)),
        3461: ("Python 3.11a1", VERSION(3, 11)),
        3462: ("Python 3.11a2", VERSION(3, 11)),
        3463: ("Python 3.11a3", VERSION(3, 11)),
        3464: ("Python 3.11a3", VERSION(3, 11)),
        3465: ("Python 3.11a3", VERSION(3, 11)),
        3466: ("Python 3.11a4", VERSION(3, 11)),
        3467: ("Python 3.11a4", VERSION(3, 11)),
        3468: ("Python 3.11a4", VERSION(3, 11)),
        3469: ("Python 3.11a4", VERSION(3, 11)),
        3470: ("Python 3.11a4", VERSION(3, 11)),
        3471: ("Python 3.11a4", VERSION(3, 11)),
        3472: ("Python 3.11a4", VERSION(3, 11)),
        3473: ("Python 3.11a4", VERSION(3, 11)),
        3474: ("Python 3.11a4", VERSION(3, 11)),
        3475: ("Python 3.11a5", VERSION(3, 11)),
        3476: ("Python 3.11a5", VERSION(3, 11)),
        3477: ("Python 3.11a5", VERSION(3, 11)),
        3478: ("Python 3.11a5", VERSION(3, 11)),
        3479: ("Python 3.11a5", VERSION(3, 11)),
        3480: ("Python 3.11a5", VERSION(3, 11)),
        3481: ("Python 3.11a5", VERSION(3, 11)),
        3482: ("Python 3.11a5", VERSION(3, 11)),
        3483: ("Python 3.11a5", VERSION(3, 11)),
        3484: ("Python 3.11a5", VERSION(3, 11)),
        3485: ("Python 3.11a5", VERSION(3, 11)),
        3486: ("Python 3.11a6", VERSION(3, 11)),
        3487: ("Python 3.11a6", VERSION(3, 11)),
        3488: ("Python 3.11a6", VERSION(3, 11)),
        3489: ("Python 3.11a6", VERSION(3, 11)),
        3490: ("Python 3.11a6", VERSION(3, 11)),
        3491: ("Python 3.11a6", VERSION(3, 11)),
        3492: ("Python 3.11a7", VERSION(3, 11)),
        3493: ("Python 3.11a7", VERSION(3, 11)),
        3494: ("Python 3.11a7", VERSION(3, 11)),
        3500: ("Python 3.12a1", VERSION(3, 12)),
        3501: ("Python 3.12a1", VERSION(3, 12)),
        3502: ("Python 3.12a1", VERSION(3, 12)),
        3503: ("Python 3.12a1", VERSION(3, 12)),
        3504: ("Python 3.12a1", VERSION(3, 12)),
        3505: ("Python 3.12a1", VERSION(3, 12)),
        3506: ("Python 3.12a1", VERSION(3, 12)),
        3507: ("Python 3.12a1", VERSION(3, 12)),
        3508: ("Python 3.12a1", VERSION(3, 12)),
        3509: ("Python 3.12a1", VERSION(3, 12)),
        3510: ("Python 3.12a1", VERSION(3, 12)),
        3511: ("Python 3.12a1", VERSION(3, 12)),
    }

    # Dictionnary which associate the pyc signature (4-byte long string)
    # to a Python version string (eg. "m\xf2\r\n" => "2.4b1")
    STR_MAGIC = dict(
        (long2raw(magic | (ord('\r') << 16) |
                  (ord('\n') << 24), LITTLE_ENDIAN), value[0])
        for magic, value in MAGIC.items())

    def validate(self):
        magic_number = self["magic_number"].value
        if magic_number not in self.MAGIC:
            return "Unknown magic number (%s)" % magic_number
        if self["magic_string"].value != "\r\n":
            return r"Wrong magic string (\r\n)"

        if self["content/bytecode"].value != "c":
            return "First object bytecode is not code"
        return True

    def getVersion(self):
        if not hasattr(self, "version"):
            signature = self.stream.readBits(0, 16, self.endian)
            self.version = self.MAGIC[signature][1]
        return self.version

    def createFields(self):
        yield UInt16(self, "magic_number", "Magic number")
        yield String(self, "magic_string", 2, r"Magic string \r\n", charset="ASCII")

        version = self.getVersion()

        # PEP 552: Deterministic pycs #31650 (Python 3.7a4); magic=3392
        if version >= 0x30700A4:
            yield Bit(self, "use_hash", "Is hash based?")
            yield Bit(self, "checked")
            yield NullBits(self, "reserved", 30)
            use_hash = self['use_hash'].value
        else:
            use_hash = False

        if use_hash:
            yield UInt64(self, "hash", "SipHash hash of the source file")
        else:
            yield TimestampUnix32(self, "timestamp", "Timestamp modulo 2**32")
            if version >= 0x3030000 and self['magic_number'].value >= 3200:
                yield UInt32(self, "filesize", "Size of the Python source file (.py) modulo 2**32")

        yield Object(self, "content")
