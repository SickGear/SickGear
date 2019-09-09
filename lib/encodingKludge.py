# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import os
import logging
import locale

from six import iteritems, PY2, text_type, string_types

logger = logging.getLogger('encodingKludge')
logger.addHandler(logging.NullHandler())


SYS_ENCODING = None
try:
    locale.setlocale(locale.LC_ALL, '')
except (locale.Error, IOError):
    pass
try:
    SYS_ENCODING = locale.getpreferredencoding()
except (locale.Error, IOError):
    pass

# For OSes that are poorly configured I'll just randomly force UTF-8
if not SYS_ENCODING or SYS_ENCODING in ('ANSI_X3.4-1968', 'US-ASCII', 'ASCII'):
    SYS_ENCODING = 'UTF-8'


# This module tries to deal with the apparently random behavior of python when dealing with unicode <-> utf-8
# encodings. It tries to just use unicode, but if that fails then it tries forcing it to utf-8. Any functions
# which return something should always return unicode.


# noinspection PyCompatibility,PyPep8Naming
def fixStupidEncodings(x, silent=False):
    if not PY2:
        return x

    if str == type(x):
        try:
            return x.decode(SYS_ENCODING)
        except UnicodeDecodeError:
            logger.error(u"Unable to decode value: " + repr(x))
    elif text_type == type(x):
        return x
    else:
        msg = u"Unknown value passed in, ignoring it: " + str(type(x)) + " (" + repr(x) + ":" + repr(type(x)) + ")"
        if silent:
            logger.debug(msg)
        else:
            logger.error(msg)


# noinspection PyCompatibility,PyPep8Naming
def fixOutEncoding(x):
    if PY2 and isinstance(x, string_types):
        return fixStupidEncodings(x)
    return x


# noinspection PyCompatibility,PyPep8Naming
def fixListEncodings(x):
    if not PY2 or type(x) not in (list, tuple):
        return x
    return filter(lambda i: None is not i, map(fixOutEncoding, x))


# noinspection PyCompatibility,PyPep8Naming
def callPeopleStupid(x):
    if not PY2:
        return x

    try:
        return x.encode(SYS_ENCODING)
    except UnicodeEncodeError:
        logger.error(u'Your data is being corrupted by a bad locale/encoding setting.'
                     u' Report this error in IRC please: %s, %s' % (repr(x), SYS_ENCODING))
        return x.encode(SYS_ENCODING, 'ignore')


# noinspection PyCompatibility,PyPep8Naming
def fixParaLists(x):
    if PY2 and list == type(x):
        return [callPeopleStupid(a) if type(a) in (str, text_type) else a for a in x]
    return x


# noinspection PyCompatibility
def win_encode_unicode(x):
    if PY2 and isinstance(x, str):
        try:
            # noinspection PyUnresolvedReferences
            return x.decode('UTF-8')
        except UnicodeDecodeError:
            pass
    return x


# noinspection PyCompatibility
def ek(func, *args, **kwargs):
    if not PY2:
        return func(*args, **kwargs)
    if 'nt' == os.name:
        # convert all str parameter values to unicode
        args = tuple([x if not isinstance(x, str) else win_encode_unicode(x) for x in args])
        # iteritems can stay, since this code will not run on py3
        kwargs = {k: x if not isinstance(x, str) else win_encode_unicode(x) for k, x in iteritems(kwargs)}
        result = func(*args, **kwargs)
    else:
        result = func(*[callPeopleStupid(x) if type(x) in (str, text_type)
                        else fixParaLists(x) for x in args], **kwargs)

    if type(result) in (list, tuple):
        return fixListEncodings(result)
    elif type(result) == str:
        return fixStupidEncodings(result)
    return result
