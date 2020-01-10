from hachoir_py3.core.endian import endian_name
from hachoir_py3.core.tools import makeUnicode
from hachoir_py3.core.dict import Dict
from hachoir_py3.core.error import error
from hachoir_py3.core.log import Logger
from hachoir_py3.metadata.metadata_item import (
    MIN_PRIORITY, MAX_PRIORITY, QUALITY_NORMAL)
from hachoir_py3.metadata.register import registerAllItems

from six import iteritems


extractors = {}


class Metadata(Logger):
    header = "Metadata"

    def __init__(self, parent, quality=QUALITY_NORMAL):
        assert isinstance(self.header, str)

        # Limit to 0.0 .. 1.0
        if parent:
            quality = parent.quality
        else:
            quality = min(max(0.0, quality), 1.0)

        object.__init__(self)
        object.__setattr__(self, "_Metadata__data", {})
        object.__setattr__(self, "quality", quality)
        header = self.__class__.header
        object.__setattr__(self, "_Metadata__header", header)

        registerAllItems(self)

    def _logger(self):
        pass

    def __setattr__(self, key, value):
        """
        Add a new value to data with name 'key'. Skip duplicates.
        """
        # Invalid key?
        if key not in self.__data:
            raise KeyError("%s has no metadata '%s'" %
                           (self.__class__.__name__, key))

        # Skip duplicates
        self.__data[key].add(value)

    def setHeader(self, text):
        object.__setattr__(self, "header", text)

    def getItems(self, key):
        try:
            return self.__data[key]
        except LookupError:
            raise ValueError("Metadata has no value '%s'" % key)

    def getItem(self, key, index):
        try:
            return self.getItems(key)[index]
        except (LookupError, ValueError):
            return None

    def has(self, key):
        return 1 <= len(self.getItems(key))

    def get(self, key, default=None, index=0):
        """
        Read first value of tag with name 'key'.

        >>> from datetime import timedelta
        >>> a = RootMetadata()
        >>> a.duration = timedelta(seconds=2300)
        >>> a.get('duration') == timedelta(seconds=2300)
        True
        >>> a.get('author', 'Anonymous')
        'Anonymous'
        """
        item = self.getItem(key, index)
        if item is None:
            if default is None:
                raise ValueError(
                    "Metadata has no value '%s' (index %s)" % (key, index))
            else:
                return default
        return item.value

    def getValues(self, key):
        try:
            data = self.__data[key]
        except LookupError:
            raise ValueError("Metadata has no value '%s'" % key)
        return [item.value for item in data]

    def getText(self, key, default=None, index=0):
        """
        Read first value, as unicode string, of tag with name 'key'.

        >>> from datetime import timedelta
        >>> a = RootMetadata()
        >>> a.duration = timedelta(seconds=2300)
        >>> a.getText('duration')
        '38 min 20 sec'
        >>> a.getText('titre', 'Unknown')
        'Unknown'
        """
        item = self.getItem(key, index)
        if item is not None:
            return item.text
        else:
            return default

    def register(self, data):
        assert data.key not in self.__data
        data.metadata = self
        self.__data[data.key] = data

    def __iter__(self):
        return iter(self.__data.values())

    def __str__(self):
        r"""
        Create a multi-line Unicode string (end of line is "\n") which
        represents all datas.

        >>> a = RootMetadata()
        >>> a.copyright = "© Hachoir"
        >>> print(repr(str(a)))
        'Metadata:\n- Copyright: \xa9 Hachoir'

        @see __str__() and exportPlaintext()
        """
        return "\n".join(self.exportPlaintext())

    def exportPlaintext(self, priority=None, human=True, line_prefix="- ", title=None):
        r"""
        Convert metadata to multi-line Unicode string and skip datas
        with priority lower than specified priority.

        Default priority is Metadata.MAX_PRIORITY. If human flag is True, data
        key are translated to better human name (eg. "bit_rate" becomes
        "Bit rate") which may be translated using gettext.

        If priority is too small, metadata are empty and so None is returned.

        >>> print(RootMetadata().exportPlaintext())
        None
        >>> meta = RootMetadata()
        >>> meta.copyright = "© Hachoir"
        >>> print(repr(meta.exportPlaintext()))
        ['Metadata:', '- Copyright: \xa9 Hachoir']

        @see __str__() and __unicode__()
        """
        if priority is not None:
            priority = max(priority, MIN_PRIORITY)
            priority = min(priority, MAX_PRIORITY)
        else:
            priority = MAX_PRIORITY
        if not title:
            title = self.header
        text = ["%s:" % title]
        for data in sorted(self, key=lambda data: data.priority):
            if priority < data.priority:
                break
            if not data.values:
                continue
            if human:
                title = data.description
            else:
                title = data.key
            for item in data.values:
                if human:
                    value = item.text
                else:
                    value = makeUnicode(item.value)
                text.append("%s%s: %s" % (line_prefix, title, value))
        if 1 < len(text):
            return text
        else:
            return None

    def exportDictionary(self, priority=None, human=True, title=None):
        r"""
        Convert metadata to python Dictionary and skip datas
        with priority lower than specified priority.

        Default priority is Metadata.MAX_PRIORITY. If human flag is True, data
        key are translated to better human name (eg. "bit_rate" becomes
        "Bit rate") which may be translated using gettext.

        If priority is too small, metadata are empty and so None is returned.

        """
        if priority is not None:
            priority = max(priority, MIN_PRIORITY)
            priority = min(priority, MAX_PRIORITY)
        else:
            priority = MAX_PRIORITY
        if not title:
            title = self.header
        text = {}
        text[title] = {}
        for data in sorted(self):
            if priority < data.priority:
                break
            if not data.values:
                continue
            if human:
                field = data.description
            else:
                field = data.key
            text[title][field] = {}
            for item in data.values:
                if human:
                    value = item.text
                else:
                    value = makeUnicode(item.value)
                text[title][field] = value
        return text

    def __bool__(self):
        return any(item for item in self.__data.values())


