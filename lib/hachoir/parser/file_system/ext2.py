"""
EXT2 (Linux) file system parser.

Author: Victor Stinner

Sources:
- EXT2FS source code
  http://ext2fsd.sourceforge.net/
- Analysis of the Ext2fs structure
  http://www.nondot.org/sabre/os/files/FileSystems/ext2fs/
- Ext4 Disk Layout
  https://ext4.wiki.kernel.org/index.php/Ext4_Disk_Layout
"""

from hachoir.parser import HachoirParser, Parser
from hachoir.field import (RootSeekableFieldSet, SeekableFieldSet, FieldSet, ParserError,
                           Bit, Bits, UInt8, UInt16, UInt32,
                           Enum, String, TimestampUnix32, RawBytes,
                           NullBytes, PaddingBits, PaddingBytes, FragmentGroup, CustomFragment)
from hachoir.core.tools import (humanDuration, humanFilesize)
from hachoir.core.endian import LITTLE_ENDIAN
from hachoir.core.text_handler import textHandler
from .linux_swap import UUID


class DirectoryEntry(FieldSet):
    file_type = {
        1: "Regular",
        2: "Directory",
        3: "Char. dev.",
        4: "Block dev.",
        5: "Fifo",
        6: "Socket",
        7: "Symlink",
        8: "Max"
    }

    def __init__(self, *args):
        FieldSet.__init__(self, *args)
        self._size = self["rec_len"].value * 8

    def createFields(self):
        yield UInt32(self, "inode", "Inode")
        yield UInt16(self, "rec_len", "Record length")
        yield UInt8(self, "name_len", "Name length")
        yield Enum(UInt8(self, "file_type", "File type"), self.file_type)
        if self["name_len"].value > 0:
            yield String(self, "name", self["name_len"].value, "File name")
        size = (self._size - self.current_size) // 8
        if size:
            yield NullBytes(self, "padding", size)

    def createDescription(self):
        name = None
        if self["name_len"].value > 0:
            name = self["name"].value.strip("\0")
        if name:
            return "Directory entry: %s" % name
        else:
            return "Directory entry (empty)"


class Flags(FieldSet):

    def createValue(self):
        return self.stream.readBits(self.absolute_address, self.size, self.parent.endian)

    def createDisplay(self):
        out = [
            field.name for field in self if field.value and isinstance(field, Bit)]
        return '{' + ', '.join(out) + '}'


class FileMode(Flags):
    static_size = 16

    file_type = {
        1: "Fifo",
        2: "Character device",
        4: "Directory",
        6: "Block device",
        8: "Regular",
        10: "Symbolic link",
        12: "Socket",
    }
    file_type_letter = {
        1: "p",
        2: "c",
        4: "d",
        6: "b",
        10: "l",
        12: "s",
    }

    def createFields(self):
        yield Bit(self, "other_exec")
        yield Bit(self, "other_write")
        yield Bit(self, "other_read")
        yield Bit(self, "group_exec")
        yield Bit(self, "group_write")
        yield Bit(self, "group_read")
        yield Bit(self, "owner_exec")
        yield Bit(self, "owner_write")
        yield Bit(self, "owner_read")
        yield Bit(self, "sticky")
        yield Bit(self, "setgid")
        yield Bit(self, "setuid")
        yield Enum(Bits(self, "file_type", 4), self.file_type)

    def createDisplay(self):
        names = (
            ("owner_read", "owner_write", "owner_exec"),
            ("group_read", "group_write", "group_exec"),
            ("other_read", "other_write", "other_exec"))
        letters = "rwx"
        mode = ["-" for index in range(10)]
        index = 1
        for loop in range(3):
            for name, letter in zip(names[loop], letters):
                if self[name].value:
                    mode[index] = letter
                index += 1
        if self['sticky'].value:
            mode[9] = 'Tt'[self['other_exec'].value]
        if self['setgid'].value:
            mode[6] = 'Ss'[self['group_exec'].value]
        if self['setuid'].value:
            mode[3] = 'Ss'[self['owner_exec'].value]

        file_type = self["file_type"].value
        if file_type in self.file_type_letter:
            mode[0] = self.file_type_letter[file_type]
        return "".join(mode)


