from hachoir.field import MissingField
from hachoir.metadata.metadata import (registerExtractor,
                                       Metadata, RootMetadata, MultipleMetadata)
from hachoir.metadata.metadata_item import QUALITY_GOOD
from hachoir.metadata.safe import fault_tolerant
from hachoir.parser.video import AsfFile, FlvFile
from hachoir.parser.video.asf import Descriptor as ASF_Descriptor
from hachoir.parser.container import MkvFile, MP4File
from hachoir.parser.video.mpeg_ts import (MPEG_TS, TS_Audio_stream_types, TS_Elementary_stream_types,
                                          TS_Video_stream_types)
from hachoir.parser.video.mpeg_video import MPEGVideoFile  # noqa
from hachoir.parser.container.mp4 import mp4_codecs, mp4_fourcc
from hachoir.parser.container.mkv import dateToDatetime
from hachoir.core.tools import makeUnicode, makePrintable, timedelta2seconds
from datetime import timedelta


class MkvMetadata(MultipleMetadata):
    tag_key = {
        "TITLE": "title",
        "URL": "url",
        "COPYRIGHT": "copyright",

        # TODO: use maybe another name?
        # Its value may be different than (...)/Info/DateUTC/date
        "DATE_RECORDED": "creation_date",

        # TODO: Extract subtitle metadata
        "SUBTITLE": "subtitle_author",
    }

    def extract(self, mkv):
        for segment in mkv.array("Segment"):
            self.processSegment(segment)

    def processSegment(self, segment):
        for field in segment:
            if field.name.startswith("Info["):
                self.processInfo(field)
            elif field.name.startswith("Tags["):
                for tag in field.array("Tag"):
                    self.processTag(tag)
            elif field.name.startswith("Tracks["):
                self.processTracks(field)
            elif field.name.startswith("Cluster["):
                if self.quality < QUALITY_GOOD:
                    return

    def processTracks(self, tracks):
        track_counter = {'audio': 1, 'video': 1, 'sub': 1}
        for entry in tracks.array("TrackEntry"):
            self.processTrack(entry, track_counter)

    def processTrack(self, track, track_counter):
        if "TrackType/enum" not in track:
            return
        if track["TrackType/enum"].display == "video":
            self.processVideo(track, track_counter)
        elif track["TrackType/enum"].display == "audio":
            self.processAudio(track, track_counter)
        elif track["TrackType/enum"].display == "subtitle":
            self.processSubtitle(track, track_counter)

    def trackCommon(self, track, meta):
        if "Name/unicode" in track:
            meta.title = track["Name/unicode"].value
        if "Language/string" in track:
            meta.language = track["Language/string"].value
        else:
            meta.language = "eng"

    def processVideo(self, track, track_counter):
        video = Metadata(self)
        self.trackCommon(track, video)
        try:
            codec = track["CodecID/string"].value
            if 'V_MS/VFW/FOURCC' == codec and "CodecPrivate/binary" in track:
                # the private data is a BITMAPINFOHEADER, its bytes 16 to 19 are the fourcc, e.g. WVC1 for VC-1
                fourcc = track["CodecPrivate/binary"].value[16:20].decode('ascii', 'replace')
                if 4 == len(fourcc):
                    codec = f'{codec} ({fourcc})'
            video.compression = codec
            if "Video" in track:
                video.width = track["Video/PixelWidth/unsigned"].value
                video.height = track["Video/PixelHeight/unsigned"].value
        except MissingField:
            pass
        self.addGroup(f'video[{track_counter["video"]}]', video, f'Video stream #{track_counter["video"]}')
        track_counter['video'] += 1

    def getDouble(self, field, parent):
        float_key = '%s/float' % parent
        if float_key in field:
            return field[float_key].value
        double_key = '%s/double' % parent
        if double_key in field:
            return field[double_key].value
        return None

    def processAudio(self, track, track_counter):
        audio = Metadata(self)
        self.trackCommon(track, audio)
        if "Audio" in track:
            frequency = self.getDouble(track, "Audio/SamplingFrequency")
            if frequency is not None:
                audio.sample_rate = frequency
            if "Audio/Channels/unsigned" in track:
                audio.nb_channel = track["Audio/Channels/unsigned"].value
            if "Audio/BitDepth/unsigned" in track:
                audio.bits_per_sample = track["Audio/BitDepth/unsigned"].value
        if "CodecID/string" in track:
            audio.compression = track["CodecID/string"].value
        self.addGroup(f'audio[{track_counter["audio"]}]', audio, f'Audio stream #{track_counter["audio"]}')
        track_counter['audio'] += 1

    def processSubtitle(self, track, track_counter):
        sub = Metadata(self)
        self.trackCommon(track, sub)
        try:
            sub.compression = track["CodecID/string"].value
        except MissingField:
            pass
        self.addGroup(f'subtitle[]{track_counter["sub"]}]', sub, f'Subtitle #{track_counter["sub"]}')
        track_counter['sub'] += 1

    def processTag(self, tag):
        for field in tag.array("SimpleTag"):
            self.processSimpleTag(field)

    def processSimpleTag(self, tag):
        if "TagName/unicode" not in tag \
                or "TagString/unicode" not in tag:
            return
        name = tag["TagName/unicode"].value
        if name not in self.tag_key:
            return
        key = self.tag_key[name]
        value = tag["TagString/unicode"].value
        setattr(self, key, value)

    def processInfo(self, info):
        if "TimecodeScale/unsigned" in info:
            duration = self.getDouble(info, "Duration")
            if duration is not None:
                try:
                    seconds = duration * \
                        info["TimecodeScale/unsigned"].value * 1e-9
                    self.duration = timedelta(seconds=seconds)
                except OverflowError:
                    # Catch OverflowError for timedelta (long int too large
                    # to be converted to an int)
                    pass
        if "DateUTC/date" in info:
            try:
                self.creation_date = dateToDatetime(info["DateUTC/date"].value)
            except OverflowError:
                pass
        if "WritingApp/unicode" in info:
            self.producer = info["WritingApp/unicode"].value
        if "MuxingApp/unicode" in info:
            self.producer = info["MuxingApp/unicode"].value
        if "Title/unicode" in info:
            self.title = info["Title/unicode"].value


