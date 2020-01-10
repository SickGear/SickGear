"""
Parser list managment:
- createParser() find the best parser for a file.
"""

import os
from hachoir_py3.core.error import warning, info
from hachoir_py3.parser import ValidateError, HachoirParserList
from hachoir_py3.stream import FileInputStream
import weakref


class QueryParser(object):
    fallback = None
    other = None

    def __init__(self, tags):
        self.validate = True
        self.use_fallback = False
        self.parser_args = None
        self.db = HachoirParserList.getInstance()
        self.parsers = set(self.db)
        parsers = []
        for tag in tags:
            if not self.parsers:
                break
            parsers += self._getByTag(tag)
            if self.fallback is None:
                self.fallback = len(parsers) == 1
        if self.parsers:
            other = len(parsers)
            parsers += list(self.parsers)
            self.other = parsers[other]
        self.parsers = parsers

    def __iter__(self):
        return iter(self.parsers)

    def translate(self, name, value):
        if name == "filename":
            filename = os.path.basename(value).split(".")
            if len(filename) <= 1:
                value = ""
            else:
                value = filename[-1].lower()
            name = "file_ext"
        return name, value

    def _getByTag(self, tag):
        if tag is None:
            self.parsers.clear()
            return []
        elif callable(tag):
            parsers = [parser for parser in self.parsers if tag(parser)]
            for parser in parsers:
                self.parsers.remove(parser)
        elif tag[0] == "class":
            self.validate = False
            return [tag[1]]
        elif tag[0] == "args":
            self.parser_args = tag[1]
            return []
        else:
            tag = self.translate(*tag)
            parsers = []
            if tag is not None:
                key = tag[0]
                byname = self.db.bytag.get(key, {})
                if tag[1] is None:
                    values = iter(byname.values())
                else:
                    values = byname.get(tag[1], ()),
                if key == "id" and values:
                    self.validate = False
                for value in values:
                    for parser in value:
                        if parser in self.parsers:
                            parsers.append(parser)
                            self.parsers.remove(parser)
        return parsers

    def parse(self, stream, fallback=True):
        if hasattr(stream, "_cached_parser"):
            parser = stream._cached_parser()
        else:
            parser = None
        if parser is not None:
            if parser.__class__ in self.parsers:
                return parser
        parser = self.doparse(stream, fallback)
        if parser is not None:
            stream._cached_parser = weakref.ref(parser)
        else:
            try:
                stream._input.close()
            except:
                pass
        return parser

    def doparse(self, stream, fallback=True):
        fb = None
        warn = warning
        for parser in self.parsers:
            try:
                parser_obj = parser(stream, validate=self.validate)
                if self.parser_args:
                    for key, value in self.parser_args.items():
                        setattr(parser_obj, key, value)
                return parser_obj
            except ValidateError as err:
                if fallback and self.fallback:
                    fb = parser
                if parser == self.other:
                    warn = info
                warn("Skip parser '%s': %s" % (parser.__name__, err))
            except Exception as err:
                if parser == self.other:
                    warn = info
                warn("Skip parser '%s': %s" % (parser.__name__, err))
            fallback = False
        if self.use_fallback and fb:
            warning("Force use of parser '%s'" % fb.__name__)
            return fb(stream)


def guessParser(stream):
    return QueryParser(stream.tags).parse(stream)


def createParser(filename, real_filename=None, tags=None):
    """
    Create a parser from a file or returns None on error.

    Options:
    - filename (unicode): Input file name ;
    - real_filename (str|unicode): Real file name.
    """
    if not tags:
        tags = []
    stream = FileInputStream(filename, real_filename, tags=tags)
    return guessParser(stream)
