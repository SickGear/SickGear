from hachoir.stream import InputSubStream
from hachoir.core.tools import humanFilesize, humanDuration
from hachoir.core.memory import limitedMemory
from hachoir.subfile.data_rate import DataRate
from hachoir.subfile.output import Output
from hachoir.subfile.pattern import HachoirPatternMatching as PatternMatching
from sys import stderr
from time import time


def skipSubfile(parser):
    subfile = parser.getParserTags().get("subfile", "")
    return (subfile == "skip")


FILE_MAX_SIZE = 100 * 1024 * 1024   # Max. file size in bytes (100 MB)
SLICE_SIZE = 64 * 1024                # Slice size in bytes (64 KB)
MEMORY_LIMIT = 50 * 1024 * 1024
PROGRESS_UPDATE = 1.5   # Minimum number of second between two progress messages


class SearchSubfile:
    """
    Tool to find file start and file size in any binary stream.

    To use it:
    - instanciate the class: subfile = SearchSubfile()
    - (optional) choose magics with: subfile.loadMagics(categories, parser_ids)
    - run the search: subfile.main()
    """

    def __init__(self, stream, offset=0, size=None):
        """
        Setup search tool, parameter:
         - filename: Input filename in locale charset
         - directory: Directory filename in locale charset where
           output files will be written
         - offset: Offset (in bytes) of the beginning of the search
         - size: Limit size (in bytes) of input file (None: no limit)
         - debug: Debug mode flag (display debug information)
        """

        # Size
        self.stream = stream
        if size is not None:
            self.size = min(self.stream.size, (offset + size) * 8)
        else:
            self.size = self.stream.size

        # Offset
        self.start_offset = offset * 8
        self.current_offset = self.start_offset
        self.slice_size = SLICE_SIZE * 8   # 64 KB (in bits)

        # Statistics
        self.datarate = DataRate(self.start_offset)
        self.main_start = time()

        # Other flags and attributes
        self.patterns = None
        self.verbose = True
        self.debug = False
        self.output = None
        self.filter = None

    def setOutput(self, directory):
        self.output = Output(directory)

    def loadParsers(self, categories=None, parser_ids=None):
        before = time()
        self.patterns = PatternMatching(categories, parser_ids)
        if self.debug:
            print("Regex compilation: %.1f ms" % ((time() - before) * 1000))
            print("Use regex: %s" % self.patterns)

    def main(self):
        """
        Run the search.
        Return True if ok, False otherwise.
        """

        # Initialize
        self.mainHeader()

        # Prepare search
        main_error = False
        try:
            # Run search
            limitedMemory(MEMORY_LIMIT, self.searchSubfiles)
        except KeyboardInterrupt:
            print("[!] Program interrupted (CTRL+C)", file=stderr)
            main_error = True
        except MemoryError:
            main_error = True
            print("[!] Memory error!", file=stderr)
        self.mainFooter()
        self.stream.close()
        return not(main_error)

    def mainHeader(self):
        # Fix slice size if needed
        self.slice_size = max(self.slice_size, self.patterns.max_length * 8)

        # Load parsers if none has been choosen
        if not self.patterns:
            self.loadParsers()

        bytes = (self.size - self.start_offset) // 8
        print("[+] Start search on %s bytes (%s)" % (
            bytes, humanFilesize(bytes)), file=stderr)
        print(file=stderr)
        self.stats = {}
        self.current_offset = self.start_offset
        self.main_start = time()

    def mainFooter(self):
        print(file=stderr)
        print("[+] End of search -- offset=%s (%s)" % (
            self.current_offset // 8, humanFilesize(self.current_offset // 8)), file=stderr)
        size = (self.current_offset - self.start_offset) // 8
        duration = time() - self.main_start
        if 0.1 <= duration:
            print("Total time: %s -- global rate: %s/sec" % (
                humanDuration(duration * 1000), humanFilesize(size // duration)), file=stderr)

    def searchSubfiles(self):
        """
        Search all subfiles in the stream, call processParser() for each parser.
        """
        self.next_offset = None
        self.next_progress = time() + PROGRESS_UPDATE
        while self.current_offset < self.size:
            self.datarate.update(self.current_offset)
            if self.verbose and self.next_progress <= time():
                self.displayProgress()
            for offset, parser in self.findMagic(self.current_offset):
                self.processParser(offset, parser)
            self.current_offset += self.slice_size
            if self.next_offset:
                self.current_offset = max(
                    self.current_offset, self.next_offset)
            self.current_offset = min(self.current_offset, self.size)

    def processParser(self, offset, parser):
        """
        Process a valid parser.
        """
        text = "[+] File at %s" % (offset // 8)
        if parser.content_size is not None:
            text += " size=%s (%s)" % (parser.content_size //
                                       8, humanFilesize(parser.content_size // 8))
        if not(parser.content_size) or parser.content_size // 8 < FILE_MAX_SIZE:
            text += ": " + parser.description
        else:
            text += ": " + parser.__class__.__name__

        if self.output and parser.content_size:
            if (offset == 0 and parser.content_size == self.size):
                text += " (don't copy whole file)"
            elif parser.content_size // 8 >= FILE_MAX_SIZE:
                text += " (don't copy file, too big)"
            elif not self.filter or self.filter(parser):
                filename = self.output.createFilename(parser.filename_suffix)
                filename = self.output.writeFile(
                    filename, self.stream, offset, parser.content_size)
                text += " => %s" % filename
        print(text)
        self.next_progress = time() + PROGRESS_UPDATE

    def findMagic(self, offset):
        """
        Find all 'magic_str' strings in stream in offset interval:
          offset..(offset+self.slice_size).

        The function returns a generator with values (offset, parser) where
        offset is beginning of a file (relative to stream begin), and not the
        position of the magic.
        """
        start = offset
        end = start + self.slice_size
        end = min(end, self.size)
        data = self.stream.readBytes(start, (end - start) // 8)
        for parser_cls, offset in self.patterns.search(data):
            offset += start
            # Skip invalid offset
            if offset < 0:
                continue
            if self.next_offset and offset < self.next_offset:
                continue

            # Create parser at found offset
            parser = self.guess(offset, parser_cls)

            # Update statistics
            if parser_cls not in self.stats:
                self.stats[parser_cls] = [0, 0]
            self.stats[parser_cls][0] += 1
            if not parser:
                continue

            # Parser is valid, yield it with the offset
            self.stats[parser_cls][1] += 1

            if self.debug:
                print("Found %s at offset %s" % (
                    parser.__class__.__name__, offset // 8), file=stderr)
            yield (offset, parser)

            # Set next offset
            if parser.content_size is not None\
                    and skipSubfile(parser):
                self.next_offset = offset + parser.content_size
                if end <= self.next_offset:
                    break

    def guess(self, offset, parser_cls):
        """
        Try the specified parser at stream offset 'offset'.

        Return the parser object, or None on failure.
        """
        substream = InputSubStream(self.stream, offset)
        try:
            return parser_cls(substream, validate=True)
        except Exception:
            return None

    def displayProgress(self):
        """
        Display progress (to stdout) of the whole process.
        Compute data rate (in byte per sec) and time estimation.
        """
        # Program next update
        self.next_progress = time() + PROGRESS_UPDATE

        # Progress offset
        percent = float(self.current_offset - self.start_offset) * \
            100 / (self.size - self.start_offset)
        offset = self.current_offset // 8
        message = "Search: %.2f%% -- offset=%u (%s)" % (
            percent, offset, humanFilesize(offset))

        # Compute data rate (byte/sec)
        average = self.datarate.average
        if average:
            message += " -- %s/sec " % humanFilesize(average // 8)
            eta = float(self.size - self.current_offset) / average
            message += " -- ETA: %s" % humanDuration(eta * 1000)

        # Display message
        print(message, file=stderr)
