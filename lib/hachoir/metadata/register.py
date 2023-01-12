from hachoir.core.tools import (
    humanDuration, humanBitRate,
    humanFrequency, humanBitSize, humanFilesize,
    humanDatetime)
from hachoir.core.language import Language
from hachoir.metadata.filter import Filter, NumberFilter, DATETIME_FILTER
from datetime import date, datetime, timedelta
from hachoir.metadata.formatter import (
    humanAudioChannel, humanFrameRate, humanComprRate, humanAltitude,
    humanPixelSize, humanDPI)
from hachoir.metadata.setter import (
    setDatetime, setTrackNumber, setTrackTotal, setLanguage)
from hachoir.metadata.metadata_item import Data

MIN_SAMPLE_RATE = 1000              # 1 kHz
MAX_SAMPLE_RATE = 192000            # 192 kHz
MAX_NB_CHANNEL = 8                  # 8 channels
MAX_WIDTH = 20000                   # 20 000 pixels
MAX_BIT_RATE = 500 * 1024 * 1024    # 500 Mbit/s
MAX_HEIGHT = MAX_WIDTH
MAX_DPI_WIDTH = 10000
MAX_DPI_HEIGHT = MAX_DPI_WIDTH
MAX_NB_COLOR = 2 ** 24              # 16 million of color
MAX_BITS_PER_PIXEL = 256            # 256 bits/pixel
MAX_FRAME_RATE = 150                # 150 frame/sec
MAX_NB_PAGE = 20000
MAX_COMPR_RATE = 1000.0
MIN_COMPR_RATE = 0.001
MAX_TRACK = 999

DURATION_FILTER = Filter(timedelta,
                         timedelta(milliseconds=1),
                         timedelta(days=365))


