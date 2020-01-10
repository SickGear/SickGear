import hachoir_py3.core.config as config
from hachoir_py3.field import Parser as GenericParser
from hachoir_py3.core.error import error
from hachoir_py3.core.tools import makeUnicode
from inspect import getmro


class ValidateError(Exception):
    pass


class HachoirParser(object):
    """
    A parser is the root of all other fields. It create first level of fields
    and have special attributes and methods:
    - tags: dictionnary with keys:
      - "file_ext": classical file extensions (string or tuple of strings) ;
      - "mime": MIME type(s) (string or tuple of strings) ;
      - "description": String describing the parser.
    - endian: Byte order (L{BIG_ENDIAN} or L{LITTLE_ENDIAN}) of input data ;
    - stream: Data input stream (set in L{__init__()}).

    Default values:
    - size: Field set size will be size of input stream ;
    - mime_type: First MIME type of tags["mime"] (if it does exist,
      None otherwise).
    """

    _autofix = False

    def __init__(self, stream, **args):
        validate = args.pop("validate", False)
        self._mime_type = None
        while validate:
            nbits = self.getParserTags()["min_size"]
            if stream.sizeGe(nbits):
                res = self.validate()
                if res is True:
                    break
                res = makeUnicode(res)
            else:
                res = "stream is smaller than %s.%s bytes" % divmod(nbits, 8)
            raise ValidateError(res or "no reason given")
        self._autofix = True

    # --- Methods that can be overridden -------------------------------------
    def createDescription(self):
        """
        Create an Unicode description
        """
        return self.PARSER_TAGS["description"]

    def createMimeType(self):
        """
        Create MIME type (string), eg. "image/png"

        If it returns None, "application/octet-stream" is used.
        """
        if "mime" in self.PARSER_TAGS:
            return self.PARSER_TAGS["mime"][0]
        return None

    def validate(self):
        """
        Check that the parser is able to parse the stream. Valid results:
        - True: stream looks valid ;
        - False: stream is invalid ;
        - str: string describing the error.
        """
        raise NotImplementedError()

    # --- Getter methods -----------------------------------------------------
    def _getDescription(self):
        if self._description is None:
            try:
                self._description = self.createDescription()
                if isinstance(self._description, str):
                    self._description = makeUnicode(self._description)
            except Exception as err:
                error("Error getting description of %s: %s"
                      % (self.path, str(err)))
                self._description = self.PARSER_TAGS["description"]
        return self._description
    description = property(_getDescription,
                           doc="Description of the parser")

    def _getMimeType(self):
        if not self._mime_type:
            try:
                self._mime_type = self.createMimeType()
            except Exception as err:
                error("Error when creating MIME type: %s" % str(err))
            if not self._mime_type \
                    and self.createMimeType != Parser.createMimeType:
                self._mime_type = Parser.createMimeType(self)
            if not self._mime_type:
                self._mime_type = "application/octet-stream"
        return self._mime_type
    mime_type = property(_getMimeType)

    def createContentSize(self):
        return None

    def _getContentSize(self):
        if not hasattr(self, "_content_size"):
            try:
                self._content_size = self.createContentSize()
            except Exception as err:
                error("Unable to compute %s content size: %s" %
                      (self.__class__.__name__, err))
                self._content_size = None
        return self._content_size
    content_size = property(_getContentSize)

    def createFilenameSuffix(self):
        """
        Create filename suffix: "." + first value of self.PARSER_TAGS["file_ext"],
        or None if self.PARSER_TAGS["file_ext"] doesn't exist.
        """
        file_ext = self.getParserTags().get("file_ext")
        if isinstance(file_ext, (tuple, list)):
            file_ext = file_ext[0]
        return file_ext and '.' + file_ext

    def _getFilenameSuffix(self):
        if not hasattr(self, "_filename_suffix"):
            self._filename_extension = self.createFilenameSuffix()
        return self._filename_extension
    filename_suffix = property(_getFilenameSuffix)

    @classmethod
    def getParserTags(cls):
        tags = {}
        for cls in reversed(getmro(cls)):
            if hasattr(cls, "PARSER_TAGS"):
                tags.update(cls.PARSER_TAGS)
        return tags

    @classmethod
    def print_(cls, out, verbose):
        tags = cls.getParserTags()
        print("- %s: %s" % (tags["id"], tags["description"]), file=out)
        if verbose:
            if "mime" in tags:
                print("  MIME type: %s" % (", ".join(tags["mime"])), file=out)
            if "file_ext" in tags:
                file_ext = ", ".join(
                    ".%s" % file_ext for file_ext in tags["file_ext"])
                print("  File extension: %s" % file_ext, file=out)

    autofix = property(lambda self: self._autofix and config.autofix)


class Parser(HachoirParser, GenericParser):

    def __init__(self, stream, **args):
        GenericParser.__init__(self, stream)
        HachoirParser.__init__(self, stream, **args)