class InodeFlags(Flags):
    static_size = 32

    def createFields(self):
        yield Bit(self, "secrm", "This file requires secure deletion (not implemented)")
        yield Bit(self, "unrm", "This file should be preserved, should undeletion be desired (not implemented)")
        yield Bit(self, "compr", "File is compressed (not really implemented)")
        yield Bit(self, "sync", "All writes to the file must be synchronous")
        yield Bit(self, "immutable", "File is immutable")
        yield Bit(self, "append", "File can only be appended")
        yield Bit(self, "nodump", "The dump(1) utility should not dump this file")
        yield Bit(self, "noatime", "Do not update access time")
        yield Bit(self, "dirty", "Dirty compressed file (not used)")
        yield Bit(self, "comprblk", "File has one or more compressed clusters (not used)")
        yield Bit(self, "nocompr", "Do not compress file (not used)")
        yield Bit(self, "encrypt", "Encrypted inode")
        yield Bit(self, "index", "Directory has hashed indexes")
        yield Bit(self, "imagic", "AFS magic directory")
        yield Bit(self, "journal_data", "File data must always be written through the journal")
        yield Bit(self, "notail", "File tail should not be merged (not used by ext4)")
        yield Bit(self, "dirsync", "All directory entry data should be written synchronously")
        yield Bit(self, "topdir", "Top of directory hierarchy")
        yield Bit(self, "huge_file", "This is a huge file")
        yield Bit(self, "extents", "Inode uses extents")
        yield Bit(self, "reserved[]")
        yield Bit(self, "ea_inode", "Inode used for a large extended attribute")
        yield Bit(self, "eofblocks", "This file has blocks allocated past EOF (deprecated)")
        yield Bit(self, "reserved[]")
        yield Bit(self, "snapfile", "Inode is a snapshot (not in mainline)")
        yield Bit(self, "reserved[]")
        yield Bit(self, "snapfile_deleted", "Snapshot is being deleted (not in mainline)")
        yield Bit(self, "snapfile_shrunk", "Snapshot shrink has completed (not in mainline)")
        yield Bit(self, "inline_data", "Inode has inline data")
        yield Bit(self, "projinherit", "Create with parents projid")
        yield Bit(self, "reserved[]")
        yield Bit(self, "reserved[]", "Reserved for ext4 library")


class ExtentNode(FieldSet):

    def __init__(self, parent, name, size=None):
        FieldSet.__init__(self, parent, name, size=size)

    def createFields(self):
        yield UInt16(self, "magic")
        yield UInt16(self, "cur_entries")
        yield UInt16(self, "max_entries")
        yield UInt16(self, "tree_depth")
        yield UInt32(self, "tree_generation")

        for i in range(self['cur_entries'].value):
            yield UInt32(self, "logical_block[]")
            yield UInt16(self, "extent_length[]")
            yield UInt16(self, "physical_block_upper[]")
            yield UInt32(self, "physical_block_lower[]")


