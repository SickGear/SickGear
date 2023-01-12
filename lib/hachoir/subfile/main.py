from hachoir.stream import FileInputStream
from hachoir.core import config
from hachoir.subfile.search import SearchSubfile
from hachoir.core.cmd_line import displayVersion
from sys import exit
from optparse import OptionGroup, OptionParser


def parseOptions():
    parser = OptionParser(usage="%prog [options] filename [output_directory]")

    common = OptionGroup(parser, "hachoir-subfile",
                         "Option of hachoir-subfile")
    common.add_option("--offset", help="Skip first bytes of input file",
                      action="store", type='int', default=0)
    common.add_option("--size", help="Maximum size of input file",
                      action="store", type='int', default=None)
    common.add_option("--category", help="Parser category list (separated with a comma)",
                      action="store", type='str', default=None)
    common.add_option("--parser", help="Parser identifier list (separated with a comma)",
                      action="store", type='str', default=None)
    common.add_option("--version", help="Display version and exit",
                      action="callback", callback=displayVersion)
    common.add_option("--quiet", help="Be quiet",
                      action="store_true", default=False)
    common.add_option("--profiler", help="Run profiler",
                      action="store_true", default=False)
    common.add_option("--debug", help="Enable debug mode",
                      action="store_true", default=False)
    parser.add_option_group(common)

    values, arguments = parser.parse_args()
    if len(arguments) == 1:
        filename, output = arguments[0], None
    elif len(arguments) == 2:
        filename, output = arguments
    else:
        parser.print_help()
        exit(1)
    return values, filename, output


def displaySearchStat(subfile):
    stats = [(parser.tags["id"], stats[0], stats[1])
             for parser, stats in subfile.stats.items()]
    print()
    print("[ Match statistics ]")
    total_hit = 0
    total_valid = 0
    if stats:
        stats.sort(key=lambda values: values[1])
        for parser_id, hit, valid in stats:
            print(" - %s: %u hit/%u valid" % (parser_id, hit, valid))
            total_hit += hit
            total_valid += valid
        print()
    else:
        print("(no match)")
    print("Total: %u hit/%u valid" % (total_hit, total_valid))


def runSearch(subfile, values):
    # Load categories and parsers
    categories = values.category
    if categories:
        categories = categories.split(",")
    parsers = values.parser
    if parsers:
        parsers = parsers.split(",")
    subfile.loadParsers(categories=categories, parser_ids=parsers)

    # Search subfiles
    ok = subfile.main()

    # Dump statistics on debug mode
    if values.debug:
        displaySearchStat(subfile)
    return ok


def main():
    # Initialize
    values, filename, output = parseOptions()
    config.quiet = True
    stream = FileInputStream(filename)
    with stream:
        subfile = SearchSubfile(stream, values.offset, values.size)
        subfile.verbose = not(values.quiet)
        subfile.debug = values.debug
        if output:
            subfile.setOutput(output)
        if values.profiler:
            from hachoir.core.profiler import runProfiler
            ok = runProfiler(runSearch, (subfile, values))
        else:
            ok = runSearch(subfile, values)
    exit(int(not ok))
