# Author: Dennis Lutter <lad1337@gmail.com>
# Author: Jonathon Saine <thezoggy@gmail.com>
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
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

# noinspection PyProtectedMember
from mimetypes import MimeTypes
from random import randint

import datetime
import glob
import copy
try:
    import json
except ImportError:
    from lib import simplejson as json
import os
import re
import time
import traceback
from . import webserve

# noinspection PyPep8Naming
import encodingKludge as ek
import exceptions_helper
from exceptions_helper import ex
from tornado import gen
from tornado.concurrent import run_on_executor
from lib import subliminal

import sickbeard
from . import classes, db, helpers, history, image_cache, logger, network_timezones, processTV, search_queue, ui
from .common import ARCHIVED, DOWNLOADED, IGNORED, SKIPPED, SNATCHED, SNATCHED_ANY, SNATCHED_BEST, SNATCHED_PROPER, \
    UNAIRED, UNKNOWN, WANTED, Quality, qualityPresetStrings, statusStrings
from .helpers import remove_article
from .indexers import indexer_api, indexer_config
from .indexers.indexer_config import *
from lib.tvinfo_base.exceptions import *
from .scene_numbering import set_scene_numbering_helper
from .search_backlog import FORCED_BACKLOG
from .show_updater import clean_ignore_require_words
from .sgdatetime import SGDatetime
from .tv import TVEpisode, TVShow,  TVidProdid
from .webserve import AddShows

from _23 import decode_str, list_keys, unquote_plus
from six import integer_types, iteritems, iterkeys, PY2, string_types, text_type

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Dict, List, Tuple


dateFormat = "%Y-%m-%d"
dateTimeFormat = "%Y-%m-%d %H:%M"
timeFormat = '%A %I:%M %p'

RESULT_SUCCESS = 10  # only use inside the run methods
RESULT_FAILURE = 20  # only use inside the run methods
RESULT_TIMEOUT = 30  # not used yet :(
RESULT_ERROR = 40  # only use outside of the run methods !
RESULT_FATAL = 50  # only use in Api.default() ! this is the "we encountered an internal error" error
RESULT_DENIED = 60  # only use in Api.default() ! this is the access denied error
result_type_map = {RESULT_SUCCESS: "success",
                   RESULT_FAILURE: "failure",
                   RESULT_TIMEOUT: "timeout",
                   RESULT_ERROR: "error",
                   RESULT_FATAL: "fatal",
                   RESULT_DENIED: "denied",
                   }
# basically everything except RESULT_SUCCESS / success is bad

quality_map = {'sdtv': Quality.SDTV,
               'sddvd': Quality.SDDVD,
               'hdtv': Quality.HDTV,
               'rawhdtv': Quality.RAWHDTV,
               'fullhdtv': Quality.FULLHDTV,
               'hdwebdl': Quality.HDWEBDL,
               'fullhdwebdl': Quality.FULLHDWEBDL,
               'hdbluray': Quality.HDBLURAY,
               'fullhdbluray': Quality.FULLHDBLURAY,
               'uhd4kweb': Quality.UHD4KWEB,
               'unknown': Quality.UNKNOWN}

quality_map_inversed = {v: k for k, v in iteritems(quality_map)}


def api_log(obj, msg, level=logger.MESSAGE):
    apikey_name = getattr(obj, 'apikey_name', '')
    if apikey_name:
        apikey_name = ' (%s)' % apikey_name
    logger.log('%s%s' % ('API%s:: ' % apikey_name, msg), level)


class ApiServerLoading(webserve.BaseHandler):
    @gen.coroutine
    def get(self, route, *args, **kwargs):
        self.finish(json.dumps({'error_msg': 'Server is loading'}))

    post = get


class PythonObjectEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, TVEpisode):
            return {'season': obj.season, 'episode': obj.episode}
        elif isinstance(obj, TVShow):
            return {'name': obj.name, 'indexer': obj.tvid, 'indexer_id': obj.prodid}
        elif isinstance(obj, datetime.datetime):
            return SGDatetime.sbfdatetime(obj, d_preset=dateFormat, t_preset='%H:%M %z')
        elif isinstance(obj, datetime.date):
            return SGDatetime.sbfdate(obj, d_preset=dateFormat)
        return json.JSONEncoder.default(self, obj)


class Api(webserve.BaseHandler):
    """ api class that returns json results """
    version = 14  # use an int since float-point is unpredictable
    indent = 4

    def check_xsrf_cookie(self):
        pass

    def set_default_headers(self):
        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.set_header('X-Robots-Tag', 'noindex, nofollow, noarchive, nocache, noodp, noydir, noimageindex, nosnippet')
        if sickbeard.SEND_SECURITY_HEADERS:
            self.set_header('X-Frame-Options', 'SAMEORIGIN')
        self.set_header('X-Application', 'SickGear')
        self.set_header('X-API-Version', Api.version)

    def prepare(self):
        # Incorporate request JSON into arguments dictionary.
        if self.request.body:
            try:
                json_data = {'payloadjson': json.loads(self.request.body)}
                self.request.arguments.update(json_data)
            except (BaseException, Exception):
                raise ApiError('Unable to parse JSON.')
        super(Api, self).prepare()

    def post(self, route, *args, **kwargs):
        return self.get(route, *args, **kwargs)

    def _decode_params(self, kwargs):
        for k, v in iteritems(kwargs):
            if isinstance(v, list):
                kwargs[k] = [decode_str(l) for l in v]
            elif isinstance(v, dict):
                kwargs[k] = {a: decode_str(b) for a, b in iteritems(v)}
            else:
                kwargs[k] = decode_str(v)
        return kwargs

    @gen.coroutine
    def get(self, route, *args, **kwargs):
        route = route.strip('/') or 'index'

        kwargs = self._decode_params(self.request.arguments)
        for arg, value in iteritems(kwargs):
            if not isinstance(value, dict) and 1 == len(value):
                kwargs[arg] = value[0]

        args = args[1:]

        self.apiKeys = sickbeard.API_KEYS
        access, accessMsg, args, kwargs = self._grand_access(self.apiKeys, route, args, kwargs)

        # set the output callback
        # default json
        outputCallbackDict = {'default': self._out_as_json,
                              'image': lambda x: x['image'],
                              }

        # do we have access ?
        if access:
            api_log(self, accessMsg, logger.DEBUG)
        else:
            api_log(self, accessMsg, logger.WARNING)
            result = yield self.async_call(outputCallbackDict['default'], (_responds(RESULT_DENIED, msg=accessMsg), ))
            self.finish(result)
            return

        # set the original call_dispatcher as the local _call_dispatcher
        _call_dispatcher = call_dispatcher
        # if profile was set wrap "_call_dispatcher" in the profile function
        if 'profile' in kwargs:
            from lib.profilehooks import profile

            _call_dispatcher = profile(_call_dispatcher, immediate=True)
            del kwargs["profile"]

        # if debug was set call the "_call_dispatcher"
        if 'debug' in kwargs:
            outDict = _call_dispatcher(self, args,
                                       kwargs)  # this way we can debug the cherry.py traceback in the browser
            del kwargs["debug"]
        else:  # if debug was not set we wrap the "call_dispatcher" in a try block to assure a json output
            try:
                outDict = yield self.async_call(_call_dispatcher, (self, args, kwargs))
            except Exception as e:  # real internal error
                api_log(self, ex(e), logger.ERROR)
                errorData = {"error_msg": ex(e),
                             "args": args,
                             "kwargs": kwargs}
                outDict = _responds(RESULT_FATAL, errorData,
                                    "SickGear encountered an internal error! Please report to the Devs")

        if 'outputType' in outDict:
            outputCallback = outputCallbackDict[outDict['outputType']]
        else:
            outputCallback = outputCallbackDict['default']
        self.finish(outputCallback(outDict))

    @run_on_executor
    def async_call(self, function, ag):
        try:
            result = function(*ag)
            return result
        except Exception as e:
            if PY2:
                logger.log('traceback: %s' % traceback.format_exc(), logger.ERROR)
            logger.log(ex(e), logger.ERROR)
            raise e

    def _out_as_json(self, dict):
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        try:
            out = json.dumps(dict, indent=self.indent, sort_keys=True, cls=PythonObjectEncoder)
            callback = self.get_query_argument('callback', None) or self.get_query_argument('jsonp', None)
            if None is not callback:
                out = '%s(%s);' % (callback, out)  # wrap with JSONP call if requested

        except Exception as e:  # if we fail to generate the output fake an error
            api_log(self, traceback.format_exc(), logger.ERROR)
            out = '{"result":"' + result_type_map[RESULT_ERROR] + '", "message": "error while composing output: "' + ex(
                e) + '"}'

        return out

    def _grand_access(self, realKeys, apiKey, args, kwargs):
        """ validate api key and log result """
        remoteIp = self.request.remote_ip
        self.apikey_name = ''

        if not sickbeard.USE_API:
            msg = u'%s - SB API Disabled. ACCESS DENIED' % remoteIp
            return False, msg, args, kwargs
        if not apiKey:
            msg = u'%s - gave NO API KEY. ACCESS DENIED' % remoteIp
            return False, msg, args, kwargs
        for realKey in realKeys:
            if apiKey == realKey[1]:
                self.apikey_name = realKey[0]
                msg = u'%s - gave correct API KEY: %s. ACCESS GRANTED' % (remoteIp, realKey[0])
                return True, msg, args, kwargs
        msg = u'%s - gave WRONG API KEY %s. ACCESS DENIED' % (remoteIp, apiKey)
        return False, msg, args, kwargs


def call_dispatcher(handler, args, kwargs):
    """ calls the appropriate CMD class
        looks for a cmd in args and kwargs
        or calls the TVDBShorthandWrapper when the first args element is a number
        or returns an error that there is no such cmd
    """
    cmds = None
    if args:
        cmds = args[0]
        args = args[1:]

    if "cmd" in kwargs:
        cmds = kwargs["cmd"]
        del kwargs["cmd"]

    api_log(handler, u"cmd: '" + str(cmds) + "'", logger.DEBUG)
    api_log(handler, u"all args: '" + str(args) + "'", logger.DEBUG)
    api_log(handler, u"all kwargs: '" + str(kwargs) + "'", logger.DEBUG)
    # logger.log(u"dateFormat: '" + str(dateFormat) + "'", logger.DEBUG)


    outDict = {}
    if None is not cmds:
        cmds = cmds.split("|")
        multiCmds = bool(1 < len(cmds))
        for cmd in cmds:
            curArgs, curKwargs = filter_params(cmd, args, kwargs)
            cmdIndex = None
            if 1 < len(cmd.split("_")):  # was a index used for this cmd ?
                cmd, cmdIndex = cmd.split("_")  # this gives us the clear cmd and the index

            api_log(handler, cmd + ": curKwargs " + str(curKwargs), logger.DEBUG)
            if not (multiCmds and cmd in ('show.getposter', 'show.getbanner')):  # skip these cmd while chaining
                try:
                    if cmd in _functionMaper:
                        curOutDict = _functionMaper.get(cmd)(handler, curArgs,
                                                             curKwargs).run()  # get the cmd class, init it and run()
                    elif _is_int(cmd):
                        curOutDict = TVDBShorthandWrapper(handler, curArgs, curKwargs, cmd).run()
                    else:
                        curOutDict = _responds(RESULT_ERROR, "No such cmd: '" + cmd + "'")
                except ApiError as e:  # Api errors that we raised, they are harmless
                    curOutDict = _responds(RESULT_ERROR, msg=ex(e))
            else:  # if someone chained one of the forbidden cmds they will get an error for this one cmd
                curOutDict = _responds(RESULT_ERROR, msg="The cmd '" + cmd + "' is not supported while chaining")

            if multiCmds:
                # note: if multiple same cmds are issued but one has not an index defined it will override all others
                # or the other way around, this depends on the order of the cmds
                # this is not a bug
                if None is cmdIndex:  # do we need a index dict for this cmd ?
                    outDict[cmd] = curOutDict
                else:
                    if cmd not in outDict:
                        outDict[cmd] = {}
                    outDict[cmd][cmdIndex] = curOutDict
            else:
                outDict = curOutDict

        if multiCmds:  # if we had multiple cmds we have to wrap it in a response dict
            outDict = _responds(RESULT_SUCCESS, outDict)
    else:  # index / no cmd given
        outDict = CMD_SickBeard(handler, args, kwargs).run()

    return outDict


def filter_params(cmd, args, kwargs):
    # type: (AnyStr, List, Dict) -> Tuple[List, Dict]
    """ return only params kwargs that are for cmd
        and rename them to a clean version (remove "<cmd>_")
        args are shared across all cmds

        all args and kwarks are lowerd

        cmd are separated by "|" e.g. &cmd=shows|future
        kwargs are namespaced with "." e.g. show.prodid=101501
        if a karg has no namespace asing it anyways (global)

        full e.g.
        /api?apikey=1234&cmd=show.seasonlist_asd|show.seasonlist_2&show.seasonlist_asd.prodid=101501&show.seasonlist_2.prodid=79488&sort=asc

        two calls of show.seasonlist
        one has the index "asd" the other one "2"
        the "indexerid" kwargs / params have the indexed cmd as a namspace
        and the kwarg / param "sort" is a used as a global
    """
    curArgs = []
    for arg in args:
        curArgs.append(arg.lower())
    curArgs = tuple(curArgs)

    curKwargs = {}
    for kwarg in kwargs:
        if 0 == kwarg.find(cmd + "."):
            cleanKey = kwarg.rpartition(".")[2]
            curKwargs[cleanKey] = kwargs[kwarg].lower()
        elif "." not in kwarg:  # the kwarg was not namespaced therefore a "global"
            curKwargs[kwarg] = kwargs[kwarg]
    return curArgs, curKwargs


class ApiCall(object):
    _help = {"desc": "No help message available. Please tell the devs that a help msg is missing for this cmd"}

    def __init__(self,
                 handler,
                 args,  # type: List
                 kwargs  # type: Dict
                 ):

        # missing
        try:
            if self._missing:
                self.run = self.return_missing
        except AttributeError:
            pass
        # help
        if 'help' in kwargs:
            self.run = self.return_help

        # RequestHandler
        self.handler = handler

        # old Sickbeard call
        self._sickbeard_call = getattr(self, '_sickbeard_call', False)
        if 'help' not in kwargs and self._sickbeard_call:
            call_name = _functionMaper_reversed.get(self.__class__, '')
            if 'sb' != call_name:
                self.log('SickBeard API call "%s" should be replaced with SickGear API "%s" calls to get much '
                           'improved detail and functionality, contact your App developer and ask them to update '
                           'their code.' % (call_name, self._get_old_command()), logger.WARNING)

        self._requiredParams = []
        self._optionalParams = []

    @property
    def sickbeard_call(self):
        if hasattr(self, '_sickbeard_call'):
            return self._sickbeard_call
        return False

    @sickbeard_call.setter
    def sickbeard_call(self, v):
        self._sickbeard_call = v

    def run(self):
        # override with real output function in subclass
        return {}

    def log(self, msg, level=logger.MESSAGE):
        api_log(self.handler, msg, level)

    def _get_old_command(self, command_class=None):
        c_class = command_class or self
        new_call_name = None
        help = getattr(c_class, '_help', None)
        if getattr(c_class, '_sickbeard_call', False) or "SickGearCommand" in help:
            call_name = _functionMaper_reversed.get(c_class.__class__, '')
            new_call_name = 'sg.%s' % call_name.replace('sb.', '') if 'sb' != call_name else 'sg'
            if new_call_name not in _functionMaper:
                if isinstance(help, dict) and "SickGearCommand" in help \
                        and help['SickGearCommand'] in _functionMaper:
                    new_call_name = help['SickGearCommand']
                else:
                    new_call_name = 'sg.*'
        return new_call_name

    def return_help(self):
        try:
            if self._requiredParams:
                pass
        except AttributeError:
            self._requiredParams = []
        try:
            if self._optionalParams:
                pass
        except AttributeError:
            self._optionalParams = []

        for paramDict, param_type in [
            (self._requiredParams, "requiredParameters"),
            (self._optionalParams, "optionalParameters")
        ]:

            if param_type in self._help:
                for param_name in paramDict:
                    if param_name not in self._help[param_type]:
                        self._help[param_type][param_name] = {}
                    if paramDict[param_name]["allowedValues"]:
                        self._help[param_type][param_name]["allowedValues"] = paramDict[param_name]["allowedValues"]
                    else:
                        self._help[param_type][param_name]["allowedValues"] = "see desc"
                    self._help[param_type][param_name]["defaultValue"] = paramDict[param_name]["defaultValue"]

            elif paramDict:
                for param_name in paramDict:
                    self._help[param_type] = {}
                    self._help[param_type][param_name] = paramDict[param_name]
            else:
                self._help[param_type] = {}
        msg = "No description available"
        if "desc" in self._help:
            msg = self._help["desc"]
            del self._help["desc"]
        return _responds(RESULT_SUCCESS, self._help, msg)

    def return_missing(self):
        if 1 == len(self._missing):
            msg = "The required parameter: '" + self._missing[0] + "' was not set"
        else:
            msg = "The required parameters: '" + "','".join(self._missing) + "' where not set"
        try:
            remote_ip = self.handler.request.remote_ip
        except (BaseException, Exception):
            remote_ip = '"unknown ip"'
        self.log("API call from host %s triggers :: %s: %s" %
                   (remote_ip, _functionMaper_reversed.get(self.__class__, ''), msg),
                   logger.ERROR)
        return _responds(RESULT_ERROR, msg=msg)

    def check_params(self,
                     args,  # type: List
                     kwargs,  # type: Dict
                     key,
                     default,
                     required,
                     type,
                     allowedValues,
                     sub_type=None
                     ):
        # TODO: explain this
        """ function to check passed params for the shorthand wrapper
            and to detect missing/required param
        """
        # Fix for applications that send tvdbid instead of indexerid
        if self.sickbeard_call and "indexerid" == key and "indexerid" not in kwargs:
            key = "tvdbid"

        missing = True
        orgDefault = default

        if "bool" == type:
            allowedValues = [0, 1]

        if args:
            default = args[0]
            missing = False
            args = args[1:]
        if kwargs.get(key):
            default = kwargs.get(key)
            missing = False
        if required:
            try:
                _ = self._missing
                self._requiredParams[key] = {"allowedValues": allowedValues, "defaultValue": orgDefault}
            except AttributeError:
                self._missing = []
                self._requiredParams = {key: {"allowedValues": allowedValues, "defaultValue": orgDefault}}
            if missing and key not in self._missing:
                self._missing.append(key)
        else:
            try:
                self._optionalParams[key] = {"allowedValues": allowedValues, "defaultValue": orgDefault}
            except AttributeError:
                self._optionalParams = {key: {"allowedValues": allowedValues, "defaultValue": orgDefault}}

        if default:
            default = self._check_param_type(default, key, type, sub_type)
            if "bool" == type:
                type = []
            self._check_param_value(default, key, allowedValues)

        return default, args

    def _check_param_type(self, value, name, type, sub_type):
        """ checks if value can be converted / parsed to type
            will raise an error on failure
            or will convert it to type and return new converted value
            can check for:
            - int: will be converted into int
            - bool: will be converted to False / True
            - list: will always return a list
            - string: will do nothing for now
            - ignore: will ignore it, just like "string"
        """
        error = False
        if "int" == type:
            if _is_int(value):
                value = int(value)
            else:
                error = True
        elif "bool" == type:
            if value in ("0", "1"):
                value = bool(int(value))
            elif value in ("true", "True", "TRUE"):
                value = True
            elif value in ("false", "False", "FALSE"):
                value = False
            else:
                error = True
        elif "list" == type:
            if None is not sub_type:
                if sub_type in integer_types:
                    if isinstance(value, integer_types):
                        value = [value]
                    elif isinstance(value, string_types):
                        if '|' in value:
                            li = [int(v) for v in value.split('|')]
                            if any([not isinstance(v, integer_types) for v in li]):
                                error = True
                            else:
                                value = li
                        else:
                            value = [int(value)]
                    else:
                        error = True
                else:
                    li = value.split('|')
                    if any([sub_type is not type(v) for v in li]):
                        error = True
                    else:
                        value = li
            else:
                value = value.split("|")
        elif "dict" == type:
            if isinstance(value, dict):
                value = value
            else:
                error = True
        elif "string" == type:
            pass
        elif "ignore" == type:
            pass
        else:
            self.log(u"Invalid param type set " + str(type) + " can not check or convert ignoring it",
                       logger.ERROR)

        if error:
            # this is a real ApiError !!
            raise ApiError(
                u"param: '" + str(name) + "' with given value: '" + str(value) + "' could not be parsed into '" + str(
                    type) + "'")

        return value

    def _check_param_value(self, value, name, allowedValues):
        """ will check if value (or all values in it ) are in allowed values
            will raise an exception if value is "out of range"
            if bool(allowedValue) == False a check is not performed and all values are excepted
        """
        if allowedValues:
            error = False
            if isinstance(value, list):
                for item in value:
                    if item not in allowedValues:
                        error = True
            else:
                if value not in allowedValues:
                    error = True

            if error:
                # this is kinda a ApiError but raising an error is the only way of quitting here
                raise ApiError(u"param: '" + str(name) + "' with given value: '" + str(
                    value) + "' is out of allowed range '" + str(allowedValues) + "'")