class FlvMetadata(MultipleMetadata):

    def extract(self, flv):
        if "video[0]" in flv:
            meta = Metadata(self)
            self.extractVideo(flv["video[0]"], meta)
            self.addGroup("video", meta, "Video stream")
        if "audio[0]" in flv:
            meta = Metadata(self)
            self.extractAudio(flv["audio[0]"], meta)
            self.addGroup("audio", meta, "Audio stream")
        # TODO: Computer duration
        # One technic: use last video/audio chunk and use timestamp
        # But this is very slow
        self.format_version = flv.description

        if "metadata/entry[1]" in flv:
            self.extractAMF(flv["metadata/entry[1]"])
        if self.has('duration'):
            self.bit_rate = flv.size / timedelta2seconds(self.get('duration'))

    @fault_tolerant
    def extractAudio(self, audio, meta):
        if audio["codec"].display == "MP3" and "music_data" in audio:
            meta.compression = audio["music_data"].description
        else:
            meta.compression = audio["codec"].display
        meta.sample_rate = audio.getSampleRate()
        if audio["is_16bit"].value:
            meta.bits_per_sample = 16
        else:
            meta.bits_per_sample = 8
        if audio["is_stereo"].value:
            meta.nb_channel = 2
        else:
            meta.nb_channel = 1

    @fault_tolerant
    def extractVideo(self, video, meta):
        meta.compression = video["fourcc"].value if "fourcc" in video else video["codec"].display

    def extractAMF(self, amf):
        for entry in amf.array("item"):
            self.useAmfEntry(entry)

    @fault_tolerant
    def useAmfEntry(self, entry):
        key = entry["key"].value
        if key == "duration":
            self.duration = timedelta(seconds=entry["value"].value)
        elif key == "creator":
            self.producer = entry["value"].value
        elif key == "audiosamplerate":
            self.sample_rate = entry["value"].value
        elif key == "framerate":
            self.frame_rate = entry["value"].value
        elif key == "metadatacreator":
            self.producer = entry["value"].value
        elif key == "metadatadate":
            self.creation_date = entry.value
        elif key == "width":
            self.width = int(entry["value"].value)
        elif key == "height":
            self.height = int(entry["value"].value)


