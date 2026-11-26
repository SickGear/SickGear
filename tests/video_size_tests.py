import os
import sys
import tempfile
import unittest
import uuid
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from sickgear import video_size
from sickgear.common import Quality

# the first bytes of sequence parameter sets that ffmpeg made, with the picture size that ffprobe reports for them
H264_1080 = '6742c028da01e0089f97'
H264_1080_INTERLACED = '674d4028f403c0227ef0'
HEVC_2160 = '420101022000000300900000030000030096a001e020021c4d'
# libvvenc
VVC_1080 = '007900ad0240800000800f02004391a801cdd36e991a4526f384d958c10209c00ca0c5'
PARAMETER_SETS = [
    (video_size.H264, H264_1080, (1920, 1080)),
    (video_size.H264, H264_1080_INTERLACED, (1920, 1080)),
    # 4:2:2 with 10 bits
    (video_size.H264, '677a0028b6cb403c0113f138', (1920, 1080)),
    # 4:4:4
    (video_size.H264, '67f4001f9196805005bb', (1280, 720)),
    (video_size.H264, '6764001facd9405005bb', (1280, 720)),
    (video_size.H264, '6742c01ed900a02ff970', (640, 360)),
    # a size that is not a multiple of 16, the picture is cropped
    (video_size.H264, '6742c028da01e0089ee7', (1916, 1076)),
    (video_size.HEVC, HEVC_2160, (3840, 2160)),
    (video_size.HEVC, '420101016000000300900000030000030078a003c080110773e5', (1916, 1076)),
    # 4:2:2 with 10 bits
    (video_size.HEVC, '4201010408000003009d08000003000078b003c0801107c4b6', (1920, 1080)),
    (video_size.HEVC, '42010101600000030090000003000003005da0028080221f2e', (1280, 536)),
    (video_size.VVC, VVC_1080, (1920, 1080)),
    # general constraint info, levels of two sub layers, a sub profile, and a conformance window of 8 rows,
    # ffprobe reports this size for the set in a stream of libvvenc
    (video_size.VVC, '007900ad0240a20000030000030000030000030180a033200112345678800f0200439f28', (1920, 1072)),
]
# sequence header of MPEG-2 video: 1440 x 1080
MPEG_1440 = '000001b35a043823ffffe018'
# video object layer headers of MPEG-4 video, from ffmpeg, and one with all the optional fields before the size
MPEG4_HEADERS = [
    ('0000012000c48d8800cd3c04871443000001b24c', (1920, 1080)),
    ('0000012000c48d8800cd1684481443000001b24c', (720, 576)),
    ('0000012000c8f8805d4032400040644032800097530c1f4cb4121c507f', (1440, 1080)),
]
# a temporal delimiter and a sequence header of AV1: libsvtav1, libaom, timing info and two operating points
# (ffprobe reports this size for it in a stream of libsvtav1), a decoder model with its operating parameters
AV1_1080 = '12000a0c02000042955dfe1b8d5f3008'
AV1_HEADERS = [
    (AV1_1080, (1920, 1080)),
    ('12000a0e2000002d4cffb3ccaf92021a0040', (1280, 720)),
    ('12000a130400000fa40003a983420009cc0008aaeff0dc', (1920, 1080)),
    ('12000a1d0400000fa40003a9814800001f41090881a7014064c40485d77fe47000', (3840, 1608)),
]


def rm_file(width, height):
    """a RealMedia file with an audio stream and a video stream"""
    def chunk(chunk_id, data):
        return chunk_id + (10 + len(data)).to_bytes(4, 'big') + bytes(2) + data

    def stream(name, mime, data):
        return chunk(b'MDPR', bytes(30) + bytes([len(name)]) + name + bytes([len(mime)]) + mime
                     + len(data).to_bytes(4, 'big') + data)

    video = b'VIDO' + b'RV40' + width.to_bytes(2, 'big') + height.to_bytes(2, 'big') + bytes(14)
    return (chunk(b'.RMF', bytes(8)) + chunk(b'PROP', bytes(40))
            + stream(b'Audio', b'audio/x-pn-realaudio', b'.ra\xfd' + bytes(60))
            + stream(b'Video', b'video/x-pn-realvideo', (4 + len(video)).to_bytes(4, 'big') + video)
            + chunk(b'DATA', bytes(64)))


def wtv_file(width, height, format_type=None, protected=True):
    """a wtv file with a stream header of a video stream, by default MPEG-2 in a format of the copy protection"""
    format_type = format_type or uuid.UUID('e06d80e3-db46-11cf-b4d1-00805f6cbbea').bytes_le
    header_size = (72, 48)[uuid.UUID('05589f80-c356-11ce-bf01-00aa0055595a').bytes_le == format_type]
    # a VIDEOINFOHEADER or VIDEOINFOHEADER2 then a BITMAPINFOHEADER
    block = bytes(header_size) + (40).to_bytes(4, 'little') + width.to_bytes(4, 'little', signed=True) \
        + height.to_bytes(4, 'little', signed=True) + bytes(28)
    sub_type = uuid.UUID('e06d8026-db46-11cf-b4d1-00805f6cbbea').bytes_le
    if protected:
        block += sub_type + format_type
        sub_type, format_type = uuid.UUID('46adbd28-6fd0-4796-93b2-155c51dc048d').bytes_le, video_size.WTV_PROTECTED
    return video_size.WTV_ID + bytes(4096) + video_size.WTV_VIDEO + sub_type + bytes(12) + format_type \
        + len(block).to_bytes(4, 'little') + block + bytes(256)


