# only the parsers that the video parsers and `hachoir.metadata.audio` import are kept
# upstream also imports itunesdb, midi, xm, s3m and mod here
from hachoir.parser.audio.aiff import AiffFile  # noqa
from hachoir.parser.audio.au import AuFile  # noqa
from hachoir.parser.audio.mpeg_audio import MpegAudioFile  # noqa
from hachoir.parser.audio.real_audio import RealAudioFile  # noqa
from hachoir.parser.audio.flac import FlacParser  # noqa