class Inode(FieldSet):
    inode_type_name = {
        1: "list of bad blocks",
        2: "Root directory",
        3: "User quota inode",
        4: "Group quota inode",
        5: "Boot loader",
        6: "Undelete directory",
        7: "Reserved group descriptors",
        8: "EXT3 journal"
    }
    static_size = (68 + 15 * 4) * 8

    def __init__(self, parent, name, index):
        FieldSet.__init__(self, parent, name, None)
        self.uniq_id = 1 + index

    def createDescription(self):
        desc = "Inode %s: " % self.uniq_id
        size = self["size"].value + (self['size_high'].value << 32)
        size = humanFilesize(size)
        if self["links_count"].value == 0:
            desc += "(unused)"
        elif 11 <= self.uniq_id:
            desc += "%s, size=%s, mode=%s" % (self.describe_file(),
                                              size, self['mode'].display)
        elif self.uniq_id in self.inode_type_name:
            desc += self.inode_type_name[self.uniq_id]
            if self.uniq_id == 2:
                desc += ", size=%s, mode=%s" % (size, self['mode'].display)
        else:
            desc += "special"
        return desc

    def describe_file(self):
        filetype = FileMode.file_type_letter.get(
            self['mode/file_type'].value, '-')
        out = self["mode/file_type"].display
        if filetype in 'pds-':
            return out
        elif filetype in 'bc':
            # block/char device
            return out + ' (%d,%d)' % (self['dev_major'].value, self['dev_minor'].value)
        elif filetype == 'l':
            # symlink
            if self['size'].value <= 60:
                return out + ' (-> %s)' % (self['link_target'].value)
        return out

    def is_fast_symlink(self):
        acl_addr = self.absolute_address + self.current_size
        # skip 15 blocks + version field
        acl_addr += (4 * 15 + 4) * 8
        acl = self.stream.readBits(acl_addr, 32, self.endian)

        b = 0
        if acl > 0:
            b = (2 << self["/superblock/log_block_size"].value)

        return (self['blocks'].value - b == 0)

    def createFields(self):
        os = self["/superblock/creator_os"].value

        yield FileMode(self, "mode", "File mode")
        yield UInt16(self, "uid", "User ID")
        yield UInt32(self, "size", "File size (in bytes)")
        yield TimestampUnix32(self, "atime", "Last access time")
        yield TimestampUnix32(self, "ctime", "Last inode change time")
        yield TimestampUnix32(self, "mtime", "Last data modification time")
        yield TimestampUnix32(self, "dtime", "Deletion time")
        yield UInt16(self, "gid", "Group ID")
        yield UInt16(self, "links_count", "Hard link count")
        yield UInt32(self, "blocks", "Number of blocks")
        yield InodeFlags(self, "flags", "Flags")
        if os == SuperBlock.OS_LINUX:
            yield UInt32(self, "version_high", "High 32 bits of the version field")
        else:
            yield NullBytes(self, "reserved[]", 4, "Reserved")

        filetype = FileMode.file_type_letter.get(
            self['mode/file_type'].value, '-')
        if filetype in 'bc':
            yield UInt8(self, "dev_minor", "Minor number of the block/char device")
            yield UInt8(self, "dev_major", "Major number of the block/char device")
            yield NullBytes(self, "block_unused", 58)
        elif filetype == 'l' and self.is_fast_symlink():
            yield String(self, "link_target", self['size'].value, "Target filename of this symlink")
            rest = 60 - self['size'].value
            if rest:
                yield NullBytes(self, "block_unused", rest)
        elif self['flags/extents'].value:
            yield ExtentNode(self, "extent_root", size=60 * 8)
        else:
            for index in range(15):
                yield UInt32(self, "block[]")

        yield UInt32(self, "version", "File version, for NFS")
        yield UInt32(self, "file_acl", "File ACL of the xattr block")
        yield UInt32(self, "size_high", "High 32 bits of the file size")
        yield UInt32(self, "faddr", "Block where the fragment of the file resides (obsolete)")

        if os == SuperBlock.OS_LINUX:
            yield UInt16(self, "blocks_high", "High 16 bits of the block count")
            yield UInt16(self, "file_acl_high", "High 16 bits of the xattr block")
            yield UInt16(self, "uid_high", "High 16 bits of user ID")
            yield UInt16(self, "gid_high", "High 16 bits of group ID")
            yield UInt16(self, "checksum", "inode checksum")
            yield NullBytes(self, "reserved[]", 2, "Reserved")
        elif os == SuperBlock.OS_HURD:
            yield UInt8(self, "frag", "Number of fragments in the block")
            yield UInt8(self, "fsize", "Fragment size")
            yield UInt16(self, "mode_high", "High 16 bits of mode")
            yield UInt16(self, "uid_high", "High 16 bits of user ID")
            yield UInt16(self, "gid_high", "High 16 bits of group ID")
            yield UInt32(self, "author", "Author ID (?)")
        else:
            yield RawBytes(self, "raw", 12, "Reserved")


class Directory(Parser):
    PARSER_TAGS = {
        "description": "Directory of EXT2/EXT3 file system",
    }
    endian = LITTLE_ENDIAN

    def createFields(self):
        while self.current_size < self.size:
            yield DirectoryEntry(self, "entry[]")

    def validate(self):
        return True


