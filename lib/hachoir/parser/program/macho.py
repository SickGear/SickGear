"""
Mach-O (Mac OS X executable file format) parser.

Resources:
- https://lowlevelbits.org/parsing-mach-o-files/
- OS X ABI Mach-O File Format Reference
  (mirrored at https://github.com/aidansteele/osx-abi-macho-file-format-reference)
- https://llvm.org/svn/llvm-project/llvm/trunk/include/llvm/BinaryFormat/

Author: Robert Xiao
Creation date: February 11, 2015
Updated: January 13, 2017
"""

from hachoir.parser import HachoirParser
from hachoir.field import (RootSeekableFieldSet, FieldSet,
                           Bit, NullBits, String, CString,
                           RawBytes, Bytes, PaddingBytes,
                           Int32, UInt32, UInt64, Enum)
from hachoir.core.text_handler import textHandler, hexadecimal
from hachoir.core.endian import LITTLE_ENDIAN, BIG_ENDIAN
from hachoir.core.bits import str2hex


CPU_ARCH_ABI64 = 0x01000000
CPU_TYPE = {
    -1: 'Any',
    1: 'VAX',
    6: 'MC680x0',
    7: 'i386',
    7 | CPU_ARCH_ABI64: 'x86_64',
    8: 'MIPS',
    10: 'MC98000',
    11: 'HPPA',
    12: 'ARM',
    12 | CPU_ARCH_ABI64: 'ARM64',
    13: 'MC88000',
    14: 'SPARC',
    15: 'I860',
    16: 'Alpha',
    18: 'PowerPC',
    18 | CPU_ARCH_ABI64: 'PowerPC64',
}

FILE_TYPE = {
    1: 'Relocatable object',
    2: 'Demand-paged executable',
    3: 'Fixed VM shared library',
    4: 'Core file',
    5: 'Preloaded executable',
    6: 'Dynamically bound shared library',
    7: 'Dynamic link editor',
    8: 'Dynamically bound bundle',
    9: 'Shared library stub for static linking only',
    10: 'Companion file with only debug sections',
    11: 'x86_64 kext',
}

MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce": (0, BIG_ENDIAN),  # 32-bit big endian
    b"\xce\xfa\xed\xfe": (0, LITTLE_ENDIAN),  # 32-bit little endian
    b"\xfe\xed\xfa\xcf": (1, BIG_ENDIAN),  # 64-bit big endian
    b"\xcf\xfa\xed\xfe": (1, LITTLE_ENDIAN),  # 64-bit little endian
}


class MachoHeader(FieldSet):

    FLAGS = [
        'NOUNDEFS', 'INCRLINK', 'DYLDLINK', 'BINDATLOAD',
        'PREBOUND', 'SPLIT_SEGS', 'LAZY_INIT', 'TWOLEVEL',
        'FORCE_FLAT', 'NOMULTIDEFS', 'NOFIXPREBINDING', 'PREBINDABLE',
        'ALLMODSBOUND', 'SUBSECTIONS_VIA_SYMBOLS', 'CANONICAL', 'WEAK_DEFINES',
        'BINDS_TO_WEAK', 'ALLOW_STACK_EXECUTION', 'ROOT_SAFE', 'SETUID_SAFE',
        'NO_REEXPORTED_DYLIBS', 'PIE', 'DEAD_STRIPPABLE_DYLIB', 'HAS_TLV_DESCRIPTORS',
        'NO_HEAP_EXECUTION',
    ]

    def createFields(self):
        yield Bytes(self, "magic", 4, "Mach-O signature")
        yield Enum(Int32(self, "cputype"), CPU_TYPE)
        yield Int32(self, "cpusubtype")
        yield Enum(UInt32(self, "filetype"), FILE_TYPE)
        yield UInt32(self, "ncmds", "Number of load commands")
        yield UInt32(self, "sizeofcmds", "Total size of all load commands")

        if self.endian == BIG_ENDIAN:
            yield NullBits(self, "flags_reserved", 32 - len(self.FLAGS))
            for flag in self.FLAGS[::-1]:
                yield Bit(self, "flags_" + flag.lower())
        else:
            for flag in self.FLAGS:
                yield Bit(self, "flags_" + flag.lower())
            yield NullBits(self, "flags_reserved", 32 - len(self.FLAGS))

        if self.parent.is64bit:
            yield UInt32(self, "reserved")

    def createDescription(self):
        return "%s %s, %d load commands, <%s>" % (
            self['cputype'].display, self['filetype'].display,
            self['ncmds'].value,
            '|'.join(f for f in self.FLAGS if self['flags_' + f.lower()].value))


