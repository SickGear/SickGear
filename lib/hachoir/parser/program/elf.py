"""
ELF (Unix/BSD executable file format) parser.

Author: Victor Stinner, Robert Xiao
Creation date: 08 may 2006
Reference:
- System V Application Binary Interface - DRAFT - 10 June 2013
  http://www.sco.com/developers/gabi/latest/contents.html
"""

from hachoir.parser import HachoirParser
from hachoir.field import (RootSeekableFieldSet, FieldSet, Bit, NullBits, RawBits,
                           UInt8, UInt16, UInt32, UInt64, Enum,
                           String, RawBytes, Bytes)
from hachoir.core.text_handler import textHandler, hexadecimal
from hachoir.core.endian import LITTLE_ENDIAN, BIG_ENDIAN


class ElfHeader(FieldSet):
    MAGIC = b"\x7FELF"
    LITTLE_ENDIAN_ID = 1
    BIG_ENDIAN_ID = 2
    MACHINE_NAME = {
        # e_machine, EM_ defines
        0: "No machine",
        1: "AT&T WE 32100",
        2: "SPARC",
        3: "Intel 80386",
        4: "Motorola 68000",
        5: "Motorola 88000",
        6: "Intel 80486",
        7: "Intel 80860",
        8: "MIPS I Architecture",
        9: "Amdahl UTS on System/370",
        10: "MIPS RS3000 Little-endian",
        11: "IBM RS/6000 XXX reserved",
        15: "Hewlett-Packard PA-RISC",
        16: "NCube XXX reserved",
        17: "Fujitsu VPP500",
        18: "Enhanced instruction set SPARC",
        19: "Intel 80960",
        20: "PowerPC 32-bit",
        21: "PowerPC 64-bit",
        22: "IBM S390",
        36: "NEC V800",
        37: "Fujitsu FR20",
        38: "TRW RH-32",
        39: "Motorola RCE",
        40: "Advanced RISC Machines (ARM)",
        41: "DIGITAL Alpha",
        42: "Hitachi Super-H",
        43: "SPARC Version 9",
        44: "Siemens Tricore",
        45: "Argonaut RISC Core",
        46: "Hitachi H8/300",
        47: "Hitachi H8/300H",
        48: "Hitachi H8S",
        49: "Hitachi H8/500",
        50: "Intel Merced (IA-64) Processor",
        51: "Stanford MIPS-X",
        52: "Motorola Coldfire",
        53: "Motorola MC68HC12",
        62: "Advanced Micro Devices x86-64",
        75: "DIGITAL VAX",
        36902: "used by NetBSD/alpha; obsolete",
    }
    CLASS_NAME = {
        # e_ident[EI_CLASS], ELFCLASS defines
        1: "32 bits",
        2: "64 bits"
    }
    TYPE_NAME = {
        # e_type, ET_ defines
        0: "No file type",
        1: "Relocatable file",
        2: "Executable file",
        3: "Shared object file",
        4: "Core file",
        0xFF00: "Processor-specific (0xFF00)",
        0xFFFF: "Processor-specific (0xFFFF)",
    }
    OSABI_NAME = {
        # e_ident[EI_OSABI], ELFOSABI_ defines
        0: "UNIX System V ABI",
        1: "HP-UX operating system",
        2: "NetBSD",
        3: "GNU/Linux",
        4: "GNU/Hurd",
        5: "86Open common IA32 ABI",
        6: "Solaris",
        7: "Monterey",
        8: "IRIX",
        9: "FreeBSD",
        10: "TRU64 UNIX",
        11: "Novell Modesto",
        12: "OpenBSD",
        97: "ARM",
        255: "Standalone (embedded) application",
    }
    ENDIAN_NAME = {
        # e_ident[EI_DATA], ELFDATA defines
        LITTLE_ENDIAN_ID: "Little endian",
        BIG_ENDIAN_ID: "Big endian",
    }

    def createFields(self):
        yield Bytes(self, "signature", 4, r'ELF signature ("\x7fELF")')
        yield Enum(UInt8(self, "class", "Class"), self.CLASS_NAME)
        if self["class"].value == 1:
            ElfLongWord = UInt32
        else:
            ElfLongWord = UInt64
        yield Enum(UInt8(self, "endian", "Endian"), self.ENDIAN_NAME)
        yield UInt8(self, "file_version", "File version")
        yield Enum(UInt8(self, "osabi_ident", "OS/syscall ABI identification"), self.OSABI_NAME)
        yield UInt8(self, "abi_version", "syscall ABI version")
        yield String(self, "pad", 7, "Pad")

        yield Enum(UInt16(self, "type", "File type"), self.TYPE_NAME)
        yield Enum(UInt16(self, "machine", "Machine type"), self.MACHINE_NAME)
        yield UInt32(self, "version", "ELF format version")
        yield textHandler(ElfLongWord(self, "entry", "Entry point"), hexadecimal)
        yield ElfLongWord(self, "phoff", "Program header file offset")
        yield ElfLongWord(self, "shoff", "Section header file offset")
        yield UInt32(self, "flags", "Architecture-specific flags")
        yield UInt16(self, "ehsize", "Elf header size (this header)")
        yield UInt16(self, "phentsize", "Program header entry size")
        yield UInt16(self, "phnum", "Program header entry count")
        yield UInt16(self, "shentsize", "Section header entry size")
        yield UInt16(self, "shnum", "Section header entry count")
        yield UInt16(self, "shstrndx", "Section header string table index")

    def isValid(self):
        if self["signature"].value != self.MAGIC:
            return "Wrong ELF signature"
        if self["class"].value not in self.CLASS_NAME:
            return "Unknown class"
        if self["endian"].value not in self.ENDIAN_NAME:
            return "Unknown endian (%s)" % self["endian"].value
        return ""