def ts_packet(pid, payload):
    """a transport stream packet that starts a payload"""
    packet = bytes([0x47, 0x40 | pid >> 8, pid & 0xFF, 0x10]) + payload
    return packet + bytes([0xFF]) * (188 - len(packet))


def ts_table(pid, table_id, data):
    """a packet with one table, its 4 bytes of CRC are not checked"""
    size = 5 + len(data) + 4
    return ts_packet(pid, bytes([0, table_id, 0xB0 | size >> 8, size & 0xFF, 0, 1, 0xC1, 0, 0]) + data + bytes(4))


def ts_file(stream_type, video, descriptors=bytes(), m2ts=False):
    """a transport stream with one program that has one video stream and one audio stream"""
    packets = [
        # program number 0 gives the PID of the network table, program number 1 the PID of the program map
        ts_table(0, 0, bytes([0, 0, 0xE0, 0x10, 0, 1, 0xF0, 0x00])),
        ts_table(0x1000, 2, bytes([0xE1, 0, 0xF0, 0, stream_type, 0xE1, 0, 0xF0, len(descriptors)]) + descriptors
                 + bytes([0x0F, 0xE1, 1, 0xF0, 0])),
        # the start of a packet of the video stream, with a 9 byte header
        ts_packet(0x100, bytes([0, 0, 1, 0xE0, 0, 0, 0x80, 0, 0]) + video),
    ] + 8 * [bytes([0x47, 0x1F, 0xFF, 0x10]) + bytes([0xFF]) * 184]
    return b''.join(bytes(4 * m2ts) + _p for _p in packets)


def unit(hex_text):
    return bytes([0, 0, 0, 1]) + bytes.fromhex(hex_text) + bytes([0, 0, 0, 1, 0x68])


