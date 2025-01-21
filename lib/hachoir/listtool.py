#
# Tool for parsing a file and writing all fields to stdout.
#

from hachoir.core.cmd_line import getHachoirOptions, configureHachoir
from hachoir.core.cmd_line import displayVersion
from hachoir.stream import InputStreamError, FileInputStream
from hachoir.parser import guessParser, HachoirParserList
from optparse import OptionGroup, OptionParser
import sys


def format_size(num_bits):
    if num_bits % 8 == 0:
        return f"{num_bits // 8}B"
    else:
        return f"{num_bits}b"


def printFieldSet(field_set, args, options={}, indent=0):
    indent_string = " " * options["indent_width"] * indent
    for field in field_set:
        value_display = ""
        if field.value is not None and options["display_value"]:
            value_display = f": {field.display}"
        size_display = ""
        if options["display_size"]:
            size_display = f", {format_size(field.size)}"
        description_display = ""
        if options["display_description"]:
            description_display = f" ({field.description})"
        print(f"{indent_string}{field.name} <{field.__class__.__name__}{size_display}>{description_display}{value_display}")

        if field.is_field_set:
            printFieldSet(field, args, options, indent + 1)


def displayParserList(*args):
    HachoirParserList().print_()
    sys.exit(0)


def parseOptions():
    parser = OptionParser(usage="%prog [options] filename [filenames...]")

    common = OptionGroup(parser, "List Tool", "Options of list tool")
    common.add_option("--parser", help="Use the specified parser (use its identifier)",
                      type="str", action="store", default=None)
    common.add_option("--offset", help="Skip first bytes of input file",
                      type="long", action="store", default=0)
    common.add_option("--parser-list", help="List all parsers then exit",
                      action="callback", callback=displayParserList)
    common.add_option("--size", help="Maximum size of bytes of input file",
                      type="long", action="store", default=None)
    common.add_option("--description", dest="display_description", help="Display description",
                      action="store_true", default=False)
    common.add_option("--hide-value", dest="display_value", help="Don't display value",
                      action="store_false", default=True)
    common.add_option("--hide-size", dest="display_size", help="Don't display size",
                      action="store_false", default=True)
    common.add_option("--indent-width", dest="indent_width", help="Indentation width",
                      type="long", action="store", default=2)
    common.add_option("--version", help="Display version and exit",
                      action="callback", callback=displayVersion)
    parser.add_option_group(common)

    hachoir = getHachoirOptions(parser)
    parser.add_option_group(hachoir)

    values, arguments = parser.parse_args()
    if len(arguments) < 1:
        parser.print_help()
        sys.exit(1)
    return values, arguments


def openParser(parser_id, filename, offset, size):
    tags = []
    if parser_id:
        tags += [("id", parser_id), None]
    try:
        stream = FileInputStream(filename,
                                 offset=offset, size=size, tags=tags)
    except InputStreamError as err:
        return None, "Unable to open file: %s" % err
    parser = guessParser(stream)
    if not parser:
        return None, "Unable to parse file: %s" % filename
    return parser, None


def main():
    # Parse options and initialize Hachoir
    values, filenames = parseOptions()
    configureHachoir(values)

    # Open file and create parser
    showing_multiple_files = len(filenames) > 1
    i = 0
    for filename in filenames:

        i += 1
        if i > 1:
            print()
        if showing_multiple_files:
            print(f"File: {filename}")

        parser, err = openParser(values.parser, filename,
                                 values.offset, values.size)
        if err:
            print(err)
            sys.exit(1)

        # Explore file
        with parser:
            printFieldSet(parser, values, {
                "display_description": values.display_description,
                "display_size": values.display_size,
                "display_value": values.display_value,
                "indent_width": values.indent_width,
            })


if __name__ == "__main__":
    main()
