from optparse import OptionGroup
from hachoir.core.log import log
from hachoir import __version__
import hachoir.core.config as config
import sys


def displayVersion(*args):
    print("Hachoir version %s" % __version__)
    sys.exit(0)


def getHachoirOptions(parser):
    """
    Create an option group (type optparse.OptionGroup) of Hachoir
    library options.
    """
    def setLogFilename(*args):
        log.setFilename(args[2])

    common = OptionGroup(parser, "Hachoir library",
                         "Configure Hachoir library")
    common.add_option("--verbose", help="Verbose mode",
                      default=False, action="store_true")
    common.add_option("--log", help="Write log in a file",
                      type="string", action="callback",
                      callback=setLogFilename)
    common.add_option("--quiet", help="Quiet mode (don't display warning)",
                      default=False, action="store_true")
    common.add_option("--debug", help="Debug mode",
                      default=False, action="store_true")
    return common


def configureHachoir(option):
    # Configure Hachoir using "option" (value from optparse)
    if option.quiet:
        config.quiet = True
    if option.verbose:
        config.verbose = True
    if option.debug:
        config.debug = True
