from hachoir.parser.parser import ValidateError, HachoirParser, Parser  # noqa
from hachoir.parser.parser_list import ParserList, HachoirParserList  # noqa
from hachoir.parser.guess import QueryParser, guessParser, createParser  # noqa
# load only the parsers that it uses (video, image, torrent), this saves about 5 MB
# upstream also imports archive, audio, file_system, game, network and program here
from hachoir.parser import container, image, misc, video  # noqa
