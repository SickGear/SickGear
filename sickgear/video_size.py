#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

"""
Picture size of a video, read from its video data.

An MPEG transport stream (ts, m2ts) and an MPEG program stream (mpg, vob) do not hold the picture size,
it is only in the headers of the video itself: the sequence header of MPEG-1 and MPEG-2 video,
and the sequence parameter set of H.264 and HEVC.
"""

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Tuple

# a header is at the start of each group of pictures, a few megabytes hold several of them
READ_SIZE = 8 * 1024 * 1024

MPEG, H264, HEVC = 'mpeg', 'h264', 'hevc'
# stream types of a program map
TS_TYPES = {0x01: MPEG, 0x02: MPEG, 0x1B: H264, 0x24: HEVC}
# format identifier of the registration descriptor of a private stream (stream type 6)
TS_REGISTRATION = {b'HEVC': HEVC}


class Bits(object):
    """read bits of bytes, first bit first"""

    def __init__(self, data):
        # type: (bytes) -> None
        self.data = data
        self.pos = 0

    def skip(self, count):
        # type: (int) -> None
        self.pos += count

    def u(self, count):
        # type: (int) -> int
        """unsigned number of count bits, IndexError when the data ends"""
        value = 0
        for _ in range(count):
            value = value << 1 | self.data[self.pos >> 3] >> (7 - (self.pos & 7)) & 1
            self.pos += 1
        return value

    def ue(self):
        # type: (...) -> int
        """unsigned Exp-Golomb number"""
        zeros = 0
        while not self.u(1):
            zeros += 1
            if 32 < zeros:
                raise ValueError('not an Exp-Golomb number')
        return (1 << zeros) - 1 + self.u(zeros)

    def se(self):
        # type: (...) -> int
        """signed Exp-Golomb number"""
        value = self.ue()
        return (value + 1) // 2 * (-1, 1)[value & 1]


def mpeg_size(data):
    # type: (bytes) -> Tuple[Optional[int], Optional[int]]
    """
    :param data: MPEG-1 or MPEG-2 video, or a stream that holds it
    :return: width and height of the first sequence header
    """
    pos = data.find(b'\x00\x00\x01\xb3')
    while -1 != pos and pos + 11 < len(data):
        head = data[pos + 4:pos + 12]
        width, height = head[0] << 4 | head[1] >> 4, (head[1] & 0xF) << 8 | head[2]
        # MPEG-4 video uses this start code for another header, so check the fields:
        # an aspect ratio code of 1 to 14, a frame rate code of 1 to 8, and the marker bit
        if width and height and 1 <= head[3] >> 4 <= 14 and 1 <= head[3] & 0xF <= 8 and head[6] & 0x20:
            return width, height
        pos = data.find(b'\x00\x00\x01\xb3', pos + 4)
    return None, None


def h264_sps_size(sps):
    # type: (bytes) -> Tuple[int, int]
    """
    :param sps: sequence parameter set of H.264 after its one byte header
    :return: width and height of the picture after cropping
    """
    bits = Bits(sps)
    profile = bits.u(8)
    # constraint flags, level
    bits.skip(16)
    bits.ue()
    chroma = 1
    if profile in (44, 83, 86, 100, 110, 118, 122, 128, 134, 135, 138, 139, 244):
        chroma = bits.ue()
        if 3 == chroma and bits.u(1):
            # separate colour planes are cropped as a picture with no chroma
            chroma = 0
        bits.ue()
        bits.ue()
        bits.skip(1)
        if bits.u(1):
            for cur_list in range((8, 12)[3 == chroma]):
                if bits.u(1):
                    last = following = 8
                    for _ in range((16, 64)[6 <= cur_list]):
                        if following:
                            following = (last + bits.se() + 256) % 256
                        last = following or last
    bits.ue()
    order_type = bits.ue()
    if 0 == order_type:
        bits.ue()
    elif 1 == order_type:
        bits.skip(1)
        bits.se()
        bits.se()
        for _ in range(bits.ue()):
            bits.se()
    bits.ue()
    bits.skip(1)
    width = 16 * (bits.ue() + 1)
    height = 16 * (bits.ue() + 1)
    # a picture of two fields has its height counted per field
    fields = 2 - bits.u(1)
    height *= fields
    if 2 == fields:
        bits.skip(1)
    bits.skip(1)
    if bits.u(1):
        left, right, top, bottom = bits.ue(), bits.ue(), bits.ue(), bits.ue()
        width -= (1, 2, 2, 1)[chroma] * (left + right)
        height -= (1, 2, 1, 1)[chroma] * fields * (top + bottom)
    return width, height


def hevc_sps_size(sps):
    # type: (bytes) -> Tuple[int, int]
    """
    :param sps: sequence parameter set of HEVC after its two byte header
    :return: width and height of the picture after cropping
    """
    bits = Bits(sps)
    bits.skip(4)
    sub_layers = bits.u(3)
    bits.skip(1)
    # profile, tier and level: 88 bits of profile and 8 bits of level
    bits.skip(96)
    present = [(bits.u(1), bits.u(1)) for _ in range(sub_layers)]
    if sub_layers:
        bits.skip(2 * (8 - sub_layers))
    for cur_profile, cur_level in present:
        bits.skip(88 * cur_profile + 8 * cur_level)
    bits.ue()
    chroma = bits.ue()
    if 3 == chroma:
        bits.skip(1)
    width, height = bits.ue(), bits.ue()
    if bits.u(1):
        left, right, top, bottom = bits.ue(), bits.ue(), bits.ue(), bits.ue()
        width -= (1, 2, 2, 1)[chroma] * (left + right)
        height -= (1, 2, 1, 1)[chroma] * (top + bottom)
    return width, height