def registerAllItems(meta):
    meta.register(Data("title", 100, "Title", type=str))
    meta.register(Data("artist", 101, "Artist", type=str))
    meta.register(Data("author", 102, "Author", type=str))
    meta.register(Data("music_composer", 103, "Music composer", type=str))

    meta.register(Data("album", 200, "Album", type=str))
    meta.register(Data("duration", 201, "Duration",
                       # integer in milliseconde
                       type=timedelta,
                       text_handler=humanDuration,
                       filter=DURATION_FILTER))
    meta.register(Data("nb_page", 202, "Nb page",
                       filter=NumberFilter(1, MAX_NB_PAGE)))
    meta.register(Data("music_genre", 203, "Music genre", type=str))
    meta.register(Data("language", 204, "Language",
                       conversion=setLanguage, type=Language))
    meta.register(Data("track_number", 205, "Track number",
                       conversion=setTrackNumber,
                       filter=NumberFilter(1, MAX_TRACK), type=int))
    meta.register(Data("track_total", 206, "Track total",
                       conversion=setTrackTotal,
                       filter=NumberFilter(1, MAX_TRACK), type=int))
    meta.register(Data("organization", 210, "Organization", type=str))
    meta.register(Data("version", 220, "Version"))

    meta.register(Data("width", 301, "Image width",
                       filter=NumberFilter(1, MAX_WIDTH),
                       type=int,
                       text_handler=humanPixelSize))
    meta.register(Data("height", 302, "Image height",
                       filter=NumberFilter(1, MAX_HEIGHT),
                       type=int,
                       text_handler=humanPixelSize))
    meta.register(Data("nb_channel", 303, "Channel",
                       text_handler=humanAudioChannel,
                       filter=NumberFilter(1, MAX_NB_CHANNEL),
                       type=int))
    meta.register(Data("sample_rate", 304, "Sample rate",
                       text_handler=humanFrequency,
                       filter=NumberFilter(MIN_SAMPLE_RATE, MAX_SAMPLE_RATE),
                       type=(int, float)))
    meta.register(Data("bits_per_sample", 305, "Bits/sample",
                       text_handler=humanBitSize,
                       filter=NumberFilter(1, 64), type=int))
    meta.register(Data("image_orientation", 306, "Image orientation"))
    meta.register(Data("nb_colors", 307, "Number of colors",
                       filter=NumberFilter(1, MAX_NB_COLOR), type=int))
    meta.register(Data("bits_per_pixel", 308, "Bits/pixel",
                       filter=NumberFilter(1, MAX_BITS_PER_PIXEL),
                       type=int))
    meta.register(Data("filename", 309, "File name", type=str))
    meta.register(Data("file_size", 310, "File size",
                       text_handler=humanFilesize,
                       type=int))
    meta.register(Data("pixel_format", 311, "Pixel format"))
    meta.register(Data("compr_size", 312, "Compressed file size",
                       text_handler=humanFilesize,
                       type=int))
    meta.register(Data("compr_rate", 313, "Compression rate",
                       text_handler=humanComprRate,
                       filter=NumberFilter(MIN_COMPR_RATE, MAX_COMPR_RATE),
                       type=(int, float)))

    meta.register(Data("width_dpi", 320, "Image DPI width",
                       filter=NumberFilter(1, MAX_DPI_WIDTH),
                       type=int,
                       text_handler=humanDPI))
    meta.register(Data("height_dpi", 321, "Image DPI height",
                       filter=NumberFilter(1, MAX_DPI_HEIGHT),
                       type=int,
                       text_handler=humanDPI))

    meta.register(Data("file_attr", 400, "File attributes"))
    meta.register(Data("file_type", 401, "File type"))
    meta.register(Data("subtitle_author", 402, "Subtitle author", type=str))

    meta.register(Data("creation_date", 500, "Creation date",
                       text_handler=humanDatetime,
                       filter=DATETIME_FILTER,
                       type=(datetime, date),
                       conversion=setDatetime))
    meta.register(Data("last_modification", 501, "Last modification",
                       text_handler=humanDatetime,
                       filter=DATETIME_FILTER,
                       type=(datetime, date),
                       conversion=setDatetime))
    meta.register(Data("latitude", 510, "Latitude", type=float))
    meta.register(Data("longitude", 511, "Longitude", type=float))
    meta.register(Data("altitude", 512, "Altitude", type=float,
                       text_handler=humanAltitude))
    meta.register(Data("location", 530, "Location", type=str))
    meta.register(Data("city", 531, "City", type=str))
    meta.register(Data("country", 532, "Country", type=str))
    meta.register(Data("charset", 540, "Charset", type=str))
    meta.register(Data("font_weight", 550, "Font weight"))

    meta.register(Data("camera_aperture", 520, "Camera aperture"))
    meta.register(Data("camera_focal", 521, "Camera focal"))
    meta.register(Data("camera_exposure", 522, "Camera exposure"))
    meta.register(Data("camera_brightness", 530, "Camera brightness"))
    meta.register(Data("camera_model", 531, "Camera model", type=str))
    meta.register(Data("camera_manufacturer", 532, "Camera manufacturer",
                       type=str))

    meta.register(Data("compression", 600, "Compression"))
    meta.register(Data("copyright", 601, "Copyright", type=str))
    meta.register(Data("url", 602, "URL", type=str))
    meta.register(Data("frame_rate", 603, "Frame rate",
                       text_handler=humanFrameRate,
                       filter=NumberFilter(1, MAX_FRAME_RATE),
                       type=(int, float)))
    meta.register(Data("bit_rate", 604, "Bit rate",
                       text_handler=humanBitRate,
                       filter=NumberFilter(1, MAX_BIT_RATE),
                       type=(int, float)))
    meta.register(Data("aspect_ratio", 604, "Aspect ratio",
                       type=(int, float)))
    meta.register(Data("thumbnail_size", 604, "Thumbnail size",
                       text_handler=humanFilesize,
                       type=(int, float)))

    meta.register(Data("iso_speed_ratings", 800, "ISO speed rating"))
    meta.register(Data("exif_version", 801, "EXIF version"))
    meta.register(Data("date_time_original", 802, "Date-time original",
                       text_handler=humanDatetime,
                       filter=DATETIME_FILTER,
                       type=(datetime, date), conversion=setDatetime))
    meta.register(Data("date_time_digitized", 803, "Date-time digitized",
                       text_handler=humanDatetime,
                       filter=DATETIME_FILTER,
                       type=(datetime, date), conversion=setDatetime))
    meta.register(Data("compressed_bits_per_pixel", 804, "Compressed bits per pixel",
                       type=(int, float)))
    meta.register(Data("shutter_speed_value", 805, "Shutter speed",
                       type=(int, float)))
    meta.register(Data("aperture_value", 806, "Aperture"))
    meta.register(Data("exposure_bias_value", 807, "Exposure bias"))
    meta.register(Data("focal_length", 808, "Focal length"))
    meta.register(Data("flashpix_version", 809, "Flashpix version"))
    meta.register(Data("focal_plane_x_resolution", 810, "Focal plane width"))
    meta.register(Data("focal_plane_y_resolution", 811, "Focal plane height",
                       type=float))
    meta.register(Data("focal_length_in_35mm_film", 812, "Focal length in 35mm film"))

    meta.register(Data("os", 900, "OS", type=str))
    meta.register(Data("producer", 901, "Producer", type=str))
    meta.register(Data("comment", 902, "Comment", type=str))
    meta.register(Data("format_version", 950, "Format version", type=str))
    meta.register(Data("mime_type", 951, "MIME type", type=str))
    meta.register(Data("endian", 952, "Endianness", type=str))
