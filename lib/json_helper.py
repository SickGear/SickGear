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

from sys import version_info

from _23 import decode_str
from requests.utils import guess_json_utf


# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from requests.models import Response as requests_Response

notPY2 = 2 != version_info[0]


class BaseJsonEncoder(object):
    is_orjson = True

    def default(self, data):
        raise TypeError


is_orjson = False
has_simplejson = False
JSON_INDENT = 2
ORJSON_OPTIONS = None
try:
    import orjson as json
    from orjson import JSONDecodeError, JSONEncodeError

    json.JSONEncoder = BaseJsonEncoder

    # noinspection PyUnresolvedReferences
    is_orjson = getattr(json.JSONEncoder, 'is_orjson', False)
    ORJSON_OPTIONS = json.OPT_NON_STR_KEYS | json.OPT_SORT_KEYS | json.OPT_INDENT_2

    try:
        import simplejson as json_fallback
    except ImportError:
        import json as json_fallback

    def _dump(obj, fp, *args, **kw):
        fp.write(json.dumps(obj, *args, **kw))

    def _load(fp, *args, **kwargs):
        return json.loads(fp.read(), *args, **kwargs)

    json.dump = _dump
    json.load = _load

except ImportError:
    JSONDecodeError = ValueError
    JSONEncodeError = ValueError, TypeError
    try:
        import simplejson as json

        if notPY2:
            from simplejson import JSONDecodeError
        has_simplejson = True
    except ImportError:
        import json

        if notPY2:
            from json import JSONDecodeError
    json_fallback = json

JSONEncoder = json.JSONEncoder


def invoke_json(method, *arg, **kwargs):
    try:
        result = getattr(json, method)(*arg, **kwargs)
    except (JSONDecodeError, JSONEncodeError):
        result = getattr(json_fallback, method)(*arg, **kwargs)

    return decode_str(result)


def invoke_load(method, *arg, **kwargs):
    response = kwargs.pop('requests_response', False)  # type: requests_Response
    if response:
        # adapted from requests.models.Response().json()
        if not response.encoding and response.content and 3 < len(response.content):
            # No encoding set. JSON RFC 4627 section 3 states to expect
            # UTF-8, -16 or -32. Detect which one to use; If the detection or decoding fails,
            # fall back to `response.text` (using charset_normalizer to make the best guess)
            encoding = guess_json_utf(response.content)
            if encoding is not None:
                try:
                    return invoke_json(
                        method, response.content.decode(encoding), *arg, **kwargs
                    )
                except (BaseException, Exception):
                    pass

        return invoke_json(method, response.text, *arg, **kwargs)

    return invoke_json(method, *arg, **kwargs)


def json_dump(*arg, **kwargs):
    return invoke_json('dump', *arg, **kwargs)


def json_dumps(*arg, **kwargs):
    if not arg[0]:
        return '{}'
    return invoke_json('dumps', *arg, **kwargs)


def json_load(*arg, **kwargs):
    return invoke_load('load', *arg, **kwargs)


def json_loads(*arg, **kwargs):
    return invoke_load('loads', *arg, **kwargs)
