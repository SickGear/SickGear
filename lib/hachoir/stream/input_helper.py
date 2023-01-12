from hachoir.core.i18n import guessBytesCharset
from hachoir.stream import InputIOStream, InputSubStream, InputStreamError


def FileInputStream(filename, real_filename=None, **args):
    """
    Create an input stream of a file. filename must be unicode or a file
    object.

    real_filename is an optional argument used to specify the real filename,
    its type can be 'str' or 'unicode'. Use real_filename when you are
    not able to convert filename to real unicode string (ie. you have to
    use unicode(name, 'replace') or unicode(name, 'ignore')).
    """
    if not real_filename:
        real_filename = (filename if isinstance(filename, str)
                         else getattr(filename, 'name', ''))
    try:
        if isinstance(filename, str):
            inputio = open(real_filename, 'rb')
        else:
            inputio = filename
            filename = getattr(filename, 'name', '')
    except IOError as err:
        errmsg = str(err)
        raise InputStreamError(
            "Unable to open file %s: %s" % (filename, errmsg))
    source = "file:" + filename
    offset = args.pop("offset", 0)
    size = args.pop("size", None)
    if offset or size:
        if size:
            size = 8 * size
        stream = InputIOStream(inputio, source=source, **args)
        return InputSubStream(stream, 8 * offset, size, **args)
    else:
        args.setdefault("tags", []).append(("filename", filename))
        return InputIOStream(inputio, source=source, **args)


def guessStreamCharset(stream, address, size, default=None):
    size = min(size, 1024 * 8)
    bytes = stream.readBytes(address, size // 8)
    return guessBytesCharset(bytes, default)