class UuidCommand(FieldSet):
    static_size = 16 * 8

    def createFields(self):
        yield RawBytes(self, "uuid", 16)

    def createValue(self):
        return self['uuid'].value

    def createDisplay(self):
        text = str2hex(self['uuid'].value, format=r"%02x")
        return "%s-%s-%s-%s-%s" % (
            text[:8], text[8:12], text[12:16], text[16:20], text[20:])

    def createDescription(self):
        return "UUID for corresponding dSYM file"


class SegmentCommand(FieldSet):

    def createFields(self):
        yield String(self, "segname", 16, strip="\0")
        yield textHandler(UInt32(self, "vmaddr"), hexadecimal)
        yield textHandler(UInt32(self, "vmsize"), hexadecimal)
        yield textHandler(UInt32(self, "fileoff"), hexadecimal)
        yield textHandler(UInt32(self, "filesize"), hexadecimal)
        yield UInt32(self, "maxprot")
        yield UInt32(self, "initprot")
        yield UInt32(self, "nsects")
        yield UInt32(self, "flags")
        for i in range(self['nsects'].value):
            yield MachoSection(self, "section[]")

    def createValue(self):
        return self['segname'].value

    def createDescription(self):
        return "Load segment %s" % (self['segname'].value)


class SegmentCommand64(FieldSet):

    def createFields(self):
        yield String(self, "segname", 16, strip="\0")
        yield textHandler(UInt64(self, "vmaddr"), hexadecimal)
        yield textHandler(UInt64(self, "vmsize"), hexadecimal)
        yield textHandler(UInt64(self, "fileoff"), hexadecimal)
        yield textHandler(UInt64(self, "filesize"), hexadecimal)
        yield UInt32(self, "maxprot")
        yield UInt32(self, "initprot")
        yield UInt32(self, "nsects")
        yield UInt32(self, "flags")
        for i in range(self['nsects'].value):
            yield MachoSection64(self, "section[]")

    def createValue(self):
        return self['segname'].value

    def createDescription(self):
        return "Load segment %s" % (self['segname'].value)


class SymtabCommand(FieldSet):
    def createFields(self):
        yield UInt32(self, "symoff")
        yield UInt32(self, "nsyms")
        yield UInt32(self, "stroff")
        yield UInt32(self, "strsize")


class SymsegCommand(FieldSet):
    def createFields(self):
        yield UInt32(self, "offset")
        yield UInt32(self, "size")


class DysymtabCommand(FieldSet):
    def createFields(self):
        yield UInt32(self, "ilocalsym")
        yield UInt32(self, "nlocalsym")
        yield UInt32(self, "iextdefsym")
        yield UInt32(self, "nextdefsym")
        yield UInt32(self, "iundefsym")
        yield UInt32(self, "nundefsym")
        yield UInt32(self, "tocoff")
        yield UInt32(self, "ntoc")
        yield UInt32(self, "modtaboff")
        yield UInt32(self, "nmodtab")
        yield UInt32(self, "extrefsymoff")
        yield UInt32(self, "nextrefsyms")
        yield UInt32(self, "indirectsymoff")
        yield UInt32(self, "nindirectsyms")
        yield UInt32(self, "extreloff")
        yield UInt32(self, "nextrel")
        yield UInt32(self, "locreloff")
        yield UInt32(self, "nlocrel")


class DylinkerCommand(FieldSet):
    def createFields(self):
        yield UInt32(self, "offset")
        yield CString(self, "name")

    def createValue(self):
        return self['name'].value


class VersionMinCommand(FieldSet):
    def createFields(self):
        yield UInt32(self, "version")
        yield UInt32(self, "sdk")

    def createDisplay(self):
        version = self['version'].value
        sdk = self['sdk'].value
        return "%d.%d.%d sdk %d.%d.%d" % (
            version >> 16, (version >> 8) & 0xff, version & 0xff,
            sdk >> 16, (sdk >> 8) & 0xff, sdk & 0xff)