class RootMetadata(Metadata):

    def __init__(self, quality=QUALITY_NORMAL):
        Metadata.__init__(self, None, quality)


class MultipleMetadata(RootMetadata):
    header = "Common"

    def __init__(self, quality=QUALITY_NORMAL):
        RootMetadata.__init__(self, quality)
        object.__setattr__(self, "_MultipleMetadata__groups", Dict())
        object.__setattr__(self, "_MultipleMetadata__key_counter", {})

    def __contains__(self, key):
        return key in self._MultipleMetadata__groups

    def __getitem__(self, key):
        return self._MultipleMetadata__groups[key]

    def iterGroups(self):
        return iter(self._MultipleMetadata__groups.values)

    def __bool__(self):
        if RootMetadata.__bool__(self):
            return True
        return any(bool(group) for group in self._MultipleMetadata__groups)

    def addGroup(self, key, metadata, header=None):
        """
        Add a new group (metadata of a sub-document).

        Returns False if the group is skipped, True if it has been added.
        """
        if not metadata:
            self.warning("Skip empty group %s" % key)
            return False
        if key.endswith("[]"):
            key = key[:-2]
            if key in self._MultipleMetadata__key_counter:
                self._MultipleMetadata__key_counter[key] += 1
            else:
                self._MultipleMetadata__key_counter[key] = 1
            key += "[%u]" % self._MultipleMetadata__key_counter[key]
        if header:
            metadata.setHeader(header)
        self._MultipleMetadata__groups.append(key, metadata)
        return True

    def exportPlaintext(self, priority=None, human=True, line_prefix="- "):
        common = Metadata.exportPlaintext(self, priority, human, line_prefix)
        if common:
            text = common
        else:
            text = []
        for key, metadata in self._MultipleMetadata__groups.iteritems():
            if not human:
                title = key
            else:
                title = None
            value = metadata.exportPlaintext(
                priority, human, line_prefix, title=title)
            if value:
                text.extend(value)
        if len(text):
            return text
        else:
            return None

    def exportDictionary(self, priority=None, human=True):
        common = Metadata.exportDictionary(self, priority, human)
        if common:
            text = common
        else:
            text = {}
        for key, metadata in self._MultipleMetadata__groups.iteritems():
            if not human:
                title = key
            else:
                title = None
            value = metadata.exportDictionary(priority, human, title=title)
            if value:
                text.update(value)
        return text


def registerExtractor(parser, extractor):
    assert parser not in extractors
    assert issubclass(extractor, RootMetadata)
    extractors[parser] = extractor


def extractMetadata(parser, quality=QUALITY_NORMAL, **kwargs):
    """
    Create a Metadata class from a parser. Returns None if no metadata
    extractor does exist for the parser class.
    """
    try:
        extractor = extractors[parser.__class__]
    except KeyError:
        return None
    metadata = extractor(quality)
    meta_extract_error = True
    try:
        if 'scan_index' in kwargs:
            metadata.extract(parser, scan_index=kwargs['scan_index'])
        else:
            metadata.extract(parser)
        meta_extract_error = False
    except (BaseException, Exception) as err:
        error("Error during metadata extraction: %s" % str(err))

    if meta_extract_error:
        try:
            # noinspection PyProtectedMember
            parser.stream._input.close()
        except (BaseException, Exception):
            pass
        return None

    if metadata:
        metadata.mime_type = parser.mime_type
        metadata.endian = endian_name[parser.endian]
    return metadata
