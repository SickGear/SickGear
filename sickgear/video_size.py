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
the video object layer header of MPEG-4 video, the sequence parameter set of H.264, HEVC and H.266,
and the sequence header of AV1.

A RealMedia file (rm, rmvb) and a Windows TV file (wtv) hold the picture size in their stream header,
which the bundled hachoir does not read.
"""

import uuid

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Tuple

# a header is at the start of each group of pictures, a few megabytes hold several of them
READ_SIZE = 8 * 1024 * 1024

MPEG, MPEG4, H264, HEVC, VVC, AV1 = 'mpeg', 'mpeg4', 'h264', 'hevc', 'vvc', 'av1'
# stream types of a program map
TS_TYPES = {0x01: MPEG, 0x02: MPEG, 0x10: MPEG4, 0x1B: H264, 0x24: HEVC, 0x33: VVC}
# format identifier of the registration descriptor of a private stream (stream type 6),
# AV1 by the carriage of AV1 in MPEG-2 TS of the Alliance for Open Media
TS_REGISTRATION = {b'HEVC': HEVC, b'AV01': AV1}

# a wtv file starts with this id, its stream header has the media type of DirectShow: major type, sub type,
# 12 bytes, format type, size of the format, then the format
WTV_ID = uuid.UUID('2000d8b7-4937-11da-a64e-0007e95ead8d').bytes_le
WTV_VIDEO = uuid.UUID('73646976-0000-0010-8000-00aa00389b71').bytes_le
# a format of the copy protection filters ends with the sub type and format type of the format that it holds
WTV_PROTECTED = uuid.UUID('6739b36f-1d5f-4ac2-8192-28bb0e73d16a').bytes_le
# format types, with the place of the picture size in the format: a BITMAPINFOHEADER after a VIDEOINFOHEADER
# of 48 bytes or a VIDEOINFOHEADER2 of 72 bytes, the width and height follow its 4 bytes of size
WTV_FORMATS = {uuid.UUID('05589f80-c356-11ce-bf01-00aa0055595a').bytes_le: 48 + 4,
               uuid.UUID('f72a76a0-eb0a-11d0-ace4-0000c0cc16ba').bytes_le: 72 + 4,
               uuid.UUID('e06d80e3-db46-11cf-b4d1-00805f6cbbea').bytes_le: 72 + 4}


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


def mpeg4_size(data):
    # type: (bytes) -> Tuple[Optional[int], Optional[int]]
    """
    :param data: MPEG-4 Part 2 video, or a stream that holds it
    :return: width and height of the first video object layer header with a rectangular picture
    """
    pos = data.find(b'\x00\x00\x01')
    while -1 != pos and pos + 4 < len(data):
        if 0x20 <= data[pos + 3] <= 0x2F:
            try:
                bits = Bits(data[pos + 4:pos + 64])
                # random accessible flag, object type
                bits.skip(9)
                version = 1
                if bits.u(1):
                    version = bits.u(4)
                    bits.skip(3)
                if 15 == bits.u(4):
                    # width and height of a pixel
                    bits.skip(16)
                if bits.u(1):
                    # chroma format, low delay
                    bits.skip(3)
                    if bits.u(1):
                        # bit rate, buffer size and occupancy, with their marker bits
                        bits.skip(79)
                shape = bits.u(2)
                if 3 == shape and 1 != version:
                    bits.skip(4)
                marker = bits.u(1)
                resolution = bits.u(16)
                marker &= bits.u(1)
                if bits.u(1):
                    bits.skip(max(1, (resolution - 1).bit_length()))
                if 0 == shape and marker and bits.u(1):
                    width = bits.u(13)
                    if bits.u(1):
                        height = bits.u(13)
                        if bits.u(1) and width and height:
                            return width, height
            except IndexError:
                pass
        pos = data.find(b'\x00\x00\x01', pos + 3)
    return None, None


def av1_size(data):
    # type: (bytes) -> Tuple[Optional[int], Optional[int]]
    """
    :param data: AV1 video as open bitstream units, with or without start codes, or a stream that holds it
    :return: the most width and height of the first sequence header that can be read
    """
    if b'\x00\x00\x01\x12\x00' in data:
        # a start code is before each unit, and a byte 3 is put in after each two bytes of zero
        data = data.replace(b'\x00\x00\x01', b'').replace(b'\x00\x00\x03', b'\x00\x00')
    # a temporal unit starts with a delimiter, unit type 2 with a size of 0, a sequence header can follow it
    pos = data.find(b'\x12\x00')
    while -1 != pos and pos + 3 < len(data):
        header = data[pos + 2]
        if 1 == header >> 3 & 0xF and not header & 0x81:
            start = pos + 3 + (0, 1)[bool(header & 0x04)]
            if header & 0x02:
                # the size of the unit, a number of 7 bits per byte
                while start < len(data) and data[start] & 0x80:
                    start += 1
                start += 1
            try:
                bits = Bits(data[start:start + 128])
                # profile, still picture
                bits.skip(4)
                if bits.u(1):
                    # a reduced header has one level
                    bits.skip(5)
                else:
                    delay_bits = model = 0
                    if bits.u(1):
                        # timing info, the ticks of a picture
                        bits.skip(64)
                        if bits.u(1):
                            bits.ue()
                        model = bits.u(1)
                        if model:
                            delay_bits = bits.u(5) + 1
                            bits.skip(42)
                    display_delay = bits.u(1)
                    for _ in range(bits.u(5) + 1):
                        bits.skip(12)
                        if 7 < bits.u(5):
                            bits.skip(1)
                        if model and bits.u(1):
                            bits.skip(2 * delay_bits + 1)
                        if display_delay and bits.u(1):
                            bits.skip(4)
                width_bits, height_bits = bits.u(4) + 1, bits.u(4) + 1
                width, height = bits.u(width_bits) + 1, bits.u(height_bits) + 1
                if 16 <= width <= 16384 and 16 <= height <= 16384:
                    return width, height
            except (IndexError, ValueError):
                pass
        pos = data.find(b'\x12\x00', pos + 2)
    return None, None


def rm_size(data):
    # type: (bytes) -> Tuple[Optional[int], Optional[int]]
    """
    :param data: start of a RealMedia file
    :return: width and height of the first video stream
    """
    # chunks of an id, 4 bytes of size and 2 bytes of version, a stream header has the id MDPR
    pos = 0
    while pos + 10 <= len(data) and b'DATA' != data[pos:pos + 4]:
        size = int.from_bytes(data[pos + 4:pos + 8], 'big')
        if b'MDPR' == data[pos:pos + 4]:
            # the header of a video stream has the id VIDO, the codec, then 2 bytes each of width and height
            video = data.find(b'VIDO', pos, pos + size)
            if -1 != video and video + 12 <= len(data):
                width, height = (int.from_bytes(data[video + _p:video + _p + 2], 'big') for _p in (8, 10))
                if width and height:
                    return width, height
        if 10 > size:
            break
        pos += size
    return None, None


def wtv_size(data):
    # type: (bytes) -> Tuple[Optional[int], Optional[int]]
    """
    :param data: start of a wtv file
    :return: width and height of the first video stream header
    """
    pos = data.find(WTV_VIDEO)
    while -1 != pos and pos + 64 <= len(data):
        format_type = data[pos + 44:pos + 60]
        size = int.from_bytes(data[pos + 60:pos + 64], 'little')
        block = data[pos + 64:pos + 64 + size]
        if WTV_PROTECTED == format_type and 32 <= len(block):
            format_type, block = block[-16:], block[:-32]
        offset = WTV_FORMATS.get(format_type)
        if offset and offset + 8 <= len(block):
            width, height = (int.from_bytes(block[offset + _p:offset + _p + 4], 'little', signed=True)
                             for _p in (0, 4))
            # the height of a picture that is stored from the top row is negative
            if width and height:
                return width, abs(height)
        pos = data.find(WTV_VIDEO, pos + 16)
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


def vvc_sps_size(sps):
    # type: (bytes) -> Tuple[int, int]
    """
    :param sps: sequence parameter set of H.266 after its two byte header
    :return: width and height of the picture after cropping
    """
    bits = Bits(sps)
    # parameter set ids
    bits.skip(8)
    sub_layers = bits.u(3)
    chroma = bits.u(2)
    bits.skip(2)
    if bits.u(1):
        # profile, tier and level: 16 bits, frame only and multilayer flags
        bits.skip(18)
        if bits.u(1):
            # 71 bits of general constraints, then a count of more bits
            bits.skip(71)
            bits.skip(bits.u(8))
        bits.skip(-bits.pos % 8)
        levels = [bits.u(1) for _ in range(sub_layers)]
        bits.skip(-bits.pos % 8)
        bits.skip(8 * sum(levels))
        bits.skip(32 * bits.u(8))
    # gradual decoding refresh
    bits.skip(1)
    if bits.u(1):
        bits.skip(1)
    width, height = bits.ue(), bits.ue()
    if bits.u(1):
        left, right, top, bottom = bits.ue(), bits.ue(), bits.ue(), bits.ue()
        width -= (1, 2, 2, 1)[chroma] * (left + right)
        height -= (1, 2, 1, 1)[chroma] * (top + bottom)
    return width, height


# per codec: bytes of the unit header, a test of the header for a sequence parameter set, the reader of the set
NAL_TYPES = {H264: (1, lambda _h: 7 == _h[0] & 0x1F, h264_sps_size),
             HEVC: (2, lambda _h: 33 == _h[0] >> 1 & 0x3F, hevc_sps_size),
             VVC: (2, lambda _h: 15 == _h[1] >> 3, vvc_sps_size)}


def nal_size(data, codec):
    # type: (bytes, AnyStr) -> Tuple[Optional[int], Optional[int]]
    """
    :param data: H.264, HEVC or H.266 video with start codes, or a stream that holds it
    :param codec: H264, HEVC or VVC
    :return: width and height of the first sequence parameter set that can be read
    """
    header_size, is_sps, read_size = NAL_TYPES[codec]
    pos = data.find(b'\x00\x00\x01')
    while -1 != pos and pos + 5 < len(data):
        following = data.find(b'\x00\x00\x01', pos + 3)
        header = data[pos + 3:pos + 5]
        if not header[0] & 0x80 and is_sps(header):
            # a parameter set has a byte 3 put in after each two bytes of zero, take those out
            unit = data[pos + 3 + header_size:(following, pos + 1024)[-1 == following]]
            try:
                width, height = read_size(unit.replace(b'\x00\x00\x03', b'\x00\x00'))
                if 16 <= width <= 16384 and 16 <= height <= 16384:
                    return width, height
            except (IndexError, ValueError):
                pass
        pos = following
    return None, None


def ts_packets(data):
    # type: (bytes) -> Tuple[Optional[int], Optional[int]]
    """
    :param data: start of an MPEG transport stream
    :return: place of the first packet and the size of a packet, or None for both when the data is not a stream
    """
    # a packet is 188 bytes and starts with byte 0x47, in an m2ts file each has 4 bytes of time code before it
    for cur_size in (188, 192):
        start = next((_s for _s in range(min(2 * cur_size, len(data) - 3 * cur_size))
                      if all(0x47 == data[_s + _n * cur_size] for _n in range(4))), None)
        if None is not start:
            return start, cur_size
    return None, None


def ts_video(data):
    # type: (bytes) -> Tuple[Optional[AnyStr], bytes]
    """
    :param data: start of an MPEG transport stream
    :return: codec of the first video stream of the first program, and the data of that stream
    """
    start, size = ts_packets(data)
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
    :param filename: path of a ts, m2ts, mpg, vob, rm, rmvb or wtv file
    :return: width and height of its video, or None for both when they are not found
    """
    try:
        with open(filename, 'rb') as fh:
            data = fh.read(4096)
            # read more of a file only when its start is of a format that is read here
            if not (data.lstrip(b'\x00').startswith(b'\x01\xba') or data.startswith((b'.RMF', WTV_ID))
                    or None is not ts_packets(data)[0]):
                return None, None
            data += fh.read(READ_SIZE - len(data))
        if data.lstrip(b'\x00').startswith(b'\x01\xba'):
            # a program stream starts with a pack header, it holds MPEG-1 or MPEG-2 video
            return mpeg_size(data)
        if data.startswith(b'.RMF'):
            return rm_size(data)
        if data.startswith(WTV_ID):
            return wtv_size(data)
        codec, video = ts_video(data)
        if MPEG == codec:
            return mpeg_size(video)
        if MPEG4 == codec:
            return mpeg4_size(video)
        if AV1 == codec:
            return av1_size(video)
        if codec:
            return nal_size(video, codec)
    except (IndexError, ValueError, OSError):
        pass
    return None, None
