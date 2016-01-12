"""
iPod Play Count parser.

Documentation:
- http://ipl.derpapst.org/wiki/ITunesDB/Play_Counts_File
  (formerly known as http://ipodlinux.org)

Author: m42i
Creation date:  01 March 2014
"""

from hachoir_parser import Parser
from hachoir_core.field import (FieldSet,
    UInt8, UInt16, UInt32, Int32, UInt64, TimestampMac32,
    String, Float32, NullBytes, Enum, RawBytes)
from hachoir_core.endian import LITTLE_ENDIAN
from hachoir_core.tools import humanDuration
from hachoir_core.text_handler import displayHandler, filesizeHandler

class PlayCountFile(Parser):
    PARSER_TAGS = {
        "id": "playcounts",
        "category": "audio",
        "min_size": 44*8,
        "magic": (('mhdp',0),),
        "description": "iPod Play Counts file"
    }

    endian = LITTLE_ENDIAN

    def validate(self):
        return self.stream.readBytes(0, 4) == 'mhdp'

    def createFields(self):
        yield String(self, "header_id", 4, "Play Count Header Markup (\"mhdp\")", charset="ISO-8859-1")
        yield UInt32(self, "header_length", "Header Length")
        yield UInt32(self, "entry_length", "Single Entry Length")
        yield UInt32(self, "entry_number", "Number of Songs on iPod")
        padding = self.seekByte(self["header_length"].value, "header padding")
        if padding:
            yield padding

        for i in xrange(self["entry_number"].value):
            yield PlayCountEntry(self, "track[]")


class PlayCountEntry(FieldSet):
    def __init__(self, *args, **kw):
        FieldSet.__init__(self, *args, **kw)
        self._size = 28*8

    def createFields(self):
        yield UInt32(self, "play_count", "Playcount since last sync")
        yield TimestampMac32(self, "last_played", "Time of the last play of the track")
        yield UInt32(self, "audio_bookmark", "Last position in milliseconds")
        yield UInt32(self, "rating", "Rating in steps of 20 up to 100")
        yield UInt32(self, "unknown", "unknown")
        yield UInt32(self, "skip_count", "Number of skips since last sync")
        yield TimestampMac32(self, "last_skipped", "Time of the last skip")