class VideoSizeTests(unittest.TestCase):
    def test_parameter_sets(self):
        for cur_codec, cur_hex, cur_size in PARAMETER_SETS:
            self.assertEqual(cur_size, video_size.nal_size(unit(cur_hex), cur_codec), msg=cur_hex)
        # a parameter set that ends too early gives no size and no error
        self.assertEqual((None, None), video_size.nal_size(unit(H264_1080[:8]), video_size.H264))
        self.assertEqual((None, None), video_size.nal_size(bytes(64), video_size.HEVC))

    def test_mpeg_sequence_header(self):
        self.assertEqual((1440, 1080), video_size.mpeg_size(bytes(20) + bytes.fromhex(MPEG_1440) + bytes(8)))
        # the start code with fields that are not valid, as MPEG-4 video has it, then a valid header
        self.assertEqual((1440, 1080), video_size.mpeg_size(
            bytes([0, 0, 1, 0xB3]) + bytes(8) + bytes.fromhex(MPEG_1440) + bytes(8)))
        self.assertEqual((None, None), video_size.mpeg_size(bytes([0, 0, 1, 0xB3]) + bytes(8)))
        self.assertEqual((None, None), video_size.mpeg_size(bytes(64)))

    def test_mpeg4_header(self):
        for cur_hex, cur_size in MPEG4_HEADERS:
            self.assertEqual(cur_size, video_size.mpeg4_size(bytes(20) + bytes.fromhex(cur_hex) + bytes(8)),
                             msg=cur_hex)
        # an MPEG-2 sequence header is not read, a header that ends too early gives no size and no error
        self.assertEqual((None, None), video_size.mpeg4_size(bytes.fromhex(MPEG_1440) + bytes(8)))
        self.assertEqual((None, None), video_size.mpeg4_size(bytes.fromhex(MPEG4_HEADERS[0][0][:20])))
        self.assertEqual((None, None), video_size.mpeg4_size(bytes(64)))

    def test_av1_sequence_header(self):
        for cur_hex, cur_size in AV1_HEADERS:
            self.assertEqual(cur_size, video_size.av1_size(bytes.fromhex(cur_hex) + bytes(8)), msg=cur_hex)
        # the format with start codes
        with_start_codes = bytes([0, 0, 1, 0x12, 0, 0, 0, 1]) + bytes.fromhex(AV1_1080)[2:]
        self.assertEqual((1920, 1080), video_size.av1_size(with_start_codes))
        # a unit of another type after the delimiter, then a sequence header in the next temporal unit
        self.assertEqual((1920, 1080), video_size.av1_size(bytes.fromhex('12003200') + bytes.fromhex(AV1_1080)))
        self.assertEqual((None, None), video_size.av1_size(bytes.fromhex(AV1_1080)[:8]))
        self.assertEqual((None, None), video_size.av1_size(bytes(64)))

    def test_stream_headers(self):
        self.assertEqual((1280, 720), video_size.rm_size(rm_file(1280, 720)))
        self.assertEqual((None, None), video_size.rm_size(rm_file(1280, 720)[:200]))
        # a format of the copy protection, a VIDEOINFOHEADER2, a VIDEOINFOHEADER, a height that is negative
        self.assertEqual((1920, 1080), video_size.wtv_size(wtv_file(1920, 1080)))
        self.assertEqual((1280, 720), video_size.wtv_size(wtv_file(1280, 720, protected=False)))
        self.assertEqual((720, 576), video_size.wtv_size(wtv_file(
            720, -576, uuid.UUID('05589f80-c356-11ce-bf01-00aa0055595a').bytes_le, protected=False)))
        # a format type that is not known
        self.assertEqual((None, None), video_size.wtv_size(wtv_file(1920, 1080, bytes(16))))
        self.assertEqual((None, None), video_size.wtv_size(wtv_file(1920, 1080)[:4200]))

    def test_files(self):
        hevc_registration = bytes([0x0A, 1, 0, 5, 4]) + b'HEVC'
        av1_registration = bytes([5, 4]) + b'AV01'
        with tempfile.TemporaryDirectory() as temp_dir:
            for cur_name, cur_data, cur_size, cur_quality in [
                ('h264.ts', ts_file(0x1B, unit(H264_1080)), (1920, 1080), Quality.FULLHDTV),
                ('h264.m2ts', ts_file(0x1B, unit(H264_1080), m2ts=True), (1920, 1080), Quality.FULLHDTV),
                ('interlaced.ts', ts_file(0x1B, unit(H264_1080_INTERLACED)), (1920, 1080), Quality.FULLHDTV),
                ('hevc.ts', ts_file(0x24, unit(HEVC_2160)), (3840, 2160), Quality.UHD4KWEB),
                # a private stream with a registration descriptor that names HEVC, after another descriptor
                ('private.ts', ts_file(6, unit(HEVC_2160), hevc_registration), (3840, 2160), Quality.UHD4KWEB),
                ('mpeg2.ts', ts_file(2, bytes.fromhex(MPEG_1440)), (1440, 1080), Quality.FULLHDTV),
                ('mpeg4.ts', ts_file(0x10, bytes.fromhex(MPEG4_HEADERS[1][0])), (720, 576), Quality.SDTV),
                ('vvc.ts', ts_file(0x33, unit(VVC_1080)), (1920, 1080), Quality.FULLHDTV),
                ('vvc.m2ts', ts_file(0x33, unit(VVC_1080), m2ts=True), (1920, 1080), Quality.FULLHDTV),
                ('av1.ts', ts_file(6, bytes.fromhex(AV1_1080), av1_registration), (1920, 1080), Quality.FULLHDTV),
                # AV1 as ffmpeg writes it, a private stream with no descriptor
                ('av1_ffmpeg.ts', ts_file(6, bytes.fromhex(AV1_1080)), (None, None), Quality.UNKNOWN),
                ('rv40.rmvb', rm_file(1280, 720), (1280, 720), Quality.HDTV),
                ('mpeg2.wtv', wtv_file(1920, 1080), (1920, 1080), Quality.FULLHDTV),
                # bytes before the first packet
                ('late.ts', bytes(range(1, 100)) + ts_file(0x1B, unit(H264_1080)), (1920, 1080), None),
                # the program map names H.264 and the video data has no parameter set
                ('no_set.ts', ts_file(0x1B, bytes(32)), (None, None), Quality.UNKNOWN),
                # a private stream with no descriptor is not video
                ('no_video.ts', ts_file(6, unit(HEVC_2160)), (None, None), Quality.UNKNOWN),
                # a program stream starts with a pack header
                ('mpeg2.vob', bytes([0, 0, 1, 0xBA]) + bytes(10) + bytes([0, 0, 1, 0xE0, 0, 0])
                 + bytes.fromhex(MPEG_1440) + bytes(64), (1440, 1080), None),
                ('text.ts', b'not a video', (None, None), None),
                ('empty.ts', b'', (None, None), None),
            ]:
                filename = os.path.join(temp_dir, cur_name)
                with open(filename, 'wb') as fh:
                    fh.write(cur_data)
                self.assertEqual(cur_size, video_size.video_size(filename), msg=cur_name)
                if None is not cur_quality:
                    self.assertEqual(cur_quality, Quality.file_quality(filename), msg=cur_name)
            self.assertEqual((None, None), video_size.video_size(os.path.join(temp_dir, 'no_file.ts')))


if '__main__' == __name__:
    suite = unittest.TestLoader().loadTestsFromTestCase(VideoSizeTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