class MP4Metadata(MultipleMetadata):

    def extract(self, mov):
        for atom in mov:
            if "movie" in atom:
                self.processMovie(atom["movie"])

    @fault_tolerant
    def processMovieHeader(self, hdr):
        self.creation_date = hdr["creation_date"].value
        self.last_modification = hdr["lastmod_date"].value
        self.duration = timedelta(seconds=float(
            hdr["duration"].value) / hdr["time_scale"].value)
        self.comment = "Play speed: %.1f%%" % (hdr["play_speed"].value * 100)
        self.comment = "User volume: %.1f%%" % (
            float(hdr["volume"].value) * 100)

    @fault_tolerant
    def processTrackHeader(self, hdr):
        width = int(hdr["frame_size_width"].value)
        height = int(hdr["frame_size_height"].value)
        if width and height:
            self.width = width
            self.height = height

    def processTrack(self, atom, track_counter):
        for field in atom:
            if "track_hdr" in field:
                self.processTrackHeader(field["track_hdr"])
            if "media" in field:
                self.processMedia(field["media"], track_counter)

    def processMedia(self, atom, track_counter):
        cur_data = {'data': []}
        for field in atom:
            if 'hdlr' in field and 'subtype' in field['hdlr']:
                if 'vide' in field['hdlr']['subtype'].value:
                    cur_data.update({'grp_key': f'video[{track_counter["video"]}]',
                                     'grp_header': f'Video stream #{track_counter["video"]}'})
                    track_counter['video'] += 1
                elif 'soun' in field['hdlr']['subtype'].value:
                    cur_data.update({'grp_key': f'audio[{track_counter["audio"]}]',
                                     'grp_header': f'Audio stream #{track_counter["audio"]}'})
                    track_counter['audio'] += 1
                elif field['hdlr']['subtype'].value in ('sbtl', 'subp'):
                    cur_data.update({'grp_key': f'subtitle[{track_counter["sub"]}]',
                                     'grp_header': f'Subtitle #{track_counter["sub"]}'})
                    track_counter['sub'] += 1

            if 'media_hdr' in field and 'language' in field['media_hdr']:
                cur_data['data'].append(('language', field['media_hdr']['language'].value))

            if 'minf' in field:
                for f in field['minf']:
                    if 'stbl' in f:
                        for s in f['stbl']:
                            if 'stsd' in s and 'sample_entry[0]' in s['stsd']:
                                sample_entry = s['stsd']['sample_entry[0]']
                                if 'format' in sample_entry:
                                    compression = sample_entry['format'].value.decode("utf-8")
                                    if compression:
                                        codec = mp4_fourcc.get(compression, compression)
                                        if 'dvh1' == compression:
                                            # this name is Dolby Vision with HEVC, and also DVCPRO HD
                                            # it is HEVC when the entry has an hvcC box, FFmpeg decides it so too
                                            codec = ('DV', codec)[b'hvcC' in sample_entry.stream.readBytes(
                                                sample_entry.absolute_address, sample_entry.size // 8)]
                                        cur_data['data'].append(('compression', codec))

                                if 'width' in sample_entry:
                                    cur_data['data'].append(('width',  sample_entry['width'].value))
                                if 'height' in sample_entry:
                                    cur_data['data'].append(('height', sample_entry['height'].value))
                                if 'samplerate' in sample_entry and 'int_part' in sample_entry['samplerate']:
                                    cur_data['data'].append(('sample_rate',
                                                             sample_entry['samplerate']['int_part'].value))
                                if 'channels' in sample_entry:
                                    cur_data['data'].append(('nb_channel', sample_entry['channels'].value))
                                if 'samplesize' in sample_entry:
                                    cur_data['data'].append(('bits_per_sample', sample_entry['samplesize'].value))

                                if ('audio' in cur_data.get('grp_key', '')
                                        or b'mp4v' == sample_entry['format'].value):
                                    for es in sample_entry:
                                        if ('esds' in es and 'ES' in es['esds'] and 'decConfigDescr' in es['esds']['ES']
                                                and 'objectTypeIndication' in es['esds']['ES']['decConfigDescr']):
                                            if (_a_c := es['esds']['ES']['decConfigDescr'
                                            ]['objectTypeIndication'].value) in mp4_codecs:
                                                # the object type is more exact than the name of the entry
                                                cur_data['data'] = [_d for _d in cur_data['data']
                                                                    if 'compression' != _d[0]]
                                                cur_data['data'].append(('compression', mp4_codecs[_a_c]))
                                            break
        if 'grp_key' in cur_data:
            cur_track = Metadata(self)
            for en in cur_data['data']:
                setattr(cur_track, en[0], en[1])
            self.addGroup(cur_data['grp_key'], cur_track, cur_data['grp_header'])

    def processMovie(self, atom):
        track_counter = {'audio': 1, 'video': 1, 'sub': 1}
        for field in atom:
            if "track" in field:
                self.processTrack(field["track"], track_counter)
            if "movie_hdr" in field:
                self.processMovieHeader(field["movie_hdr"])


class AsfMetadata(MultipleMetadata):
    EXT_DESC_TO_ATTR = {
        "Encoder": "producer",
        "ToolName": "producer",
        "AlbumTitle": "album",
        "Track": "track_number",
        "TrackNumber": "track_total",
        "Year": "creation_date",
        "AlbumArtist": "author",
    }
    SKIP_EXT_DESC = set((
        # Useless informations
        "WMFSDKNeeded", "WMFSDKVersion",
        "Buffer Average", "VBR Peak", "EncodingTime",
        "MediaPrimaryClassID", "UniqueFileIdentifier",
    ))

    def extract(self, asf):
        if "header/content" in asf:
            self.processHeader(asf["header/content"])

    def processHeader(self, header):
        compression = []
        is_vbr = None

        if "ext_desc/content" in header:
            # Extract all data from ext_desc
            data = {}
            for desc in header.array("ext_desc/content/descriptor"):
                self.useExtDescItem(desc, data)

            # Have ToolName and ToolVersion? If yes, group them to producer key
            if "ToolName" in data and "ToolVersion" in data:
                self.producer = "%s (version %s)" % (
                    data["ToolName"], data["ToolVersion"])
                del data["ToolName"]
                del data["ToolVersion"]

            # "IsVBR" key
            if "IsVBR" in data:
                is_vbr = (data["IsVBR"] == 1)
                del data["IsVBR"]

            # Store data
            for key, value in data.items():
                if key in self.EXT_DESC_TO_ATTR:
                    key = self.EXT_DESC_TO_ATTR[key]
                else:
                    if isinstance(key, str):
                        key = makePrintable(key, "ISO-8859-1")
                    value = "%s=%s" % (key, value)
                    key = "comment"
                setattr(self, key, value)

        if "file_prop/content" in header:
            self.useFileProp(header["file_prop/content"], is_vbr)

        if "codec_list/content" in header:
            for codec in header.array("codec_list/content/codec"):
                if "name" in codec:
                    text = codec["name"].value
                    if "desc" in codec and codec["desc"].value:
                        text = "%s (%s)" % (text, codec["desc"].value)
                    compression.append(text)

        audio_index = 1
        video_index = 1
        for index, stream_prop in enumerate(header.array("stream_prop")):
            if "content/audio_header" in stream_prop:
                meta = Metadata(self)
                self.streamProperty(header, index, meta)
                self.streamAudioHeader(
                    stream_prop["content/audio_header"], meta)
                if self.addGroup("audio[%u]" % audio_index, meta, "Audio stream #%u" % audio_index):
                    audio_index += 1
            elif "content/video_header" in stream_prop:
                meta = Metadata(self)
                self.streamProperty(header, index, meta)
                self.streamVideoHeader(
                    stream_prop["content/video_header"], meta)
                if self.addGroup("video[%u]" % video_index, meta, "Video stream #%u" % video_index):
                    video_index += 1

        if "metadata/content" in header:
            info = header["metadata/content"]
            try:
                self.title = info["title"].value
                self.author = info["author"].value
                self.copyright = info["copyright"].value
            except MissingField:
                pass

    @fault_tolerant
    def streamAudioHeader(self, audio, meta):
        if not meta.has("compression"):
            meta.compression = audio["twocc"].display
        meta.nb_channel = audio["channels"].value
        meta.sample_rate = audio["sample_rate"].value
        meta.bits_per_sample = audio["bits_per_sample"].value

    @fault_tolerant
    def streamVideoHeader(self, video, meta):
        meta.width = video["width"].value
        meta.height = video["height"].value
        if "bmp_info" in video:
            bmp_info = video["bmp_info"]
            if not meta.has("compression"):
                meta.compression = bmp_info["codec"].display
            meta.bits_per_pixel = bmp_info["bpp"].value

    @fault_tolerant
    def useExtDescItem(self, desc, data):
        if desc["type"].value == ASF_Descriptor.TYPE_BYTE_ARRAY:
            # Skip binary data
            return
        key = desc["name"].value
        if "/" in key:
            # Replace "WM/ToolName" with "ToolName"
            key = key.split("/", 1)[1]
        if key in self.SKIP_EXT_DESC:
            # Skip some keys
            return
        value = desc["value"].value
        if not value:
            return
        value = makeUnicode(value)
        data[key] = value

    @fault_tolerant
    def useFileProp(self, prop, is_vbr):
        self.creation_date = prop["creation_date"].value
        self.duration = prop["play_duration"].value - prop["preroll"].value
        if prop["seekable"].value:
            self.comment = "Is seekable"
        value = prop["max_bitrate"].value
        text = prop["max_bitrate"].display
        if is_vbr is True:
            text = "VBR (%s max)" % text
        elif is_vbr is False:
            text = "%s (CBR)" % text
        else:
            text = "%s (max)" % text
        self.bit_rate = (value, text)

    def streamProperty(self, header, index, meta):
        key = "bit_rates/content/bit_rate[%u]/avg_bitrate" % index
        if key in header:
            meta.bit_rate = header[key].value

        # TODO: Use codec list
        # It doesn't work when the video uses /header/content/bitrate_mutex
        # since the codec list are shared between streams but... how is it
        # shared?
#        key = "codec_list/content/codec[%u]" % index
#        if key in header:
#            codec = header[key]
#            if "name" in codec:
#                text = codec["name"].value
#                if "desc" in codec and codec["desc"].value:
#                    meta.compression = "%s (%s)" % (text, codec["desc"].value)
#                else:
#                    meta.compression = text


# format identifiers of the registration descriptor of a private stream (type 6)
TS_Registration_video = {b'AV01': 'AV1', b'HEVC': 'HEVC', b'VC-1': 'VC-1', b'VVC ': 'VVC'}


class TSMetadata(MultipleMetadata):

    def extract(self, mov):
        pmt_pid = None
        stream_ids = {'video': [], 'audio': []}
        for packet in mov:
            if 'pid' in packet:
                if (0 == packet['pid'].value and 'payload' in packet
                        and 'PAT' in packet['payload']):
                    # program number 0 gives the PID of the network table, not of a program map
                    pmt_pid = next((program['Program map PID'].value for program in packet['payload']['PAT']
                                    if program['Program num'].value), None)
                elif pmt_pid == packet['pid'].value:
                    if 'PMT' in packet['payload']:
                        self.processPMT(packet['payload']['PMT'], stream_ids)
                    break


    def processPMT(self, data, stream_ids):
        track_counter = {'audio': 1, 'video': 1, 'sub': 1}
        for d in data:
            if 'Elementary Stream #' in d.name:
                cur_data = {'data': []}
                codec = None
                if 0x06 == d['stream type'].value and 'Elementary stream descriptors' in d:
                    # private data, a registration descriptor (tag 5) can name its codec
                    descriptors = d['Elementary stream descriptors'].value
                    while 6 <= len(descriptors) and not codec:
                        if 5 == descriptors[0]:
                            codec = TS_Registration_video.get(descriptors[2:6])
                        descriptors = descriptors[2 + descriptors[1]:]
                if codec or d['stream type'].value in TS_Video_stream_types:
                    cur_data.update({'grp_key': f'video[{track_counter["video"]}]',
                                     'grp_header': f'Video stream #{track_counter["video"]}'})
                    stream_ids['video'].append(d['Elementary PID'].value)
                    track_counter['video'] += 1
                elif d['stream type'].value in TS_Audio_stream_types:
                    cur_data.update({'grp_key': f'audio[{track_counter["audio"]}]',
                                     'grp_header': f'Audio stream #{track_counter["audio"]}'})
                    stream_ids['audio'].append(d['Elementary PID'].value)
                    track_counter['audio'] += 1
                else:
                    continue
                cur_data['data'].append(('compression', codec or TS_Elementary_stream_types.get(d['stream type'].value)))
                cur_track = Metadata(self)
                for en in cur_data['data']:
                    setattr(cur_track, en[0], en[1])
                self.addGroup(cur_data['grp_key'], cur_track, cur_data['grp_header'])


class MPEGMetadata(MultipleMetadata):

    @staticmethod
    def videoVersion(mov):
        # the parser gives the version of the pack header, and a pack of version 1 can hold MPEG-2 video
        # MPEG-2 video has an extension start code (B5) after its sequence header (B3), MPEG-1 video has not
        stream = mov.stream
        limit = min(stream.size or 0, 2 * 1024 * 1024 * 8)
        start = stream.searchBytes(b'\0\0\1\xb3', 0, limit)
        while None is not start and limit >= start + 12 * 8:
            # a sequence header is 12 bytes, and up to 128 bytes of matrices
            following = stream.readBytes(start + 4 * 8, min(160, (limit - start) // 8 - 4))
            # MPEG-4 video uses this start code for another header, so check the fields: a width and a height,
            # an aspect ratio code of 1 to 14, a frame rate code of 1 to 8, and the marker bit
            if (following[0] or following[1] >> 4) and (following[1] & 0xF or following[2]) \
                    and 1 <= following[3] >> 4 <= 14 and 1 <= following[3] & 0xF <= 8 and following[6] & 0x20:
                code = following.find(b'\0\0\1', 8)
                return 'MPEG-2 video' if -1 != code and following[code + 3:code + 4] == b'\xb5' else 'MPEG-1 video'
            start = stream.searchBytes(b'\0\0\1\xb3', start + 4 * 8, limit)
        return None

    def extract(self, mov):
        video_track = Metadata(self)
        # with no sequence header of MPEG-1 or MPEG-2 video, the codec is another one and is not known
        if codec := self.videoVersion(mov):
            video_track.compression = codec
        self.addGroup('video[1]', video_track, 'Video stream #1')


registerExtractor(MP4File, MP4Metadata)
registerExtractor(AsfFile, AsfMetadata)
registerExtractor(FlvFile, FlvMetadata)
registerExtractor(MkvFile, MkvMetadata)
registerExtractor(MPEG_TS, TSMetadata)
registerExtractor(MPEGVideoFile, MPEGMetadata)