class TVDBShorthandWrapper(ApiCall):
    _help = {"desc": "this is an internal function wrapper. call the help command directly for more information"}

    def __init__(self,
                 handler,
                 args,  # type: List
                 kwargs,  # type: Dict
                 sid  # type: AnyStr
                 ):
        self.handler = handler
        self.origArgs = args
        self.kwargs = kwargs
        self.sid = sid

        self.s, args = self.check_params(args, kwargs, "s", None, False, "ignore", [])
        self.e, args = self.check_params(args, kwargs, "e", None, False, "ignore", [])
        self.args = args

        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ internal function wrapper """
        args = (self.sid,) + self.origArgs
        if self.e:
            return CMD_Episode(self.handler, args, self.kwargs).run()
        elif self.s:
            return CMD_ShowSeasons(self.handler, args, self.kwargs).run()
        else:
            return CMD_Show(self.handler, args, self.kwargs).run()


# ###############################
# helper functions         #
# ###############################

def _sizeof_fmt(num):
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if 1024.00 > num:
            return "%3.2f %s" % (num, x)
        num /= 1024.00


def _is_int(data):
    try:
        int(data)
    except (TypeError, ValueError, OverflowError):
        return False
    else:
        return True


def _rename_element(dict, oldKey, newKey):
    try:
        dict[newKey] = dict[oldKey]
        del dict[oldKey]
    except (ValueError, TypeError, NameError):
        pass
    return dict


def _responds(result_type, data=None, msg=""):
    """
    result is a string of given "type" (success/failure/timeout/error)
    message is a human readable string, can be empty
    data is either a dict or a array, can be a empty dict or empty array
    """
    if None is data:
        data = {}
    return {"result": result_type_map[result_type],
            "message": msg,
            "data": data}


def _get_quality_string(q):
    qualityString = "Custom"
    if q in qualityPresetStrings:
        qualityString = qualityPresetStrings[q]
    elif q in Quality.qualityStrings:
        qualityString = Quality.qualityStrings[q]
    return qualityString


def _get_status_Strings(s):
    return statusStrings[s]


def _ordinal_to_dateTimeForm(ordinal):
    # workaround for episodes with no airdate
    if 1 != int(ordinal):
        date = datetime.date.fromordinal(ordinal)
    else:
        return ""
    return date.strftime(dateTimeFormat)


def _ordinal_to_dateForm(ordinal):
    if 1 != int(ordinal):
        date = datetime.date.fromordinal(ordinal)
    else:
        return ""
    return date.strftime(dateFormat)


def _historyDate_to_dateTimeForm(timeString):
    date = datetime.datetime.strptime(timeString, history.dateFormat)
    return date.strftime(dateTimeFormat)


def _replace_statusStrings_with_statusCodes(statusStrings):
    statusCodes = []
    if "snatched" in statusStrings:
        statusCodes += Quality.SNATCHED
    if "downloaded" in statusStrings:
        statusCodes += Quality.DOWNLOADED
    if "skipped" in statusStrings:
        statusCodes.append(SKIPPED)
    if "wanted" in statusStrings:
        statusCodes.append(WANTED)
    if "archived" in statusStrings:
        statusCodes += Quality.ARCHIVED
    if "ignored" in statusStrings:
        statusCodes.append(IGNORED)
    if "unaired" in statusStrings:
        statusCodes.append(UNAIRED)
    return statusCodes


def _mapQuality(show_obj):
    quality_map = _getQualityMap()

    anyQualities = []
    bestQualities = []

    iqualityID, aqualityID = Quality.splitQuality(int(show_obj))
    if iqualityID:
        for quality in iqualityID:
            anyQualities.append(quality_map[quality])
    if aqualityID:
        for quality in aqualityID:
            bestQualities.append(quality_map[quality])
    return anyQualities, bestQualities


def _getQualityMap():
    return quality_map_inversed


def _getRootDirs():
    if "" == sickbeard.ROOT_DIRS:
        return {}

    rootDir = {}
    root_dirs = sickbeard.ROOT_DIRS.split('|')
    default_index = int(sickbeard.ROOT_DIRS.split('|')[0])

    rootDir["default_index"] = int(sickbeard.ROOT_DIRS.split('|')[0])
    # remove default_index value from list (this fixes the offset)
    root_dirs.pop(0)

    if len(root_dirs) < default_index:
        return {}

    # clean up the list - replace %xx escapes by their single-character equivalent
    root_dirs = [unquote_plus(x) for x in root_dirs]

    default_dir = root_dirs[default_index]

    dir_list = []
    for root_dir in root_dirs:
        valid = 1
        try:
            ek.ek(os.listdir, root_dir)
        except (BaseException, Exception):
            valid = 0
        default = 0
        if root_dir is default_dir:
            default = 1

        dir_list.append({'valid': valid, 'location': root_dir, 'default': default})

    return dir_list


class ApiError(Exception):
    """Generic API error"""


class IntParseError(Exception):
    """A value could not be parsed into a int. But should be parsable to a int """


# -------------------------------------------------------------------------------------#

class CMD_ListCommands(ApiCall):
    _help = {"desc": "list help of all commands"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get help information for all commands """
        out = ''
        table_sickgear_commands = ''
        table_sickbeard_commands = ''
        for f, v in sorted(iteritems(_functionMaper), key=lambda x: (re.sub(r'^s[bg]\.', '', x[0], flags=re.I),
                                                                     re.sub(r'^sg\.', '1', x[0], flags=re.I))):
            if 'listcommands' == f:
                continue
            help = getattr(v, '_help', None)
            is_old_command = isinstance(help, dict) and "SickGearCommand" in help
            if is_old_command:
                table_sickbeard_commands += '<tr><td>%s</td>' % f
            else:
                table_sickgear_commands += '<tr><td>%s</td>' % f
            color = ("", " style='color: grey !important;'")[is_old_command]
            out += '<hr><h1 class="command"%s>%s%s</h1>' \
                   % (color, f, ("",
                                 " <span style='font-size: 50%;color: black;'>(Sickbeard compatibility command)</span>"
                                 )[is_old_command])
            if isinstance(help, dict):
                sg_cmd_new = self._get_old_command(command_class=v)
                sg_cmd = ''
                if sg_cmd_new:
                    sg_cmd = '<td>%s</td>' % sg_cmd_new
                    out += "<p style='color: darkgreen !important;'>for all features use SickGear API Command: <b>%s</b></p>" % sg_cmd_new
                if "desc" in help:
                    if is_old_command:
                        table_sickbeard_commands += '<td>%s</td>%s' % (help['desc'], sg_cmd)
                    else:
                        table_sickgear_commands += '<td>%s</td>' % help['desc']
                    out += help['desc']

                table = ''

                if "requiredParameters" in help and isinstance(help['requiredParameters'], dict):
                    for p, d in iteritems(help['requiredParameters']):
                        des = ''
                        if isinstance(d, dict) and 'desc' in d:
                            des = d.get('desc')
                        table += "<tr><td><span>%s <span class='parareq'>required</span></span></td>" \
                                 "<td><p>%s</p></td></tr>" % (p, des)

                if "optionalParameters" in help and isinstance(help['optionalParameters'], dict):
                    for p, d in iteritems(help['optionalParameters']):
                        des = ''
                        if isinstance(d, dict) and 'desc' in d:
                            des = d.get('desc')
                        table += "<tr><td><span>%s <span class='paraopt'>optional</span></span></td>" \
                                 "<td><p>%s</p></td></tr>" % (p, des)
                if table:
                    out += "<table class='sickbeardTable' cellspacing='1' border='1' cellpadding='0'><thead>" \
                           "<tr><th style='width: 25%'>Parameter</th><th>Description</th></tr>" \
                           "</thead><tbody>"
                    out += table
                    out += '</tbody></table>'
            else:
                if is_old_command:
                    table_sickbeard_commands += '<td>%s</td><td></td>' % 'no description'
                else:
                    table_sickgear_commands += '<td>%s</td>' % 'no description'

            if is_old_command:
                table_sickbeard_commands += '</tr>'
            else:
                table_sickgear_commands += '</tr>'

        if table_sickbeard_commands:
            out = "<h1>SickBeard Commands (compatibility):</h1>" \
                  "<table class='sickbeardTable' cellspacing='1' border='1' cellpadding='0'><thead>" \
                  "<tr><th style='width: 25%'>Command</th><th>Description</th>" \
                  "<th style='width: 25%'>Replacement SickGear Command</th></tr>" \
                  "</thead><tbody>" + table_sickbeard_commands + '</tbody></table>' + out

        if table_sickgear_commands:
            out = "<h1>SickGear Commands:</h1>" \
                  "<table class='sickbeardTable' cellspacing='1' border='1' cellpadding='0'><thead>" \
                  "<tr><th style='width: 25%'>Command</th><th>Description</th></tr>" \
                  "</thead><tbody>" + table_sickgear_commands + '</tbody></table>' + out

        return out


class CMD_Help(ApiCall):
    _help = {"desc": "get help information for a given subject/command",
             "optionalParameters": {"subject": {"desc": "command - the top level command"}}}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.subject, args = self.check_params(args, kwargs, "subject", "help",
                                               False, "string", iterkeys(_functionMaper))
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get help information for a given subject/command """
        if self.subject in _functionMaper:
            out = _responds(RESULT_SUCCESS, _functionMaper.get(self.subject)(None, (), {"help": 1}).run())
        else:
            out = _responds(RESULT_FAILURE, msg="No such cmd")
        return out


class CMD_SickGearComingEpisodes(ApiCall):
    _help = {"desc": "get the daily schedule",
             "optionalParameters":
                 {"sort": {"desc": "change the sort order"},
                  "type": {"desc": "one or more of allowed values separated by |"},
                  "paused": {"desc": "0 to exclude paused shows, 1 to include them, "
                                     "2 to only view paused, or omitted to use the SG default"},
                  }
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.sort, args = self.check_params(args, kwargs, "sort", "date", False, "string", ["date", "show", "network"])
        self.type, args = self.check_params(args, kwargs, "type", "today|missed|soon|later", False, "list",
                                            ["missed", "later", "today", "soon"])
        self.paused, args = self.check_params(args, kwargs, "paused", sickbeard.EPISODE_VIEW_DISPLAY_PAUSED,
                                              False, "int", [0, 1, 2])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the daily schedule """
        sql_result, fanart, sorts, next_week_dt, today, next_week = webserve.MainHandler.get_daily_schedule()
        sql_result.sort(key=sorts[(self.sort, 'time')['date' == self.sort]])

        finalEpResults = {}

        # add all requested types or all
        for curType in self.type:
            finalEpResults[curType] = []

        for ep in sql_result:
            """
                Missed:   yesterday... (less than 1week)
                Today:    today
                Soon:     tomorrow till next week
                Later:    later than next week
            """

            if not ((int(ep['paused']) and self.paused) or (not int(ep['paused']) and 2 != self.paused)):
                continue

            ep['airdate'] = int(ep["airdate"])

            status = "soon"
            if ep["airdate"] < today:
                status = "missed"
            elif ep["airdate"] >= next_week:
                status = "later"
            elif today <= ep["airdate"] < next_week:
                if ep["airdate"] == today:
                    status = "today"
                else:
                    status = "soon"

            # skip unwanted
            if None is not self.type and status not in self.type:
                continue

            if not ep["network"]:
                ep["network"] = ""

            ep["quality"] = _get_quality_string(ep["quality"])
            # clean up Tvdb horrible airs field
            ep['airs'] = str(ep['airs']).replace('am', ' AM').replace('pm', ' PM').replace('  ', ' ')
            # start day of the week on 1 (monday)
            ep['weekday'] = 1 + datetime.date.fromordinal(ep['airdate']).weekday()
            ep['ep_name'] = ep['name']
            ep['ep_plot'] = ep['description']
            # add parsed_datetime to the dict
            ep['local_datetime'] = SGDatetime.sbstrftime(
                SGDatetime.convert_to_setting(ep['parsed_datetime'], force_local=True), dateTimeFormat)
            ep['status_str'] = statusStrings[ep['status']]
            ep['network'] = ep['episode_network'] or ep['network']
            ep['timezone'] = ep['ep_timezone'] or ep['show_timezone'] or ep['timezone'] or (
                    ep['network'] and network_timezones.get_network_timezone(ep['network'], return_name=True)[1])

            # remove all field we don't want for api response
            for cur_f in list_keys(ep):
                if cur_f not in [  # fields to preserve
                    'absolute_number', 'air_by_date', 'airdate', 'airs', 'archive_firstmatch',
                    'classification', 'data_network', 'data_show_name',
                    'ep_name', 'ep_plot', 'episode', 'episode_id', 'genre',
                    'imdb_id', 'imdb_url', 'indexer', 'indexer_id', 'indexerid',
                    'lang', 'local_datetime', 'network', 'overview', 'parsed_datetime', 'paused', 'prod_id',
                    'quality', 'runtime', 'scene', 'scene_absolute_number', 'scene_episode', 'scene_season',
                    'season', 'show_id', 'show_name', 'show_network', 'show_status', 'showid', 'startyear',
                    'status', 'status_str', 'tag', 'timezone', 'trakt_watched', 'tv_id', 'tvid_prodid',
                    'version', 'weekday'
                ]:
                    del ep[cur_f]

            # Add tvdbid for backward compatibility
            try:
                show_obj = helpers.find_show_by_id({ep['tv_id']: ep['prod_id']})
                ep['tvdbid'] = show_obj.ids.get(TVINFO_TVDB, {'id': 0})['id']
                ep['ids'] = {k: v.get('id') for k, v in iteritems(show_obj.ids)}
            except (BaseException, Exception):
                ep['tvdbid'] = (None, ep['prod_id'])[TVINFO_TVDB == ep['tv_id']]
                ep['ids'] = None

            ep['airdate'] = SGDatetime.sbfdate(
                datetime.date.fromordinal(ep['airdate']), d_preset=dateFormat)
            ep['parsed_datetime'] = SGDatetime.sbfdatetime(ep['parsed_datetime'],
                                                           d_preset=dateFormat, t_preset='%H:%M %z')

            # TODO: check if this obsolete
            if status not in finalEpResults:
                finalEpResults[status] = []

            finalEpResults[status].append(ep)

        return _responds(RESULT_SUCCESS, finalEpResults)