class SectionFlags(FieldSet):

    def createFields(self):
        field_thunks = (
            lambda: Bit(self, "is_writable", "Section contains writable data?"),
            lambda: Bit(self, "is_alloc", "Section occupies memory?"),
            lambda: Bit(self, "is_exec", "Section contains executable instructions?"),
            lambda: NullBits(self, "reserved[]", 1),
            lambda: Bit(self, "is_merged", "Section might be merged to eliminate duplication?"),
            lambda: Bit(self, "is_strings", "Section contains nul terminated strings?"),
            lambda: Bit(self, "is_info_link", "sh_info field of this section header holds section header table index?"),
            lambda: Bit(self, "preserve_link_order", "Section requires special ordering for linker?"),
            lambda: Bit(self, "os_nonconforming", "Section rqeuires OS-specific processing?"),
            lambda: Bit(self, "is_group", "Section is a member of a section group?"),
            lambda: Bit(self, "is_tls", "Section contains TLS data?"),
            lambda: Bit(self, "is_compressed", "Section contains compressed data?"),
            lambda: NullBits(self, "reserved[]", 8),
            lambda: RawBits(self, "os_specific", 8, "OS specific flags"),
            lambda: RawBits(self, "processor_specific", 4, "Processor specific flags"),
        )

        if self.root.endian == BIG_ENDIAN:
            if self.root.is64bit:
                yield RawBits(self, "reserved[]", 32)
            for t in reversed(field_thunks):
                yield t()
        else:
            for t in field_thunks:
                yield t()
            if self.root.is64bit:
                yield RawBits(self, "reserved[]", 32)


class SymbolStringTableOffset(UInt32):

    def createDisplay(self):
        section_index = self['/header/shstrndx'].value
        section = self['/section[' + str(section_index) + ']']
        text = section.value[self.value:]
        text = text.decode('utf-8')
        return text.split('\0', 1)[0]


class SectionHeader32(FieldSet):
    static_size = 40 * 8
    TYPE_NAME = {
        # sh_type, SHT_ defines
        0: "Inactive",
        1: "Program defined information",
        2: "Symbol table section",
        3: "String table section",
        4: "Relocation section with addends",
        5: "Symbol hash table section",
        6: "Dynamic section",
        7: "Note section",
        8: "Block started by symbol (BSS) or No space section",
        9: "Relocation section without addends",
        10: "Reserved - purpose unknown",
        11: "Dynamic symbol table section",
    }

    def createFields(self):
        yield SymbolStringTableOffset(self, "name", "Section name (index into section header string table)")
        yield Enum(textHandler(UInt32(self, "type", "Section type"), hexadecimal), self.TYPE_NAME)
        yield SectionFlags(self, "flags", "Section flags")
        yield textHandler(UInt32(self, "VMA", "Virtual memory address"), hexadecimal)
        yield textHandler(UInt32(self, "LMA", "Logical memory address (offset in file)"), hexadecimal)
        yield textHandler(UInt32(self, "size", "Section size (bytes)"), hexadecimal)
        yield UInt32(self, "link", "Index of a related section")
        yield UInt32(self, "info", "Type-dependent information")
        yield UInt32(self, "addr_align", "Address alignment (bytes)")
        yield UInt32(self, "entry_size", "Size of each entry in section")

    def createDescription(self):
        return "Section header (name: %s, type: %s)" % \
            (self["name"].display, self["type"].display)


class SectionHeader64(SectionHeader32):
    static_size = 64 * 8

    def createFields(self):
        yield SymbolStringTableOffset(self, "name", "Section name (index into section header string table)")
        yield Enum(textHandler(UInt32(self, "type", "Section type"), hexadecimal), self.TYPE_NAME)
        yield SectionFlags(self, "flags", "Section flags")
        yield textHandler(UInt64(self, "VMA", "Virtual memory address"), hexadecimal)
        yield textHandler(UInt64(self, "LMA", "Logical memory address (offset in file)"), hexadecimal)
        yield textHandler(UInt64(self, "size", "Section size (bytes)"), hexadecimal)
        yield UInt32(self, "link", "Index of a related section")
        yield UInt32(self, "info", "Type-dependent information")
        yield UInt64(self, "addr_align", "Address alignment (bytes)")
        yield UInt64(self, "entry_size", "Size of each entry in section")


