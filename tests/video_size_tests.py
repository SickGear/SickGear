import os
import sys
import tempfile
import unittest
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from sickgear import video_size
from sickgear.common import Quality

# the first bytes of sequence parameter sets that ffmpeg made, with the picture size that ffprobe reports for them
H264_1080 = '6742c028da01e0089f97'
H264_1080_INTERLACED = '674d4028f403c0227ef0'
HEVC_2160 = '420101022000000300900000030000030096a001e020021c4d'
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
]
# sequence header of MPEG-2 video: 1440 x 1080
MPEG_1440 = '000001b35a043823ffffe018'


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

    def test_files(self):
        hevc_registration = bytes([0x0A, 1, 0, 5, 4]) + b'HEVC'
        with tempfile.TemporaryDirectory() as temp_dir:
            for cur_name, cur_data, cur_size, cur_quality in [
                ('h264.ts', ts_file(0x1B, unit(H264_1080)), (1920, 1080), Quality.FULLHDTV),
                ('h264.m2ts', ts_file(0x1B, unit(H264_1080), m2ts=True), (1920, 1080), Quality.FULLHDTV),
                ('interlaced.ts', ts_file(0x1B, unit(H264_1080_INTERLACED)), (1920, 1080), Quality.FULLHDTV),
                ('hevc.ts', ts_file(0x24, unit(HEVC_2160)), (3840, 2160), Quality.UHD4KWEB),
                # a private stream with a registration descriptor that names HEVC, after another descriptor
                ('private.ts', ts_file(6, unit(HEVC_2160), hevc_registration), (3840, 2160), Quality.UHD4KWEB),
                ('mpeg2.ts', ts_file(2, bytes.fromhex(MPEG_1440)), (1440, 1080), Quality.FULLHDTV),
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