class CMD_ComingEpisodes(CMD_SickGearComingEpisodes):
    _help = {"desc": "get the daily schedule",
             "optionalParameters":
                 {"sort": {"desc": "change the sort order"},
                  "type": {"desc": "one or more of allowed values separated by |"},
                  "paused": {"desc": "0 to exclude paused shows, 1 to include them, or omitted to use the SG default"}
                  },
             "SickGearCommand": "sg.future"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearComingEpisodes.__init__(self, handler, args, kwargs)


class CMD_SickGearEpisode(ApiCall):
    _help = {"desc": "get episode information",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    "season": {"desc": "the season number"},
                                    "episode": {"desc": "the episode number"}
                                    },
             "optionalParameters": {"full_path": {
                 "desc": "show the full absolute path (if valid) instead of a relative path for the episode location"}},
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.s, args = self.check_params(args, kwargs, "season", None, True, "int", [])
        self.e, args = self.check_params(args, kwargs, "episode", None, True, "int", [])
        # optional
        self.fullPath, args = self.check_params(args, kwargs, "full_path", 0, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get episode information """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        my_db = db.DBConnection(row_type="dict")
        sql_result = my_db.select(
            "SELECT name, description, airdate, status, location, file_size, release_name, "
            " subtitles, absolute_number,scene_season, scene_episode, scene_absolute_number"
            " FROM tv_episodes"
            " WHERE indexer = ? AND showid = ?"
            " AND episode = ? AND season = ?",
            [self.tvid, self.prodid, self.e, self.s])
        if 1 != len(sql_result):
            raise ApiError("Episode not found")
        episode = sql_result[0]
        # handle path options
        # absolute vs relative vs broken
        showPath = None
        try:
            showPath = show_obj.location
        except exceptions_helper.ShowDirNotFoundException:
            pass

        if bool(self.fullPath) and showPath:
            pass
        elif not bool(self.fullPath) and showPath:
            # using the length because lstrip removes too much
            showPathLength = len(showPath) + 1  # the / or \ yeah not that nice i know
            episode["location"] = episode["location"][showPathLength:]
        elif not showPath:  # show dir is broken ... episode path will be empty
            episode["location"] = ""
        # convert stuff to human form
        timezone, episode['timezone'] = network_timezones.get_network_timezone(show_obj.network, return_name=True)
        episode['airdate'] = SGDatetime.sbfdate(SGDatetime.convert_to_setting(
            network_timezones.parse_date_time(int(episode['airdate']), show_obj.airs, timezone)), d_preset=dateFormat)
        status, quality = Quality.splitCompositeStatus(int(episode["status"]))
        episode["status"] = _get_status_Strings(status)
        episode["quality"] = _get_quality_string(quality)
        episode["file_size_human"] = _sizeof_fmt(episode["file_size"])

        return _responds(RESULT_SUCCESS, episode)


class CMD_Episode(CMD_SickGearEpisode):
    _help = {"desc": "get detailed episode info",
             "requiredParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "season": {"desc": "the season number"},
                                    "episode": {"desc": "the episode number"}
                                    },
             "optionalParameters": {"full_path": {
                 "desc": "show the full absolute path (if valid) instead of a relative path for the episode location"},
                                   },
             "SickGearCommand": "sg.episode",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearEpisode.__init__(self, handler, args, kwargs)


class CMD_SickGearEpisodeSearch(ApiCall):
    _help = {"desc": "search for an episode. the response might take some time",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    "season": {"desc": "the season number"},
                                    "episode": {"desc": "the episode number"}
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.s, args = self.check_params(args, kwargs, "season", None, True, "int", [])
        self.e, args = self.check_params(args, kwargs, "episode", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ search for an episode """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        # retrieve the episode object and fail if we can't get one
        ep_obj = show_obj.get_episode(int(self.s), int(self.e))
        if isinstance(ep_obj, str):
            return _responds(RESULT_FAILURE, msg="Episode not found")

        # make a queue item for it and put it on the queue
        ep_queue_item = search_queue.ManualSearchQueueItem(show_obj, ep_obj)
        sickbeard.search_queue_scheduler.action.add_item(ep_queue_item)

        # wait until the queue item tells us whether it worked or not
        while None is ep_queue_item.success:
            time.sleep(1)

        # return the correct json value
        if ep_queue_item.success:
            status, quality = Quality.splitCompositeStatus(ep_obj.status)
            # TODO: split quality and status?
            return _responds(RESULT_SUCCESS, {"quality": _get_quality_string(quality)},
                             "Snatched (" + _get_quality_string(quality) + ")")

        return _responds(RESULT_FAILURE, msg='Unable to find episode')


class CMD_EpisodeSearch(CMD_SickGearEpisodeSearch):
    _help = {"desc": "search for an episode. the response might take some time",
             "requiredParameters": {"tvdbid": {"desc": "thetvdb.com id of a show"},
                                    "season": {"desc": "the season number"},
                                    "episode": {"desc": "the episode number"}
                                    },
             "SickGearCommand": "sg.episode.search",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearEpisodeSearch.__init__(self, handler, args, kwargs)


class CMD_SickGearEpisodeSetStatus(ApiCall):
    _help = {"desc": "set status of an episode (or season if episode is not provided)",
             "requiredParameters": {
                 "indexer": {"desc": "indexer of a show"},
                 "indexerid": {"desc": "unique id of a show"},
                 "season": {"desc": "the season number"},
                 "status": {
                     "desc": "the status values: wanted, skipped, archived, ignored, failed, snatched, downloaded"}
             },
             "optionalParameters": {
                 "episode": {"desc": "the episode number"},
                 "force": {"desc": "should we replace existing (downloaded) episodes or not"},
                 "quality": {"desc": "set quality of episode(s), only for statuses: snatched, downloaded, archived"}}
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.s, args = self.check_params(args, kwargs, "season", None, True, "int", [])
        self.status, args = self.check_params(args, kwargs, "status", None, True, "string", [
            "wanted", "skipped", "archived", "ignored", "failed", "snatched", "downloaded"])
        # optional
        self.e, args = self.check_params(args, kwargs, "episode", None, False, "int", [])
        self.force, args = self.check_params(args, kwargs, "force", 0, False, "bool", [])
        self.quality, args = self.check_params(args, kwargs, "quality", None, False, "string", [q for q in quality_map])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ set status of an episode or a season (when no ep is provided) """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        # convert the string status to a int
        for status in statusStrings.statusStrings:
            if str(statusStrings[status]).lower() == str(self.status).lower():
                self.status = status
                break
        else:  # if we dont break out of the for loop we got here.
            # the allowed values has at least one item that could not be matched against the internal status strings
            raise ApiError("The status string could not be matched to a status. Report to Devs!")

        if None is not self.quality:
            if self.status not in (SNATCHED, SNATCHED_BEST, SNATCHED_PROPER, DOWNLOADED, ARCHIVED):
                return _responds(RESULT_FAILURE, msg="Can't set status %s together with quailty: %s" %
                                                     (statusStrings[self.status], self.quality))
            self.quality = quality_map[self.quality]

        # ep_obj_list = []
        if self.e:
            ep_obj = show_obj.get_episode(self.s, self.e)
            if None is ep_obj:
                return _responds(RESULT_FAILURE, msg="Episode not found")
            ep_obj_list = [ep_obj]
        else:
            # get all episode numbers from self,season
            ep_obj_list = show_obj.get_all_episodes(season=self.s)

        def _epResult(result_code, ep, msg=""):
            return {'season': ep.season, 'episode': ep.episode, 'status': _get_status_Strings(ep.status),
                    'result': result_type_map[result_code], 'message': msg}

        ep_results = []
        failure = False
        start_backlog = False
        segments = {}

        sql_l = []
        for ep_obj in ep_obj_list:
            with ep_obj.lock:
                if self.status == WANTED:
                    # figure out what episodes are wanted so we can backlog them
                    if ep_obj.season in segments:
                        segments[ep_obj.season].append(ep_obj)
                    else:
                        segments[ep_obj.season] = [ep_obj]

                # don't let them mess up UNAIRED episodes
                if ep_obj.status == UNAIRED:
                    if None is not self.e:
                        # setting the status of a UNAIRED is only considered a failure
                        # if we directly wanted this episode, but is ignored on a season request
                        ep_results.append(
                            _epResult(RESULT_FAILURE, ep_obj, "Refusing to change status because it is UNAIRED"))
                        failure = True
                    continue

                # allow the user to force setting the status for an already downloaded episode
                if ep_obj.status in Quality.DOWNLOADED and not self.force and None is self.quality:
                    ep_results.append(_epResult(RESULT_FAILURE, ep_obj,
                                                "Refusing to change status because it is already marked as DOWNLOADED"))
                    failure = True
                    continue

                if None is not self.quality:
                    ep_obj.status = Quality.compositeStatus(self.status, self.quality)
                else:
                    ep_obj.status = self.status
                result = ep_obj.get_sql()
                if None is not result:
                    sql_l.append(result)

                if self.status == WANTED:
                    start_backlog = True
                ep_results.append(_epResult(RESULT_SUCCESS, ep_obj))

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

        extra_msg = ""
        if start_backlog:
            for season, segment in iteritems(segments):  # type: int, List[TVEpisode]
                backlog_queue_item = search_queue.BacklogQueueItem(show_obj, segment)
                sickbeard.search_queue_scheduler.action.add_item(backlog_queue_item)

                self.log(u'Starting backlog for %s season %s because some episodes were set to WANTED' %
                         (show_obj.unique_name, season))

            extra_msg = " Backlog started"

        if failure:
            return _responds(RESULT_FAILURE, ep_results, 'Failed to set all or some status. Check data.' + extra_msg)
        else:
            return _responds(RESULT_SUCCESS, msg='All status set successfully.' + extra_msg)


class CMD_EpisodeSetStatus(CMD_SickGearEpisodeSetStatus):
    _help = {"desc": "set status of an episode or season (when no ep is provided)",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com unique id of a show"},
                                    "season": {"desc": "the season number"},
                                    "status": {"desc": "the status values: wanted, skipped, archived, ignored, failed"}
                                    },
             "optionalParameters": {"episode": {"desc": "the episode number"},
                                    "force": {"desc": "should we replace existing (downloaded) episodes or not"}
                                    },
             "SickGearCommand": "sg.episode.setstatus",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        kwargs['indexer'] = TVINFO_TVDB
        CMD_SickGearEpisodeSetStatus.__init__(self, handler, args, kwargs)


class CMD_SickGearSubtitleSearch(ApiCall):
    _help = {"desc": "search episode subtitles. the response might take some time",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    "season": {"desc": "the season number"},
                                    "episode": {"desc": "the episode number"}
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.s, args = self.check_params(args, kwargs, "season", None, True, "int", [])
        self.e, args = self.check_params(args, kwargs, "episode", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ search episode subtitles """
        if not sickbeard.USE_SUBTITLES:
            return _responds(RESULT_FAILURE, msg='Subtitle search is disabled in SickGear')

        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        # retrieve the episode object and fail if we can't get one
        ep_obj = show_obj.get_episode(int(self.s), int(self.e))
        if isinstance(ep_obj, str):
            return _responds(RESULT_FAILURE, msg="Episode not found")

        # try do download subtitles for that episode
        previous_subtitles = ep_obj.subtitles

        try:
            _ = ep_obj.download_subtitles()
        except (BaseException, Exception):
            return _responds(RESULT_FAILURE, msg='Unable to find subtitles')

        # return the correct json value
        if previous_subtitles != ep_obj.subtitles:
            status = 'New subtitles downloaded: %s' % ' '.join([
                "<img src='" + sickbeard.WEB_ROOT + "/images/flags/" + subliminal.language.Language(
                    x).alpha2 + ".png' alt='" + subliminal.language.Language(x).name + "'/>" for x in
                sorted(list(set(ep_obj.subtitles).difference(previous_subtitles)))])
            response = _responds(RESULT_SUCCESS, msg='New subtitles found')
        else:
            status = 'No subtitles downloaded'
            response = _responds(RESULT_FAILURE, msg='Unable to find subtitles')

        ui.notifications.message('Subtitles Search', status)

        return response


class CMD_SubtitleSearch(ApiCall):
    _help = {"desc": "search episode subtitles. the response might take some time",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com unique id of a show"},
                                    "season": {"desc": "the season number"},
                                    "episode": {"desc": "the episode number"}
                                    },
             "SickGearCommand": "sg.episode.subtitlesearch",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        ApiCall.__init__(self, handler, args, kwargs)


class CMD_SickGearExceptions(ApiCall):
    _help = {"desc": "get scene exceptions for all or a given show",
             "optionalParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, False, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get scene exceptions for all or a given show """
        my_db = db.DBConnection(row_type="dict")

        if None is self.prodid:
            sql_result = my_db.select("SELECT s.indexer, se.show_name, se.indexer_id AS 'indexerid' "
                                      "FROM scene_exceptions AS se INNER JOIN tv_shows as s "
                                      "ON se.indexer_id == s.indexer_id")
            scene_exceptions = {}
            for cur_result in sql_result:
                indexerid = cur_result["indexerid"]
                indexer = cur_result["indexer"]
                if self.sickbeard_call:
                    if indexerid not in scene_exceptions:
                        scene_exceptions[indexerid] = []
                    scene_exceptions[indexerid].append(cur_result["show_name"])
                else:
                    if indexerid not in scene_exceptions.get(indexer, {}):
                        scene_exceptions.setdefault(indexer, {})[indexerid] = []
                    scene_exceptions.setdefault(indexer, {})[indexerid].append(cur_result["show_name"])

        else:
            show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
            if not show_obj:
                return _responds(RESULT_FAILURE, msg="Show not found")

            sql_result = my_db.select(
                "SELECT indexer, show_name, indexer_id AS 'indexerid' FROM scene_exceptions "
                "WHERE indexer = ? AND indexer_id = ?", [self.tvid, self.prodid])
            scene_exceptions = []
            for cur_result in sql_result:
                scene_exceptions.append(cur_result["show_name"])

        return _responds(RESULT_SUCCESS, scene_exceptions)


class CMD_Exceptions(CMD_SickGearExceptions):
    _help = {"desc": "get scene exceptions for all or a given show",
             "optionalParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.exceptions",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearExceptions.__init__(self, handler, args, kwargs)


class CMD_SetExceptions(ApiCall):
    _help = {"desc": "set scene exceptions for a given show",
             "requiredParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    "forseason": {"desc": "exception for season, -1 for all seasons"},
                                    },
             "optionalParameters": {"add": {"desc": "list of exceptions to add"},
                                    "remove": {"desc": "list of exceptions to remove"}},
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.forseason, args = self.check_params(args, kwargs, "forseason", None, True, "int", [])
        # optional
        self.add, args = self.check_params(args, kwargs, "add", None, False, "list", [])
        self.remove, args = self.check_params(args, kwargs, "remove", None, False, "list", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        if not self.add and not self.remove:
            return _responds(RESULT_FAILURE, 'No Exceptions provided to be add or removed.')

        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, 'Could not find any show in db from indexer: %s with id: %s' %
                             (self.tvid, self.prodid))

        my_db = db.DBConnection(row_type="dict")
        sql_result = my_db.select("SELECT show_name, season, indexer, indexer_id AS 'indexerid'"
                                  " FROM scene_exceptions"
                                  " WHERE indexer = ? AND indexer_id = ?"
                                  " AND season = ?",
                                  [self.tvid, self.prodid, self.forseason])

        cl = []
        curexep = [(s['show_name'], s['season']) for s in sql_result]
        add_list = []
        remove_list = []
        if self.remove:
            for r in self.remove:
                if (r, self.forseason) in curexep:
                    cl.append(['DELETE FROM scene_exceptions WHERE indexer = ? AND indexer_id = ? AND season = ? '
                               'AND show_name = ?', [self.tvid, self.prodid, self.forseason, r]])
                    try:
                        curexep.remove((r, self.forseason))
                    except ValueError:
                        pass
                    remove_list.append(r)

        if self.add:
            for a in self.add:
                if (a, self.forseason) not in curexep:
                    cl.append(['INSERT INTO scene_exceptions (show_name, indexer, indexer_id, season) VALUES (?,?,?,?)',
                               [a, self.tvid, self.prodid, self.forseason]])
                    curexep.append((a, self.forseason))
                    add_list.append(a)

        if cl:
            my_db.mass_action(cl)
        return _responds(RESULT_SUCCESS, data={'added': add_list, 'removed': remove_list, 'for season': self.forseason,
                                               'current': [c[0] for c in curexep], 'indexer': self.tvid,
                                               'indexerid': self.prodid},
                         msg='Exceptions changed.')


class CMD_SickGearHistory(ApiCall):
    _help = {"desc": "get the sickgear downloaded/snatched history",
             "optionalParameters": {"limit": {"desc": "limit returned results"},
                                    "type": {"desc": "only show a specific type of results"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.limit, args = self.check_params(args, kwargs, "limit", 100, False, "int", [])
        self.type, args = self.check_params(args, kwargs, "type", None, False, "string", ["downloaded", "snatched"])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the sickgear downloaded/snatched history """

        # typeCodes = []
        if "downloaded" == self.type:
            self.type = "Downloaded"
            typeCodes = Quality.DOWNLOADED + Quality.ARCHIVED + Quality.FAILED
        elif "snatched" == self.type:
            self.type = "Snatched"
            typeCodes = Quality.SNATCHED_ANY
        else:
            typeCodes = Quality.SNATCHED_ANY + Quality.DOWNLOADED + Quality.ARCHIVED + Quality.FAILED

        my_db = db.DBConnection(row_type="dict")

        ulimit = min(int(self.limit), 100)
        if 0 == ulimit:
            # noinspection SqlResolve
            sql_result = my_db.select(
                "SELECT h.*, show_name, s.indexer FROM history h, tv_shows s WHERE h.hide = 0" +
                " AND h.showid=s.indexer_id" +
                ("", " AND s.indexer=%s" % TVINFO_TVDB)[self.sickbeard_call] +
                " AND action in (" + ','.join(['?'] * len(typeCodes)) + ") ORDER BY date DESC", typeCodes)
        else:
            # noinspection SqlResolve
            sql_result = my_db.select(
                "SELECT h.*, show_name, s.indexer FROM history h, tv_shows s WHERE h.hide = 0" +
                " AND h.showid=s.indexer_id" +
                ("", " AND s.indexer=%s" % TVINFO_TVDB)[self.sickbeard_call] +
                " AND action in (" + ','.join(['?'] * len(typeCodes)) + ") ORDER BY date DESC LIMIT ?",
                typeCodes + [ulimit])

        results = []
        for cur_result in sql_result:
            status, quality = Quality.splitCompositeStatus(int(cur_result["action"]))
            status = _get_status_Strings(status)
            if self.type and not status == self.type:
                continue
            cur_result["status"] = status
            cur_result["quality"] = _get_quality_string(quality)
            cur_result["date"] = _historyDate_to_dateTimeForm(str(cur_result["date"]))
            del cur_result["action"]
            _rename_element(cur_result, "showid", "indexerid")
            cur_result["resource_path"] = os.path.dirname(cur_result["resource"])
            cur_result["resource"] = os.path.basename(cur_result["resource"])
            # Add tvdbid for backward compatibility
            cur_result['tvdbid'] = (None, cur_result['indexerid'])[TVINFO_TVDB == cur_result['indexer']]
            results.append(cur_result)

        return _responds(RESULT_SUCCESS, results)


class CMD_History(CMD_SickGearHistory):
    _help = {"desc": "get the sickgear downloaded/snatched history",
             "optionalParameters": {"limit": {"desc": "limit returned results"},
                                    "type": {"desc": "only show a specific type of results"},
                                    },
             "SickGearCommand": "sg.history",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearHistory.__init__(self, handler, args, kwargs)


class CMD_SickGearHistoryClear(ApiCall):
    _help = {"desc": "clear the sickgear history"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ clear the sickgear history """
        my_db = db.DBConnection()
        my_db.action('UPDATE history SET hide = ? WHERE hide = 0', [1])

        return _responds(RESULT_SUCCESS, msg="History cleared")


class CMD_HistoryClear(CMD_SickGearHistoryClear):
    _help = {"desc": "clear the sickgear history",
             "SickGearCommand": "sg.history.clear"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearHistoryClear.__init__(self, handler, args, kwargs)


class CMD_SickGearHistoryTrim(ApiCall):
    _help = {"desc": "trim the sickgear history by removing entries greater than 30 days old"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ trim the sickgear history """
        my_db = db.DBConnection()
        my_db.action("UPDATE history SET hide = ? WHERE date < " + str(
            (datetime.datetime.now() - datetime.timedelta(days=30)).strftime(history.dateFormat)), [1])

        return _responds(RESULT_SUCCESS, msg="Removed history entries greater than 30 days old")


class CMD_HistoryTrim(CMD_SickGearHistoryTrim):
    _help = {"desc": "trim the sickgear history by removing entries greater than 30 days old",
             "SickGearCommand": "sg.history.trim"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearHistoryTrim.__init__(self, handler, args, kwargs)


class CMD_SickGearLogs(ApiCall):
    _help = {"desc": "get log file entries",
             "optionalParameters": {"min_level ": {
                 "desc": "the minimum level classification of log entries to return,"
                         " with each level inheriting log entries from the level above"}}
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.min_level, args = self.check_params(args, kwargs, "min_level", "error", False, "string",
                                                 ["error", "warning", "info", "debug"])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get log file entries """
        # 10 = Debug / 20 = Info / 30 = Warning / 40 = Error
        min_level = logger.reverseNames[str(self.min_level).upper()]
        max_lines = 50

        regex = r"^(\d\d\d\d)\-(\d\d)\-(\d\d)\s*(\d\d)\:(\d\d):(\d\d)\s*([A-Z]+)\s*(.+?)\s*\:\:\s*(.*)$"

        final_data = []
        normal_data = []
        truncate = []
        repeated = None
        num_lines = 0

        if os.path.isfile(logger.sb_log_instance.log_file_path):
            for x in logger.sb_log_instance.reverse_readline(logger.sb_log_instance.log_file_path):

                x = decode_str(x)
                match = re.match(regex, x)

                if match:
                    level = match.group(7)
                    if level not in logger.reverseNames:
                        normal_data = []
                        continue

                    if logger.reverseNames[level] >= min_level:
                        if truncate and not normal_data and truncate[0] == match.group(8) + match.group(9):
                            truncate += [match.group(8) + match.group(9)]
                            repeated = x
                            continue

                        if 1 < len(truncate):
                            final_data[-1] = repeated.strip() + ' (... %s repeat lines)\n' % len(truncate)

                        truncate = [match.group(8) + match.group(9)]

                        final_data.append(x)
                        if any(normal_data):
                            final_data += ['%02s) %s' % (n + 1, x) for n, x in enumerate(normal_data[::-1])] + \
                                          ['<br />']
                            num_lines += len(normal_data)
                            normal_data = []
                    else:
                        normal_data = []
                        continue

                else:
                    if not any(normal_data) and not any([x.strip()]):
                        continue

                    normal_data.append(re.sub(r'\r?\n', '<br />', x.replace('<', '&lt;').replace('>', '&gt;')))

                num_lines += 1

                if num_lines >= max_lines:
                    break

        return _responds(RESULT_SUCCESS, final_data)


class CMD_Logs(CMD_SickGearLogs):
    _help = {"desc": "get log file entries",
             "optionalParameters": {"min_level ": {
                 "desc": "the minimum level classification of log entries to return,"
                         " with each level inheriting log entries from the level above"}},
             "SickGearCommand": "sg.logs",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearLogs.__init__(self, handler, args, kwargs)


class CMD_SickGearPostProcess(ApiCall):
    _help = {"desc": "process completed media files to a show location",
             "optionalParameters": {"path": {"desc": "Path to process"},
                                    "force_replace": {"desc": "Force already processed dir/files"},
                                    "return_data": {"desc": "Return results for the process"},
                                    "process_method": {"desc": "Symlink, hardlink, move, or copy file(s)"},
                                    "is_priority": {"desc": "Replace file(s) even if existing at a higher quality"},
                                    "type": {"desc": "Type of media process request this is, auto or manual"},
                                    "failed": {"desc": "Mark as failed download"},
                                    "client": {"desc": "String representing the calling client"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.path, args = self.check_params(args, kwargs, "path", None, False, "string", [])
        self.force_replace, args = self.check_params(args, kwargs, "force_replace", 0, False, "bool", [])
        self.return_data, args = self.check_params(args, kwargs, "return_data", 0, False, "bool", [])
        self.process_method, args = self.check_params(args, kwargs, "process_method", False, False, "string", [
            "copy", "symlink", "hardlink", "move"])
        self.is_priority, args = self.check_params(args, kwargs, "is_priority", 0, False, "bool", [])
        self.type, args = self.check_params(args, kwargs, "type", "auto", False, "string", ["auto", "manual"])
        self.failed, args = self.check_params(args, kwargs, "failed", 0, False, "bool", [])
        self.client, args = self.check_params(args, kwargs, "client", None, False, "string", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ Starts the postprocess """
        if not self.path and not sickbeard.TV_DOWNLOAD_DIR:
            return _responds(RESULT_FAILURE, msg="You need to provide a path or set TV Download Dir")

        if not self.path:
            self.path = sickbeard.TV_DOWNLOAD_DIR

        if not self.type:
            self.type = 'manual'

        data = processTV.processDir(self.path, process_method=self.process_method, force=self.force_replace,
                                    force_replace=self.is_priority, failed=self.failed, pp_type=self.type,
                                    client=self.client)

        if not self.return_data:
            data = ""

        return _responds(RESULT_SUCCESS, data=data, msg="Started postprocess for %s" % self.path)


class CMD_PostProcess(CMD_SickGearPostProcess):
    _help = {"desc": "process completed media files to a show location",
             "optionalParameters": {"path": {"desc": "Path to process"},
                                    "force_replace": {"desc": "Force already processed dir/files"},
                                    "return_data": {"desc": "Return results for the process"},
                                    "process_method": {"desc": "Symlink, hardlink, move, or copy file(s)"},
                                    "is_priority": {"desc": "Replace file(s) even if existing at a higher quality"},
                                    "type": {"desc": "Type of media process request this is, auto or manual"}
                                    },
             "SickGearCommand": "sg.postprocess",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        kwargs['failed'] = "0"
        try:
            if 'client' in kwargs:
                del kwargs['client']
        except (BaseException, Exception):
            pass
        CMD_SickGearPostProcess.__init__(self, handler, args, kwargs)


class CMD_SickGear(ApiCall):
    _help = {"desc": "get API information"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get API information """
        data = {"sb_version": sickbeard.BRANCH, "api_version": Api.version, "fork": "SickGear",
                "api_commands": sorted([x for x in _functionMaper if 'listcommands' != x])}
        return _responds(RESULT_SUCCESS, data)


class CMD_SickBeard(CMD_SickGear):
    _help = {"desc": "get API information",
             "SickGearCommand": "sg", }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGear.__init__(self, handler, args, kwargs)


class CMD_SickGearAddRootDir(ApiCall):
    _help = {"desc": "add a user configured parent directory",
             "requiredParameters": {"location": {"desc": "the full path to root (parent) directory"}
                                    },
             "optionalParameters": {"default": {"desc": "make the location passed the default root (parent) directory"}
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.location, args = self.check_params(args, kwargs, "location", None, True, "string", [])
        # optional
        self.default, args = self.check_params(args, kwargs, "default", 0, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ add a user configured parent directory """

        self.location = unquote_plus(self.location)
        location_matched = 0
        index = 0

        # disallow adding/setting an invalid dir
        if not ek.ek(os.path.isdir, self.location):
            return _responds(RESULT_FAILURE, msg="Location is invalid")

        root_dirs = []

        if "" == sickbeard.ROOT_DIRS:
            self.default = 1
        else:
            root_dirs = sickbeard.ROOT_DIRS.split('|')
            index = int(sickbeard.ROOT_DIRS.split('|')[0])
            root_dirs.pop(0)
            # clean up the list - replace %xx escapes by their single-character equivalent
            root_dirs = [unquote_plus(x) for x in root_dirs]
            for x in root_dirs:
                if x == self.location:
                    location_matched = 1
                    if 1 == self.default:
                        index = root_dirs.index(self.location)
                    break

        if 0 == location_matched:
            if 1 == self.default:
                root_dirs.insert(0, self.location)
            else:
                root_dirs.append(self.location)

        root_dirs_new = [unquote_plus(x) for x in root_dirs]
        root_dirs_new.insert(0, index)
        root_dirs_new = '|'.join([text_type(x) for x in root_dirs_new])

        sickbeard.ROOT_DIRS = root_dirs_new
        return _responds(RESULT_SUCCESS, _getRootDirs(), msg="Root directories updated")


class CMD_SickBeardAddRootDir(CMD_SickGearAddRootDir):
    _help = {"desc": "add a user configured parent directory ",
             "requiredParameters": {"location": {"desc": "the full path to root (parent) directory"}
                                    },
             "optionalParameters": {"default": {"desc": "make the location passed the default root (parent) directory"}
                                    },
             "SickGearCommand": "sg.addrootdir",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearAddRootDir.__init__(self, handler, args, kwargs)


class CMD_SickGearCheckScheduler(ApiCall):
    _help = {"desc": "query the scheduler for event statuses, upcoming, running, and past"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ query the scheduler for event statuses, upcoming, running, and past """
        my_db = db.DBConnection()
        sql_result = my_db.select("SELECT last_backlog FROM info")

        backlogPaused = sickbeard.search_queue_scheduler.action.is_backlog_paused()
        backlogRunning = sickbeard.search_queue_scheduler.action.is_backlog_in_progress()
        nextBacklog = sickbeard.backlog_search_scheduler.next_run().strftime(dateFormat)

        data = {"backlog_is_paused": int(backlogPaused), "backlog_is_running": int(backlogRunning),
                "last_backlog": (0 < len(sql_result) and _ordinal_to_dateForm(sql_result[0]["last_backlog"])) or '',
                "next_backlog": nextBacklog}
        return _responds(RESULT_SUCCESS, data)


class CMD_SickBeardCheckScheduler(CMD_SickGearCheckScheduler):
    _help = {"desc": "query the scheduler for event statuses, upcoming, running, and past",
             "SickGearCommand": "sg.checkscheduler"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearCheckScheduler.__init__(self, handler, args, kwargs)


class CMD_SickGearDeleteRootDir(ApiCall):
    _help = {"desc": "delete a user configured parent directory",
             "requiredParameters": {"location": {"desc": "the full path to root (parent) directory"}}
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.location, args = self.check_params(args, kwargs, "location", None, True, "string", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ delete a user configured parent directory """
        if sickbeard.ROOT_DIRS == "":
            return _responds(RESULT_FAILURE, _getRootDirs(), msg="No root directories detected")

        newIndex = 0
        root_dirs_new = []
        root_dirs = sickbeard.ROOT_DIRS.split('|')
        index = int(root_dirs[0])
        root_dirs.pop(0)
        # clean up the list - replace %xx escapes by their single-character equivalent
        root_dirs = [unquote_plus(x) for x in root_dirs]
        old_root_dir = root_dirs[index]
        for curRootDir in root_dirs:
            if not curRootDir == self.location:
                root_dirs_new.append(curRootDir)
            else:
                newIndex = 0

        for curIndex, curNewRootDir in enumerate(root_dirs_new):
            if curNewRootDir is old_root_dir:
                newIndex = curIndex
                break

        root_dirs_new = [unquote_plus(x) for x in root_dirs_new]
        if 0 < len(root_dirs_new):
            root_dirs_new.insert(0, newIndex)
        root_dirs_new = "|".join([text_type(x) for x in root_dirs_new])

        sickbeard.ROOT_DIRS = root_dirs_new
        # what if the root dir was not found?
        return _responds(RESULT_SUCCESS, _getRootDirs(), msg="Root directory deleted")


class CMD_SickBeardDeleteRootDir(CMD_SickGearDeleteRootDir):
    _help = {"desc": "delete a user configured parent directory",
             "requiredParameters": {"location": {"desc": "the full path to root (parent) directory"}},
             "SickGearCommand": "sg.deleterootdir"
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearDeleteRootDir.__init__(self, handler, args, kwargs)


class CMD_SickGearForceSearch(ApiCall):
    _help = {'desc': 'force the specified search type to run',
             "requiredParameters": {"searchtype": {"desc": "type of search to be forced: recent, backlog, proper"}}
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.searchtype, args = self.check_params(args, kwargs, "searchtype", "recent", True, "string",
                                                  ["recent", "backlog", "proper"])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ force the specified search type to run """
        result = None
        if 'recent' == self.searchtype and not sickbeard.search_queue_scheduler.action.is_recentsearch_in_progress() \
                and not sickbeard.recent_search_scheduler.action.amActive:
            result = sickbeard.recent_search_scheduler.forceRun()
        elif 'backlog' == self.searchtype and not sickbeard.search_queue_scheduler.action.is_backlog_in_progress() \
                and not sickbeard.backlog_search_scheduler.action.amActive:
            sickbeard.backlog_search_scheduler.force_search(force_type=FORCED_BACKLOG)
            result = True
        elif 'proper' == self.searchtype and not sickbeard.search_queue_scheduler.action.is_propersearch_in_progress() \
                and not sickbeard.proper_finder_scheduler.action.amActive:
            result = sickbeard.proper_finder_scheduler.forceRun()
        if result:
            return _responds(RESULT_SUCCESS, msg='%s search successfully forced' % self.searchtype)
        return _responds(RESULT_FAILURE,
                         msg='Can not force the %s search because it\'s already active' % self.searchtype)


class CMD_SickBeardForceSearch(CMD_SickGearForceSearch):
    _help = {'desc': 'force the episode recent search',
             "SickGearCommand": "sg.forcesearch", }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['searchtype'] = 'recent'
        self.sickbeard_call = True
        CMD_SickGearForceSearch.__init__(self, handler, args, kwargs)


class CMD_SickGearSearchQueue(ApiCall):
    _help = {'desc': 'get a list of the sickgear search queue states'}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get a list of the sickgear search queue states """
        return _responds(RESULT_SUCCESS, sickbeard.search_queue_scheduler.action.queue_length())


class CMD_SickGearGetDefaults(ApiCall):
    _help = {"desc": "get various sickgear default system values"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get various sickgear default system values """

        anyQualities, bestQualities = _mapQuality(sickbeard.QUALITY_DEFAULT)

        data = {"status": statusStrings[sickbeard.STATUS_DEFAULT].lower(),
                "flatten_folders": int(sickbeard.FLATTEN_FOLDERS_DEFAULT), "initial": anyQualities,
                "archive": bestQualities, "future_show_paused": int(sickbeard.EPISODE_VIEW_DISPLAY_PAUSED)}
        return _responds(RESULT_SUCCESS, data)


class CMD_SickBeardGetDefaults(CMD_SickGearGetDefaults):
    _help = {"desc": "get various sickgear default system values",
             "SickGearCommand": "sg.getdefaults"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearGetDefaults.__init__(self, handler, args, kwargs)


class CMD_SickGearGetMessages(ApiCall):
    _help = {"desc": "get list of ui notifications"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        messages = []
        for cur_notification in ui.notifications.get_notifications(self.handler.request.remote_ip):
            messages.append({"title": cur_notification.title,
                             "message": cur_notification.message,
                             "type": cur_notification.type})
        return _responds(RESULT_SUCCESS, messages)


class CMD_SickBeardGetMessages(CMD_SickGearGetMessages):
    _help = {"desc": "get list of ui notifications",
             "SickGearCommand": "sg.getmessages"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearGetMessages.__init__(self, handler, args, kwargs)


class CMD_SickGearGetQualities(ApiCall):
    _help = {"desc": "get globally available qualities"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        return _responds(RESULT_SUCCESS, quality_map)


class CMD_SickGearGetIndexers(ApiCall):
    _help = {"desc": "get tv info source list",
             "optionalParameters": {"searchable-only": {"desc": "only return searchable sources"}}}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.searchable_only, args = self.check_params(args, kwargs, "searchable-only", False, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        result = {}
        for i in indexer_config.tvinfo_config:
            for d, v in iteritems(indexer_config.tvinfo_config[i]):
                if self.searchable_only and (indexer_config.tvinfo_config[i].get('mapped_only') or
                                             not indexer_config.tvinfo_config[i].get('active') or
                                             indexer_config.tvinfo_config[i].get('defunct')):
                    continue
                if d in ['id', 'name', 'show_url', 'mapped_only', 'main_url'] and \
                        isinstance(v, (string_types, tuple, dict, list, integer_types, float, bool)):
                    if 'mapped_only' == d:
                        key = 'searchable'
                        val = not v and indexer_config.tvinfo_config[i].get('active') \
                            and not indexer_config.tvinfo_config[i].get('defunct')
                    else:
                        key = d
                        if 'show_url' == d:
                            val = re.sub(r'%\d{,2}d', '{INDEXER-ID}', v, flags=re.I)
                        else:
                            val = v
                    result.setdefault(i, {}).update({key: val})
        return _responds(RESULT_SUCCESS, result)


class CMD_SickGearGetIndexerIcon(ApiCall):
    _help = {"desc": "get tv info source icon",
             "requiredParameters": {"indexer": {"desc": "indexer"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().all_sources])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        # doesn't work
        i = indexer_config.tvinfo_config.get(self.tvid)
        if not i:
            self.handler.set_status(404)
            return _responds(RESULT_FAILURE, 'Icon not found')
        img = i['icon']
        image = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick', 'images', img)
        if not ek.ek(os.path.isfile, image):
            self.handler.set_status(404)
            return _responds(RESULT_FAILURE, 'Icon not found')
        return {'outputType': 'image', 'image': self.handler.get_image(image)}


class CMD_SickGearGetNetworkIcon(ApiCall):
    _help = {"desc": "get network icon",
             "requiredParameters": {"network": {"desc": "name of network"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.network, args = self.check_params(args, kwargs, "network", None, True, "string", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        image = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick', 'images', 'network',
                      '%s.png' % self.network.lower())
        if not ek.ek(os.path.isfile, image):
            self.handler.set_status(404)
            return _responds(RESULT_FAILURE, 'Icon not found')
        return {'outputType': 'image', 'image': self.handler.get_image(image)}


class CMD_SickGearGetqualityStrings(ApiCall):
    _help = {"desc": "get human readable quality strings"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        return _responds(RESULT_SUCCESS, Quality.qualityStrings)


class CMD_SickGearGetRootDirs(ApiCall):
    _help = {"desc": "get list of user configured parent directories"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get list of user configured parent directories """

        return _responds(RESULT_SUCCESS, _getRootDirs())


class CMD_SickBeardGetRootDirs(CMD_SickGearGetRootDirs):
    _help = {"desc": "get list of user configured parent directories",
             "SickGearCommand": "sg.getrootdirs"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearGetRootDirs.__init__(self, handler, args, kwargs)


class CMD_SickGearPauseBacklog(ApiCall):
    _help = {"desc": "pause the backlog search",
             "optionalParameters": {"pause": {"desc": "pause or unpause the global backlog"}}
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.pause, args = self.check_params(args, kwargs, "pause", 0, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ pause the backlog search """
        if self.pause:
            sickbeard.search_queue_scheduler.action.pause_backlog()
            return _responds(RESULT_SUCCESS, msg="Backlog paused")
        else:
            sickbeard.search_queue_scheduler.action.unpause_backlog()
            return _responds(RESULT_SUCCESS, msg="Backlog unpaused")


class CMD_SickBeardPauseBacklog(CMD_SickGearPauseBacklog):
    _help = {"desc": "pause the backlog search",
             "optionalParameters": {"pause": {"desc": "pause or unpause the global backlog"}},
             "SickGearCommand": "sg.pausebacklog"
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearPauseBacklog.__init__(self, handler, args, kwargs)


class CMD_SickGearPing(ApiCall):
    _help = {"desc": "check to see if sickgear is running", }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ check to see if sickgear is running """
        self.handler.set_header('Cache-Control', "max-age=0,no-cache,no-store")
        if sickbeard.started:
            return _responds(RESULT_SUCCESS, {"pid": sickbeard.PID}, "Pong")
        else:
            return _responds(RESULT_SUCCESS, msg="Pong")


class CMD_SickBeardPing(CMD_SickGearPing):
    _help = {"desc": "check to see if sickgear is running",
             "SickGearCommand": "sg.ping"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearPing.__init__(self, handler, args, kwargs)


class CMD_SickGearRestart(ApiCall):
    _help = {"desc": "restart sickgear"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ restart sickgear """
        sickbeard.restart(soft=False)
        return _responds(RESULT_SUCCESS, msg="SickGear is restarting...")


class CMD_SickBeardRestart(CMD_SickGearRestart):
    _help = {"desc": "restart sickgear",
             "SickGearCommand": "sg.restart"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearRestart.__init__(self, handler, args, kwargs)


class CMD_SickGearSearchIndexers(ApiCall):
    _help = {"desc": "search for show on a tv info source with a given string and language",
             "optionalParameters": {"name": {"desc": "name of the show you want to search for"},
                                    "indexerid": {"desc": "thetvdb.com or tvrage.com unique id of a show"},
                                    "lang": {"desc": "the 2 letter abbreviation lang id"},
                                    "indexer": {"desc": "indexer to search, use -1 to search all indexers"}
                                    }
             }

    valid_languages = {
        'el': 20, 'en': 7, 'zh': 27, 'it': 15, 'cs': 28, 'es': 16, 'ru': 22,
        'nl': 13, 'pt': 26, 'no': 9, 'tr': 21, 'pl': 18, 'fr': 17, 'hr': 31,
        'de': 14, 'da': 10, 'fi': 11, 'hu': 19, 'ja': 25, 'he': 24, 'ko': 32,
        'sv': 8, 'sl': 30}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.name, args = self.check_params(args, kwargs, "name", None, False, "string", [])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        # self.lang, args = self.check_params(args, kwargs, "lang", "en", False, "string", self.valid_languages.keys())
        self.indexers, args = self.check_params(args, kwargs, "indexers", -1, False, "list",
                                                [-1] + [i for i in indexer_api.TVInfoAPI().search_sources], int)

        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ search for show on a tv info source with a given string and language """
        if 1 > len(self.indexers) and -1 in self.indexers:
            raise ApiError('Mix of -1 (all Indexer) and specific Indexer not allowed')

        all_indexer = 1 == len(self.indexers) and -1 == self.indexers[0]
        lang_id = self.valid_languages['en']

        if self.name and not self.prodid:  # only name was given
            results = []
            indexertosearch = (self.indexers, [i for i in indexer_api.TVInfoAPI().sources if
                                               indexer_api.TVInfoAPI(i).config.get('active') and
                                               not indexer_api.TVInfoAPI(i).config.get('mapped_only') and
                                               not indexer_api.TVInfoAPI(i).config.get('defunct')])[all_indexer]
            for i in indexertosearch:
                tvinfo_config = sickbeard.TVInfoAPI(i).api_params.copy()
                tvinfo_config['language'] = 'en'
                tvinfo_config['custom_ui'] = classes.AllShowInfosNoFilterListUI
                t = sickbeard.TVInfoAPI(i).setup(**tvinfo_config)

                try:
                    apiData = t[decode_str(self.name), False]
                except (BaseException, Exception) as e:
                    continue

                for curSeries in (apiData or []):
                    s = {"indexerid": int(curSeries['id']),
                         "name": curSeries['seriesname'],
                         "first_aired": curSeries['firstaired'],
                         "indexer": i,
                         "aliases": curSeries.get('aliases', None),
                         "relevance": AddShows.get_uw_ratio(self.name, curSeries['seriesname'],
                                                            curSeries.get('aliases', None))}
                    if TVINFO_TVDB == i:
                        s["tvdbid"] = int(curSeries['id'])
                    else:
                        s["tvdbid"] = None
                    results.append(s)

            if not results:
                return _responds(RESULT_FAILURE, msg="Did not get result from %s" %
                                                     ', '.join([sickbeard.TVInfoAPI(i).name for i in indexertosearch]))

            results = sorted(results, key=lambda x: x['relevance'], reverse=True)

            return _responds(RESULT_SUCCESS, {"results": results, "langid": lang_id, "lang": 'en'})

        elif self.prodid and not all_indexer and 1 == len(self.indexers):
            tvinfo_config = sickbeard.TVInfoAPI(self.indexers[0]).api_params.copy()

            tvinfo_config['language'] = 'en'
            tvinfo_config['custom_ui'] = classes.AllShowInfosNoFilterListUI

            tvinfo_config['actors'] = False

            t = sickbeard.TVInfoAPI(self.indexers[0]).setup(**tvinfo_config)

            try:
                show_info = t[int(self.prodid), False]
            except BaseTVinfoError as e:
                self.log(u"Unable to find show with id " + str(self.prodid), logger.WARNING)
                return _responds(RESULT_SUCCESS, {"results": [], "langid": lang_id, "lang": 'en'})

            if not show_info.data['seriesname']:
                self.log(
                    u"Found show with indexerid " + str(self.prodid) + ", however it contained no show name",
                    logger.DEBUG)
                return _responds(RESULT_FAILURE, msg="Show contains no name, invalid result")

            showOut = [{"indexerid": self.prodid,
                        "indexer": self.indexers[0],
                        "name": text_type(show_info.data['seriesname']),
                        "first_aired": show_info.data['firstaired'],
                        "aliases": show_info.data.get('aliases', None),
                        "relevance": AddShows.get_uw_ratio(self.name, show_info.data['seriesname'],
                                                           show_info.data.get('aliases', None))}]

            if TVINFO_TVDB == self.indexers[0]:
                showOut[0]["tvdbid"] = int(show_info.data['id'])
            else:
                showOut[0]["tvdbid"] = None

            showOut = sorted(showOut, key=lambda x: x['relevance'], reverse=True)
            return _responds(RESULT_SUCCESS, {"results": showOut, "langid": lang_id, "lang": 'en'})
        else:
            return _responds(RESULT_FAILURE, msg="Either indexer + indexerid or name is required")


class CMD_SickBeardSearchIndexers(CMD_SickGearSearchIndexers):
    _help = {"desc": "search for show on the tvdb with a given string and language",
             "optionalParameters": {"name": {"desc": "name of the show you want to search for"},
                                    "indexerid": {"desc": "thetvdb.com unique id of a show"},
                                    "lang": {"desc": "the 2 letter abbreviation lang id"},
                                    },
             "SickGearCommand": "sg.searchtv",
             }

    def __init__(self, handler, args, kwargs):
        kwargs['indexers'] = TVINFO_TVDB
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearSearchIndexers.__init__(self, handler, args, kwargs)


class CMD_SickGearSetDefaults(ApiCall):
    _help = {"desc": "set various sickgear default system values",
             "optionalParameters": {"initial": {"desc": "initial quality to use when adding shows"},
                                    "archive": {"desc": "archive quality to use when adding shows"},
                                    "flatten_folders": {"desc": "flatten show subfolders when adding shows"},
                                    "status": {"desc": "status to change episodes to with missing media"},
                                    "future_show_paused": {"desc": "show/hide paused shows on the daily schedule page"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.initial, args = self.check_params(args, kwargs, "initial", None, False, "list", [q for q in quality_map])
        self.archive, args = self.check_params(args, kwargs, "archive", None, False, "list", [q for q in quality_map])
        self.future_show_paused, args = self.check_params(args, kwargs, "future_show_paused", None, False, "bool", [])
        self.flatten_folders, args = self.check_params(args, kwargs, "flatten_folders", None, False, "bool", [])
        self.status, args = self.check_params(args, kwargs, "status", None, False, "string",
                                              ["wanted", "skipped", "archived", "ignored"])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ set various sickgear default system values """

        iqualityID = []
        aqualityID = []

        if self.initial:
            for quality in self.initial:
                iqualityID.append(quality_map[quality])
        if self.archive:
            for quality in self.archive:
                aqualityID.append(quality_map[quality])

        if iqualityID or aqualityID:
            sickbeard.QUALITY_DEFAULT = Quality.combineQualities(iqualityID, aqualityID)

        if self.status:
            # convert the string status to a int
            for status in statusStrings.statusStrings:
                if statusStrings[status].lower() == str(self.status).lower():
                    self.status = status
                    break
            # this should be obsolete because of the above
            if self.status not in statusStrings.statusStrings:
                raise ApiError("Invalid Status")
            # only allow the status options we want
            if int(self.status) not in (3, 5, 6, 7):
                raise ApiError("Status Prohibited")
            sickbeard.STATUS_DEFAULT = self.status

        if None is not self.flatten_folders:
            sickbeard.FLATTEN_FOLDERS_DEFAULT = int(self.flatten_folders)

        if None is not self.future_show_paused:
            sickbeard.EPISODE_VIEW_DISPLAY_PAUSED = int(self.future_show_paused)

        sickbeard.save_config()

        return _responds(RESULT_SUCCESS, msg="Saved defaults")


class CMD_SickBeardSetDefaults(CMD_SickGearSetDefaults):
    _help = {"desc": "set various sickgear default system values",
             "optionalParameters": {"initial": {"desc": "initial quality to use when adding shows"},
                                    "archive": {"desc": "archive quality to use when adding shows"},
                                    "flatten_folders": {"desc": "flatten show subfolders when adding shows"},
                                    "status": {"desc": "status to change episodes to with missing media"}
             },
             "SickGearCommand": "sg.setdefaults",
    }

    def __init__(self, handler, args, kwargs):
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearSetDefaults.__init__(self, handler, args, kwargs)


class CMD_SickGearSetSceneNumber(ApiCall):
    _help = {"desc": "set scene numbers for a show",
             "requiredParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    },
             "optionalParameters": {"forSeason": {"desc": "season number of a show"},
                                    "forEpisode": {"desc": "episode number of a show"},
                                    "forAbsolute": {"desc": "absolute episode number of a show"},
                                    "sceneSeason": {"desc": "scene season number of a show to set"},
                                    "sceneEpisode": {"desc": "scene episode number of a show to set"},
                                    "sceneAbsolute": {"desc": "scene absolute episode number of a show to set"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.tvid, args = self.check_params(
            args, kwargs, "indexer", None, True, "int", [i for i in indexer_api.TVInfoAPI().sources])
        # optional
        self.forSeason, args = self.check_params(args, kwargs, "forSeason", None, False, "int", [])
        self.forEpisode, args = self.check_params(args, kwargs, "forEpisode", None, False, "int", [])
        self.forAbsolute, args = self.check_params(args, kwargs, "forAbsolute", None, False, "int", [])
        self.sceneSeason, args = self.check_params(args, kwargs, "sceneSeason", None, False, "int", [])
        self.sceneEpisode, args = self.check_params(args, kwargs, "sceneEpisode", None, False, "int", [])
        self.sceneAbsolute, args = self.check_params(args, kwargs, "sceneAbsolute", None, False, "int", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ saving scene numbers """

        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Can't find show")
        if not show_obj.is_scene:
            return _responds(RESULT_FAILURE, msg="Show scene numbering disabled")

        result = set_scene_numbering_helper(self.tvid, self.prodid, self.forSeason, self.forEpisode,
                                            self.forAbsolute, self.sceneSeason, self.sceneEpisode, self.sceneAbsolute)

        if not result['success']:
            return _responds(RESULT_FAILURE, result)

        return _responds(RESULT_SUCCESS, result)


class CMD_SickGearActivateSceneNumber(ApiCall):
    _help = {"desc": "de-/activate scene numbers",
             "requiredParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    "activate": {"desc": "de-/activate scene numbering"}},
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.activate, args = self.check_params(args, kwargs, "activate", None, True, "bool", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ de-/activate scene numbers """

        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Can't find show")

        show_obj.scene = int(self.activate)
        show_obj.save_to_db()

        return _responds(RESULT_SUCCESS, data={'indexer': self.tvid, 'indexerid': self.prodid,
                                               'show_name': show_obj.name, 'scenenumbering': show_obj.is_scene},
                         msg="Scene Numbering %sactivated" % ('de', '')[self.activate])


class CMD_SickGearShutdown(ApiCall):
    _help = {"desc": "shutdown sickgear"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ shutdown sickgear """
        sickbeard.events.put(sickbeard.events.SystemEvent.SHUTDOWN)
        return _responds(RESULT_SUCCESS, msg="SickGear is shutting down...")


class CMD_SickBeardShutdown(CMD_SickGearShutdown):
    _help = {"desc": "shutdown sickgear",
             "SickGearCommand": "sg.shutdown",
             }

    def __init__(self, handler, args, kwargs):
        self.sickbeard_call = True
        CMD_SickGearShutdown.__init__(self, handler, args, kwargs)


class CMD_SickGearListIgnoreWords(ApiCall):
    _help = {"desc": "get ignore word list (uses global list if both indexerid and indexer params are not set)",
             "optionalParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, False, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get ignore word list """
        if self.tvid and self.prodid:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                'SELECT show_name, rls_ignore_words, rls_global_exclude_ignore'
                ' FROM tv_shows'
                ' WHERE indexer = ? AND indexer_id = ?',
                [self.tvid, self.prodid])
            if sql_result:
                ignore_words = sql_result[0]['rls_ignore_words']
                return_data = {'type': 'show', 'indexer': self.tvid, 'indexerid': self.prodid,
                               'show name': sql_result[0]['show_name'],
                               'global exclude ignore':
                                   helpers.split_word_str(sql_result[0]['rls_global_exclude_ignore'])[0]}
                return_type = '%s:' % sql_result[0]['show_name']
            else:
                return _responds(RESULT_FAILURE, msg='Show not found.')
        elif (None is self.tvid) != (None is self.prodid):
            return _responds(RESULT_FAILURE, msg='You must supply indexer + indexerid.')
        else:
            ignore_words = helpers.generate_word_str(sickbeard.IGNORE_WORDS, sickbeard.IGNORE_WORDS_REGEX)
            return_data = {'type': 'global'}
            return_type = 'Global'

        return_data['use regex'] = ignore_words.startswith('regex:')
        return_data['ignore words'] = [w.strip() for w in ignore_words.replace('regex:', '').split(',') if w.strip()]
        return _responds(RESULT_SUCCESS, data=return_data, msg="%s ignore word list" % return_type)


class ApiSetWords(ApiCall):

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, False, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.add, args = self.check_params(args, kwargs, "add", None, False, "list", [])
        self.remove, args = self.check_params(args, kwargs, "remove", None, False, "list", [])
        self.add_exclude, args = self.check_params(args, kwargs, "add_exclude", None, False, "list", [])
        self.remove_exclude, args = self.check_params(args, kwargs, "remove_exclude", None, False, "list", [])
        self.regex, args = self.check_params(args, kwargs, "regex", None, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def _create_words(self, words, exclude_list=None):
        exclude_list = exclude_list or []
        word_list = {w.strip() for w in words.replace('regex:', '').split(',') if w.strip()}

        use_regex = self.regex if None is not self.regex else words.startswith('regex:')

        for a in self.add or []:
            if a not in exclude_list:
                word_list.add(a.strip())
        for r in self.remove or []:
            try:
                word_list.remove(r)
            except KeyError:
                pass

        return use_regex, word_list, \
            ('', '%s%s' % (('', 'regex:')[use_regex],
                           ', '.join([w.strip() for w in word_list if w.strip()])))[0 < len(word_list)]


class CMD_SickGearSetIgnoreWords(ApiSetWords):
    _help = {"desc": "set ignore word list (uses global list if both indexerid and indexer params are not set)",
             "optionalParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    "add": {"desc": "add words to list"},
                                    "remove": {"desc": "remove words from list"},
                                    "add_exclude": {"desc": "add global exclude words"},
                                    "remove_exclude": {"desc": "remove global exclude words"},
                                    "regex": {"desc": "interpret ALL (including existing) ignore words as regex"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        super(CMD_SickGearSetIgnoreWords, self).__init__(handler, args, kwargs)

    def run(self):
        """ set ignore word list """
        if (not self.add and not self.remove and not self.add_exclude and not self.remove_exclude) or \
                ((self.add_exclude or self.remove_exclude) and not (self.tvid and self.prodid)):
            return _responds(RESULT_FAILURE, msg=('No indexer, indexerid provided',
                                                  'No words to add/remove provided')[None is not self.tvid and
                                                                                     None is not self.prodid])

        use_regex = None
        return_type = ''
        ignore_list = set()

        if self.tvid and self.prodid:
            show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
            if not show_obj:
                return _responds(RESULT_FAILURE, msg="Show not found")

            return_data = {'type': 'show', 'indexer': self.tvid, 'indexerid': self.prodid,
                           'show name': show_obj.name}

            if any([self.add, self.remove, self.add_exclude, self.remove_exclude]):
                my_db = db.DBConnection()
                sql_results = my_db.select(
                    'SELECT show_name, rls_ignore_words, rls_global_exclude_ignore'
                    ' FROM tv_shows'
                    ' WHERE indexer = ? AND indexer_id = ?', [self.tvid, self.prodid])
                if sql_results:
                    ignore_words = sql_results[0]['rls_ignore_words']
                    ignore_list, use_regex = helpers.split_word_str(ignore_words)
                    exclude_ignore = helpers.split_word_str(sql_results[0]['rls_global_exclude_ignore'])[0]
                    exclude_ignore = {i for i in exclude_ignore if i in sickbeard.IGNORE_WORDS}
                    return_type = '%s:' % sql_results[0]['show_name']

                    if self.add or self.remove:
                        use_regex, ignore_list, new_ignore_words = \
                            self._create_words(ignore_words, sickbeard.IGNORE_WORDS)
                        my_db.action('UPDATE tv_shows'
                                     ' SET rls_ignore_words = ?'
                                     ' WHERE indexer = ? AND indexer_id = ?',
                                     [new_ignore_words, self.tvid, self.prodid])
                        show_obj.rls_ignore_words, show_obj.rls_ignore_words_regex = \
                            helpers.split_word_str(new_ignore_words)

                    if self.add_exclude or self.remove_exclude:
                        for a in self.add_exclude or []:
                            if a in sickbeard.IGNORE_WORDS:
                                exclude_ignore.add(a)
                        for r in self.remove_exclude or []:
                            try:
                                exclude_ignore.remove(r)
                            except KeyError:
                                pass

                        my_db.action('UPDATE tv_shows SET rls_global_exclude_ignore = ?'
                                     ' WHERE indexer = ? AND indexer_id = ?',
                                     [helpers.generate_word_str(exclude_ignore), self.tvid, self.prodid])
                        show_obj.rls_global_exclude_ignore = copy.copy(exclude_ignore)

                    return_data['global exclude ignore'] = exclude_ignore
        elif (None is self.tvid) != (None is self.prodid):
            return _responds(RESULT_FAILURE, msg='You must supply indexer + indexerid.')
        else:
            ignore_words = helpers.generate_word_str(sickbeard.IGNORE_WORDS, sickbeard.IGNORE_WORDS_REGEX)
            use_regex, ignore_list, new_ignore_words = self._create_words(ignore_words)
            sickbeard.IGNORE_WORDS, sickbeard.IGNORE_WORDS_REGEX = helpers.split_word_str(new_ignore_words)
            sickbeard.save_config()
            return_data = {'type': 'global'}
            return_type = 'Global'

        if None is not use_regex:
            return_data['use regex'] = use_regex
        elif None is not self.regex:
            return_data['use regex'] = self.regex
        return_data['ignore words'] = ignore_list
        clean_ignore_require_words()
        return _responds(RESULT_SUCCESS, data=return_data, msg="%s set ignore word list" % return_type)


class CMD_SickGearListRequireWords(ApiCall):
    _help = {"desc": "get require word list (uses global list if both indexerid and indexer params are not set)",
             "optionalParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, False, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)
        self.old_call = False

    def run(self):
        """ get require word list """
        if self.tvid and self.prodid:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                'SELECT show_name, rls_require_words, rls_global_exclude_require'
                ' FROM tv_shows'
                ' WHERE indexer = ? AND indexer_id = ?',
                [self.tvid, self.prodid])
            if sql_result:
                require_words = sql_result[0]['rls_require_words']
                return_data = {'type': 'show', 'indexer': self.tvid, 'indexerid': self.prodid,
                               'show name': sql_result[0]['show_name'],
                               'global exclude require':
                                   helpers.split_word_str(sql_result[0]['rls_global_exclude_require'])[0]}
                return_type = '%s:' % sql_result[0]['show_name']
            else:
                return _responds(RESULT_FAILURE, msg='Show not found.')
        elif (None is self.tvid) != (None is self.prodid):
            return _responds(RESULT_FAILURE, msg='You must supply indexer + indexerid.')
        else:
            require_words = helpers.generate_word_str(sickbeard.REQUIRE_WORDS, sickbeard.REQUIRE_WORDS_REGEX)
            return_data = {'type': 'global'}
            return_type = 'Global'

        return_data['use regex'] = require_words.startswith('regex:')
        return_data['require%s words' % ('', 'd')[self.old_call]] = [w.strip() for w in
                                                                     require_words.replace('regex:', '').split(',')
                                                                     if w.strip()]
        return _responds(RESULT_SUCCESS, data=return_data, msg="%s require word list" % return_type)


class CMD_SickGearListRequireWords_old(CMD_SickGearListRequireWords):
    def __init__(self, handler, args, kwargs):
        CMD_SickGearListRequireWords.__init__(self, handler, args, kwargs)
        self.old_call = True


class CMD_SickGearSetRequireWords(ApiSetWords):
    _help = {"desc": "set require word list (uses global list if both indexerid and indexer params are not set)",
             "optionalParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    "add": {"desc": "add words to list"},
                                    "remove": {"desc": "remove words from list"},
                                    "add_exclude": {"desc": "add global exclude words"},
                                    "remove_exclude": {"desc": "remove global exclude words"},
                                    "regex": {"desc": "interpret ALL (including existing) ignore words as regex"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        super(CMD_SickGearSetRequireWords, self).__init__(handler, args, kwargs)
        self.old_call = False

    def run(self):
        """ set require words """
        if (not self.add and not self.remove and not self.add_exclude and not self.remove_exclude) or \
                ((self.add_exclude or self.remove_exclude) and not (self.tvid and self.prodid)):
            return _responds(RESULT_FAILURE, msg=('No indexer, indexerid provided',
                                                  'No words to add/remove provided')[None is not self.tvid and
                                                                                     None is not self.prodid])

        use_regex = None
        return_type = ''
        require_list = set()

        if self.tvid and self.prodid:
            show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
            if not show_obj:
                return _responds(RESULT_FAILURE, msg="Show not found")

            return_data = {'type': 'show', 'indexer': self.tvid, 'indexerid': self.prodid,
                           'show name': show_obj.name}

            if any([self.add, self.remove, self.add_exclude, self.remove_exclude]):
                my_db = db.DBConnection()
                sql_result = my_db.select(
                    'SELECT show_name, rls_require_words, rls_global_exclude_require'
                    ' FROM tv_shows'
                    ' WHERE indexer = ? AND indexer_id = ?', [self.tvid, self.prodid])
                if sql_result:
                    require_words = sql_result[0]['rls_require_words']
                    require_list, use_regex = helpers.split_word_str(require_words)
                    exclude_require = helpers.split_word_str(sql_result[0]['rls_global_exclude_require'])[0]
                    exclude_require = {r for r in exclude_require if r in sickbeard.REQUIRE_WORDS}
                    return_type = '%s:' % sql_result[0]['show_name']

                    if self.add or self.remove:
                        use_regex, require_list, new_require_words = \
                            self._create_words(require_words, sickbeard.REQUIRE_WORDS)
                        my_db.action('UPDATE tv_shows'
                                     ' SET rls_require_words = ?'
                                     ' WHERE indexer = ? AND indexer_id = ?',
                                     [new_require_words, self.tvid, self.prodid])
                        show_obj.rls_require_words, show_obj.rls_require_words_regex = \
                            helpers.split_word_str(new_require_words)

                    if self.add_exclude or self.remove_exclude:
                        for a in self.add_exclude or []:
                            if a in sickbeard.REQUIRE_WORDS:
                                exclude_require.add(a)
                        for r in self.remove_exclude or []:
                            try:
                                exclude_require.remove(r)
                            except KeyError:
                                pass
                        my_db.action(
                            'UPDATE tv_shows SET rls_global_exclude_require = ?'
                            ' WHERE indexer = ? AND indexer_id = ?',
                            [helpers.generate_word_str(exclude_require), self.tvid, self.prodid])
                        show_obj.rls_global_exclude_require = copy.copy(exclude_require)

                    return_data['global exclude require'] = exclude_require
        elif (None is self.tvid) != (None is self.prodid):
            return _responds(RESULT_FAILURE, msg='You must supply indexer + indexerid.')
        else:
            require_words = helpers.generate_word_str(sickbeard.REQUIRE_WORDS, sickbeard.REQUIRE_WORDS_REGEX)
            use_regex, require_list, new_require_words = self._create_words(require_words)

            sickbeard.REQUIRE_WORDS, sickbeard.REQUIRE_WORDS_REGEX = helpers.split_word_str(new_require_words)
            sickbeard.save_config()
            return_data = {'type': 'global'}
            return_type = 'Global'

        if None is not use_regex:
            return_data['use regex'] = use_regex
        elif None is not self.regex:
            return_data['use regex'] = self.regex
        return_data['require%s words' % ('', 'd')[self.old_call]] = require_list
        clean_ignore_require_words()
        return _responds(RESULT_SUCCESS, data=return_data,
                         msg="%s set %s" % (return_type, ('require word list', 'requried words')[self.old_call]))


class CMD_SickGearSetRequireWords_old(CMD_SickGearSetRequireWords):
    def __init__(self, handler, args, kwargs):
        CMD_SickGearSetRequireWords.__init__(self, handler, args, kwargs)
        self.old_call = True


class CMD_SickGearUpdateWatchedState(ApiCall):
    _help = {"desc": "Update db with details of media file(s) that are watched or unwatched",
             "requiredParameters": {
                 "payloadjson": {
                     "desc": "a dict of dicts transmitted as JSON via POST request"},
             }}

    def __init__(self, handler, args, kwargs):
        # required
        self.payloadjson, args = self.check_params(args, kwargs, "payloadjson", None, True, "dict", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ Update db with details of media file that is watched or unwatched """
        payload = self.payloadjson.copy()

        webserve.MainHandler.update_watched_state(payload, as_json=False)

        if not payload:
            return _responds(RESULT_FAILURE, msg='Request made to SickGear with invalid payload')

        return _responds(RESULT_SUCCESS, payload)


class CMD_SickGearShow(ApiCall):
    _help = {"desc": "get show information",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"overview": {"desc": "include overview"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.overview, args = self.check_params(args, kwargs, "overview", False, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get show information """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        showDict = {"season_list": CMD_SickGearShowSeasonList(self.handler, (),
                                                              {'indexer': self.tvid, 'indexerid': self.prodid}
                                                              ).run()['data'],
                    "cache": CMD_SickGearShowCache(self.handler, (), {'indexer': self.tvid,
                                                                      'indexerid': self.prodid}).run()['data']}

        genreList = []
        if show_obj.genre:
            genreListTmp = show_obj.genre.split("|")
            for genre in genreListTmp:
                if genre:
                    genreList.append(genre)
        showDict["genre"] = genreList
        showDict["quality"] = _get_quality_string(show_obj.quality)

        anyQualities, bestQualities = _mapQuality(show_obj.quality)
        showDict["quality_details"] = {"initial": anyQualities, "archive": bestQualities}

        try:
            showDict["location"] = show_obj.location
        except exceptions_helper.ShowDirNotFoundException:
            showDict["location"] = ""

        showDict["language"] = show_obj.lang
        showDict["show_name"] = show_obj.name
        showDict["paused"] = show_obj.paused
        showDict["subtitles"] = show_obj.subtitles
        showDict["air_by_date"] = show_obj.air_by_date
        showDict["flatten_folders"] = show_obj.flatten_folders
        showDict["sports"] = show_obj.sports
        showDict["anime"] = show_obj.anime
        # clean up tvdb horrible airs field
        showDict["airs"] = str(show_obj.airs).replace('am', ' AM').replace('pm', ' PM').replace('  ', ' ')
        showDict["indexerid"] = self.prodid
        showDict["tvrage_id"] = show_obj.ids.get(TVINFO_TVRAGE, {'id': 0})['id']
        showDict['ids'] = {k: v.get('id') for k, v in iteritems(show_obj.ids)}
        showDict["tvrage_name"] = show_obj.name
        showDict["network"] = show_obj.network
        if not showDict["network"]:
            showDict["network"] = ""
        showDict["status"] = show_obj.status
        showDict["scenenumbering"] = show_obj.is_scene
        showDict["upgrade_once"] = show_obj.upgrade_once
        showDict["ignorewords"] = helpers.generate_word_str(show_obj.rls_ignore_words, show_obj.rls_ignore_words_regex)
        showDict["global_exclude_ignore"] = helpers.generate_word_str(show_obj.rls_global_exclude_ignore)
        showDict["requirewords"] = helpers.generate_word_str(show_obj.rls_require_words, show_obj.rls_require_words_regex)
        showDict["global_exclude_require"] = helpers.generate_word_str(show_obj.rls_global_exclude_require)
        if self.overview:
            showDict["overview"] = show_obj.overview
        showDict["prune"] = show_obj.prune
        showDict["tag"] = show_obj.tag
        showDict["imdb_id"] = show_obj.imdbid
        showDict["classification"] = show_obj.classification
        showDict["runtime"] = show_obj.runtime
        showDict["startyear"] = show_obj.startyear
        showDict["indexer"] = show_obj.tvid
        timezone, showDict['timezone'] = network_timezones.get_network_timezone(showDict['network'], return_name=True)

        if show_obj.next_episode():
            dtEpisodeAirs = SGDatetime.convert_to_setting(
                network_timezones.parse_date_time(show_obj.nextaired, showDict['airs'], timezone))
            showDict['airs'] = SGDatetime.sbftime(dtEpisodeAirs, t_preset=timeFormat).lstrip('0').replace(' 0', ' ')
            showDict['next_ep_airdate'] = SGDatetime.sbfdate(dtEpisodeAirs, d_preset=dateFormat)
        else:
            showDict['next_ep_airdate'] = ''

        return _responds(RESULT_SUCCESS, showDict)


class CMD_Show(CMD_SickGearShow):
    _help = {"desc": "get thetvdb.com show information",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "optionalParameters": {"overview": {"desc": "include overview"},
                                    },
             "SickGearCommand": "sg.show",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShow.__init__(self, handler, args, kwargs)


class CMD_SickGearShowAddExisting(ApiCall):
    _help = {"desc": "add a show to SickGear from an existing folder",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "production id of a show"},
                                    "location": {"desc": "full path to the existing folder for the show"}
                                    },
             "optionalParameters": {"initial": {"desc": "initial quality for the show"},
                                    "archive": {"desc": "archive quality for the show"},
                                    "upgrade_once": {"desc": "upgrade only once"},
                                    "pause": {"desc": "pause show search tasks to allow edits"},
                                    "subtitles": {"desc": "allow search episode subtitle"},
                                    "flatten_folders": {"desc": "flatten subfolders for the show"}
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().search_sources])
        self.location, args = self.check_params(args, kwargs, "location", None, True, "string", [])
        # optional
        self.initial, args = self.check_params(args, kwargs, "initial", None, False, "list", [q for q in quality_map])
        self.archive, args = self.check_params(args, kwargs, "archive", None, False, "list", [q for q in quality_map])
        self.upgradeonce, args = self.check_params(args, kwargs, "upgrade_once", False, False, "bool", [])

        self.pause, args = self.check_params(args, kwargs, "pause", int(sickbeard.PAUSE_DEFAULT), False, "int", [])
        self.flatten_folders, args = self.check_params(args, kwargs, "flatten_folders",
                                                       str(sickbeard.FLATTEN_FOLDERS_DEFAULT), False, "bool", [])
        self.subtitles, args = self.check_params(args, kwargs, "subtitles", int(sickbeard.USE_SUBTITLES), False, "int",
                                                 [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ add a show to SickGear from an existing folder """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if show_obj:
            return _responds(RESULT_FAILURE, msg="An existing indexerid already exists in the database")

        if not ek.ek(os.path.isdir, self.location):
            return _responds(RESULT_FAILURE, msg='Not a valid location')

        lINDEXER_API_PARMS = sickbeard.TVInfoAPI(self.tvid).api_params.copy()
        lINDEXER_API_PARMS['language'] = 'en'
        lINDEXER_API_PARMS['custom_ui'] = classes.AllShowInfosNoFilterListUI
        lINDEXER_API_PARMS['actors'] = False

        t = sickbeard.TVInfoAPI(self.tvid).setup(**lINDEXER_API_PARMS)

        try:
            myShow = t[int(self.prodid), False]
        except BaseTVinfoError as e:
            self.log(u"Unable to find show with id " + str(self.tvid), logger.WARNING)
            return _responds(RESULT_FAILURE, msg="Unable to retrieve information from indexer")

        indexerName = None
        if None is myShow or getattr(t, 'show_not_found', False) or not myShow.data['seriesname']:
            self.log(
                "Found show with tvid %s prodid %s, however it contained no show name" % (self.tvid, self.prodid),
                logger.DEBUG)
            return _responds(RESULT_FAILURE, msg="Unable to retrieve information from indexer")

        else:
            indexerName = myShow.data['seriesname']

        if not indexerName:
            return _responds(RESULT_FAILURE, msg="Unable to retrieve information from indexer")

        # use default quality as a failsafe
        newQuality = int(sickbeard.QUALITY_DEFAULT)
        iqualityID = []
        aqualityID = []

        if self.initial:
            for quality in self.initial:
                iqualityID.append(quality_map[quality])
        if self.archive:
            for quality in self.archive:
                aqualityID.append(quality_map[quality])

        if iqualityID or aqualityID:
            newQuality = Quality.combineQualities(iqualityID, aqualityID)

        sickbeard.show_queue_scheduler.action.add_show(
            int(self.tvid), int(self.prodid), self.location,
            quality=newQuality, upgrade_once=self.upgradeonce,
            paused=self.pause, default_status=SKIPPED, flatten_folders=int(self.flatten_folders)
        )

        return _responds(RESULT_SUCCESS, {"name": indexerName}, indexerName + " has been queued to be added")


class CMD_ShowAddExisting(CMD_SickGearShowAddExisting):
    _help = {"desc": "add a show to SickGear from an existing folder",
             "requiredParameters": {"tvdbid": {"desc": "thetvdb.com id"},
                                    "location": {"desc": "full path to the existing folder for the show"}
                                    },
             "optionalParameters": {"initial": {"desc": "initial quality for the show"},
                                    "archive": {"desc": "archive quality for the show"},
                                    "flatten_folders": {"desc": "flatten subfolders for the show"},
                                    "subtitles": {"desc": "allow search episode subtitle"}
                                    },
             "SickGearCommand": "sg.show.addexisting",
             }

    def __init__(self, handler, args, kwargs):
        kwargs['indexer'] = TVINFO_TVDB
        # required
        if 'tvdbid' in kwargs and 'indexerid' not in kwargs:
            kwargs['indexerid'], args = self.check_params(args, kwargs, "tvdbid", None, True, "int", [])
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearShowAddExisting.__init__(self, handler, args, kwargs)


class CMD_SickGearShowAddNew(ApiCall):
    _help = {"desc": "add a new show to sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of show"},
                                    "indexerid": {"desc": "id of show"},
                                    },
             "optionalParameters": {"initial": {"desc": "initial quality for the show"},
                                    "location": {"desc": "base path for where the show folder is to be created"},
                                    "archive": {"desc": "archive quality for the show"},
                                    "upgrade_once": {"desc": "upgrade only once"},
                                    "flatten_folders": {"desc": "flatten subfolders for the show"},
                                    "status": {"desc": "status of missing episodes"},
                                    "subtitles": {"desc": "allow search episode subtitle"},
                                    "anime": {"desc": "set show to anime"},
                                    "scene": {"desc": "show searches episodes by scene numbering"}
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().search_sources])
        # optional
        self.location, args = self.check_params(args, kwargs, "location", None, False, "string", [])
        self.initial, args = self.check_params(args, kwargs, "initial", None, False, "list", [q for q in quality_map])
        self.archive, args = self.check_params(args, kwargs, "archive", None, False, "list", [q for q in quality_map])
        self.upgradeonce, args = self.check_params(args, kwargs, "upgrade_once", False, False, "bool", [])
        self.pause, args = self.check_params(args, kwargs, "pause", int(sickbeard.PAUSE_DEFAULT), False, "int", [])
        self.status, args = self.check_params(args, kwargs, "status", None, False, "string",
                                              ["wanted", "skipped", "archived", "ignored"])
        self.scene, args = self.check_params(args, kwargs, "scene", int(sickbeard.SCENE_DEFAULT), False, "int", [])
        self.subtitles, args = self.check_params(
            args, kwargs, "subtitles", int(sickbeard.USE_SUBTITLES), False, "int", [])
        self.flatten_folders, args = self.check_params(args, kwargs, "flatten_folders",
                                                       str(sickbeard.FLATTEN_FOLDERS_DEFAULT), False, "bool", [])
        self.anime, args = self.check_params(args, kwargs, "anime", int(sickbeard.ANIME_DEFAULT), False, "int", [])
        self.lang = 'en'

        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ add a show to SickGear from an existing folder """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if show_obj:
            return _responds(RESULT_FAILURE, msg="An existing indexerid already exists in database")

        if not self.location:
            if "" != sickbeard.ROOT_DIRS:
                root_dirs = sickbeard.ROOT_DIRS.split('|')
                root_dirs.pop(0)
                default_index = int(sickbeard.ROOT_DIRS.split('|')[0])
                self.location = root_dirs[default_index]
            else:
                return _responds(RESULT_FAILURE, msg="Root directory is not set, please provide a location")

        if not ek.ek(os.path.isdir, self.location):
            return _responds(RESULT_FAILURE, msg="'" + self.location + "' is not a valid location")

        # use default quality as a failsafe
        newQuality = int(sickbeard.QUALITY_DEFAULT)
        iqualityID = []
        aqualityID = []

        if self.initial:
            for quality in self.initial:
                iqualityID.append(quality_map[quality])
        if self.archive:
            for quality in self.archive:
                aqualityID.append(quality_map[quality])

        if iqualityID or aqualityID:
            newQuality = Quality.combineQualities(iqualityID, aqualityID)

        # use default status as a failsafe
        newStatus = sickbeard.STATUS_DEFAULT
        if self.status:
            # convert the string status to a int
            for status in statusStrings.statusStrings:
                if statusStrings[status].lower() == str(self.status).lower():
                    self.status = status
                    break
            # TODO: check if obsolete
            if self.status not in statusStrings.statusStrings:
                raise ApiError("Invalid Status")
            # only allow the status options we want
            if int(self.status) not in (3, 5, 6, 7):
                return _responds(RESULT_FAILURE, msg="Status prohibited")
            newStatus = self.status

        lINDEXER_API_PARMS = sickbeard.TVInfoAPI(self.tvid).api_params.copy()
        lINDEXER_API_PARMS['language'] = 'en'
        lINDEXER_API_PARMS['custom_ui'] = classes.AllShowInfosNoFilterListUI
        lINDEXER_API_PARMS['actors'] = False

        t = sickbeard.TVInfoAPI(self.tvid).setup(**lINDEXER_API_PARMS)

        try:
            myShow = t[int(self.prodid), False]
        except BaseTVinfoError as e:
            self.log(u"Unable to find show with id " + str(self.tvid), logger.WARNING)
            return _responds(RESULT_FAILURE, msg="Unable to retrieve information from indexer")

        indexerName = None
        if None is myShow or getattr(t, 'show_not_found', False) or not myShow.data['seriesname']:
            self.log(
                "Found show with tvid %s prodid %s, however it contained no show name" % (self.tvid, self.prodid),
                logger.DEBUG)
            return _responds(RESULT_FAILURE, msg="Unable to retrieve information from indexer")

        else:
            indexerName = myShow.data['seriesname']

        if not indexerName:
            return _responds(RESULT_FAILURE, msg="Unable to retrieve information from indexer")

        # moved the logic check to the end in an attempt to eliminate empty directory being created from previous errors
        showPath = helpers.generate_show_dir_name(self.location, indexerName)

        # don't create show dir if config says not to
        if sickbeard.ADD_SHOWS_WO_DIR:
            self.log(u"Skipping initial creation of " + showPath + " due to config.ini setting")
        else:
            dir_exists = helpers.make_dir(showPath)
            if not dir_exists:
                self.log(u"Unable to create the folder " + showPath + ", can't add the show", logger.ERROR)
                return _responds(RESULT_FAILURE, {"path": showPath},
                                 "Unable to create the folder " + showPath + ", can't add the show")
            else:
                helpers.chmod_as_parent(showPath)

        sickbeard.show_queue_scheduler.action.add_show(
            int(self.tvid), int(self.prodid), showPath,
            quality=newQuality, upgrade_once=self.upgradeonce,
            paused=self.pause, default_status=newStatus, scene=self.scene, subtitles=self.subtitles,
            flatten_folders=int(self.flatten_folders), anime=self.anime,
            new_show=True, lang=self.lang
        )

        return _responds(RESULT_SUCCESS, {"name": indexerName}, indexerName + " has been queued to be added")


class CMD_ShowAddNew(CMD_SickGearShowAddNew):
    _help = {"desc": "add a new show to sickgear",
             "requiredParameters": {"tvdbid": {"desc": "thetvdb.com id"}
                                    },
             "optionalParameters": {"location": {"desc": "base path for where the show folder is to be created"},
                                    "initial": {"desc": "initial quality for the show"},
                                    "archive": {"desc": "archive quality for the show"},
                                    "pause": {"desc": "pause show search tasks to allow edits"},
                                    "status": {"desc": "status of missing episodes"},
                                    "scene": {"desc": "show searches episodes by scene numbering"},
                                    "subtitles": {"desc": "allow search episode subtitle"},
                                    "flatten_folders": {"desc": "flatten subfolders for the show"},
                                    "anime": {"desc": "set show to anime"},
                                    "lang": {"desc": "the 2 letter lang abbreviation id"}
                                    },
             "SickGearCommand": "sg.show.addnew",
             }

    valid_languages = {
        'el': 20, 'en': 7, 'zh': 27, 'it': 15, 'cs': 28, 'es': 16, 'ru': 22,
        'nl': 13, 'pt': 26, 'no': 9, 'tr': 21, 'pl': 18, 'fr': 17, 'hr': 31,
        'de': 14, 'da': 10, 'fi': 11, 'hu': 19, 'ja': 25, 'he': 24, 'ko': 32,
        'sv': 8, 'sl': 30}

    def __init__(self, handler, args, kwargs):
        kwargs['indexer'] = TVINFO_TVDB
        if 'tvdbid' in kwargs and 'indexerid' not in kwargs:
            kwargs['indexerid'], args = self.check_params(args, kwargs, "tvdbid", None, True, "int", [])
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearShowAddNew.__init__(self, handler, args, kwargs)


class CMD_SickGearShowCache(ApiCall):
    _help = {"desc": "check sickgear's cache to see if the banner or poster image for a show is valid",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ check sickgear's cache to see if the banner or poster image for a show is valid """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        # TODO: catch if cache dir is missing/invalid.. so it doesn't break show/show.cache
        # return {"poster": 0, "banner": 0}

        cache_obj = image_cache.ImageCache()

        has_poster = 0
        has_banner = 0

        if ek.ek(os.path.isfile, cache_obj.poster_path(show_obj.tvid, show_obj.prodid)):
            has_poster = 1
        if ek.ek(os.path.isfile, cache_obj.banner_path(show_obj.tvid, show_obj.prodid)):
            has_banner = 1

        return _responds(RESULT_SUCCESS, {"poster": has_poster, "banner": has_banner})


class CMD_ShowCache(CMD_SickGearShowCache):
    _help = {"desc": "check sickgear's cache to see if the banner or poster image for a show is valid",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.cache",
             }

    def __init__(self,
                 handler,
                 args,  # type: List
                 kwargs  # type: Dict
                 ):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowCache.__init__(self, handler, args, kwargs)


class CMD_SickGearShowDelete(ApiCall):
    _help = {"desc": "delete a show from sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"full": {"desc": "delete files/folder of show"}}
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.full_delete, args = self.check_params(args, kwargs, "full", False, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ delete a show from sickgear """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        if sickbeard.show_queue_scheduler.action.isBeingAdded(
                show_obj) or sickbeard.show_queue_scheduler.action.isBeingUpdated(show_obj):
            return _responds(RESULT_FAILURE, msg="Show can not be deleted while being added or updated")

        show_obj.delete_show(full=self.full_delete)
        return _responds(RESULT_SUCCESS, msg='%s has been deleted' % show_obj.unique_name)


class CMD_ShowDelete(CMD_SickGearShowDelete):
    _help = {"desc": "delete a show from sickgear",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.delete",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowDelete.__init__(self, handler, args, kwargs)


class CMD_SickGearShowGetQuality(ApiCall):
    _help = {"desc": "get the quality setting for a show in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the quality setting for a show in sickgear """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        anyQualities, bestQualities = _mapQuality(show_obj.quality)

        data = {"initial": anyQualities, "archive": bestQualities}

        if not self.sickbeard_call:
            data['upgrade_once'] = show_obj.upgrade_once

        return _responds(RESULT_SUCCESS, data)


class CMD_ShowGetQuality(CMD_SickGearShowGetQuality):
    _help = {"desc": "get the quality setting for a show in sickgear",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.getquality",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowGetQuality.__init__(self, handler, args, kwargs)


class CMD_SickGearShowGetPoster(ApiCall):
    _help = {"desc": "get the poster stored for a show in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the poster for a show in sickgear """
        return {'outputType': 'image', 'image': self.handler.show_poster({self.tvid: self.prodid}, 'poster', True)}


class CMD_ShowGetPoster(CMD_SickGearShowGetPoster):
    _help = {"desc": "get the poster stored for a show in sickgear",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.getposter",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowGetPoster.__init__(self, handler, args, kwargs)


class CMD_SickGearShowGetBanner(ApiCall):
    _help = {"desc": "get the banner stored for a show in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the banner for a show in sickgear """
        return {'outputType': 'image', 'image': self.handler.show_poster({self.tvid: self.prodid}, 'banner', True)}


class CMD_ShowGetBanner(CMD_SickGearShowGetBanner):
    _help = {"desc": "get the banner stored for a show in sickgear",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.getbanner",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowGetBanner.__init__(self, handler, args, kwargs)


class CMD_SickGearShowListFanart(ApiCall):
    _help = {"desc": "get list of fanarts stored for a show",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get list of fanarts stored for a show """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        fanart = []
        rating_names = {10: 'group', 20: 'favorite', 30: 'avoid'}
        cache_obj = image_cache.ImageCache()
        for img in ek.ek(glob.glob, cache_obj.fanart_path(
                show_obj.tvid, show_obj.prodid).replace('fanart.jpg', '*')) or []:
            match = re.search(r'(\d+(?:\.(\w*?(\d*)))?\.(?:\w{5,8}))\.fanart\.', img, re.I)
            if match and match.group(1):
                fanart += [(match.group(1), rating_names.get(sickbeard.FANART_RATINGS.get(
                    str(TVidProdid({self.tvid: self.prodid})()), {}).get(match.group(1), ''), ''))]

        return _responds(RESULT_SUCCESS, fanart)


class CMD_SickGearShowRateFanart(ApiCall):
    _help = {"desc": "set a fanart rating",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    "fanartname": {"desc": "fanart name form sg.show.listfanart"},
                                    "rating": {"desc": "rate: unrate, group, favorite, avoid"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.fanartname, args = self.check_params(args, kwargs, "fanartname", None, True, "string", [])
        self.rating, args = self.check_params(args, kwargs, "rating", None, True, "string",
                                              ['unrate', 'group', 'favorite', 'avoid'])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ set a fanart rating """
        cache_obj = image_cache.ImageCache()
        fanartfile = cache_obj.fanart_path(self.tvid, self.prodid).replace('fanart.jpg',
                                                                           '%s.fanart.jpg' % self.fanartname)
        if not ek.ek(os.path.isfile, fanartfile):
            return _responds(RESULT_FAILURE, msg='Unknown Fanart')
        fan_ratings = {'unrate': 0, 'group': 10, 'favorite': 20, 'avoid': 30}
        show_id = TVidProdid({self.tvid: self.prodid})()
        if 'unrate' == self.rating and str(show_id) in sickbeard.FANART_RATINGS \
                and self.fanartname in sickbeard.FANART_RATINGS[str(show_id)]:
            del sickbeard.FANART_RATINGS[str(show_id)][self.fanartname]
        else:
            sickbeard.FANART_RATINGS.setdefault(str(show_id), {})[self.fanartname] = fan_ratings[self.rating]
        sickbeard.save_config()
        return _responds(RESULT_SUCCESS, msg='Rated Fanart: %s = %s' % (self.fanartname, self.rating))


class CMD_SickGearShowGetFanart(ApiCall):
    _help = {"desc": "get the fanart stored for a show"
                     " X-Fanartname response header resturns Fanart name or default for not found",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"fanartname": {"desc": "fanart name form sg.show.listfanart"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.fanartname, args = self.check_params(args, kwargs, "fanartname", None, False, "string", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the fanart stored for a show """
        cache_obj = image_cache.ImageCache()
        default_fanartfile = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick', 'images', 'trans.png')
        fanartfile = default_fanartfile
        used_fanart = 'default'
        if self.fanartname:
            fanartfile = cache_obj.fanart_path(self.tvid, self.prodid).replace('fanart.jpg',
                                                                               '%s.fanart.jpg' % self.fanartname)
            if not ek.ek(os.path.isfile, fanartfile):
                fanartfile = default_fanartfile
                used_fanart = self.fanartname
        else:
            fanart = []
            for img in ek.ek(glob.glob, cache_obj.fanart_path(self.tvid, self.prodid).replace('fanart.jpg', '*')) or []:
                if not ek.ek(os.path.isfile, img):
                    continue
                match = re.search(r'(\d+(?:\.(\w*?(\d*)))?\.(?:\w{5,8}))\.fanart\.', img, re.I)
                if match and match.group(1):
                    fanart += [(img, match.group(1), sickbeard.FANART_RATINGS.get(
                        str(TVidProdid({self.tvid: self.prodid})()), {}).get(match.group(1), 0))]
            if fanart:
                fanartsorted = sorted([f for f in fanart if f[2] != 30], key=lambda x: x[2], reverse=True)
                max_fa = max([f[2] for f in fanartsorted])
                fanartsorted = [f for f in fanartsorted if f[2] == max_fa]
                if fanartsorted:
                    random_fanart = randint(0, len(fanartsorted) - 1)
                    fanartfile = fanartsorted[random_fanart][0]
                    used_fanart = fanartsorted[random_fanart][1]

        if fanartfile and ek.ek(os.path.isfile, fanartfile):
            with ek.ek(open, fanartfile, 'rb') as f:
                mime_type, encoding = MimeTypes().guess_type(fanartfile)
                self.handler.set_header('X-Fanartname', used_fanart)
                self.handler.set_header('Content-Type', mime_type)
                return {'outputType': 'image', 'image': f.read()}

        # we should never get here
        return _responds(RESULT_FAILURE, msg='No Fanart found')


class CMD_SickGearShowPause(ApiCall):
    _help = {"desc": "set the paused state for a show",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"pause": {"desc": "the pause state to set"}
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.pause, args = self.check_params(args, kwargs, "pause", 0, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ set the paused state for a show """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        if self.pause:
            show_obj.paused = True
            show_obj.save_to_db()
            return _responds(RESULT_SUCCESS, msg='%s has been paused' % show_obj.unique_name)
        else:
            show_obj.paused = False
            show_obj.save_to_db()
            return _responds(RESULT_SUCCESS, msg='%s has been unpaused' % show_obj.unique_name)

        # return _responds(RESULT_FAILURE, msg=str(show_obj.name) + " was unable to be paused")


class CMD_ShowPause(CMD_SickGearShowPause):
    _help = {"desc": "set the paused state for a show",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "optionalParameters": {"pause": {"desc": "the pause state to set"}
                                    },
             "SickGearCommand": "sg.show.pause",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowPause.__init__(self, handler, args, kwargs)


class CMD_SickGearShowRefresh(ApiCall):
    _help = {"desc": "refresh a show in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"}, },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ refresh a show in sickgear """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        try:
            sickbeard.show_queue_scheduler.action.refreshShow(show_obj)
            return _responds(RESULT_SUCCESS, msg='%s has queued to be refreshed' % show_obj.unique_name)
        except exceptions_helper.CantRefreshException as e:
            # TODO: log the exception
            return _responds(RESULT_FAILURE, msg='Unable to refresh %s. %s' % (show_obj.unique_name, ex(e)))


class CMD_ShowRefresh(CMD_SickGearShowRefresh):
    _help = {"desc": "refresh a show in sickgear",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.refresh",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowRefresh.__init__(self, handler, args, kwargs)


class CMD_SickGearShowSeasonList(ApiCall):
    _help = {"desc": "get a season list for a show",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"sort": {"desc": "change the sort order from descending to ascending"}}
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.sort, args = self.check_params(args, kwargs, "sort", "desc", False, "string",
                                            ["asc", "desc"])  # "asc" and "desc" default and fallback is "desc"
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get a season list for a show """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        my_db = db.DBConnection(row_type="dict")
        if "asc" == self.sort:
            # noinspection SqlRedundantOrderingDirection
            sql_result = my_db.select(
                "SELECT DISTINCT season"
                " FROM tv_episodes"
                " WHERE indexer = ? AND showid = ?"
                " ORDER BY season ASC",
                [self.tvid, self.prodid])
        else:
            sql_result = my_db.select(
                "SELECT DISTINCT season"
                " FROM tv_episodes"
                " WHERE indexer = ? AND showid = ?"
                " ORDER BY season DESC",
                [self.tvid, self.prodid])
        seasonList = []  # a list with all season numbers
        for cur_result in sql_result:
            seasonList.append(int(cur_result["season"]))

        return _responds(RESULT_SUCCESS, seasonList)


class CMD_ShowSeasonList(CMD_SickGearShowSeasonList):
    _help = {"desc": "get a season list for a show",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "optionalParameters": {"sort": {"desc": "change the sort order from descending to ascending"}
                                    },
             "SickGearCommand": "sg.show.seasonlist",
             }

    def __init__(self,
                 handler,
                 args,  # type: List
                 kwargs  # type: Dict
                 ):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowSeasonList.__init__(self, handler, args, kwargs)


class CMD_SickGearShowSeasons(ApiCall):
    _help = {"desc": "get episode list of all or a specific season",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"season": {"desc": "the season number"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.season, args = self.check_params(args, kwargs, "season", None, False, "int", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get episode list of all or a specific season """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        my_db = db.DBConnection(row_type="dict")

        if None is self.season:
            sql_result = my_db.select(
                "SELECT name, description, absolute_number, scene_absolute_number, episode,"
                " scene_episode, scene_season, airdate, status, season"
                " FROM tv_episodes"
                " WHERE indexer = ? AND showid = ?",
                [self.tvid, self.prodid])
            seasons = {}  # type: Dict[int, Dict]
            for cur_result in sql_result:
                status, quality = Quality.splitCompositeStatus(int(cur_result["status"]))
                cur_result["status"] = _get_status_Strings(status)
                cur_result["quality"] = _get_quality_string(quality)
                timezone, cur_result['timezone'] = network_timezones.get_network_timezone(show_obj.network,
                                                                                          return_name=True)
                dtEpisodeAirs = SGDatetime.convert_to_setting(
                    network_timezones.parse_date_time(cur_result['airdate'], show_obj.airs, timezone))
                cur_result['airdate'] = SGDatetime.sbfdate(dtEpisodeAirs, d_preset=dateFormat)
                cur_result['scene_episode'] = helpers.try_int(cur_result['scene_episode'])
                cur_result['scene_season'] = helpers.try_int(cur_result['scene_season'])
                cur_result['absolute_number'] = helpers.try_int(cur_result['absolute_number'])
                cur_result['scene_absolute_number'] = helpers.try_int(cur_result['scene_absolute_number'])
                curSeason = int(cur_result["season"])
                curEpisode = int(cur_result["episode"])
                del cur_result["season"]
                del cur_result["episode"]
                if curSeason not in seasons:
                    seasons[curSeason] = {}
                seasons[curSeason][curEpisode] = cur_result

        else:
            sql_result = my_db.select(
                "SELECT name, description, absolute_number, scene_absolute_number,"
                " episode, scene_episode, scene_season, airdate, status"
                " FROM tv_episodes"
                " WHERE indexer = ? AND showid = ? AND season = ?",
                [self.tvid, self.prodid, self.season])
            if len(sql_result) == 0:
                return _responds(RESULT_FAILURE, msg="Season not found")
            seasons = {}
            for cur_result in sql_result:
                curEpisode = int(cur_result["episode"])
                del cur_result["episode"]
                status, quality = Quality.splitCompositeStatus(int(cur_result["status"]))
                cur_result["status"] = _get_status_Strings(status)
                cur_result["quality"] = _get_quality_string(quality)
                timezone, cur_result['timezone'] = network_timezones.get_network_timezone(show_obj.network,
                                                                                          return_name=True)
                dtEpisodeAirs = SGDatetime.convert_to_setting(
                    network_timezones.parse_date_time(cur_result['airdate'], show_obj.airs, timezone))
                cur_result['airdate'] = SGDatetime.sbfdate(dtEpisodeAirs, d_preset=dateFormat)
                cur_result['scene_episode'] = helpers.try_int(cur_result['scene_episode'])
                cur_result['scene_season'] = helpers.try_int(cur_result['scene_season'])
                cur_result['absolute_number'] = helpers.try_int(cur_result['absolute_number'])
                cur_result['scene_absolute_number'] = helpers.try_int(cur_result['scene_absolute_number'])
                if curEpisode not in seasons:
                    seasons[curEpisode] = {}
                seasons[curEpisode] = cur_result

        return _responds(RESULT_SUCCESS, seasons)


class CMD_ShowSeasons(CMD_SickGearShowSeasons):
    _help = {"desc": "get episode list of all or a specific season",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "optionalParameters": {"season": {"desc": "the season number"},
                                    },
             "SickGearCommand": "sg.show.seasons",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowSeasons.__init__(self, handler, args, kwargs)


class CMD_SickGearShowSetQuality(ApiCall):
    _help = {
        "desc": "set desired quality of a show in sickgear"
                " if neither initial or archive are provided then the config default quality will be used",
        "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                               "indexerid": {"desc": "unique id of a show"}},
        "optionalParameters": {"initial": {"desc": "initial quality for the show"},
                               "archive": {"desc": "archive quality for the show"},
                               "upgrade_once": {"desc": "upgrade only once"}}
            }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # this for whatever reason removes hdbluray not sdtv... which is just wrong.
        # reverting to previous code.. plus we didnt use the new code everywhere.
        # self.archive, args = self.check_params(
        # args, kwargs, "archive", None, False, "list", _getQualityMap().values()[1:])
        self.initial, args = self.check_params(args, kwargs, "initial", None, False, "list", [q for q in quality_map])
        self.archive, args = self.check_params(args, kwargs, "archive", None, False, "list", [q for q in quality_map])
        self.upgradeonce, args = self.check_params(args, kwargs, "upgrade_once", False, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ set the quality for a show in sickgear by taking in a deliminated
            string of qualities, map to their value and combine for new values
        """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        # use default quality as a failsafe
        newQuality = int(sickbeard.QUALITY_DEFAULT)
        iqualityID = []
        aqualityID = []

        if self.initial:
            for quality in self.initial:
                iqualityID.append(quality_map[quality])
        if self.archive:
            for quality in self.archive:
                aqualityID.append(quality_map[quality])

        if iqualityID or aqualityID:
            newQuality = Quality.combineQualities(iqualityID, aqualityID)
        show_obj.quality = newQuality

        show_obj.upgrade_once = self.upgradeonce

        show_obj.save_to_db()

        return _responds(RESULT_SUCCESS,
                         msg='%s quality has been changed to %s' % (show_obj.unique_name,
                                                                    _get_quality_string(show_obj.quality)))


class CMD_ShowSetQuality(CMD_SickGearShowSetQuality):
    _help = {
        "desc": "set desired quality of a show in sickgear"
                " if neither initial or archive are provided then the config default quality will be used",
        "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"}},
        "optionalParameters": {"initial": {"desc": "initial quality for the show"},
                               "archive": {"desc": "archive quality for the show"}},
        "SickGearCommand": "sg.show.setquality",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help

        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowSetQuality.__init__(self, handler, args, kwargs)


class CMD_SickGearShowStats(ApiCall):
    _help = {"desc": "get episode statistics for a show",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get episode statistics for a given show """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        # show stats
        episode_status_counts_total = {"total": 0}
        for status in statusStrings.statusStrings:
            if status in SNATCHED_ANY + [UNKNOWN, DOWNLOADED]:
                continue
            episode_status_counts_total[status] = 0

        # add all the downloaded qualities
        episode_qualities_counts_download = {"total": 0}
        for statusCode in Quality.DOWNLOADED:
            status, quality = Quality.splitCompositeStatus(statusCode)
            if quality in [Quality.NONE]:
                continue
            episode_qualities_counts_download[statusCode] = 0

        # add all snatched qualities
        episode_qualities_counts_snatch = {"total": 0}
        for statusCode in Quality.SNATCHED_ANY:
            status, quality = Quality.splitCompositeStatus(statusCode)
            if quality in [Quality.NONE]:
                continue
            episode_qualities_counts_snatch[statusCode] = 0

        my_db = db.DBConnection(row_type="dict")
        sql_result = my_db.select("SELECT status, season FROM tv_episodes WHERE season != 0 AND showid = ? "
                                  "AND indexer = ?",
                                  [self.prodid, self.tvid])
        # the main loop that goes through all episodes
        for cur_result in sql_result:
            status, quality = Quality.splitCompositeStatus(int(cur_result["status"]))

            episode_status_counts_total["total"] += 1

            if status in Quality.DOWNLOADED:
                episode_qualities_counts_download["total"] += 1
                episode_qualities_counts_download[int(cur_result["status"])] += 1
            elif status in Quality.SNATCHED_ANY:
                episode_qualities_counts_snatch["total"] += 1
                episode_qualities_counts_snatch[int(cur_result["status"])] += 1
            elif 0 == status:  # we dont count NONE = 0 = N/A
                pass
            else:
                episode_status_counts_total[status] += 1

        # the outgoing container
        episodes_stats = {"downloaded": {}}
        # turning codes into strings
        for statusCode in episode_qualities_counts_download:
            if "total" == statusCode:
                episodes_stats["downloaded"]["total"] = episode_qualities_counts_download[statusCode]
                continue
            status, quality = Quality.splitCompositeStatus(int(statusCode))
            statusString = Quality.qualityStrings[quality].lower().replace(" ", "_").replace("(", "").replace(")", "")
            episodes_stats["downloaded"][statusString] = episode_qualities_counts_download[statusCode]

        episodes_stats["snatched"] = {}
        # turning codes into strings
        # and combining proper and normal
        for statusCode in episode_qualities_counts_snatch:
            if "total" == statusCode:
                episodes_stats["snatched"]["total"] = episode_qualities_counts_snatch[statusCode]
                continue
            status, quality = Quality.splitCompositeStatus(int(statusCode))
            statusString = Quality.qualityStrings[quality].lower().replace(" ", "_").replace("(", "").replace(")", "")
            if Quality.qualityStrings[quality] in episodes_stats["snatched"]:
                episodes_stats["snatched"][statusString] += episode_qualities_counts_snatch[statusCode]
            else:
                episodes_stats["snatched"][statusString] = episode_qualities_counts_snatch[statusCode]

        # episodes_stats["total"] = {}
        for statusCode in episode_status_counts_total:
            if "total" == statusCode:
                episodes_stats["total"] = episode_status_counts_total[statusCode]
                continue
            status, quality = Quality.splitCompositeStatus(int(statusCode))
            statusString = statusStrings.statusStrings[statusCode].lower().replace(" ", "_").replace("(", "").replace(
                ")", "")
            episodes_stats[statusString] = episode_status_counts_total[statusCode]

        return _responds(RESULT_SUCCESS, episodes_stats)


class CMD_ShowStats(CMD_SickGearShowStats):
    _help = {"desc": "get episode statistics for a show",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.stats",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowStats.__init__(self, handler, args, kwargs)


class CMD_SickGearShowUpdate(ApiCall):
    _help = {"desc": "update a show in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.tvid, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                            [i for i in indexer_api.TVInfoAPI().search_sources])
        self.prodid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ update a show in sickgear """
        show_obj = helpers.find_show_by_id({self.tvid: self.prodid})
        if not show_obj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        try:
            sickbeard.show_queue_scheduler.action.updateShow(show_obj, True)
            return _responds(RESULT_SUCCESS, msg='%s has queued to be updated' % show_obj.unique_name)
        except exceptions_helper.CantUpdateException as e:
            self.log(u'Unable to update %s. %s' % (show_obj.unique_name, ex(e)), logger.ERROR)
            return _responds(RESULT_FAILURE, msg='Unable to update %s. %s' % (show_obj.unique_name, ex(e)))


class CMD_ShowUpdate(CMD_SickGearShowUpdate):
    _help = {"desc": "update a show in sickgear",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.update",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = TVINFO_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowUpdate.__init__(self, handler, args, kwargs)


class CMD_SickGearShows(ApiCall):
    _help = {"desc": "get all shows in sickgear",
             "optionalParameters": {"sort": {"desc": "sort the list of shows by show name instead of indexerid"},
                                    "paused": {"desc": "only return shows that are set to paused"},
                                    "overview": {"desc": "include overview"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.sort, args = self.check_params(args, kwargs, "sort", "id", False, "string", ["id", "name"])
        self.paused, args = self.check_params(args, kwargs, "paused", None, False, "bool", [])
        self.overview, args = self.check_params(args, kwargs, "overview", False, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display_is_int_multi( self.prodid ) shows in sickgear """
        shows = {}

        for cur_show_obj in sickbeard.showList:

            if self.sickbeard_call and TVINFO_TVDB != cur_show_obj.tvid:
                continue

            if None is not self.paused and bool(self.paused) != bool(cur_show_obj.paused):
                continue

            genreList = []
            if cur_show_obj.genre:
                genreListTmp = cur_show_obj.genre.split("|")
                for genre in genreListTmp:
                    if genre:
                        genreList.append(genre)
            anyQualities, bestQualities = _mapQuality(cur_show_obj.quality)

            showDict = {
                "paused": cur_show_obj.paused,
                "quality": _get_quality_string(cur_show_obj.quality),
                "language": cur_show_obj.lang,
                "air_by_date": cur_show_obj.air_by_date,
                "airs": cur_show_obj.airs,
                "flatten_folders": cur_show_obj.flatten_folders,
                "genre": genreList,
                "location": cur_show_obj._location,
                "quality_details": {"initial": anyQualities, "archive": bestQualities},
                "sports": cur_show_obj.sports,
                "anime": cur_show_obj.anime,
                "indexerid": cur_show_obj.prodid,
                "indexer": cur_show_obj.tvid,
                "tvdbid": cur_show_obj.ids.get(TVINFO_TVDB, {'id': 0})['id'],
                'ids': {k: v.get('id') for k, v in iteritems(cur_show_obj.ids)},
                "tvrage_id": cur_show_obj.ids.get(TVINFO_TVRAGE, {'id': 0})['id'],
                "tvrage_name": cur_show_obj.name,
                "network": cur_show_obj.network,
                "show_name": cur_show_obj.name,
                "status": cur_show_obj.status,
                "subtitles": cur_show_obj.subtitles,
                "scenenumbering": cur_show_obj.is_scene,
                "upgrade_once": cur_show_obj.upgrade_once,
                "ignorewords": helpers.generate_word_str(cur_show_obj.rls_ignore_words, cur_show_obj.rls_ignore_words_regex),
                "global_exclude_ignore": helpers.generate_word_str(cur_show_obj.rls_global_exclude_ignore),
                "requirewords": helpers.generate_word_str(cur_show_obj.rls_require_words, cur_show_obj.rls_require_words_regex),
                "global_exclude_require": helpers.generate_word_str(cur_show_obj.rls_global_exclude_require),
                "prune": cur_show_obj.prune,
                "tag": cur_show_obj.tag,
                "imdb_id": cur_show_obj.imdbid,
                "classification": cur_show_obj.classification,
                "runtime": cur_show_obj.runtime,
                "startyear": cur_show_obj.startyear,
            }

            if self.overview:
                showDict["overview"] = cur_show_obj.overview

            timezone, showDict['timezone'] = network_timezones.get_network_timezone(showDict['network'],
                                                                                    return_name=True)

            if cur_show_obj.next_episode():
                dtEpisodeAirs = SGDatetime.convert_to_setting(
                    network_timezones.parse_date_time(cur_show_obj.nextaired, cur_show_obj.airs, timezone))
                showDict['next_ep_airdate'] = SGDatetime.sbfdate(dtEpisodeAirs, d_preset=dateFormat)
            else:
                showDict['next_ep_airdate'] = ''

            showDict["cache"] = CMD_SickGearShowCache(self.handler, (), {"indexer": cur_show_obj.tvid,
                                                                         "indexerid": cur_show_obj.prodid}).run()["data"]
            if not showDict["network"]:
                showDict["network"] = ""
            if "name" == self.sort:
                shows[cur_show_obj.name] = showDict
            else:
                if self.sickbeard_call:
                    shows[cur_show_obj.prodid] = showDict
                else:
                    shows[cur_show_obj.tvid_prodid] = showDict

        return _responds(RESULT_SUCCESS, shows)


class CMD_Shows(CMD_SickGearShows):
    _help = {"desc": "get all thetvdb.com shows in sickgear",
             "optionalParameters": {"sort": {"desc": "sort the list of shows by show name instead of indexerid"},
                                    "paused": {"desc": "only show the shows that are set to paused"},
                                    "overview": {"desc": "include overview"},
                                    },
             "SickGearCommand": "sg.shows",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearShows.__init__(self, handler, args, kwargs)


class CMD_SickGearShowsBrowseTrakt(ApiCall):
    _help = {"desc": "browse trakt shows in sickgear",
             "requiredParameters": {"type": {"desc": "type to browse: anticipated, newshows, newseasons, popular, "
                                                     "trending, recommended, watchlist"},
                                    },
             "optionalParameters": {"account_id": {"desc": "account_id for recommended, watchlist - "
                                                           "see sg.listtraktaccounts"}},
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.type, args = self.check_params(args, kwargs, "type", "anticipated", True, "string",
                                            ["anticipated", "newshows", "newseasons", "popular", "trending",
                                             "recommended", "watchlist"])
        # optional
        self.account, args = self.check_params(args, kwargs, "account_id", None, False, "int",
                                               [s for s in sickbeard.TRAKT_ACCOUNTS])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ browse trakt shows in sickgear """
        urls = {'anticipated': 'shows/anticipated?limit=%s&' % 100,
                'newshows': '/calendars/all/shows/new/%s/%s?' % (SGDatetime.sbfdate(
                        dt=datetime.datetime.now() + datetime.timedelta(days=-16), d_preset='%Y-%m-%d'), 32),
                'newseasons': '/calendars/all/shows/premieres/%s/%s?' % (SGDatetime.sbfdate(
                        dt=datetime.datetime.now() + datetime.timedelta(days=-16), d_preset='%Y-%m-%d'), 32),
                'popular': 'shows/popular?limit=%s&' % 100,
                'trending': 'shows/trending?limit=%s&' % 100,
                'recommended': 'recommendations/shows?limit=%s&' % 100,
                }
        kwargs = {}
        if self.type in ('recommended', 'watchlist'):
            if not self.account:
                return _responds(RESULT_FAILURE, msg='Need Trakt account')
            kwargs['send_oauth'] = self.account
            urls['watchlist'] = 'users/%s/watchlist/shows?limit=%s&' \
                                % (sickbeard.TRAKT_ACCOUNTS[self.account].slug, 100)
        try:
            data, oldest, newest = AddShows.get_trakt_data(urls[self.type], **kwargs)
        except Exception as e:
            return _responds(RESULT_FAILURE, msg=ex(e))
        return _responds(RESULT_SUCCESS, data)


class CMD_SickGearListTraktAccounts(ApiCall):
    _help = {"desc": "list Trakt accounts in sickgear"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ list Trakt accounts in sickgear """
        accounts = [{'name': v.name, 'account_id': v.account_id} for a, v in iteritems(sickbeard.TRAKT_ACCOUNTS)]
        return _responds(RESULT_SUCCESS, accounts)


class CMD_SickGearShowsForceUpdate(ApiCall):
    _help = {"desc": "force the daily show update now"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ force the daily show update now """
        if sickbeard.show_queue_scheduler.action.isShowUpdateRunning() \
                or sickbeard.show_update_scheduler.action.amActive:
            return _responds(RESULT_FAILURE, msg="show update already running.")

        result = sickbeard.show_update_scheduler.forceRun()
        if result:
            return _responds(RESULT_SUCCESS, msg="daily show update started")
        return _responds(RESULT_FAILURE, msg="can't start show update currently")


class CMD_SickGearShowsQueue(ApiCall):
    _help = {"desc": "list the show update queue"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ list the show update queue """
        return _responds(RESULT_SUCCESS, sickbeard.show_queue_scheduler.action.queue_length())


class CMD_SickGearShowsStats(ApiCall):
    _help = {"desc": "get the global shows and episode stats"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the global shows and episode stats """
        stats = {}

        indexer_limit = ('', ' AND indexer = %s' % TVINFO_TVDB)[self.sickbeard_call]
        my_db = db.DBConnection()
        today = str(datetime.date.today().toordinal())

        stats["shows_total"] = (len(sickbeard.showList),
                                len([cur_so for cur_so in sickbeard.showList
                                     if TVINFO_TVDB == cur_so.tvid]))[self.sickbeard_call]

        stats["shows_active"] = len(
            [cur_so for cur_so in sickbeard.showList
             if 0 == cur_so.paused and "Ended" != cur_so.status
             and (not self.sickbeard_call
                  or TVINFO_TVDB == cur_so.tvid)])

        stats["ep_downloaded"] = my_db.select("SELECT COUNT(*) FROM tv_episodes WHERE status IN (" + ",".join(
            [str(status) for status in
             Quality.DOWNLOADED + Quality.ARCHIVED]) + ") AND season != 0 and episode != 0 AND airdate <= " + today +
                                             indexer_limit)[0][0]

        stats["ep_total"] = my_db.select(
            "SELECT COUNT(*) FROM tv_episodes WHERE season != 0 AND episode != 0 AND (airdate != 1 OR status IN (" +
            ",".join([str(status) for status in Quality.SNATCHED_ANY + Quality.DOWNLOADED + Quality.ARCHIVED]) +
            ")) AND airdate <= " + today + " AND status != " + str(IGNORED) + indexer_limit)[0][0]

        return _responds(RESULT_SUCCESS, stats)


# WARNING: never define a cmd call string that contains a "_" (underscore)
class CMD_ShowsStats(CMD_SickGearShowsStats):
    _help = {"desc": "get the global thetvdb.com shows and episode stats",
             "SickGearCommand": "sg.shows.stats"}
# this is reserved for cmd indexes used while cmd chaining

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearShowsStats.__init__(self, handler, args, kwargs)

# WARNING: never define a param name that contains a "." (dot)
# this is reserved for cmd namspaces used while cmd chaining
# this is reserved for cmd indexes used while cmd chaining

# WARNING: never define a param name that contains a "." (dot)
# this is reserved for cmd namspaces used while cmd chaining


_functionMaper = {"help": CMD_Help,
                  "listcommands": CMD_ListCommands,
                  "future": CMD_ComingEpisodes,
                  "sg.future": CMD_SickGearComingEpisodes,
                  "episode": CMD_Episode,
                  "sg.episode": CMD_SickGearEpisode,
                  "episode.search": CMD_EpisodeSearch,
                  "sg.episode.search": CMD_SickGearEpisodeSearch,
                  "episode.setstatus": CMD_EpisodeSetStatus,
                  "sg.episode.setstatus": CMD_SickGearEpisodeSetStatus,
                  "episode.subtitlesearch": CMD_SubtitleSearch,
                  "sg.episode.subtitlesearch": CMD_SickGearSubtitleSearch,
                  "exceptions": CMD_Exceptions,
                  "sg.exceptions": CMD_SickGearExceptions,
                  'sg.setexceptions': CMD_SetExceptions,
                  "history": CMD_History,
                  "sg.history": CMD_SickGearHistory,
                  "history.clear": CMD_HistoryClear,
                  "sg.history.clear": CMD_SickGearHistoryClear,
                  "history.trim": CMD_HistoryTrim,
                  "sg.history.trim": CMD_SickGearHistoryTrim,
                  "logs": CMD_Logs,
                  "sg.logs": CMD_SickGearLogs,
                  "sb": CMD_SickBeard,
                  "sg": CMD_SickGear,
                  "postprocess": CMD_PostProcess,
                  "sg.postprocess": CMD_SickGearPostProcess,
                  "sb.addrootdir": CMD_SickBeardAddRootDir,
                  "sg.addrootdir": CMD_SickGearAddRootDir,
                  "sb.checkscheduler": CMD_SickBeardCheckScheduler,
                  "sg.checkscheduler": CMD_SickGearCheckScheduler,
                  "sb.deleterootdir": CMD_SickBeardDeleteRootDir,
                  "sg.deleterootdir": CMD_SickGearDeleteRootDir,
                  "sb.forcesearch": CMD_SickBeardForceSearch,
                  "sg.forcesearch": CMD_SickGearForceSearch,
                  "sg.searchqueue": CMD_SickGearSearchQueue,
                  "sb.getdefaults": CMD_SickBeardGetDefaults,
                  "sg.getdefaults": CMD_SickGearGetDefaults,
                  "sb.getmessages": CMD_SickBeardGetMessages,
                  "sg.getmessages": CMD_SickGearGetMessages,
                  "sg.getqualities": CMD_SickGearGetQualities,
                  "sg.getqualitystrings": CMD_SickGearGetqualityStrings,
                  "sb.getrootdirs": CMD_SickBeardGetRootDirs,
                  "sg.getrootdirs": CMD_SickGearGetRootDirs,
                  "sb.pausebacklog": CMD_SickBeardPauseBacklog,
                  "sg.pausebacklog": CMD_SickGearPauseBacklog,
                  "sb.ping": CMD_SickBeardPing,
                  "sg.ping": CMD_SickGearPing,
                  "sb.restart": CMD_SickBeardRestart,
                  "sg.restart": CMD_SickGearRestart,
                  "sb.searchtvdb": CMD_SickBeardSearchIndexers,
                  "sg.searchtv": CMD_SickGearSearchIndexers,
                  "sb.setdefaults": CMD_SickBeardSetDefaults,
                  "sg.setdefaults": CMD_SickGearSetDefaults,
                  "sg.setscenenumber": CMD_SickGearSetSceneNumber,
                  "sg.activatescenenumbering": CMD_SickGearActivateSceneNumber,
                  "sg.getindexers": CMD_SickGearGetIndexers,
                  "sg.getindexericon": CMD_SickGearGetIndexerIcon,
                  "sg.getnetworkicon": CMD_SickGearGetNetworkIcon,
                  "sb.shutdown": CMD_SickBeardShutdown,
                  "sg.shutdown": CMD_SickGearShutdown,
                  "sg.listignorewords": CMD_SickGearListIgnoreWords,
                  "sg.setignorewords": CMD_SickGearSetIgnoreWords,
                  "sg.listrequiredwords": CMD_SickGearListRequireWords_old,  # old method name
                  "sg.setrequiredwords": CMD_SickGearSetRequireWords_old,  # old method name
                  "sg.listrequirewords": CMD_SickGearListRequireWords,
                  "sg.setrequirewords": CMD_SickGearSetRequireWords,
                  "sg.updatewatchedstate": CMD_SickGearUpdateWatchedState,
                  "show": CMD_Show,
                  "sg.show": CMD_SickGearShow,
                  "show.addexisting": CMD_ShowAddExisting,
                  "sg.show.addexisting": CMD_SickGearShowAddExisting,
                  "show.addnew": CMD_ShowAddNew,
                  "sg.show.addnew": CMD_SickGearShowAddNew,
                  "show.cache": CMD_ShowCache,
                  "sg.show.cache": CMD_SickGearShowCache,
                  "show.delete": CMD_ShowDelete,
                  "sg.show.delete": CMD_SickGearShowDelete,
                  "show.getquality": CMD_ShowGetQuality,
                  "sg.show.getquality": CMD_SickGearShowGetQuality,
                  "show.getposter": CMD_ShowGetPoster,
                  "sg.show.getposter": CMD_SickGearShowGetPoster,
                  "show.getbanner": CMD_ShowGetBanner,
                  "sg.show.getbanner": CMD_SickGearShowGetBanner,
                  "sg.show.listfanart": CMD_SickGearShowListFanart,
                  "sg.show.ratefanart": CMD_SickGearShowRateFanart,
                  "sg.show.getfanart": CMD_SickGearShowGetFanart,
                  "show.pause": CMD_ShowPause,
                  "sg.show.pause": CMD_SickGearShowPause,
                  "show.refresh": CMD_ShowRefresh,
                  "sg.show.refresh": CMD_SickGearShowRefresh,
                  "show.seasonlist": CMD_ShowSeasonList,
                  "sg.show.seasonlist": CMD_SickGearShowSeasonList,
                  "show.seasons": CMD_ShowSeasons,
                  "sg.show.seasons": CMD_SickGearShowSeasons,
                  "show.setquality": CMD_ShowSetQuality,
                  "sg.show.setquality": CMD_SickGearShowSetQuality,
                  "show.stats": CMD_ShowStats,
                  "sg.show.stats": CMD_SickGearShowStats,
                  "show.update": CMD_ShowUpdate,
                  "sg.show.update": CMD_SickGearShowUpdate,
                  "shows": CMD_Shows,
                  "sg.shows": CMD_SickGearShows,
                  "sg.shows.browsetrakt": CMD_SickGearShowsBrowseTrakt,
                  "sg.listtraktaccounts": CMD_SickGearListTraktAccounts,
                  "shows.stats": CMD_ShowsStats,
                  "sg.shows.stats": CMD_SickGearShowsStats,
                  "sg.shows.forceupdate": CMD_SickGearShowsForceUpdate,
                  "sg.shows.queue": CMD_SickGearShowsQueue,
                  }

_functionMaper_reversed = {v: k for k, v in iteritems(_functionMaper)}