def nal_size(data, codec):
    # type: (bytes, AnyStr) -> Tuple[Optional[int], Optional[int]]
    """
    :param data: H.264 or HEVC video with start codes, or a stream that holds it
    :param codec: H264 or HEVC
    :return: width and height of the first sequence parameter set that can be read
    """
    pos = data.find(b'\x00\x00\x01')
    while -1 != pos and pos + 4 < len(data):
        following = data.find(b'\x00\x00\x01', pos + 3)
        header = data[pos + 3]
        if not header & 0x80 and (7 == header & 0x1F if H264 == codec else 33 == header >> 1 & 0x3F):
            # a parameter set has a byte 3 put in after each two bytes of zero, take those out
            unit = data[pos + 3 + (1, 2)[HEVC == codec]:(following, pos + 1024)[-1 == following]]
            try:
                read_size = (h264_sps_size, hevc_sps_size)[HEVC == codec]
                width, height = read_size(unit.replace(b'\x00\x00\x03', b'\x00\x00'))
                if 16 <= width <= 16384 and 16 <= height <= 16384:
                    return width, height
            except (IndexError, ValueError):
                pass
        pos = following
    return None, None


def ts_video(data):
    # type: (bytes) -> Tuple[Optional[AnyStr], bytes]
    """
    :param data: start of an MPEG transport stream
    :return: codec of the first video stream of the first program, and the data of that stream
    """
    # a packet is 188 bytes and starts with byte 0x47, in an m2ts file each has 4 bytes of time code before it
    start = size = None
    for cur_size in (188, 192):
        start = next((_s for _s in range(min(2 * cur_size, len(data) - 3 * cur_size))
                      if all(0x47 == data[_s + _n * cur_size] for _n in range(4))), None)
        if None is not start:
            size = cur_size
            break
    if None is size:
        return None, b''

    def packets():
        for cur_pos in range(start, len(data) - 187, size):
            if 0x47 != data[cur_pos]:
                continue
            # bit 0x10 of the fourth byte: the packet has a payload, bit 0x20: fill bytes come before it
            payload_pos = cur_pos + 4 + (0, 1 + data[cur_pos + 4])[bool(data[cur_pos + 3] & 0x20)]
            if data[cur_pos + 3] & 0x10 and payload_pos < cur_pos + 188:
                yield ((data[cur_pos + 1] & 0x1F) << 8 | data[cur_pos + 2], data[cur_pos + 1] & 0x40,
                       data[payload_pos:cur_pos + 188])

    map_pid = video_pid = codec = None
    for cur_pid, cur_start, cur_payload in packets():
        if not cur_start or cur_pid not in (0, map_pid) or len(cur_payload) < 13 + cur_payload[0]:
            continue
        # a table starts after a pointer byte: table id, 12 bits of length, 5 more bytes of header
        table = cur_payload[1 + cur_payload[0]:]
        end = min(len(table), 3 + ((table[1] & 0xF) << 8 | table[2]) - 4)
        if 0 == cur_pid and 0 == table[0]:
            # program number 0 gives the PID of the network table, not of a program map
            map_pid = next(((table[_p + 2] & 0x1F) << 8 | table[_p + 3] for _p in range(8, end - 3, 4)
                            if table[_p] or table[_p + 1]), None)
        elif cur_pid == map_pid and 2 == table[0]:
            pos = 12 + ((table[10] & 0xF) << 8 | table[11])
            while pos + 5 <= end:
                info = (table[pos + 3] & 0xF) << 8 | table[pos + 4]
                codec = TS_TYPES.get(table[pos])
                if 6 == table[pos]:
                    descriptors = table[pos + 5:pos + 5 + info]
                    while 6 <= len(descriptors) and not codec:
                        if 5 == descriptors[0]:
                            codec = TS_REGISTRATION.get(descriptors[2:6])
                        descriptors = descriptors[2 + descriptors[1]:]
                if codec:
                    video_pid = (table[pos + 1] & 0x1F) << 8 | table[pos + 2]
                    break
                pos += 5 + info
            break
    if None is video_pid:
        return None, b''
    return codec, b''.join(_payload for _pid, _start, _payload in packets() if _pid == video_pid)


def video_size(filename):
    # type: (AnyStr) -> Tuple[Optional[int], Optional[int]]
    """
    :param filename: path of a ts, m2ts, mpg or vob file
    :return: width and height of its video, or None for both when they are not found
    """
    try:
        with open(filename, 'rb') as fh:
            data = fh.read(READ_SIZE)
        if data.lstrip(b'\x00').startswith(b'\x01\xba'):
            # a program stream starts with a pack header, it holds MPEG-1 or MPEG-2 video
            return mpeg_size(data)
        codec, video = ts_video(data)
        if MPEG == codec:
            return mpeg_size(video)
        if codec:
            return nal_size(video, codec)
    except (IndexError, ValueError, OSError):
        pass
    return None, None