class ProgramFlags(FieldSet):
    static_size = 32
    FLAGS = (('pf_r', 'readable'), ('pf_w', 'writable'), ('pf_x', 'executable'))

    def createFields(self):
        if self.root.endian == BIG_ENDIAN:
            yield NullBits(self, "padding[]", 29)
            for fld, desc in self.FLAGS:
                yield Bit(self, fld, "Segment is " + desc)
        else:
            for fld, desc in reversed(self.FLAGS):
                yield Bit(self, fld, "Segment is " + desc)
            yield NullBits(self, "padding[]", 29)

    def createDescription(self):
        attribs = []
        for fld, desc in self.FLAGS:
            if self[fld].value:
                attribs.append(desc)
        return 'Segment is ' + ', '.join(attribs)


class ProgramHeader32(FieldSet):
    TYPE_NAME = {
        # p_type, PT_ defines
        0: "Unused program header table entry",
        1: "Loadable program segment",
        2: "Dynamic linking information",
        3: "Program interpreter",
        4: "Auxiliary information",
        5: "Reserved, unspecified semantics",
        6: "Entry for header table itself",
        7: "Thread Local Storage segment",
        0x70000000: "MIPS_REGINFO",
    }
    static_size = 32 * 8

    def createFields(self):
        yield Enum(UInt32(self, "type", "Segment type"), ProgramHeader32.TYPE_NAME)
        yield UInt32(self, "offset", "Offset")
        yield textHandler(UInt32(self, "vaddr", "V. address"), hexadecimal)
        yield textHandler(UInt32(self, "paddr", "P. address"), hexadecimal)
        yield UInt32(self, "file_size", "File size")
        yield UInt32(self, "mem_size", "Memory size")
        yield ProgramFlags(self, "flags")
        yield UInt32(self, "align", "Alignment padding")

    def createDescription(self):
        return "Program Header (%s)" % self["type"].display


class ProgramHeader64(ProgramHeader32):
    static_size = 56 * 8

    def createFields(self):
        yield Enum(UInt32(self, "type", "Segment type"), ProgramHeader32.TYPE_NAME)
        yield ProgramFlags(self, "flags")
        yield UInt64(self, "offset", "Offset")
        yield textHandler(UInt64(self, "vaddr", "V. address"), hexadecimal)
        yield textHandler(UInt64(self, "paddr", "P. address"), hexadecimal)
        yield UInt64(self, "file_size", "File size")
        yield UInt64(self, "mem_size", "Memory size")
        yield UInt64(self, "align", "Alignment padding")


class ElfFile(HachoirParser, RootSeekableFieldSet):
    PARSER_TAGS = {
        "id": "elf",
        "category": "program",
        "file_ext": ("so", ""),
        "min_size": 52 * 8,  # At least one program header
        "mime": (
            "application/x-executable",
            "application/x-object",
            "application/x-sharedlib",
            "application/x-executable-file",
            "application/x-coredump"),
        "magic": ((ElfHeader.MAGIC, 0),),
        "description": "ELF Unix/BSD program/library"
    }
    endian = LITTLE_ENDIAN

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(
            self, None, "root", stream, None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        if self.stream.readBytes(0, len(ElfHeader.MAGIC)) != ElfHeader.MAGIC:
            return "Invalid magic"
        err = self["header"].isValid()
        if err:
            return err
        return True

    def createFields(self):
        # Choose the right endian depending on endian specified in header
        if self.stream.readBits(5 * 8, 8, BIG_ENDIAN) == ElfHeader.BIG_ENDIAN_ID:
            self.endian = BIG_ENDIAN
        else:
            self.endian = LITTLE_ENDIAN

        # Parse header and program headers
        yield ElfHeader(self, "header", "Header")
        self.is64bit = (self["header/class"].value == 2)

        for index in range(self["header/phnum"].value):
            if self.is64bit:
                yield ProgramHeader64(self, "prg_header[]")
            else:
                yield ProgramHeader32(self, "prg_header[]")

        self.seekByte(self["header/shoff"].value, relative=False)

        for index in range(self["header/shnum"].value):
            if self.is64bit:
                yield SectionHeader64(self, "section_header[]")
            else:
                yield SectionHeader32(self, "section_header[]")

        for index in range(self["header/shnum"].value):
            field = self["section_header[" + str(index) + "]"]
            if field['size'].value != 0 and field['type'].value != 8:
                # skip NOBITS sections
                self.seekByte(field['LMA'].value, relative=False)
                yield RawBytes(self, "section[" + str(index) + "]", field['size'].value)

    def createDescription(self):
        return "ELF Unix/BSD program/library: %s" % (
            self["header/class"].display)