class DyldInfoCommand(FieldSet):
    def createFields(self):
        yield UInt32(self, "rebase_off")
        yield UInt32(self, "rebase_size")
        yield UInt32(self, "bind_off")
        yield UInt32(self, "bind_size")
        yield UInt32(self, "weak_bind_off")
        yield UInt32(self, "weak_bind_size")
        yield UInt32(self, "lazy_bind_off")
        yield UInt32(self, "lazy_bind_size")
        yield UInt32(self, "export_off")
        yield UInt32(self, "export_size")


class DylibCommand(FieldSet):
    def createFields(self):
        yield UInt32(self, "offset")
        yield UInt32(self, "timestamp")
        yield UInt32(self, "current_version")
        yield UInt32(self, "compatibility_version")
        yield CString(self, "name")

    def createValue(self):
        return self['name'].value


class MachoSection(FieldSet):
    def createFields(self):
        yield String(self, "sectname", 16, strip="\0")
        yield String(self, "segname", 16, strip="\0")
        yield textHandler(UInt32(self, "addr"), hexadecimal)
        yield textHandler(UInt32(self, "size"), hexadecimal)
        yield textHandler(UInt32(self, "offset"), hexadecimal)
        yield textHandler(UInt32(self, "align"), hexadecimal)
        yield textHandler(UInt32(self, "reloff"), hexadecimal)
        yield UInt32(self, "nreloc")
        yield UInt32(self, "flags")
        yield UInt32(self, "reserved1")
        yield UInt32(self, "reserved2")

    def createValue(self):
        return self['segname'].value + ',' + self['sectname'].value

    def createDescription(self):
        return "Section %s,%s" % (self['segname'].value, self['sectname'].value)


class MachoSection64(FieldSet):

    def createFields(self):
        yield String(self, "sectname", 16, strip="\0")
        yield String(self, "segname", 16, strip="\0")
        yield textHandler(UInt64(self, "addr"), hexadecimal)
        yield textHandler(UInt64(self, "size"), hexadecimal)
        yield textHandler(UInt32(self, "offset"), hexadecimal)
        yield textHandler(UInt32(self, "align"), hexadecimal)
        yield textHandler(UInt32(self, "reloff"), hexadecimal)
        yield UInt32(self, "nreloc")
        yield UInt32(self, "flags")
        yield UInt32(self, "reserved1")
        yield UInt32(self, "reserved2")
        yield RawBytes(self, "padding", 4)

    def createValue(self):
        return self['segname'].value + ',' + self['sectname'].value

    def createDescription(self):
        return "Section %s,%s" % (self['segname'].value, self['sectname'].value)


