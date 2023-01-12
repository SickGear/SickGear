from hachoir.core.error import error
from hachoir.core.i18n import getTerminalCharset
from hachoir.core.benchmark import Benchmark
from hachoir.stream import InputStreamError
from hachoir.core.tools import makePrintable
from hachoir.core.cmd_line import displayVersion
from hachoir.parser import createParser, ParserList
import hachoir.core.config as hachoir_config
from hachoir.metadata import config
from optparse import OptionParser
from hachoir.metadata import extractMetadata
from hachoir.metadata.metadata import extractors as metadata_extractors
import sys


def displayParserList(*args):
    parser_list = ParserList()
    for parser in list(metadata_extractors.keys()):
        parser_list.add(parser)
    parser_list.print_("List of metadata extractors.")
    sys.exit(0)


def parseOptions():
    parser = OptionParser(usage="%prog [options] files")
    parser.add_option("--type", help="Only display file type (description)",
                      action="store_true", default=False)
    parser.add_option("--mime", help="Only display MIME type",
                      action="store_true", default=False)
    parser.add_option("--level",
                      help="Quantity of information to display from 1 to 9 (9 is the maximum)",
                      action="store", default="9", type="choice",
                      choices=[str(choice) for choice in range(1, 9 + 1)])
    parser.add_option("--raw", help="Raw output",
                      action="store_true", default=False)
    parser.add_option("--bench", help="Run benchmark",
                      action="store_true", default=False)
    parser.add_option("--force-parser", help="List all parsers then exit",
                      type="str")
    parser.add_option("--parser-list", help="List all parsers then exit",
                      action="callback", callback=displayParserList)
    parser.add_option("--profiler", help="Run profiler",
                      action="store_true", default=False)
    parser.add_option("--version", help="Display version and exit",
                      action="callback", callback=displayVersion)
    parser.add_option("--quality", help="Information quality (0.0=fastest, 1.0=best, and default is 0.5)",
                      action="store", type="float", default="0.5")
    parser.add_option("--maxlen", help="Maximum string length in characters, 0 means unlimited (default: %s)" % config.MAX_STR_LENGTH,
                      type="int", default=config.MAX_STR_LENGTH)
    parser.add_option("--verbose", help="Verbose mode",
                      default=False, action="store_true")
    parser.add_option("--debug", help="Debug mode",
                      default=False, action="store_true")

    values, filename = parser.parse_args()
    if len(filename) == 0:
        parser.print_help()
        sys.exit(1)

    # Update limits
    config.MAX_STR_LENGTH = values.maxlen
    if values.raw:
        config.RAW_OUTPUT = True

    return values, filename


def processFile(values, filename,
                display_filename=False, priority=None, human=True, display=True):
    charset = getTerminalCharset()

    # Create parser
    try:
        if values.force_parser:
            tags = [("id", values.force_parser), None]
        else:
            tags = None
        parser = createParser(filename, tags=tags)
    except InputStreamError as err:
        error(str(err))
        return False
    if not parser:
        error("Unable to parse file: %s" % filename)
        return False

    with parser:
        # Extract metadata
        extract_metadata = not(values.mime or values.type)
        if extract_metadata:
            try:
                metadata = extractMetadata(parser, values.quality)
            except Exception as err:
                error(str(err))
                metadata = None
            if not metadata:
                parser.error("Hachoir can't extract metadata, but is able to parse: %s"
                             % filename)
                return False
        else:
            if values.type:
                result = parser.description
            else:
                result = parser.mime_type

    if display:
        # Display metadatas on stdout
        if extract_metadata:
            text = metadata.exportPlaintext(priority=priority, human=human)
            if not text:
                text = ["(no metadata, priority may be too small)"]
            if display_filename:
                for line in text:
                    line = "%s: %s" % (filename, line)
                    print(makePrintable(line, charset))
            else:
                for line in text:
                    print(makePrintable(line, charset))
        else:
            text = result
            if display_filename:
                text = "%s: %s" % (filename, text)
            print(text)
    return True


def processFiles(values, filenames, display=True):
    human = not(values.raw)
    ok = True
    priority = int(values.level) * 100 + 99
    display_filename = (1 < len(filenames))
    for filename in filenames:
        ok &= processFile(values, filename, display_filename,
                          priority, human, display)
    return ok


def benchmarkMetadata(values, filenames):
    bench = Benchmark()
    bench.run(processFiles, values, filenames, display=False)


def profile(values, filenames):
    from hachoir.core.profiler import runProfiler
    return runProfiler(processFiles, (values, filenames), {'display': False})


def main():
    try:
        # Parser options and initialize Hachoir
        values, filenames = parseOptions()

        if values.debug:
            hachoir_config.debug = True
        elif values.verbose:
            hachoir_config.verbose = True
        else:
            hachoir_config.quiet = True

        if values.profiler:
            ok = profile(values, filenames)
        elif values.bench:
            ok = benchmarkMetadata(values, filenames)
        else:
            ok = processFiles(values, filenames)
    except KeyboardInterrupt:
        print("Program interrupted (CTRL+C).")
        ok = False
    sys.exit(int(not ok))