class Bitmap(FieldSet):
    itemdesc = 'Item'

    def __init__(self, parent, name, start, count, size, description, **kw):
        description = "%s: %s items" % (description, count)
        FieldSet.__init__(self, parent, name, description, size=size, **kw)
        self.start = 1 + start
        self.count = count

    def createFields(self):
        for index in range(self.count):
            yield Bit(self, "item[]", "%s %s" % (self.itemdesc, self.start + index))
        if self.size > self.count:
            yield PaddingBytes(self, "padding", (self.size - self.count) // 8, pattern='\xff')


class BlockBitmap(Bitmap):
    itemdesc = 'Block'


class InodeBitmap(Bitmap):
    itemdesc = 'Inode'


class GroupDescriptorFlags(Flags):
    static_size = 16

    def createFields(self):
        yield Bit(self, "inode_uninit", "inode table and bitmap are not initialized")
        yield Bit(self, "block_uninit", "block bitmap is not initialized")
        yield Bit(self, "inode_zeroed", "inode table is zeroed")
        yield PaddingBits(self, "reserved[]", 13)


class GroupDescriptor(FieldSet):
    static_size = 32 * 8

    def __init__(self, parent, name, index):
        FieldSet.__init__(self, parent, name)
        self.uniq_id = index

    def createDescription(self):
        blocks_per_group = self["/superblock/blocks_per_group"].value
        start = self.uniq_id * blocks_per_group
        end = start + blocks_per_group
        return "Group descriptor: blocks %s-%s" % (start, end)

    def createFields(self):
        yield UInt32(self, "block_bitmap", "Starting block index of the block bitmap")
        yield UInt32(self, "inode_bitmap", "Starting block index of the inode bitmap")
        yield UInt32(self, "inode_table", "Starting block index of the inode table")
        yield UInt16(self, "free_blocks_count", "Number of free blocks")
        yield UInt16(self, "free_inodes_count", "Number of free inodes")
        yield UInt16(self, "used_dirs_count", "Number of inodes allocated to directories")
        yield GroupDescriptorFlags(self, "bg_flags", "Block group flags")
        yield UInt32(self, "exclude_bitmap", "Starting block index of the snapshot exclusion bitmap")
        yield UInt16(self, "block_bitmap_csum", "Block bitmap checksum")
        yield UInt16(self, "inode_bitmap_csum", "Inode bitmap checksum")
        yield UInt16(self, "itable_unused", "Number of unused inodes")
        yield UInt16(self, "checksum", "Group descriptor checksum")


class FeatureCompatFlags(Flags):
    static_size = 32

    def createFields(self):
        yield Bit(self, "dir_prealloc", "Directory preallocation")
        yield Bit(self, "imagic_inodes", "imagic inodes - use unclear")
        yield Bit(self, "has_journal", "Has a journal")
        yield Bit(self, "ext_attr", "Supports extended attributes")
        yield Bit(self, "resize_inode", "Has reserved GDT blocks for FS expansion")
        yield Bit(self, "dir_index", "Has directory indices")
        yield Bit(self, "lazy_bg", "Lazy block groups (not used by Linux)")
        yield Bit(self, "exclude_inode", "Exclude inode (deprecated)")
        yield Bit(self, "exclude_bitmap", "Exclude bitmap (unused)")
        yield Bit(self, "sparse_super2", "Sparse Super Block v2")
        yield PaddingBits(self, "reserved[]", 22)


class FeatureIncompatFlags(Flags):
    static_size = 32

    def createFields(self):
        yield Bit(self, "compression", "Compression")
        yield Bit(self, "filetype", "Directory entries record file type")
        yield Bit(self, "recover", "FS needs recovery")
        yield Bit(self, "journal_dev", "FS has a separate journal device")
        yield Bit(self, "meta_bg", "Meta block groups")
        yield Bit(self, "reserved[]")
        yield Bit(self, "extents", "Files use extents")
        yield Bit(self, "64bit", "FS can have up to 2^64 blocks")
        yield Bit(self, "mmp", "Multiple mount protection")
        yield Bit(self, "flex_bg", "Flexible block groups")
        yield Bit(self, "ea_inode", "Inodes can be used for large xattrs")
        yield Bit(self, "reserved[]")
        yield Bit(self, "dirdata", "Data in directory entry")
        yield Bit(self, "csum_seed", "Metadata checksum seed in the superblock")
        yield Bit(self, "largedir", "Large directory >2GB, or 3-level htree")
        yield Bit(self, "inline_data", "Data in inode")
        yield Bit(self, "encrypt", "Encrypted inodes present")
        yield PaddingBits(self, "reserved[]", 15)


class FeatureROCompatFlags(Flags):
    static_size = 32

    def createFields(self):
        yield Bit(self, "sparse_super", "Sparse superblocks")
        yield Bit(self, "large_file", "The FS has been used to store a file >2GiB")
        yield Bit(self, "btree_dir")
        yield Bit(self, "huge_file", "The FS has files whose sizes are in units of logical blocks")
        yield Bit(self, "gdt_csum", "Group descriptors have checksums")
        yield Bit(self, "dir_nlink", "ext3 32k subdir limit does not apply")
        yield Bit(self, "extra_isize", "FS has large inodes")
        yield Bit(self, "has_snapshot", "FS has a snapshot")
        yield Bit(self, "quota", "FS has quotas")
        yield Bit(self, "bigalloc", "FS supports allocating extents in units of clusters (fragments)")
        yield Bit(self, "metadata_csum", "FS supports metadata checksums")
        yield Bit(self, "replica", "FS supports replicas")
        yield Bit(self, "readonly", "FS is readonly")
        yield PaddingBits(self, "reserved[]", 19)


class DefaultMountOptionFlags(Flags):
    static_size = 32

    def createFields(self):
        yield Bit(self, "debug", "Print debug info upon mount")
        yield Bit(self, "bsdgroups", "New files take the gid of the containing dir")
        yield Bit(self, "xattr_user", "Support userspace-provided xattrs")
        yield Bit(self, "acl", "Support POSIX access control lists")
        yield Bit(self, "uid16", "Do not support 32-bit UIDs")
        yield Enum(Bits(self, "jmode", 2, "Journaling mode"),
                   {0: "none", 1: "data", 2: "ordered", 3: "wback"})
        yield Bit(self, "reserved[]")
        yield Bit(self, "nobarrier", "Disable write flushes")
        yield Bit(self, "block_validity", "Track metadata blocks to avoid treating them as data blocks")
        yield Bit(self, "discard", "Tell the storage device when blocks become unused")
        yield Bit(self, "nodelalloc", "Disable delayed allocation")
        yield PaddingBits(self, "reserved[]", 20)

    def createDisplay(self):
        out = []
        for field in self:
            if field.name == 'jmode':
                if field.value:
                    out.append('jmode_' + field.display)
            elif field.value:
                out.append(field.name)
        return '{' + ', '.join(out) + '}'


class SuperBlock(FieldSet):
    static_size = 1024 * 8

    OS_LINUX = 0
    OS_HURD = 1
    os_name = {
        0: "Linux",
        1: "Hurd",
        2: "Masix",
        3: "FreeBSD",
        4: "Lites",
        5: "WinNT"
    }
    state_desc = {
        1: "Valid (Unmounted cleanly)",
        2: "Error (Errors detected)",
        4: "Orphan FS (Orphans being recovered)",
    }
    error_handling_desc = {1: "Continue", 2: "Remount R/O", 3: "Panic"}
    revision_levels = {
        0: "The good old (original) format",
        1: "V2 format w/ dynamic inode sizes",
    }
    htree_hash_algo_desc = {
        0: 'Legacy', 1: 'Half MD4', 2: 'TEA', 3: 'Legacy unsigned', 4: 'Half MD4 unsigned', 5: 'TEA unsigned'
    }

    def __init__(self, parent, name):
        FieldSet.__init__(self, parent, name)
        self._group_count = None

    def createDescription(self):
        if self["feature_compat/has_journal"].value:
            fstype = "ext3"
        else:
            fstype = "ext2"
        return "Superblock: %s file system" % fstype

    def createFields(self):
        yield UInt32(self, "inodes_count", "Total inode count")
        yield UInt32(self, "blocks_count", "Total block count")
        yield UInt32(self, "r_blocks_count", "Reserved (superuser-only) block count")
        yield UInt32(self, "free_blocks_count", "Free block count")
        yield UInt32(self, "free_inodes_count", "Free inode count")
        yield UInt32(self, "first_data_block", "First data block")
        yield UInt32(self, "log_block_size", "Block size = 2**(10+log_block_size)")
        yield UInt32(self, "log_frag_size", "Cluster size = 2**log_frag_size")
        yield UInt32(self, "blocks_per_group", "Blocks per group")
        yield UInt32(self, "frags_per_group", "Fragments per group")
        yield UInt32(self, "inodes_per_group", "Inodes per group")
        yield TimestampUnix32(self, "mtime", "Mount time")
        yield TimestampUnix32(self, "wtime", "Write time")
        yield UInt16(self, "mnt_count", "Mount count since the last fsck")
        yield UInt16(self, "max_mnt_count", "Max mount count before fsck is needed")
        yield UInt16(self, "magic", "Magic number (0xEF53)")
        yield Enum(UInt16(self, "state", "File system state"), self.state_desc)
        yield Enum(UInt16(self, "errors", "Behaviour when detecting errors"), self.error_handling_desc)
        yield UInt16(self, "minor_rev_level", "Minor revision level")
        yield TimestampUnix32(self, "last_check", "Time of last check")
        yield textHandler(UInt32(self, "check_interval", "Maximum time between checks"), self.postMaxTime)
        yield Enum(UInt32(self, "creator_os", "Creator OS"), self.os_name)
        yield Enum(UInt32(self, "rev_level", "Revision level"), self.revision_levels)
        yield UInt16(self, "def_resuid", "Default uid for reserved blocks")
        yield UInt16(self, "def_resgid", "Default gid for reserved blocks")
        yield UInt32(self, "first_ino", "First non-reserved inode")
        yield UInt16(self, "inode_size", "Size of inode structure")
        yield UInt16(self, "block_group_nr", "Block group # of this superblock")
        yield FeatureCompatFlags(self, "feature_compat", "Compatible feature set (can mount even if these features are unsupported)")
        yield FeatureIncompatFlags(self, "feature_incompat", "Incompatible feature set (must support all features to mount)")
        yield FeatureROCompatFlags(self, "feature_ro_compat", "Read-only compatible feature set (can only mount r/o if a feature is unsupported)")
        yield UUID(self, "uuid", "128-bit UUID for volume")
        yield String(self, "volume_name", 16, "Volume name", strip="\0")
        yield String(self, "last_mounted", 64, "Directory where last mounted", strip="\0")
        yield UInt32(self, "compression", "For compression (algorithm usage bitmap)")
        yield UInt8(self, "prealloc_blocks", "Number of blocks to try to preallocate")
        yield UInt8(self, "prealloc_dir_blocks", "Number to preallocate for directories")
        yield UInt16(self, "reserved_gdt_blocks", "Number of reserved GDT entries for future expansion")
        yield RawBytes(self, "journal_uuid", 16, "UUID of journal superblock")
        yield UInt32(self, "journal_inum", "Inode number of journal file")
        yield UInt32(self, "journal_dev", "Device number of journal file (if ext_journal feature is set)")
        yield UInt32(self, "last_orphan", "Start of list of orphaned inodes to delete")
        # ext3 stuff
        yield RawBytes(self, "hash_seed", 16, "Seeds used for the directory indexing hash algorithm")
        yield Enum(UInt8(self, "def_hash_version", "Default hash version for directory indexing"),
                   self.htree_hash_algo_desc)
        yield UInt8(self, "jnl_backup_type", "Does jnl_blocks contain a backup of i_block and i_size?")
        yield UInt16(self, "desc_size", "Size of group descriptors (if 64bit feature is set)")
        yield DefaultMountOptionFlags(self, "default_mount_opts", "Default mount options")
        yield UInt32(self, "first_meta_bg", "First metablock block group (if meta_bg feature is set)")
        yield TimestampUnix32(self, "mkfs_time", "When the filesystem was created")
        yield RawBytes(self, "jnl_blocks", 17 * 4, "Backup of the journal inode's i_block and i_size")

        yield PaddingBytes(self, "reserved[]", (1024 << self['log_block_size'].value) - self.current_size // 8)

    def _getGroupCount(self):
        if self._group_count is None:
            # Calculate number of groups
            blocks_per_group = self["blocks_per_group"].value
            self._group_count = (self["blocks_count"].value - self[
                                 "first_data_block"].value + (blocks_per_group - 1)) // blocks_per_group
        return self._group_count
    group_count = property(_getGroupCount)

    def postMaxTime(self, chunk):
        return humanDuration(chunk.value * 1000)


class GroupDescriptors(FieldSet):

    def __init__(self, parent, name, count):
        FieldSet.__init__(self, parent, name)
        self.count = count

    def createDescription(self):
        return "Group descriptors: %s items" % self.count

    def createFields(self):
        for index in range(self.count):
            yield GroupDescriptor(self, "group[]", index)


class InodeTable(FieldSet):

    def __init__(self, parent, name, start, count):
        FieldSet.__init__(self, parent, name)
        self.start = start
        self.count = count
        inode_size = self["/superblock/inode_size"].value
        if inode_size == 0:
            inode_size = 128
        self._size = self.count * inode_size * 8

    def createDescription(self):
        return "Inodes: %s items" % self.count

    def createFields(self):
        for index in range(self.start, self.start + self.count):
            yield Inode(self, "inode[]", index)


class IndirectBlock(FieldSet):

    def __init__(self, parent, name, size):
        FieldSet.__init__(self, parent, name, size=size * 8)
        self.count = size // 4

    def createFields(self):
        for i in range(self.count):
            yield UInt32(self, "block[]")


class Group(SeekableFieldSet):

    def __init__(self, parent, name, descriptor):
        self.superblock = parent['superblock']
        block_size = 1024 << self.superblock['log_block_size'].value
        size = block_size * self.superblock['blocks_per_group'].value * 8
        SeekableFieldSet.__init__(self, parent, name, size=size)
        self.descriptor = descriptor

    def createDescription(self):
        desc = "Group %s" % (self.descriptor.uniq_id)
        return desc

    def seekBlock(self, block):
        self.seekBit(block * self.root.block_size * 8, relative=False)

    def createFields(self):
        superblock = self["/superblock"]

        # Compute number of block and inodes
        block_count = superblock["blocks_per_group"].value
        inode_count = superblock["inodes_per_group"].value
        block_index = self.descriptor.uniq_id * block_count
        inode_index = self.descriptor.uniq_id * inode_count
        if (block_count % 8) != 0:
            raise ParserError("Invalid block count")
        if (inode_count % 8) != 0:
            raise ParserError("Invalid inode count")
        block_count = min(block_count, superblock[
                          "blocks_count"].value - block_index)
        inode_count = min(inode_count, superblock[
                          "inodes_count"].value - inode_index)

        bitmap_block_size = self.root.block_size * 8
        block_bitmap_size = (block_count + bitmap_block_size -
                             1) // bitmap_block_size * bitmap_block_size
        inode_bitmap_size = (inode_count + bitmap_block_size -
                             1) // bitmap_block_size * bitmap_block_size

        self.seekBlock(self.descriptor["block_bitmap"].value)
        yield BlockBitmap(self, "block_bitmap", block_index, block_count, block_bitmap_size, "Block bitmap")

        self.seekBlock(self.descriptor["inode_bitmap"].value)
        yield InodeBitmap(self, "inode_bitmap", inode_index, inode_count, inode_bitmap_size, "Inode bitmap")

        self.seekBlock(self.descriptor["inode_table"].value)
        yield InodeTable(self, "inode_table", inode_index, inode_count)

        inode_bitmap = self['inode_bitmap']
        for i, inode in enumerate(self['inode_table'].array('inode')):
            if not inode_bitmap['item[%d]' % i].value:
                continue
            if inode['blocks'].value == 0:
                continue
            blocks = inode.array('block')
            if not blocks:
                continue
            if inode['mode/file_type'].display == 'Directory':
                parser = Directory
            else:
                parser = None
            group = FragmentGroup(parser=parser)
            for b in range(12):
                if not blocks[b].value:
                    continue
                self.seekBlock(blocks[b].value)
                yield CustomFragment(self, "inode[%d]block[]" % i, self.root.block_size * 8,
                                     None, group=group)
            if blocks[12].value:
                # indirect block
                self.seekBlock(blocks[12].value)
                indirect = IndirectBlock(self, "inode[%d]indirect" % i, self.root.block_size)
                yield indirect
                for b in indirect.array('block'):
                    if not b.value:
                        continue
                    self.seekBlock(b.value)
                    yield CustomFragment(self, "inode[%d]block[]" % i, self.root.block_size * 8,
                                         None, group=group)
            if blocks[13].value:
                # TODO: double-indirect block
                pass
            if blocks[14].value:
                # TODO: triple-indirect block
                pass


class EXT2_FS(HachoirParser, RootSeekableFieldSet):
    """
    Parse an EXT2 or EXT3 partition.

    Attributes:
       * block_size: Size of a block (in bytes)

    Fields:
       * superblock: Most important block, store most important informations
       * ...
    """
    PARSER_TAGS = {
        "id": "ext2",
        "category": "file_system",
        "description": "EXT2/EXT3 file system",
        "min_size": (1024 * 2) * 8,
        "magic": (
            # (magic, state=valid)
            (b"\x53\xEF\1\0", 1080 * 8),
            # (magic, state=error)
            (b"\x53\xEF\2\0", 1080 * 8),
            # (magic, state=error)
            (b"\x53\xEF\4\0", 1080 * 8),
        ),
    }
    endian = LITTLE_ENDIAN

    def __init__(self, stream, **args):
        RootSeekableFieldSet.__init__(
            self, None, "root", stream, None, stream.askSize(self))
        HachoirParser.__init__(self, stream, **args)

    def validate(self):
        if self.stream.readBytes((1024 + 56) * 8, 2) != b"\x53\xEF":
            return "Invalid magic number"
        if not (0 <= self["superblock/log_block_size"].value <= 2):
            return "Invalid (log) block size"
        if self["superblock/inode_size"].value not in (0, 128):
            return "Unsupported inode size"
        return True

    def createFields(self):
        # Skip something (what is stored here? MBR?)
        yield NullBytes(self, "padding[]", 1024)

        # Read superblock
        superblock = SuperBlock(self, "superblock")
        yield superblock
        self.block_size = 1024 << superblock["log_block_size"].value  # in bytes

        if self.block_size == 1024:
            self.seekBlock(2)
        else:
            # block_size > 1024
            self.seekBlock(1)

        # Read groups' descriptor
        groups = GroupDescriptors(self, "group_desc", superblock.group_count)
        yield groups

        for group in groups.array('group'):
            self.seekBlock(min(group[f].value for f in [
                           'block_bitmap', 'inode_bitmap', 'inode_table']))
            yield Group(self, "group[]", group)

    def seekBlock(self, block):
        self.seekBit(block * self.block_size * 8)

    def getSuperblock(self):
        # FIXME: Use superblock copy if main superblock is invalid
        return self["superblock"]

    def createDescription(self):
        superblock = self.getSuperblock()
        block_size = 1024 << superblock["log_block_size"].value
        nb_block = superblock["blocks_count"].value
        total = nb_block * block_size
        used = (superblock["free_blocks_count"].value) * block_size
        desc = "EXT2/EXT3"
        if "group[0]/inode_table/inode[7]/blocks" in self:
            if 0 < self["group[0]/inode_table/inode[7]/blocks"].value:
                desc = "EXT3"
            else:
                desc = "EXT2"
        return desc + " file system: total=%s, used=%s, block=%s" % (
            humanFilesize(total), humanFilesize(used),
            humanFilesize(block_size))