class MachoLoadCommand(FieldSet):
    LC_REQ_DYLD = 0x80000000

    LC_SEGMENT = 0x1
    LC_SYMTAB = 0x2
    LC_SYMSEG = 0x3
    LC_THREAD = 0x4
    LC_UNIXTHREAD = 0x5
    LC_LOADFVMLIB = 0x6
    LC_IDFVMLIB = 0x7
    LC_IDENT = 0x8
    LC_FVMFILE = 0x9
    LC_PREPAGE = 0xa
    LC_DYSYMTAB = 0xb
    LC_LOAD_DYLIB = 0xc
    LC_ID_DYLIB = 0xd
    LC_LOAD_DYLINKER = 0xe
    LC_ID_DYLINKER = 0xf
    LC_PREBOUND_DYLIB = 0x10
    LC_ROUTINES = 0x11
    LC_SUB_FRAMEWORK = 0x12
    LC_SUB_UMBRELLA = 0x13
    LC_SUB_CLIENT = 0x14
    LC_SUB_LIBRARY = 0x15
    LC_TWOLEVEL_HINTS = 0x16
    LC_PREBIND_CKSUM = 0x17
    LC_LOAD_WEAK_DYLIB = 0x18 | LC_REQ_DYLD
    LC_SEGMENT_64 = 0x19
    LC_ROUTINES_64 = 0x1a
    LC_UUID = 0x1b
    LC_RPATH = 0x1c | LC_REQ_DYLD
    LC_CODE_SIGNATURE = 0x1d
    LC_SEGMENT_SPLIT_INFO = 0x1e
    LC_REEXPORT_DYLIB = 0x1f | LC_REQ_DYLD
    LC_LAZY_LOAD_DYLIB = 0x20
    LC_ENCRYPTION_INFO = 0x21
    LC_DYLD_INFO = 0x22
    LC_DYLD_INFO_ONLY = 0x22 | LC_REQ_DYLD
    LC_LOAD_UPWARD_DYLIB = 0x23 | LC_REQ_DYLD
    LC_VERSION_MIN_MACOSX = 0x24
    LC_VERSION_MIN_IPHONEOS = 0x25
    LC_FUNCTION_STARTS = 0x26
    LC_DYLD_ENVIRONMENT = 0x27
    LC_MAIN = 0x28 | LC_REQ_DYLD
    LC_DATA_IN_CODE = 0x29
    LC_SOURCE_VERSION = 0x2a
    LC_DYLIB_CODE_SIGN_DRS = 0x2b
    LC_ENCRYPTION_INFO_64 = 0x2c
    LC_LINKER_OPTION = 0x2d
    LC_LINKER_OPTIMIZATION_HINT = 0x2e
    LC_VERSION_MIN_TVOS = 0x2f
    LC_VERSION_MIN_WATCHOS = 0x30
    LC_NOTE = 0x31
    LC_BUILD_VERSION = 0x32

    LOAD_COMMANDS = {
        LC_SEGMENT: ("Segment", SegmentCommand),
        LC_SYMTAB: ("Symbol table", SymtabCommand),
        LC_SYMSEG: ("Symbol segment", SymsegCommand),
        LC_THREAD: ("Thread", None),
        LC_UNIXTHREAD: ("UNIX thread", None),
        LC_LOADFVMLIB: ("Load fixed VM library", None),
        LC_IDFVMLIB: ("Fixed VM library identification", None),
        LC_IDENT: ("Object identification", None),
        LC_FVMFILE: ("Fixed VM file inclusion", None),
        LC_PREPAGE: ("Prepage", None),
        LC_DYSYMTAB: ("Dynamic symbol table", DysymtabCommand),
        LC_LOAD_DYLIB: ("Load dynamic library", DylibCommand),
        LC_ID_DYLIB: ("Dynamic library identification", None),
        LC_LOAD_DYLINKER: ("Load dynamic linker", DylinkerCommand),
        LC_ID_DYLINKER: ("Dynamic linker identification", None),
        LC_PREBOUND_DYLIB: ("Prebound modules", None),
        LC_ROUTINES: ("Image routines", None),
        LC_SUB_FRAMEWORK: ("Sub-framework", None),
        LC_SUB_UMBRELLA: ("Sub-umbrella", None),
        LC_SUB_CLIENT: ("Sub-client", None),
        LC_SUB_LIBRARY: ("Sub-library", None),
        LC_TWOLEVEL_HINTS: ("Two-level lookup hints", None),
        LC_PREBIND_CKSUM: ("Prebind checksum", None),

        LC_LOAD_WEAK_DYLIB: ("Load dynamic library weakly", None),
        LC_SEGMENT_64: ("64-bit segment", SegmentCommand64),
        LC_ROUTINES_64: ("64-bit image routines", None),
        LC_UUID: ("UUID", UuidCommand),
        LC_RPATH: ("Runpath additions", None),
        LC_CODE_SIGNATURE: ("Code signature", None),
        LC_SEGMENT_SPLIT_INFO: ("Segment split info", None),
        LC_REEXPORT_DYLIB: ("Load and re-export dylib", None),
        LC_LAZY_LOAD_DYLIB: ("Lazy load dynamic library", None),
        LC_ENCRYPTION_INFO: ("Encrypted segment information", None),
        LC_DYLD_INFO: ("Compressed dyld info", DyldInfoCommand),
        LC_DYLD_INFO_ONLY: ("Compressed dyld info", DyldInfoCommand),
        LC_LOAD_UPWARD_DYLIB: ("Load upward dylib", None),
        LC_VERSION_MIN_MACOSX: ("Minimum macOS version", VersionMinCommand),
        LC_VERSION_MIN_IPHONEOS: ("Minimum iOS version", VersionMinCommand),
        LC_FUNCTION_STARTS: ("Compressed function start address table", None),
        LC_DYLD_ENVIRONMENT: ("dyld environment variables", None),
        LC_MAIN: ("Main thread info", None),
        LC_DATA_IN_CODE: ("Table of non-instructions in text segment", None),
        LC_SOURCE_VERSION: ("Source code version info", None),
        LC_DYLIB_CODE_SIGN_DRS: ("Code signing info from linked dylibs", None),
    }
    LOAD_COMMANDS_DISPLAY = {k: v[0] for k, v in LOAD_COMMANDS.items()}

    def createFields(self):
        yield Enum(UInt32(self, "cmd"), self.LOAD_COMMANDS_DISPLAY)
        yield UInt32(self, "cmdsize")
        self._size = self['cmdsize'].value * 8
        desc, parser = self.LOAD_COMMANDS.get(self['cmd'].value, ("", None))
        if parser:
            yield parser(self, "data")
            # data is word aligned
            padding_length = self['cmdsize'].value - self.current_size // 8
            if padding_length:
                yield PaddingBytes(self, "padding", padding_length)
        else:
            yield RawBytes(self, "data",
                           self['cmdsize'].value - self.current_size // 8)

    def createValue(self):
        return self['cmd'].value

    def createDisplay(self):
        return self['cmd'].display + ': ' + self['data'].display

    def createDescription(self):
        return self['data'].description


class MachoFileBase(RootSeekableFieldSet):

    def createFields(self):
        baseaddr = self.absolute_address
        # Choose size and endianness based on magic
        magic = self.stream.readBytes(baseaddr, 4)
        self.is64bit, self.endian = MACHO_MAGICS[magic]

        yield MachoHeader(self, "header")
        for i in range(self['header/ncmds'].value):
            yield MachoLoadCommand(self, "load_command[]")

    def createDescription(self):
        return "Mach-O program/library: %s" % (self["header/cputype"].display)


class MachoFile(HachoirParser, MachoFileBase):
    PARSER_TAGS = {
        "id": "macho",
        "category": "program",
        "file_ext": ("dylib", "bundle", "o", ""),
        "min_size": (28 + 56) * 8,  # Header + one segment load command
        "mime": (
            "application/x-executable",
            "application/x-object",
            "application/x-sharedlib",
            "application/x-executable-file",
            "application/x-coredump"),
        "magic": tuple((m, 0) for m in MACHO_MAGICS),
        "description": "Mach-O program/library"
    }
    endian = BIG_ENDIAN

    def __init__(self, stream, **args):
        MachoFileBase.__init__(self, None, "root", stream,
                               None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        if self.stream.readBytes(0, 4) not in MACHO_MAGICS:
            return "Invalid magic"
        return True


class MachoFatArch(FieldSet):

    def createFields(self):
        yield Enum(Int32(self, "cputype"), CPU_TYPE)
        yield Int32(self, "cpusubtype")
        yield textHandler(UInt32(self, "offset"), hexadecimal)
        yield UInt32(self, "size")
        yield UInt32(self, "align")
        self['align'].createDescription = lambda: str(1 << self['align'].value)


class MachoFatHeader(FieldSet):

    def createFields(self):
        yield Bytes(self, "magic", 4, "Mach-O signature")
        yield UInt32(self, "nfat_arch", "Number of architectures in this fat file")
        for i in range(self['nfat_arch'].value):
            yield MachoFatArch(self, 'arch[]')


class MachoFatFile(HachoirParser, RootSeekableFieldSet):
    MAGIC_BE = b"\xca\xfe\xba\xbe"
    MAGIC_LE = b"\xbe\xba\xfe\xca"

    PARSER_TAGS = {
        "id": "macho_fat",
        "category": "program",
        "file_ext": ("dylib", "bundle", ""),
        # One page + size for one arch
        "min_size": 4096 * 8 + MachoFile.PARSER_TAGS['min_size'],
        "mime": (
            "application/x-executable",
            "application/x-object",
            "application/x-sharedlib",
            "application/x-executable-file",
            "application/x-coredump"),
        "magic": ((MAGIC_LE, 0), (MAGIC_BE, 0)),
        "description": "Mach-O fat program/library"
    }
    endian = BIG_ENDIAN

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(
            self, None, "root", stream, None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        if self.stream.readBytes(0, 4) not in (self.MAGIC_LE, self.MAGIC_BE):
            return "Invalid magic"
        if self['header/nfat_arch'].value >= 16:
            # This helps to distinguish mach-o from java.
            return "Too many architectures"
        return True

    def createFields(self):
        # Choose the right endian based on file magic
        if self.stream.readBytes(0, 4) == self.MAGIC_LE:
            self.endian = LITTLE_ENDIAN
        else:
            self.endian = BIG_ENDIAN

        # Parse header and program headers
        yield MachoFatHeader(self, "header", "Header")
        for arch in self['header'].array('arch'):
            self.seekByte(arch['offset'].value)
            yield MachoFileBase(self, 'file[]', self.stream, None, arch['size'].value * 8)
