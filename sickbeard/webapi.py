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

import os
import time
import urllib
import datetime
import re
import traceback
import sickbeard
import webserve
import glob

from mimetypes import MimeTypes
from random import randint

from sickbeard import db, logger, exceptions, history, ui, helpers
from sickbeard import encodingKludge as ek
from sickbeard import search_queue
from sickbeard import image_cache
from sickbeard import classes
from sickbeard import processTV
from sickbeard import network_timezones, sbdatetime
from sickbeard.exceptions import ex, MultipleShowObjectsException
from sickbeard.common import SNATCHED, SNATCHED_ANY, SNATCHED_PROPER, SNATCHED_BEST, DOWNLOADED, SKIPPED, UNAIRED, IGNORED, ARCHIVED, WANTED, UNKNOWN
from sickbeard.helpers import remove_article
from sickbeard.scene_numbering import set_scene_numbering_helper
from common import Quality, qualityPresetStrings, statusStrings
from sickbeard.indexers.indexer_config import *
from sickbeard.indexers import indexer_config, indexer_api
from tornado import gen
from sickbeard.search_backlog import FORCED_BACKLOG
from sickbeard.webserve import NewHomeAddShows

try:
    import json
except ImportError:
    from lib import simplejson as json

from lib import subliminal


dateFormat = "%Y-%m-%d"
dateTimeFormat = "%Y-%m-%d %H:%M"
timeFormat = '%A %I:%M %p'

RESULT_SUCCESS = 10  # only use inside the run methods
RESULT_FAILURE = 20  # only use inside the run methods
RESULT_TIMEOUT = 30  # not used yet :(
RESULT_ERROR = 40  # only use outside of the run methods !
RESULT_FATAL = 50  # only use in Api.default() ! this is the "we encountered an internal error" error
RESULT_DENIED = 60  # only use in Api.default() ! this is the acces denied error
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

quality_map_inversed = {v: k for k, v in quality_map.iteritems()}


class Api(webserve.BaseHandler):
    """ api class that returns json results """
    version = 10  # use an int since float-point is unpredictible
    intent = 4

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
            except (StandardError, Exception):
                raise ApiError('Unable to parse JSON.')
        super(Api, self).prepare()

    def post(self, route, *args, **kwargs):
        return self.get(route, *args, **kwargs)

    @gen.coroutine
    def get(self, route, *args, **kwargs):
        route = route.strip('/') or 'index'

        kwargs = self.request.arguments
        for arg, value in kwargs.items():
            if not isinstance(value, dict) and len(value) == 1:
                kwargs[arg] = value[0]

        args = args[1:]

        self.apiKey = sickbeard.API_KEY
        access, accessMsg, args, kwargs = self._grand_access(self.apiKey, route, args, kwargs)

        # set the output callback
        # default json
        outputCallbackDict = {'default': self._out_as_json,
                              'image': lambda x: x['image'],
        }

        # do we have acces ?
        if access:
            logger.log(accessMsg, logger.DEBUG)
        else:
            logger.log(accessMsg, logger.WARNING)
            return outputCallbackDict['default'](_responds(RESULT_DENIED, msg=accessMsg))

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
                outDict = _call_dispatcher(self, args, kwargs)
            except Exception as e:  # real internal error oohhh nooo :(
                logger.log(u"API :: " + ex(e), logger.ERROR)
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

    def _out_as_json(self, dict):
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        try:
            out = json.dumps(dict, indent=self.intent, sort_keys=True)
            callback = self.get_query_argument('callback', None) or self.get_query_argument('jsonp', None)
            if None is not callback:
                out = '%s(%s);' % (callback, out)  # wrap with JSONP call if requested

        except Exception as e:  # if we fail to generate the output fake an error
            logger.log(u'API :: ' + traceback.format_exc(), logger.ERROR)
            out = '{"result":"' + result_type_map[RESULT_ERROR] + '", "message": "error while composing output: "' + ex(
                e) + '"}'

        return out

    def _grand_access(self, realKey, apiKey, args, kwargs):
        """ validate api key and log result """
        remoteIp = self.request.remote_ip

        if not sickbeard.USE_API:
            msg = u'API :: ' + remoteIp + ' - SB API Disabled. ACCESS DENIED'
            return False, msg, args, kwargs
        elif apiKey == realKey:
            msg = u'API :: ' + remoteIp + ' - gave correct API KEY. ACCESS GRANTED'
            return True, msg, args, kwargs
        elif not apiKey:
            msg = u'API :: ' + remoteIp + ' - gave NO API KEY. ACCESS DENIED'
            return False, msg, args, kwargs
        else:
            msg = u'API :: ' + remoteIp + ' - gave WRONG API KEY ' + apiKey + '. ACCESS DENIED'
            return False, msg, args, kwargs


def call_dispatcher(handler, args, kwargs):
    """ calls the appropriate CMD class
        looks for a cmd in args and kwargs
        or calls the TVDBShorthandWrapper when the first args element is a number
        or returns an error that there is no such cmd
    """
    logger.log(u"API :: all args: '" + str(args) + "'", logger.DEBUG)
    logger.log(u"API :: all kwargs: '" + str(kwargs) + "'", logger.DEBUG)
    # logger.log(u"API :: dateFormat: '" + str(dateFormat) + "'", logger.DEBUG)

    cmds = None
    if args:
        cmds = args[0]
        args = args[1:]

    if "cmd" in kwargs:
        cmds = kwargs["cmd"]
        del kwargs["cmd"]

    outDict = {}
    if cmds != None:
        cmds = cmds.split("|")
        multiCmds = bool(len(cmds) > 1)
        for cmd in cmds:
            curArgs, curKwargs = filter_params(cmd, args, kwargs)
            cmdIndex = None
            if len(cmd.split("_")) > 1:  # was a index used for this cmd ?
                cmd, cmdIndex = cmd.split("_")  # this gives us the clear cmd and the index

            logger.log(u"API :: " + cmd + ": curKwargs " + str(curKwargs), logger.DEBUG)
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
            else:  # if someone chained one of the forbiden cmds they will get an error for this one cmd
                curOutDict = _responds(RESULT_ERROR, msg="The cmd '" + cmd + "' is not supported while chaining")

            if multiCmds:
                # note: if multiple same cmds are issued but one has not an index defined it will override all others
                # or the other way around, this depends on the order of the cmds
                # this is not a bug
                if cmdIndex is None:  # do we need a index dict for this cmd ?
                    outDict[cmd] = curOutDict
                else:
                    if not cmd in outDict:
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
    """ return only params kwargs that are for cmd
        and rename them to a clean version (remove "<cmd>_")
        args are shared across all cmds

        all args and kwarks are lowerd

        cmd are separated by "|" e.g. &cmd=shows|future
        kwargs are namespaced with "." e.g. show.indexerid=101501
        if a karg has no namespace asing it anyways (global)

        full e.g.
        /api?apikey=1234&cmd=show.seasonlist_asd|show.seasonlist_2&show.seasonlist_asd.indexerid=101501&show.seasonlist_2.indexerid=79488&sort=asc

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
        if kwarg.find(cmd + ".") == 0:
            cleanKey = kwarg.rpartition(".")[2]
            curKwargs[cleanKey] = kwargs[kwarg].lower()
        elif not "." in kwarg:  # the kwarg was not namespaced therefore a "global"
            curKwargs[kwarg] = kwargs[kwarg]
    return curArgs, curKwargs


class ApiCall(object):
    _help = {"desc": "No help message available. Please tell the devs that a help msg is missing for this cmd"}

    def __init__(self, handler, args, kwargs):

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

        # old sickbeard call
        self._sickbeard_call = getattr(self, '_sickbeard_call', False)

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

        for paramDict, type in [(self._requiredParams, "requiredParameters"),
                                (self._optionalParams, "optionalParameters")]:

            if type in self._help:
                for paramName in paramDict:
                    if not paramName in self._help[type]:
                        self._help[type][paramName] = {}
                    if paramDict[paramName]["allowedValues"]:
                        self._help[type][paramName]["allowedValues"] = paramDict[paramName]["allowedValues"]
                    else:
                        self._help[type][paramName]["allowedValues"] = "see desc"
                    self._help[type][paramName]["defaultValue"] = paramDict[paramName]["defaultValue"]

            elif paramDict:
                for paramName in paramDict:
                    self._help[type] = {}
                    self._help[type][paramName] = paramDict[paramName]
            else:
                self._help[type] = {}
        msg = "No description available"
        if "desc" in self._help:
            msg = self._help["desc"]
            del self._help["desc"]
        return _responds(RESULT_SUCCESS, self._help, msg)

    def return_missing(self):
        if len(self._missing) == 1:
            msg = "The required parameter: '" + self._missing[0] + "' was not set"
        else:
            msg = "The required parameters: '" + "','".join(self._missing) + "' where not set"
        return _responds(RESULT_ERROR, msg=msg)

    def check_params(self, args, kwargs, key, default, required, type, allowedValues, sub_type=None):
        # TODO: explain this
        """ function to check passed params for the shorthand wrapper
            and to detect missing/required param
        """
        # Fix for applications that send tvdbid instead of indexerid
        if self.sickbeard_call and key == "indexerid" and "indexerid" not in kwargs:
            key = "tvdbid"

        missing = True
        orgDefault = default

        if type == "bool":
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
                self._missing
                self._requiredParams[key] = {"allowedValues": allowedValues,
                                             "defaultValue": orgDefault}
            except AttributeError:
                self._missing = []
                self._requiredParams = {}
                self._requiredParams[key] = {"allowedValues": allowedValues,
                                             "defaultValue": orgDefault}
            if missing and key not in self._missing:
                self._missing.append(key)
        else:
            try:
                self._optionalParams[key] = {"allowedValues": allowedValues,
                                             "defaultValue": orgDefault}
            except AttributeError:
                self._optionalParams = {}
                self._optionalParams[key] = {"allowedValues": allowedValues,
                                             "defaultValue": orgDefault}

        if default:
            default = self._check_param_type(default, key, type, sub_type)
            if type == "bool":
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
        if type == "int":
            if _is_int(value):
                value = int(value)
            else:
                error = True
        elif type == "bool":
            if value in ("0", "1"):
                value = bool(int(value))
            elif value in ("true", "True", "TRUE"):
                value = True
            elif value in ("false", "False", "FALSE"):
                value = False
            else:
                error = True
        elif type == "list":
            if None is not sub_type:
                if sub_type in (int, long):
                    if isinstance(value, (int, long)):
                        value = [value]
                    elif isinstance(value, basestring):
                        if '|' in value:
                            li = [int(v) for v in value.split('|')]
                            if any([not isinstance(v, (int, long)) for v in li]):
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
        elif type == "dict":
            if isinstance(value, dict):
                value = value
            else:
                error = True
        elif type == "string":
            pass
        elif type == "ignore":
            pass
        else:
            logger.log(u"API :: Invalid param type set " + str(type) + " can not check or convert ignoring it",
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
                    if not item in allowedValues:
                        error = True
            else:
                if not value in allowedValues:
                    error = True

            if error:
                # this is kinda a ApiError but raising an error is the only way of quitting here
                raise ApiError(u"param: '" + str(name) + "' with given value: '" + str(
                    value) + "' is out of allowed range '" + str(allowedValues) + "'")


class TVDBShorthandWrapper(ApiCall):
    _help = {"desc": "this is an internal function wrapper. call the help command directly for more information"}

    def __init__(self, handler, args, kwargs, sid):
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
        if num < 1024.00:
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
    if data is None:
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
    if int(ordinal) != 1:
        date = datetime.date.fromordinal(ordinal)
    else:
        return ""
    return date.strftime(dateTimeFormat)


def _ordinal_to_dateForm(ordinal):
    if int(ordinal) != 1:
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


def _mapQuality(showObj):
    quality_map = _getQualityMap()

    anyQualities = []
    bestQualities = []

    iqualityID, aqualityID = Quality.splitQuality(int(showObj))
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
    if sickbeard.ROOT_DIRS == "":
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
    root_dirs = [urllib.unquote_plus(x) for x in root_dirs]

    default_dir = root_dirs[default_index]

    dir_list = []
    for root_dir in root_dirs:
        valid = 1
        try:
            ek.ek(os.listdir, root_dir)
        except:
            valid = 0
        default = 0
        if root_dir is default_dir:
            default = 1

        curDir = {}
        curDir['valid'] = valid
        curDir['location'] = root_dir
        curDir['default'] = default
        dir_list.append(curDir)

    return dir_list


class ApiError(Exception):
    "Generic API error"


class IntParseError(Exception):
    "A value could not be parsed into a int. But should be parsable to a int "


# -------------------------------------------------------------------------------------#

class CMD_ListCommands(ApiCall):
    _help = {"desc": "list help of all commands",
    }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display help information for all commands """
        out = ''
        table_sickgear_commands = ''
        table_sickbeard_commands = ''
        for f, v in sorted(_functionMaper.iteritems(), key=lambda x: (re.sub(r'^s[bg]\.', '', x[0], flags=re.I), re.sub(r'^sg\.', '1', x[0], flags=re.I))):
            if 'listcommands' == f:
                continue
            help = getattr(v, '_help', None)
            is_old_command = isinstance(help, dict) and "SickGearCommand" in help
            if is_old_command:
                table_sickbeard_commands += '<tr><td>%s</td>' % f
            else:
                table_sickgear_commands += '<tr><td>%s</td>' % f
            color = ("", " style='color: grey !important;'")[is_old_command]
            out += '<hr><h1 class="command"%s>%s%s</h1>' % (color, f, ("", " <span style='font-size: 50%;color: black;'>(Sickbeard compatibility command)</span>")[is_old_command])
            if isinstance(help, dict):
                sg_c = ''
                if "SickGearCommand" in help:
                    sg_c += '<td>%s</td>' % help['SickGearCommand']
                    out += "<p style='color: darkgreen !important;'>for all features use SickGear API Command: <b>%s</b></p>" % help['SickGearCommand']
                if "desc" in help:
                    if is_old_command:
                        table_sickbeard_commands += '<td>%s</td>%s' % (help['desc'], sg_c)
                    else:
                        table_sickgear_commands += '<td>%s</td>' % help['desc']
                    out += help['desc']

                table = ''

                if "requiredParameters" in help and isinstance(help['requiredParameters'], dict):
                    for p, d in help['requiredParameters'].iteritems():
                        des = ''
                        if isinstance(d, dict) and 'desc' in d:
                            des = d.get('desc')
                        table += "<tr><td><span>%s <span class='parareq'>required</span></span></td><td><p>%s</p></td></tr>" % (p, des)

                if "optionalParameters" in help and isinstance(help['optionalParameters'], dict):
                    for p, d in help['optionalParameters'].iteritems():
                        des = ''
                        if isinstance(d, dict) and 'desc' in d:
                            des = d.get('desc')
                        table += "<tr><td><span>%s <span class='paraopt'>optional</span></span></td><td><p>%s</p></td></tr>" % (p, des)
                if table:
                    out += "<table class='sickbeardTable' cellspacing='1' border='1' cellpadding='0'><thead><tr><th style='width: 25%'>Parameter</th><th>Description</th></tr></thead><tbody>"
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
            out = "<h1>SickBeard Commands (compatibility):</h1><table class='sickbeardTable' cellspacing='1' border='1' cellpadding='0'><thead><tr><th " \
                  "style='width: 25%'>Command</th><th>Description</th><th style='width: 25%'>Replacement SickGear Command</th></tr></thead><tbody>" + table_sickbeard_commands + '</tbody></table>' + out

        if table_sickgear_commands:
            out = "<h1>SickGear Commands:</h1><table class='sickbeardTable' cellspacing='1' border='1' cellpadding='0'><thead><tr><th " \
                  "style='width: 25%'>Command</th><th>Description</th></tr></thead><tbody>" + table_sickgear_commands + '</tbody></table>' + out

        return out


class CMD_Help(ApiCall):
    _help = {"desc": "display help information for a given subject/command",
             "optionalParameters": {"subject": {"desc": "command - the top level command"},
             }
    }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.subject, args = self.check_params(args, kwargs, "subject", "help", False, "string", _functionMaper.keys())
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display help information for a given subject/command """
        if self.subject in _functionMaper:
            out = _responds(RESULT_SUCCESS, _functionMaper.get(self.subject)((), {"help": 1}).run())
        else:
            out = _responds(RESULT_FAILURE, msg="No such cmd")
        return out


class CMD_SickGearComingEpisodes(ApiCall):
    _help = {"desc": "display the coming episodes",
             "optionalParameters": {"sort": {"desc": "change the sort order"},
                                    "type": {"desc": "one or more of allowedValues separated by |"},
                                    "paused": {
                                        "desc": "0 to exclude paused shows, 1 to include them, or omitted to use the SB default"},
             }
    }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.sort, args = self.check_params(args, kwargs, "sort", "date", False, "string", ["date", "show", "network"])
        self.type, args = self.check_params(args, kwargs, "type", "today|missed|soon|later", False, "list",
                                            ["missed", "later", "today", "soon"])
        self.paused, args = self.check_params(args, kwargs, "paused", sickbeard.EPISODE_VIEW_DISPLAY_PAUSED, False, "int",
                                              [0, 1])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display the coming episodes """
        today_dt = datetime.date.today()
        today = today_dt.toordinal()
        yesterday_dt = today_dt - datetime.timedelta(days=1)
        yesterday = yesterday_dt.toordinal()
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).toordinal()
        next_week_dt = (datetime.date.today() + datetime.timedelta(days=7))
        next_week = (next_week_dt + datetime.timedelta(days=1)).toordinal()
        recently = (yesterday_dt - datetime.timedelta(days=sickbeard.EPISODE_VIEW_MISSED_RANGE)).toordinal()

        done_show_list = []
        qualList = Quality.SNATCHED + Quality.DOWNLOADED + Quality.ARCHIVED + [IGNORED]

        myDB = db.DBConnection()
        sql_results = myDB.select(
            "SELECT airdate, airs, runtime, tv_shows.indexer AS 'indexer', episode, name AS 'ep_name', "
            "tv_episodes.status as 'status', description AS 'ep_plot', network, season, showid AS 'indexerid', "
            "show_name, tv_shows.quality AS quality, tv_shows.status AS 'show_status', "
            "tv_shows.paused AS 'paused' FROM tv_episodes, tv_shows WHERE " +
            ("", "tv_shows.indexer = %s AND " % INDEXER_TVDB)[self.sickbeard_call] +
            "season != 0 AND airdate >= ? AND " 
            "airdate <= ? AND tv_shows.indexer_id = tv_episodes.showid AND tv_shows.indexer == tv_episodes.indexer AND "
            "tv_episodes.status NOT IN (" + ','.join(['?'] * len(qualList)) + ")", [yesterday, next_week] + qualList)
        for cur_result in sql_results:
            done_show_list.append((int(cur_result["indexerid"]), int(cur_result["indexer"])))

        more_sql_results = [m for m in myDB.select(
            "SELECT airdate, airs, runtime, tv_shows.indexer AS 'indexer', episode, name AS 'ep_name', "
            "outer_eps.status as 'status', description AS 'ep_plot', network, season, showid AS 'indexerid', "
            "show_name, tv_shows.quality AS quality, tv_shows.status AS 'show_status', "
            "tv_shows.paused AS 'paused' FROM tv_episodes outer_eps, tv_shows WHERE " +
            ("", "tv_shows.indexer = %s AND " % INDEXER_TVDB)[self.sickbeard_call] +
            "season != 0 AND "
            "tv_shows.indexer_id = outer_eps.showid AND tv_shows.indexer == outer_eps.indexer AND "
            "airdate = (SELECT airdate FROM tv_episodes inner_eps WHERE inner_eps.season != 0 AND "
            "inner_eps.showid = outer_eps.showid AND inner_eps.indexer == outer_eps.indexer AND "
            "inner_eps.airdate >= ? ORDER BY inner_eps.airdate ASC LIMIT 1) AND "
            "outer_eps.status NOT IN (" + ','.join(['?'] * len(Quality.DOWNLOADED + Quality.SNATCHED)) + ")",
            [next_week] + Quality.DOWNLOADED + Quality.SNATCHED) if (int(m['indexerid']), int(m['indexer']))
                            not in done_show_list]
        sql_results += more_sql_results

        more_sql_results = myDB.select(
            "SELECT airdate, airs, runtime, tv_shows.indexer AS 'indexer', episode, name AS 'ep_name', "
            "tv_episodes.status as 'status', description AS 'ep_plot', network, season, showid AS 'indexerid', "
            "show_name, tv_shows.quality AS quality, tv_shows.status AS 'show_status', "
            "tv_shows.paused AS 'paused' FROM tv_episodes, tv_shows WHERE " +
            ("", "tv_shows.indexer = %s AND " % INDEXER_TVDB)[self.sickbeard_call] +
            "season != 0 AND tv_shows.indexer_id = tv_episodes.showid AND tv_shows.indexer == tv_episodes.indexer AND "
            "airdate <= ? AND airdate >= ? AND "
            "tv_episodes.status = ? AND tv_episodes.status NOT IN (" + ','.join(
                ['?'] * len(qualList)) + ")", [tomorrow, recently, WANTED] + qualList)
        sql_results += more_sql_results

        sql_results = list(set(sql_results))

        # make a dict out of the sql results
        sql_results = [dict(row) for row in sql_results
                       if Quality.splitCompositeStatus(helpers.tryInt(row['status']))[0] not in
                       [DOWNLOADED, SNATCHED, SNATCHED_PROPER, SNATCHED_BEST, ARCHIVED, IGNORED, SKIPPED]]

        # multi dimension sort
        sorts = {
            'date': (lambda a, b: cmp(
                (a['parsed_datetime'], a['data_show_name'], a['season'], a['episode']),
                (b['parsed_datetime'], b['data_show_name'], b['season'], b['episode']))),
            'network': (lambda a, b: cmp(
                (a['data_network'], a['parsed_datetime'], a['data_show_name'], a['season'], a['episode']),
                (b['data_network'], b['parsed_datetime'], b['data_show_name'], b['season'], b['episode']))),
            'show': (lambda a, b: cmp(
                (a['data_show_name'], a['parsed_datetime'], a['season'], a['episode']),
                (b['data_show_name'], b['parsed_datetime'], b['season'], b['episode'])))
        }

        def value_maybe_article(value=None):
            if None is value:
                return ''
            return (remove_article(value.lower()), value.lower())[sickbeard.SORT_ARTICLE]

        # add parsed_datetime to the dict
        for index, item in enumerate(sql_results):
            timezone, sql_results[index]['timezone'] = network_timezones.get_network_timezone(item['network'],
                                                                                              return_name=True)
            p_t = network_timezones.parse_date_time(item['airdate'], item['airs'], timezone)
            sql_results[index]['parsed_datetime'] = p_t
            sql_results[index]['local_datetime'] = sbdatetime.sbdatetime.sbstrftime(
                sbdatetime.sbdatetime.convert_to_setting(p_t, force_local=True), dateTimeFormat)
            sql_results[index]['data_show_name'] = value_maybe_article(item['show_name'])
            sql_results[index]['data_network'] = value_maybe_article(item['network'])
            sql_results[index]['status_str'] = statusStrings[item['status']]

        sql_results.sort(sorts[self.sort])

        finalEpResults = {}

        # add all requested types or all
        for curType in self.type:
            finalEpResults[curType] = []

        for ep in sql_results:
            """
                Missed:   yesterday... (less than 1week)
                Today:    today
                Soon:     tomorrow till next week
                Later:    later than next week
            """

            if ep["paused"] and not self.paused:
                continue

            ep['airdate'] = int(ep["airdate"])

            status = "soon"
            if ep["airdate"] < today:
                status = "missed"
            elif ep["airdate"] >= next_week:
                status = "later"
            elif ep["airdate"] >= today and ep["airdate"] < next_week:
                if ep["airdate"] == today:
                    status = "today"
                else:
                    status = "soon"

            # skip unwanted
            if self.type is not None and not status in self.type:
                continue

            if not ep["network"]:
                ep["network"] = ""

            ep["quality"] = _get_quality_string(ep["quality"])
            # clean up tvdb horrible airs field
            ep['airs'] = str(ep['airs']).replace('am', ' AM').replace('pm', ' PM').replace('  ', ' ')
            # start day of the week on 1 (monday)
            ep['weekday'] = 1 + datetime.date.fromordinal(ep['airdate']).weekday()
            # Add tvdbid for backward compability
            try:
                showObj = helpers.find_show_by_id(sickbeard.showList, {ep['indexer']: ep['indexerid']})
                ep['tvdbid'] = showObj.ids.get(INDEXER_TVDB, {'id': 0})['id']
                ep['ids'] = {k: v.get('id') for k, v in showObj.ids.iteritems()}
            except (StandardError, Exception):
                ep['tvdbid'] = (None, ep['indexerid'])[INDEXER_TVDB == ep['indexer']]
                ep['ids'] = None

            ep['airdate'] = sbdatetime.sbdatetime.sbfdate(datetime.date.fromordinal(ep['airdate']), d_preset=dateFormat)
            ep['parsed_datetime'] = sbdatetime.sbdatetime.sbfdatetime(ep['parsed_datetime'], d_preset=dateFormat, t_preset='%H:%M %z')

            # TODO: check if this obsolete
            if not status in finalEpResults:
                finalEpResults[status] = []

            finalEpResults[status].append(ep)

        return _responds(RESULT_SUCCESS, finalEpResults)


class CMD_ComingEpisodes(CMD_SickGearComingEpisodes):
    _help = {"desc": "display the coming episodes",
             "optionalParameters": {"sort": {"desc": "change the sort order"},
                                    "type": {"desc": "one or more of allowedValues separated by |"},
                                    "paused": {
                                        "desc": "0 to exclude paused shows, 1 to include them, or omitted to use the SB default"},
                                    },
             "SickGearCommand": "sg.future",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearComingEpisodes.__init__(self, handler, args, kwargs)


class CMD_SickGearEpisode(ApiCall):
    _help = {"desc": "display detailed info about an episode",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    "season": {"desc": "the season number"},
                                    "episode": {"desc": "the episode number"}
                                    },
             "optionalParameters": {"full_path": {
                 "desc": "show the full absolute path (if valid) instead of a relative path for the episode location"},

                                    },
            }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.s, args = self.check_params(args, kwargs, "season", None, True, "int", [])
        self.e, args = self.check_params(args, kwargs, "episode", None, True, "int", [])
        # optional
        self.fullPath, args = self.check_params(args, kwargs, "full_path", 0, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display detailed info about an episode """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        myDB = db.DBConnection(row_type="dict")
        sqlResults = myDB.select(
            "SELECT name, description, airdate, status, location, file_size, release_name, subtitles, absolute_number, "
            "scene_season, scene_episode, scene_absolute_number FROM tv_episodes WHERE indexer = ? AND showid = ? "
            "AND episode = ? AND season = ?",
            [self.indexer, self.indexerid, self.e, self.s])
        if not len(sqlResults) == 1:
            raise ApiError("Episode not found")
        episode = sqlResults[0]
        # handle path options
        # absolute vs relative vs broken
        showPath = None
        try:
            showPath = showObj.location
        except sickbeard.exceptions.ShowDirNotFoundException:
            pass

        if bool(self.fullPath) == True and showPath:
            pass
        elif bool(self.fullPath) == False and showPath:
            # using the length because lstrip removes to much
            showPathLength = len(showPath) + 1  # the / or \ yeah not that nice i know
            episode["location"] = episode["location"][showPathLength:]
        elif not showPath:  # show dir is broken ... episode path will be empty
            episode["location"] = ""
        # convert stuff to human form
        timezone, episode['timezone'] = network_timezones.get_network_timezone(showObj.network, return_name=True)
        episode['airdate'] = sbdatetime.sbdatetime.sbfdate(sbdatetime.sbdatetime.convert_to_setting(network_timezones.parse_date_time(int(episode['airdate']), showObj.airs, timezone)), d_preset=dateFormat)
        status, quality = Quality.splitCompositeStatus(int(episode["status"]))
        episode["status"] = _get_status_Strings(status)
        episode["quality"] = _get_quality_string(quality)
        episode["file_size_human"] = _sizeof_fmt(episode["file_size"])

        return _responds(RESULT_SUCCESS, episode)


class CMD_Episode(CMD_SickGearEpisode):
    _help = {"desc": "display detailed info about an episode",
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
        kwargs['indexer'] = INDEXER_TVDB
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
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.s, args = self.check_params(args, kwargs, "season", None, True, "int", [])
        self.e, args = self.check_params(args, kwargs, "episode", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ search for an episode """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        # retrieve the episode object and fail if we can't get one
        epObj = showObj.getEpisode(int(self.s), int(self.e))
        if isinstance(epObj, str):
            return _responds(RESULT_FAILURE, msg="Episode not found")

        # make a queue item for it and put it on the queue
        ep_queue_item = search_queue.ManualSearchQueueItem(showObj, epObj)
        sickbeard.searchQueueScheduler.action.add_item(ep_queue_item)  #@UndefinedVariable

        # wait until the queue item tells us whether it worked or not
        while ep_queue_item.success == None:  #@UndefinedVariable
            time.sleep(1)

        # return the correct json value
        if ep_queue_item.success:
            status, quality = Quality.splitCompositeStatus(epObj.status)  #@UnusedVariable
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
             "SickGearCommand": "episode.search",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearEpisodeSearch.__init__(self, handler, args, kwargs)


class CMD_SickGearEpisodeSetStatus(ApiCall):
    _help = {"desc": "set status of an episode or season (when no ep is provided)",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    "season": {"desc": "the season number"},
                                    "status": {"desc": "the status values: wanted, skipped, archived, ignored, failed, snatched, downloaded"}
                                    },
             "optionalParameters": {"episode": {"desc": "the episode number"},
                                    "force": {"desc": "should we replace existing (downloaded) episodes or not"},
                                    "quality": {"desc": "set quality of episode(s), only for statuses: snatched, downloaded, archived"},
                                    }
            }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.s, args = self.check_params(args, kwargs, "season", None, True, "int", [])
        self.status, args = self.check_params(args, kwargs, "status", None, True, "string",
                                              ["wanted", "skipped", "archived", "ignored", "failed", "snatched", "downloaded"])
        # optional
        self.e, args = self.check_params(args, kwargs, "episode", None, False, "int", [])
        self.force, args = self.check_params(args, kwargs, "force", 0, False, "bool", [])
        self.quality, args = self.check_params(args, kwargs, "quality", None, False, "string", [q for q in quality_map])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ set status of an episode or a season (when no ep is provided) """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
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

        ep_list = []
        if self.e:
            epObj = showObj.getEpisode(self.s, self.e)
            if epObj == None:
                return _responds(RESULT_FAILURE, msg="Episode not found")
            ep_list = [epObj]
        else:
            # get all episode numbers frome self,season
            ep_list = showObj.getAllEpisodes(season=self.s)

        def _epResult(result_code, ep, msg=""):
            return {'season': ep.season, 'episode': ep.episode, 'status': _get_status_Strings(ep.status),
                    'result': result_type_map[result_code], 'message': msg}

        ep_results = []
        failure = False
        start_backlog = False
        segments = {}

        sql_l = []
        for epObj in ep_list:
            with epObj.lock:
                if self.status == WANTED:
                    # figure out what episodes are wanted so we can backlog them
                    if epObj.season in segments:
                        segments[epObj.season].append(epObj)
                    else:
                        segments[epObj.season] = [epObj]

                # don't let them mess up UNAIRED episodes
                if epObj.status == UNAIRED:
                    if self.e != None:  # setting the status of a unaired is only considert a failure if we directly wanted this episode, but is ignored on a season request
                        ep_results.append(
                            _epResult(RESULT_FAILURE, epObj, "Refusing to change status because it is UNAIRED"))
                        failure = True
                    continue

                # allow the user to force setting the status for an already downloaded episode
                if epObj.status in Quality.DOWNLOADED and not self.force and None is self.quality:
                    ep_results.append(_epResult(RESULT_FAILURE, epObj,
                                                "Refusing to change status because it is already marked as DOWNLOADED"))
                    failure = True
                    continue

                if None is not self.quality:
                    epObj.status = Quality.compositeStatus(self.status, self.quality)
                else:
                    epObj.status = self.status
                result = epObj.get_sql()
                if None is not result:
                    sql_l.append(result)

                if self.status == WANTED:
                    start_backlog = True
                ep_results.append(_epResult(RESULT_SUCCESS, epObj))

        if 0 < len(sql_l):
            myDB = db.DBConnection()
            myDB.mass_action(sql_l)

        extra_msg = ""
        if start_backlog:
            for season, segment in segments.items():
                cur_backlog_queue_item = search_queue.BacklogQueueItem(showObj, segment)
                sickbeard.searchQueueScheduler.action.add_item(cur_backlog_queue_item)  #@UndefinedVariable

                logger.log(u"API :: Starting backlog for " + showObj.name + " season " + str(
                    season) + " because some episodes were set to WANTED")

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
        kwargs['indexer'] = INDEXER_TVDB
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
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.s, args = self.check_params(args, kwargs, "season", None, True, "int", [])
        self.e, args = self.check_params(args, kwargs, "episode", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ search episode subtitles """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        # retrieve the episode object and fail if we can't get one
        epObj = showObj.getEpisode(int(self.s), int(self.e))
        if isinstance(epObj, str):
            return _responds(RESULT_FAILURE, msg="Episode not found")

        # try do download subtitles for that episode
        previous_subtitles = epObj.subtitles

        try:
            subtitles = epObj.downloadSubtitles()
        except:
            return _responds(RESULT_FAILURE, msg='Unable to find subtitles')

        # return the correct json value
        if previous_subtitles != epObj.subtitles:
            status = 'New subtitles downloaded: %s' % ' '.join([
                "<img src='" + sickbeard.WEB_ROOT + "/images/flags/" + subliminal.language.Language(
                    x).alpha2 + ".png' alt='" + subliminal.language.Language(x).name + "'/>" for x in
                sorted(list(set(epObj.subtitles).difference(previous_subtitles)))])
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
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        ApiCall.__init__(self, handler, args, kwargs)


class CMD_SickGearExceptions(ApiCall):
    _help = {"desc": "display scene exceptions for all or a given show",
             "optionalParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    }
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, False, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display scene exceptions for all or a given show """
        myDB = db.DBConnection(row_type="dict")

        if self.indexerid is None:
            sqlResults = myDB.select("SELECT s.indexer, se.show_name, se.indexer_id AS 'indexerid' "
                                     "FROM scene_exceptions AS se INNER JOIN tv_shows as s "
                                     "ON se.indexer_id == s.indexer_id")
            scene_exceptions = {}
            for row in sqlResults:
                indexerid = row["indexerid"]
                indexer = row["indexer"]
                if self.sickbeard_call:
                    if indexerid not in scene_exceptions:
                        scene_exceptions[indexerid] = []
                    scene_exceptions[indexerid].append(row["show_name"])
                else:
                    if indexerid not in scene_exceptions.get(indexer, {}):
                        scene_exceptions.setdefault(indexer, {})[indexerid] = []
                    scene_exceptions.setdefault(indexer, {})[indexerid].append(row["show_name"])

        else:
            showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
            if not showObj:
                return _responds(RESULT_FAILURE, msg="Show not found")

            sqlResults = myDB.select(
                "SELECT show_name, indexer_id AS 'indexerid' FROM scene_exceptions WHERE indexer_id = ?",
                [self.indexerid])
            scene_exceptions = []
            for row in sqlResults:
                scene_exceptions.append(row["show_name"])

        return _responds(RESULT_SUCCESS, scene_exceptions)


class CMD_Exceptions(CMD_SickGearExceptions):
    _help = {"desc": "display scene exceptions for all or a given show",
             "optionalParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.exceptions",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearExceptions.__init__(self, handler, args, kwargs)


class CMD_SetExceptions(ApiCall):
    _help = {"desc": "set scene exceptions for a given show",
             "requiredParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    "forseason": {"desc": "exception for season, -1 for all seasons"},
             },
             "optionalParameters": {"add": {"desc": "list of exceptions to add"},
                                    "remove": {"desc": "list of exceptions to remove"},
             },
    }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.forseason, args = self.check_params(args, kwargs, "forseason", None, True, "int", [])
        # optional
        self.add, args = self.check_params(args, kwargs, "add", None, False, "list", [])
        self.remove, args = self.check_params(args, kwargs, "remove", None, False, "list", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        if not self.add and not self.remove:
            return _responds(RESULT_FAILURE, 'No Exceptions provided to be add or removed.')

        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, 'Could not find any show in db from indexer: %s with id: %s' %
                             (self.indexer, self.indexerid))

        myDB = db.DBConnection(row_type="dict")
        sqlResults = myDB.select("SELECT show_name, season, indexer_id AS 'indexerid' FROM scene_exceptions WHERE "
                                 "indexer_id = ? and season = ?", [self.indexerid, self.forseason])

        cl = []
        curexep = [(s['show_name'], s['season']) for s in sqlResults]
        add_list = []
        remove_list = []
        if self.remove:
            for r in self.remove:
                if (r, self.forseason) in curexep:
                    cl.append(['DELETE FROM scene_exceptions WHERE indexer_id = ? AND season = ? AND show_name = ?',
                               [self.indexerid, self.forseason, r]])
                    try:
                        curexep.remove((r, self.forseason))
                    except ValueError:
                        pass
                    remove_list.append(r)

        if self.add:
            for a in self.add:
                if (a, self.forseason) not in curexep:
                    cl.append(['INSERT INTO scene_exceptions (show_name, indexer_id, season) VALUES (?,?,?)',
                               [a, self.indexerid, self.forseason]])
                    curexep.append((a, self.forseason))
                    add_list.append(a)

        if cl:
            myDB.mass_action(cl)
        return _responds(RESULT_SUCCESS, data={'added': add_list, 'removed': remove_list, 'for season': self.forseason,
                                               'current': [c[0] for c in curexep], 'indexer': self.indexer,
                                               'indexerid': self.indexerid},
                         msg='Exceptions changed.')


class CMD_SickGearHistory(ApiCall):
    _help = {"desc": "display sickgear downloaded/snatched history",
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
        """ display sickgear downloaded/snatched history """

        typeCodes = []
        if self.type == "downloaded":
            self.type = "Downloaded"
            typeCodes = Quality.DOWNLOADED
        elif self.type == "snatched":
            self.type = "Snatched"
            typeCodes = Quality.SNATCHED
        else:
            typeCodes = Quality.SNATCHED + Quality.DOWNLOADED

        myDB = db.DBConnection(row_type="dict")

        ulimit = min(int(self.limit), 100)
        if ulimit == 0:
            sqlResults = myDB.select(
                "SELECT h.*, show_name, s.indexer FROM history h, tv_shows s WHERE h.showid=s.indexer_id" +
                ("", " AND s.indexer=%s" % INDEXER_TVDB)[self.sickbeard_call] +
                " AND action in (" + ','.join(['?'] * len(typeCodes)) + ") ORDER BY date DESC", typeCodes)
        else:
            sqlResults = myDB.select(
                "SELECT h.*, show_name, s.indexer FROM history h, tv_shows s WHERE h.showid=s.indexer_id" +
                ("", " AND s.indexer=%s" % INDEXER_TVDB)[self.sickbeard_call] +
                " AND action in (" + ','.join(['?'] * len(typeCodes)) + ") ORDER BY date DESC LIMIT ?",
                typeCodes + [ulimit])

        results = []
        for row in sqlResults:
            status, quality = Quality.splitCompositeStatus(int(row["action"]))
            status = _get_status_Strings(status)
            if self.type and not status == self.type:
                continue
            row["status"] = status
            row["quality"] = _get_quality_string(quality)
            row["date"] = _historyDate_to_dateTimeForm(str(row["date"]))
            del row["action"]
            _rename_element(row, "showid", "indexerid")
            row["resource_path"] = os.path.dirname(row["resource"])
            row["resource"] = os.path.basename(row["resource"])
            # Add tvdbid for backward compability
            row['tvdbid'] = (None, row['indexerid'])[INDEXER_TVDB == row['indexer']]
            results.append(row)

        return _responds(RESULT_SUCCESS, results)


class CMD_History(CMD_SickGearHistory):
    _help = {"desc": "display sickgear downloaded/snatched history",
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
    _help = {"desc": "clear sickgear's history",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ clear sickgear's history """
        myDB = db.DBConnection()
        myDB.action("DELETE FROM history WHERE 1=1")

        return _responds(RESULT_SUCCESS, msg="History cleared")


class CMD_HistoryClear(CMD_SickGearHistoryClear):
    _help = {"desc": "clear sickgear's history",
             "SickGearCommand": "sg.history.clear",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearHistoryClear.__init__(self, handler, args, kwargs)


class CMD_SickGearHistoryTrim(ApiCall):
    _help = {"desc": "trim sickgear's history by removing entries greater than 30 days old"
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ trim sickgear's history """
        myDB = db.DBConnection()
        myDB.action("DELETE FROM history WHERE date < " + str(
            (datetime.datetime.today() - datetime.timedelta(days=30)).strftime(history.dateFormat)))

        return _responds(RESULT_SUCCESS, msg="Removed history entries greater than 30 days old")


class CMD_HistoryTrim(CMD_SickGearHistoryTrim):
    _help = {"desc": "trim sickgear's history by removing entries greater than 30 days old",
             "SickGearCommand": "sg.history.trim",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearHistoryTrim.__init__(self, handler, args, kwargs)


class CMD_SickGearLogs(ApiCall):
    _help = {"desc": "view sickgear's log",
             "optionalParameters": {"min_level ": {
                 "desc": "the minimum level classification of log entries to show, with each level inherting its above level"}}
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.min_level, args = self.check_params(args, kwargs, "min_level", "error", False, "string",
                                                 ["error", "warning", "info", "debug"])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ view sickgear's log """
        # 10 = Debug / 20 = Info / 30 = Warning / 40 = Error
        min_level = logger.reverseNames[str(self.min_level).upper()]
        max_lines = 50

        regex = "^(\d\d\d\d)\-(\d\d)\-(\d\d)\s*(\d\d)\:(\d\d):(\d\d)\s*([A-Z]+)\s*(.+?)\s*\:\:\s*(.*)$"

        final_data = []
        normal_data = []
        truncate = []
        repeated = None
        num_lines = 0

        if os.path.isfile(logger.sb_log_instance.log_file_path):
            for x in logger.sb_log_instance.reverse_readline(logger.sb_log_instance.log_file_path):

                x = x.decode('utf-8')
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
    _help = {"desc": "view sickgear's log",
             "optionalParameters": {"min_level ": {
                 "desc": "the minimum level classification of log entries to show, with each level inherting its above level"}},
             "SickGearCommand": "sg.logs",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearLogs.__init__(self, handler, args, kwargs)


class CMD_SickGearPostProcess(ApiCall):
    _help = {"desc": "Manual postprocess TV Download Dir",
             "optionalParameters": {"path": {"desc": "Post process this folder"},
                                    "force_replace": {"desc": "Force already Post Processed Dir/Files"},
                                    "return_data": {"desc": "Returns result for the process"},
                                    "process_method": {"desc": "Symlink, hardlink, move or copy the file"},
                                    "is_priority": {"desc": "Replace the file even if it exists in a higher quality)"},
                                    "type": {"desc": "What type of postprocess request is this, auto of manual"}
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.path, args = self.check_params(args, kwargs, "path", None, False, "string", [])
        self.force_replace, args = self.check_params(args, kwargs, "force_replace", 0, False, "bool", [])
        self.return_data, args = self.check_params(args, kwargs, "return_data", 0, False, "bool", [])
        self.process_method, args = self.check_params(args, kwargs, "process_method", False, False, "string", ["copy", "symlink", "hardlink", "move"])
        self.is_priority, args = self.check_params(args, kwargs, "is_priority", 0, False, "bool", [])
        self.type, args = self.check_params(args, kwargs, "type", "auto", None, "string", ["auto", "manual"])
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

        data = processTV.processDir(self.path, process_method=self.process_method, force=self.force_replace, force_replace=self.is_priority, failed=False, type=self.type)

        if not self.return_data:
            data = ""

        return _responds(RESULT_SUCCESS, data=data, msg="Started postprocess for %s" % self.path)


class CMD_PostProcess(CMD_SickGearPostProcess):
    _help = {"desc": "Manual postprocess TV Download Dir",
             "optionalParameters": {"path": {"desc": "Post process this folder"},
                                    "force_replace": {"desc": "Force already Post Processed Dir/Files"},
                                    "return_data": {"desc": "Returns result for the process"},
                                    "process_method": {"desc": "Symlink, hardlink, move or copy the file"},
                                    "is_priority": {"desc": "Replace the file even if it exists in a higher quality)"},
                                    "type": {"desc": "What type of postprocess request is this, auto of manual"}
                                    },
             "SickGearCommand": "sg.postprocess",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearPostProcess.__init__(self, handler, args, kwargs)


class CMD_SickGear(ApiCall):
    _help = {"desc": "display misc sickgear related information"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display misc sickgear related information """
        data = {"sb_version": sickbeard.BRANCH, "api_version": Api.version, "fork": "SickGear",
                "api_commands": sorted(x for x in _functionMaper.keys() if 'listcommands' != x)}
        return _responds(RESULT_SUCCESS, data)


class CMD_SickBeard(CMD_SickGear):
    _help = {"desc": "display misc sickgear related information",
             "SickGearCommand": "sg",}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGear.__init__(self, handler, args, kwargs)


class CMD_SickGearAddRootDir(ApiCall):
    _help = {"desc": "add a sickgear user's parent directory",
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
        """ add a parent directory to sickgear's config """

        self.location = urllib.unquote_plus(self.location)
        location_matched = 0
        index = 0

        # dissallow adding/setting an invalid dir
        if not ek.ek(os.path.isdir, self.location):
            return _responds(RESULT_FAILURE, msg="Location is invalid")

        root_dirs = []

        if sickbeard.ROOT_DIRS == "":
            self.default = 1
        else:
            root_dirs = sickbeard.ROOT_DIRS.split('|')
            index = int(sickbeard.ROOT_DIRS.split('|')[0])
            root_dirs.pop(0)
            # clean up the list - replace %xx escapes by their single-character equivalent
            root_dirs = [urllib.unquote_plus(x) for x in root_dirs]
            for x in root_dirs:
                if (x == self.location):
                    location_matched = 1
                    if (self.default == 1):
                        index = root_dirs.index(self.location)
                    break

        if (location_matched == 0):
            if (self.default == 1):
                root_dirs.insert(0, self.location)
            else:
                root_dirs.append(self.location)

        root_dirs_new = [urllib.unquote_plus(x) for x in root_dirs]
        root_dirs_new.insert(0, index)
        root_dirs_new = '|'.join(unicode(x) for x in root_dirs_new)

        sickbeard.ROOT_DIRS = root_dirs_new
        return _responds(RESULT_SUCCESS, _getRootDirs(), msg="Root directories updated")


class CMD_SickBeardAddRootDir(CMD_SickGearAddRootDir):
    _help = {"desc": "add a sickgear user's parent directory",
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
    _help = {"desc": "query the scheduler"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ query the scheduler """
        myDB = db.DBConnection()
        sqlResults = myDB.select("SELECT last_backlog FROM info")

        backlogPaused = sickbeard.searchQueueScheduler.action.is_backlog_paused()  #@UndefinedVariable
        backlogRunning = sickbeard.searchQueueScheduler.action.is_backlog_in_progress()  #@UndefinedVariable
        nextBacklog = sickbeard.backlogSearchScheduler.next_run().strftime(dateFormat).decode(sickbeard.SYS_ENCODING)

        data = {"backlog_is_paused": int(backlogPaused), "backlog_is_running": int(backlogRunning),
                "last_backlog": _ordinal_to_dateForm(sqlResults[0]["last_backlog"]),
                "next_backlog": nextBacklog}
        return _responds(RESULT_SUCCESS, data)


class CMD_SickBeardCheckScheduler(CMD_SickGearCheckScheduler):
    _help = {"desc": "query the scheduler",
             "SickGearCommand": "sg.checkscheduler"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearCheckScheduler.__init__(self, handler, args, kwargs)


class CMD_SickGearDeleteRootDir(ApiCall):
    _help = {"desc": "delete a sickgear user's parent directory",
             "requiredParameters": {"location": {"desc": "the full path to root (parent) directory"}}
            }

    def __init__(self, handler, args, kwargs):
        # required
        self.location, args = self.check_params(args, kwargs, "location", None, True, "string", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ delete a parent directory from sickgear's config """
        if sickbeard.ROOT_DIRS == "":
            return _responds(RESULT_FAILURE, _getRootDirs(), msg="No root directories detected")

        newIndex = 0
        root_dirs_new = []
        root_dirs = sickbeard.ROOT_DIRS.split('|')
        index = int(root_dirs[0])
        root_dirs.pop(0)
        # clean up the list - replace %xx escapes by their single-character equivalent
        root_dirs = [urllib.unquote_plus(x) for x in root_dirs]
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

        root_dirs_new = [urllib.unquote_plus(x) for x in root_dirs_new]
        if len(root_dirs_new) > 0:
            root_dirs_new.insert(0, newIndex)
        root_dirs_new = "|".join(unicode(x) for x in root_dirs_new)

        sickbeard.ROOT_DIRS = root_dirs_new
        # what if the root dir was not found?
        return _responds(RESULT_SUCCESS, _getRootDirs(), msg="Root directory deleted")


class CMD_SickBeardDeleteRootDir(CMD_SickGearDeleteRootDir):
    _help = {"desc": "delete a sickgear user's parent directory",
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
    _help = {'desc': 'force the given search type searches',
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
        """ force the given search type search """
        result = None
        if 'recent' == self.searchtype:
            result = sickbeard.recentSearchScheduler.forceRun()
        elif 'backlog' == self.searchtype:
            result = sickbeard.backlogSearchScheduler.force_search(force_type=FORCED_BACKLOG)
        elif 'proper' == self.searchtype:
            result = sickbeard.properFinderScheduler.forceRun()
        if result:
            return _responds(RESULT_SUCCESS, msg='%s search successfully forced' % self.searchtype)
        return _responds(RESULT_FAILURE,
                         msg='Can not force the %s search because it\'s already active' % self.searchtype)


class CMD_SickBeardForceSearch(CMD_SickGearForceSearch):
    _help = {'desc': 'force the episode recent search early',
             "SickGearCommand": "sg.forcesearch",}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['searchtype'] = 'recent'
        self.sickbeard_call = True
        CMD_SickGearForceSearch.__init__(self, handler, args, kwargs)


class CMD_SickGearSearchQueue(ApiCall):
    _help = {'desc': 'list sickgear\'s search queue'}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ list sickgear's search queue """
        return _responds(RESULT_SUCCESS, sickbeard.searchQueueScheduler.action.queue_length())


class CMD_SickGearGetDefaults(ApiCall):
    _help = {"desc": "get sickgear user defaults"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get sickgear user defaults """

        anyQualities, bestQualities = _mapQuality(sickbeard.QUALITY_DEFAULT)

        data = {"status": statusStrings[sickbeard.STATUS_DEFAULT].lower(),
                "flatten_folders": int(sickbeard.FLATTEN_FOLDERS_DEFAULT), "initial": anyQualities,
                "archive": bestQualities, "future_show_paused": int(sickgear.EPISODE_VIEW_DISPLAY_PAUSED)}
        return _responds(RESULT_SUCCESS, data)


class CMD_SickBeardGetDefaults(CMD_SickGearGetDefaults):
    _help = {"desc": "get sickgear user defaults",
             "SickGearCommand": "sg.getdefaults"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearGetDefaults.__init__(self, handler, args, kwargs)


class CMD_SickGearGetMessages(ApiCall):
    _help = {"desc": "get all messages"}

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
    _help = {"desc": "get all messages",
             "SickGearCommand": "sg.getmessages"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearGetMessages.__init__(self, handler, args, kwargs)


class CMD_SickGearGetQualities(ApiCall):
    _help = {"desc": "get all qualities"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        return _responds(RESULT_SUCCESS, quality_map)


class CMD_SickGearGetIndexers(ApiCall):
    _help = {"desc": "get indexer list",
             "optionalParameters": {"searchable-only ": {"desc": "searchable indexers only"}}}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.searchable_only, args = self.check_params(args, kwargs, "searchable-only", False, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        result = {}
        for i in indexer_config.indexerConfig:
            for d, v in indexer_config.indexerConfig[i].iteritems():
                if self.searchable_only and (indexer_config.indexerConfig[i].get('mapped_only') or
                                             not indexer_config.indexerConfig[i].get('active') or
                                             indexer_config.indexerConfig[i].get('defunct')):
                    continue
                if d in ['id', 'name', 'show_url', 'mapped_only', 'main_url'] and \
                        isinstance(v, (basestring, tuple, dict, list, int, long, float, bool)):
                    if 'mapped_only' == d:
                        key = 'searchable'
                        val = not v and indexer_config.indexerConfig[i].get('active') and \
                              not indexer_config.indexerConfig[i].get('defunct')
                    else:
                        key = d
                        if 'show_url' == d:
                            val = re.sub(r'%\d{,2}d', '{INDEXER-ID}', v, flags=re.I)
                        else:
                            val = v
                    result.setdefault(i, {}).update({key: val})
        return _responds(RESULT_SUCCESS, result)


class CMD_SickGearGetIndexerIcon(ApiCall):
    _help = {"desc": "get indexer icon",
             "requiredParameters": {"indexer": {"desc": "indexer"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().all_indexers])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        # doesn't work
        i = indexer_config.indexerConfig.get(self.indexer)
        if not i:
            self.handler.set_status(404)
            return _responds(RESULT_FAILURE, 'Icon not found')
        img = i['icon']
        image = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick', 'images', img)
        if not ek.ek(os.path.isfile, image):
            self.handler.set_status(404)
            return _responds(RESULT_FAILURE, 'Icon not found')
        return {'outputType': 'image', 'image': self.handler.getImage(image)}


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
        return {'outputType': 'image', 'image': self.handler.getImage(image)}


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
    _help = {"desc": "get sickgear user parent directories"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the parent directories defined in sickgear's config """

        return _responds(RESULT_SUCCESS, _getRootDirs())


class CMD_SickBeardGetRootDirs(CMD_SickGearGetRootDirs):
    _help = {"desc": "get sickgear user parent directories",
             "SickGearCommand": "sg.getrootdirs"}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearGetRootDirs.__init__(self, handler, args, kwargs)


class CMD_SickGearPauseBacklog(ApiCall):
    _help = {"desc": "pause the backlog search",
             "optionalParameters": {"pause ": {"desc": "pause or unpause the global backlog"}}
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
            sickbeard.searchQueueScheduler.action.pause_backlog()  #@UndefinedVariable
            return _responds(RESULT_SUCCESS, msg="Backlog paused")
        else:
            sickbeard.searchQueueScheduler.action.unpause_backlog()  #@UndefinedVariable
            return _responds(RESULT_SUCCESS, msg="Backlog unpaused")


class CMD_SickBeardPauseBacklog(CMD_SickGearPauseBacklog):
    _help = {"desc": "pause the backlog search",
             "optionalParameters": {"pause ": {"desc": "pause or unpause the global backlog"}},
             "SickGearCommand": "sg.pausebacklog"
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearPauseBacklog.__init__(self, handler, args, kwargs)


class CMD_SickGearPing(ApiCall):
    _help = {"desc": "check to see if sickgear is running",}

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
        sickbeard.events.put(sickbeard.events.SystemEvent.RESTART)
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
    _help = {"desc": "search for show on the indexers with a given string and language",
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
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        # self.lang, args = self.check_params(args, kwargs, "lang", "en", False, "string", self.valid_languages.keys())
        self.indexers, args = self.check_params(args, kwargs, "indexers", -1, False, "list",
                                                [-1] + [i for i in indexer_api.indexerApi().search_indexers], int)

        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ search for show at indexers with a given string and language """
        if 1 > len(self.indexers) and -1 in self.indexers:
            raise ApiError('Mix of -1 (all Indexer) and specific Indexer not allowed')

        all_indexer = 1 == len(self.indexers) and -1 == self.indexers[0]

        if self.name and not self.indexerid:  # only name was given
            results = []
            indexertosearch = (self.indexers, [i for i in indexer_api.indexerApi().indexers if
                                indexer_api.indexerApi(i).config.get('active') and
                                not indexer_api.indexerApi(i).config.get('mapped_only') and
                                not indexer_api.indexerApi(i).config.get('defunct')])[all_indexer]
            for i in indexertosearch:
                lINDEXER_API_PARMS = sickbeard.indexerApi(i).api_params.copy()
                lINDEXER_API_PARMS['language'] = 'en'
                lINDEXER_API_PARMS['custom_ui'] = classes.AllShowsNoFilterListUI
                t = sickbeard.indexerApi(i).indexer(**lINDEXER_API_PARMS)

                apiData = None

                try:
                    apiData = t[str(self.name).encode(), False]
                except (StandardError, Exception):
                    pass

                for curSeries in apiData:
                    s = {"indexerid": int(curSeries['id']),
                         "name": curSeries['seriesname'],
                         "first_aired": curSeries['firstaired'],
                         "indexer": i,
                         "aliases": curSeries.get('aliases', None),
                         "relevance": NewHomeAddShows.get_UWRatio(self.name, curSeries['seriesname'],
                                                                  curSeries.get('aliases', None))}
                    if INDEXER_TVDB == i:
                        s["tvdbid"] = int(curSeries['id'])
                    else:
                        s["tvdbid"] = None
                    results.append(s)

            if not results:
                return _responds(RESULT_FAILURE, msg="Did not get result from %s" %
                                                     ', '.join([sickbeard.indexerApi(i).name for i in indexertosearch]))

            results = sorted(results, key=lambda x: x['relevance'], reverse=True)

            return _responds(RESULT_SUCCESS, {"results": results, "langid": 'en'})

        elif self.indexerid and not all_indexer and 1 == len(self.indexers):
            lINDEXER_API_PARMS = sickbeard.indexerApi(self.indexers[0]).api_params.copy()

            lang_id = 'en'
            lINDEXER_API_PARMS['language'] = 'en'
            lINDEXER_API_PARMS['custom_ui'] = classes.AllShowsNoFilterListUI

            lINDEXER_API_PARMS['actors'] = False

            t = sickbeard.indexerApi(self.indexers[0]).indexer(**lINDEXER_API_PARMS)

            try:
                myShow = t[int(self.indexerid), False]
            except (sickbeard.indexer_shownotfound, sickbeard.indexer_error):
                logger.log(u"API :: Unable to find show with id " + str(self.indexerid), logger.WARNING)
                return _responds(RESULT_SUCCESS, {"results": [], "langid": lang_id})

            if not myShow.data['seriesname']:
                logger.log(
                    u"API :: Found show with indexerid " + str(self.indexerid) + ", however it contained no show name",
                    logger.DEBUG)
                return _responds(RESULT_FAILURE, msg="Show contains no name, invalid result")

            showOut = [{"indexerid": self.indexerid,
                        "indexer": self.indexers[0],
                        "name": unicode(myShow.data['seriesname']),
                        "first_aired": myShow.data['firstaired'],
                        "aliases": myShow.data.get('aliases', None),
                        "relevance": NewHomeAddShows.get_UWRatio(self.name, myShow.data['seriesname'],
                                                                 myShow.data.get('aliases', None))}]

            if INDEXER_TVDB == self.indexers[0]:
                showOut[0]["tvdbid"] = int(myShow.data['id'])
            else:
                showOut[0]["tvdbid"] = None

            showOut = sorted(showOut, key=lambda x: x['relevance'], reverse=True)
            return _responds(RESULT_SUCCESS, {"results": showOut, "langid": lang_id})
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
        kwargs['indexers'] = INDEXER_TVDB
        # super, missing, help
        self.sickbeard_call = True
        CMD_SickGearSearchIndexers.__init__(self, handler, args, kwargs)


class CMD_SickBeardSetDefaults(ApiCall):
    _help = {"desc": "set sickgear user defaults",
             "optionalParameters": {"initial": {"desc": "initial quality for the show"},
                                    "archive": {"desc": "archive quality for the show"},
                                    "flatten_folders": {"desc": "flatten subfolders within the show directory"},
                                    "status": {"desc": "status of missing episodes"}
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
        """ set sickgear user defaults """

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
            # this should be obsolete bcause of the above
            if not self.status in statusStrings.statusStrings:
                raise ApiError("Invalid Status")
            #only allow the status options we want
            if int(self.status) not in (3, 5, 6, 7):
                raise ApiError("Status Prohibited")
            sickbeard.STATUS_DEFAULT = self.status

        if self.flatten_folders != None:
            sickbeard.FLATTEN_FOLDERS_DEFAULT = int(self.flatten_folders)

        if self.future_show_paused != None:
            sickbeard.EPISODE_VIEW_DISPLAY_PAUSED = int(self.future_show_paused)

        return _responds(RESULT_SUCCESS, msg="Saved defaults")


class CMD_SickGearSetSceneNumber(ApiCall):
    _help = {"desc": "set Scene Numbers",
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
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
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

        result = set_scene_numbering_helper(self.indexerid, self.indexer, self.forSeason, self.forEpisode,
                                            self.forAbsolute, self.sceneSeason, self.sceneEpisode, self.sceneEpisode)

        if not result['success']:
            return _responds(RESULT_FAILURE, result)

        return _responds(RESULT_SUCCESS, result)


class CMD_SickGearActivateSceneNumber(ApiCall):
    _help = {"desc": "De-/Activate Scene Numbers",
             "requiredParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    "activate": {"desc": "de-/activate scene numbering"}},
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.activate, args = self.check_params(args, kwargs, "activate", None, True, "bool", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ de-/activate scene numbers """

        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Can't find show")

        showObj.scene = int(self.activate)
        showObj.saveToDB()

        return _responds(RESULT_SUCCESS, data={'indexer': self.indexer, 'indexerid': self.indexerid,
                                               'show_name': showObj.name, 'scenenumbering': showObj.is_scene},
                         msg="Scene Numbering %sactivated" % ('de', '')[self.activate])


class CMD_SickBeardShutdown(ApiCall):
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


class CMD_SickGearListIgnoreWords(ApiCall):
    _help = {"desc": "list ignore words",
             "optionalParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    }
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, False, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ list ignore words """
        if self.indexer and self.indexerid:
            myDB = db.DBConnection()
            sqlResults = myDB.select('SELECT show_name, rls_ignore_words FROM tv_shows WHERE indexer = ? AND '
                                     'indexer_id = ?', [self.indexer, self.indexerid])
            if sqlResults:
                ignore_words = sqlResults[0]['rls_ignore_words']
                return_data = {'type': 'show', 'indexer': self.indexer, 'indexerid': self.indexerid,
                               'show name': sqlResults[0]['show_name']}
                return_type = '%s:' % sqlResults[0]['show_name']
            else:
                return _responds(RESULT_FAILURE, msg='Show not found.')
        elif (None is self.indexer) != (None is self.indexerid):
            return _responds(RESULT_FAILURE, msg='You must supply indexer + indexerid.')
        else:
            ignore_words = sickbeard.IGNORE_WORDS
            return_data = {'type': 'global'}
            return_type = 'Global'

        return_data['use regex'] = ignore_words.startswith('regex:')
        return_data['ignore words'] = [w.strip() for w in ignore_words.replace('regex:', '').split(',')]
        return _responds(RESULT_SUCCESS, data=return_data, msg="%s ignore words" % return_type)


class CMD_SickGearSetIgnoreWords(ApiCall):
    _help = {"desc": "set ignore words",
             "optionalParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    "add": {"desc": "add words to list"},
                                    "remove": {"desc": "remove words from list"},
                                    "regex": {"desc": "interpret ALL (including existing) ignore words as regex"},
                                    }
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, False, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.add, args = self.check_params(args, kwargs, "add", None, False, "list", [])
        self.remove, args = self.check_params(args, kwargs, "remove", None, False, "list", [])
        self.regex, args = self.check_params(args, kwargs, "regex", None, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ set ignore words """
        if not self.add and not self.remove:
            return _responds(RESULT_FAILURE, msg="No words to add/remove provided")

        def _create_ignore_words():
            use_regex = ignore_words.startswith('regex:')
            ignore_list = [w.strip() for w in ignore_words.replace('regex:', '').split(',')]

            if None is not self.regex:
                use_regex = self.regex
            if self.add:
                for a in self.add:
                    ignore_list.append(a)
            if self.remove:
                for r in self.remove:
                    try:
                        ignore_list.remove(r)
                    except ValueError:
                        pass
            return use_regex, ignore_list, '%s%s' % (('', 'regex:')[use_regex], ', '.join(ignore_list))

        if self.indexer and self.indexerid:
            showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
            if not showObj:
                return _responds(RESULT_FAILURE, msg="Show not found")

            myDB = db.DBConnection()
            sqlResults = myDB.select('SELECT show_name, rls_ignore_words FROM tv_shows WHERE indexer = ? AND '
                                     'indexer_id = ?', [self.indexer, self.indexerid])

            ignore_words = ''
            if sqlResults:
                ignore_words = sqlResults[0]['rls_ignore_words']

            return_data = {'type': 'show', 'indexer': self.indexer, 'indexerid': self.indexerid,
                           'show name': sqlResults[0]['show_name']}
            return_type = '%s:' % sqlResults[0]['show_name']

            use_regex, ignore_list, new_ignore_words = _create_ignore_words()
            myDB.action('UPDATE tv_shows SET rls_ignore_words = ? WHERE indexer = ? AND indexer_id = ?',
                        [new_ignore_words, self.indexer, self.indexerid])
        elif (None is self.indexer) != (None is self.indexerid):
            return _responds(RESULT_FAILURE, msg='You must supply indexer + indexerid.')
        else:
            ignore_words = sickbeard.IGNORE_WORDS
            use_regex, ignore_list, new_ignore_words = _create_ignore_words()
            sickbeard.IGNORE_WORDS = new_ignore_words
            sickbeard.save_config()
            return_data = {'type': 'global'}
            return_type = 'Global'

        return_data['use regex'] = use_regex
        return_data['ignore words'] = ignore_list
        return _responds(RESULT_SUCCESS, data=return_data, msg="%s set ignore words" % return_type)


class CMD_SickGearListRequireWords(ApiCall):
    _help = {"desc": "list requried words",
             "optionalParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    }
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, False, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ list required words """
        if self.indexer and self.indexerid:
            myDB = db.DBConnection()
            sqlResults = myDB.select('SELECT show_name, rls_require_words FROM tv_shows WHERE indexer = ? '
                                     'AND indexer_id = ?', [self.indexer, self.indexerid])
            if sqlResults:
                required_words = sqlResults[0]['rls_require_words']
                return_data = {'type': 'show', 'indexer': self.indexer, 'indexerid': self.indexerid,
                               'show name': sqlResults[0]['show_name']}
                return_type = '%s:' % sqlResults[0]['show_name']
            else:
                return _responds(RESULT_FAILURE, msg='Show not found.')
        elif (None is self.indexer) != (None is self.indexerid):
            return _responds(RESULT_FAILURE, msg='You must supply indexer + indexerid.')
        else:
            required_words = sickbeard.REQUIRE_WORDS
            return_data = {'type': 'global'}
            return_type = 'Global'

        return_data['use regex'] = required_words.startswith('regex:')
        return_data['required words'] = [w.strip() for w in required_words.replace('regex:', '').split(',')]
        return _responds(RESULT_SUCCESS, data=return_data, msg="%s required words" % return_type)


class CMD_SickGearSetRequrieWords(ApiCall):
    _help = {"desc": "set required words",
             "optionalParameters": {"indexerid": {"desc": "unique id of a show"},
                                    "indexer": {"desc": "indexer of a show"},
                                    "add": {"desc": "add words to list"},
                                    "remove": {"desc": "remove words from list"},
                                    "regex": {"desc": "interpret ALL (including existing) ignore words as regex"},
                                    }
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, False, "int", [])
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, False, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.add, args = self.check_params(args, kwargs, "add", None, False, "list", [])
        self.remove, args = self.check_params(args, kwargs, "remove", None, False, "list", [])
        self.regex, args = self.check_params(args, kwargs, "regex", None, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ set ignore words """
        if not self.add and not self.remove:
            return _responds(RESULT_FAILURE, msg="No words to add/remove provided")

        def _create_required_words():
            use_regex = requried_words.startswith('regex:')
            require_list = [w.strip() for w in requried_words.replace('regex:', '').split(',')]

            if None is not self.regex:
                use_regex = self.regex
            if self.add:
                for a in self.add:
                    require_list.append(a)
            if self.remove:
                for r in self.remove:
                    try:
                        require_list.remove(r)
                    except ValueError:
                        pass
            return use_regex, require_list, '%s%s' % (('', 'regex:')[use_regex], ', '.join(require_list))

        if self.indexer and self.indexerid:
            showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
            if not showObj:
                return _responds(RESULT_FAILURE, msg="Show not found")

            myDB = db.DBConnection()
            sqlResults = myDB.select('SELECT show_name, rls_require_words FROM tv_shows WHERE indexer = ? AND '
                                     'indexer_id = ?', [self.indexer, self.indexerid])

            requried_words = ''
            if sqlResults:
                requried_words = sqlResults[0]['rls_require_words']

            return_data = {'type': 'show', 'indexer': self.indexer, 'indexerid': self.indexerid,
                           'show name': sqlResults[0]['show_name']}
            return_type = '%s:' % sqlResults[0]['show_name']

            use_regex, required_list, new_required_words = _create_required_words()
            myDB.action('UPDATE tv_shows SET rls_require_words = ? WHERE indexer = ? AND indexer_id = ?',
                        [new_required_words, self.indexer, self.indexerid])
        elif (None is self.indexer) != (None is self.indexerid):
            return _responds(RESULT_FAILURE, msg='You must supply indexer + indexerid.')
        else:
            requried_words = sickbeard.REQUIRE_WORDS
            use_regex, required_list, new_required_words = _create_required_words()
            sickbeard.REQUIRE_WORDS = new_required_words
            sickbeard.save_config()
            return_data = {'type': 'global'}
            return_type = 'Global'

        return_data['use regex'] = use_regex
        return_data['required words'] = required_list
        return _responds(RESULT_SUCCESS, data=return_data, msg="%s set requried words" % return_type)


class CMD_SickGearUpdateWatchedState(ApiCall):
    _help = {"desc": "Update db with details of media file that is watched or unwatched",
             "requiredParameters": {
                 "payloadjson": {
                     "desc": "Payload is a dict of dicts transmitted as JSON via POST request"},
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

        from webserve import MainHandler
        MainHandler.update_watched_state(payload, as_json=False)

        if not payload:
            return _responds(RESULT_FAILURE, msg='Request made to SickGear with invalid payload')

        return _responds(RESULT_SUCCESS, payload)


class CMD_SickGearShow(ApiCall):
    _help = {"desc": "display information for a given show",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"overview": {"desc": "include overview"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.overview, args = self.check_params(args, kwargs, "overview", False, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display information for a given show """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        showDict = {}
        showDict["season_list"] = CMD_ShowSeasonList(self.handler, (), {"indexerid": self.indexerid}).run()["data"]
        showDict["cache"] = CMD_ShowCache(self.handler, (), {"indexerid": self.indexerid}).run()["data"]

        genreList = []
        if showObj.genre:
            genreListTmp = showObj.genre.split("|")
            for genre in genreListTmp:
                if genre:
                    genreList.append(genre)
        showDict["genre"] = genreList
        showDict["quality"] = _get_quality_string(showObj.quality)

        anyQualities, bestQualities = _mapQuality(showObj.quality)
        showDict["quality_details"] = {"initial": anyQualities, "archive": bestQualities}

        try:
            showDict["location"] = showObj.location
        except sickbeard.exceptions.ShowDirNotFoundException:
            showDict["location"] = ""

        showDict["language"] = showObj.lang
        showDict["show_name"] = showObj.name
        showDict["paused"] = showObj.paused
        showDict["subtitles"] = showObj.subtitles
        showDict["air_by_date"] = showObj.air_by_date
        showDict["flatten_folders"] = showObj.flatten_folders
        showDict["sports"] = showObj.sports
        showDict["anime"] = showObj.anime
        #clean up tvdb horrible airs field
        showDict["airs"] = str(showObj.airs).replace('am', ' AM').replace('pm', ' PM').replace('  ', ' ')
        showDict["indexerid"] = self.indexerid
        showDict["tvrage_id"] = showObj.ids.get(INDEXER_TVRAGE, {'id': 0})['id']
        showDict['ids'] = {k: v.get('id') for k, v in showObj.ids.iteritems()}
        showDict["tvrage_name"] = showObj.name
        showDict["network"] = showObj.network
        if not showDict["network"]:
            showDict["network"] = ""
        showDict["status"] = showObj.status
        showDict["scenenumbering"] = showObj.is_scene
        showDict["upgrade_once"] = showObj.upgrade_once
        showDict["ignorewords"] = showObj.rls_ignore_words
        showDict["requirewords"] = showObj.rls_require_words
        if self.overview:
            showDict["overview"] = showObj.overview
        showDict["tag"] = showObj.tag
        showDict["imdb_id"] = showObj.imdbid
        showDict["classification"] = showObj.classification
        showDict["runtime"] = showObj.runtime
        showDict["startyear"] = showObj.startyear
        showDict["indexer"] = showObj.indexer
        timezone, showDict['timezone'] = network_timezones.get_network_timezone(showDict['network'], return_name=True)

        if showObj.nextaired:
            dtEpisodeAirs = sbdatetime.sbdatetime.convert_to_setting(
                network_timezones.parse_date_time(showObj.nextaired, showDict['airs'], timezone))
            showDict['airs'] = sbdatetime.sbdatetime.sbftime(dtEpisodeAirs,
                                                             t_preset=timeFormat).lstrip('0').replace(' 0', ' ')
            showDict['next_ep_airdate'] = sbdatetime.sbdatetime.sbfdate(dtEpisodeAirs, d_preset=dateFormat)
        else:
            showDict['next_ep_airdate'] = ''

        return _responds(RESULT_SUCCESS, showDict)


class CMD_Show(CMD_SickGearShow):
    _help = {"desc": "display information for a given thetvdb.com show",
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
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearShow.__init__(self, handler, args, kwargs)


class CMD_SickGearShowAddExisting(ApiCall):
    _help = {"desc": "add a show in SickGear with an existing folder",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "indexer id of a show"},
                                    "location": {"desc": "full path to the existing folder for the show"}
             },
             "optionalParameters": {"initial": {"desc": "initial quality for the show"},
                                    "archive": {"desc": "archive quality for the show"},
                                    "upgrade_once": {"desc": "upgrade only once"},
                                    "flatten_folders": {"desc": "flatten subfolders for the show"},
                                    "subtitles": {"desc": "allow search episode subtitle"}
             }
    }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().search_indexers])
        self.location, args = self.check_params(args, kwargs, "location", None, True, "string", [])
        # optional
        self.initial, args = self.check_params(args, kwargs, "initial", None, False, "list", [q for q in quality_map])
        self.archive, args = self.check_params(args, kwargs, "archive", None, False, "list", [q for q in quality_map])
        self.upgradeonce, args = self.check_params(args, kwargs, "upgrade_once", False, False, "bool", [])

        self.flatten_folders, args = self.check_params(args, kwargs, "flatten_folders",
                                                       str(sickbeard.FLATTEN_FOLDERS_DEFAULT), False, "bool", [])
        self.subtitles, args = self.check_params(args, kwargs, "subtitles", int(sickbeard.USE_SUBTITLES), False, "int",
            [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ add a show in sickgear with an existing folder """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if showObj:
            return _responds(RESULT_FAILURE, msg="An existing indexerid already exists in the database")

        if not ek.ek(os.path.isdir, self.location):
            return _responds(RESULT_FAILURE, msg='Not a valid location')

        indexerName = None
        indexerResult = CMD_SickBeardSearchIndexers(self.handler, [],
                                                    {"indexerid": self.indexerid, "indexer": self.indexer}).run()

        if indexerResult['result'] == result_type_map[RESULT_SUCCESS]:
            if not indexerResult['data']['results']:
                return _responds(RESULT_FAILURE, msg="Empty results returned, check indexerid and try again")
            if len(indexerResult['data']['results']) == 1 and 'name' in indexerResult['data']['results'][0]:
                indexerName = indexerResult['data']['results'][0]['name']

        if not indexerName:
            return _responds(RESULT_FAILURE, msg="Unable to retrieve information from indexer")

        #use default quality as a failsafe
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

        sickbeard.showQueueScheduler.action.addShow(int(self.indexer), int(self.indexerid), self.location, SKIPPED,
                                                    newQuality, int(self.flatten_folders),
                                                    upgrade_once=self.upgradeonce)

        return _responds(RESULT_SUCCESS, {"name": indexerName}, indexerName + " has been queued to be added")


class CMD_ShowAddExisting(CMD_SickGearShowAddExisting):
    _help = {"desc": "add a show in sickgear with an existing folder",
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
        kwargs['indexer'] = INDEXER_TVDB
        # required
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
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().search_indexers])
        # optional
        self.location, args = self.check_params(args, kwargs, "location", None, False, "string", [])
        self.initial, args = self.check_params(args, kwargs, "initial", None, False, "list", [q for q in quality_map])
        self.archive, args = self.check_params(args, kwargs, "archive", None, False, "list", [q for q in quality_map])
        self.upgradeonce, args = self.check_params(args, kwargs, "upgrade_once", False, False, "bool", [])
        self.flatten_folders, args = self.check_params(args, kwargs, "flatten_folders",
                                                       str(sickbeard.FLATTEN_FOLDERS_DEFAULT), False, "bool", [])
        self.status, args = self.check_params(args, kwargs, "status", None, False, "string",
                                              ["wanted", "skipped", "archived", "ignored"])
        self.subtitles, args = self.check_params(args, kwargs, "subtitles", int(sickbeard.USE_SUBTITLES), False, "int",
            [])
        self.anime, args = self.check_params(args, kwargs, "anime", int(sickbeard.ANIME_DEFAULT), False, "int",
            [])
        self.scene, args = self.check_params(args, kwargs, "scene", int(sickbeard.SCENE_DEFAULT), False, "int",
            [])
        self.lang = 'en'

        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ add a show in sickgear with an existing folder """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if showObj:
            return _responds(RESULT_FAILURE, msg="An existing indexerid already exists in database")

        if not self.location:
            if sickbeard.ROOT_DIRS != "":
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
            #TODO: check if obsolete
            if not self.status in statusStrings.statusStrings:
                raise ApiError("Invalid Status")
            # only allow the status options we want
            if int(self.status) not in (3, 5, 6, 7):
                return _responds(RESULT_FAILURE, msg="Status prohibited")
            newStatus = self.status

        indexerName = None
        indexerResult = CMD_SickBeardSearchIndexers(self.handler, [],
                                                    {"indexerid": self.indexerid, "indexer": self.indexer}).run()

        if indexerResult['result'] == result_type_map[RESULT_SUCCESS]:
            if not indexerResult['data']['results']:
                return _responds(RESULT_FAILURE, msg="Empty results returned, check indexerid and try again")
            if len(indexerResult['data']['results']) == 1 and 'name' in indexerResult['data']['results'][0]:
                indexerName = indexerResult['data']['results'][0]['name']

        if not indexerName:
            return _responds(RESULT_FAILURE, msg="Unable to retrieve information from indexer")

        # moved the logic check to the end in an attempt to eliminate empty directory being created from previous errors
        showPath = ek.ek(os.path.join, self.location, helpers.sanitizeFileName(indexerName))

        # don't create show dir if config says not to
        if sickbeard.ADD_SHOWS_WO_DIR:
            logger.log(u"Skipping initial creation of " + showPath + " due to config.ini setting")
        else:
            dir_exists = helpers.makeDir(showPath)
            if not dir_exists:
                logger.log(u"API :: Unable to create the folder " + showPath + ", can't add the show", logger.ERROR)
                return _responds(RESULT_FAILURE, {"path": showPath},
                                 "Unable to create the folder " + showPath + ", can't add the show")
            else:
                helpers.chmodAsParent(showPath)

        sickbeard.showQueueScheduler.action.addShow(int(self.indexer), int(self.indexerid), showPath, newStatus,
                                                    newQuality,
                                                    int(self.flatten_folders), self.lang, self.subtitles, self.anime,
                                                    self.scene, new_show=True, upgrade_once=self.upgradeonce)  # @UndefinedVariable

        return _responds(RESULT_SUCCESS, {"name": indexerName}, indexerName + " has been queued to be added")


class CMD_ShowAddNew(CMD_SickGearShowAddNew):
    _help = {"desc": "add a new show to sickgear",
             "requiredParameters": {"tvdbid": {"desc": "thetvdb.com id"}
                                    },
             "optionalParameters": {"initial": {"desc": "initial quality for the show"},
                                    "location": {"desc": "base path for where the show folder is to be created"},
                                    "archive": {"desc": "archive quality for the show"},
                                    "flatten_folders": {"desc": "flatten subfolders for the show"},
                                    "status": {"desc": "status of missing episodes"},
                                    "lang": {"desc": "the 2 letter lang abbreviation id"},
                                    "subtitles": {"desc": "allow search episode subtitle"},
                                    "anime": {"desc": "set show to anime"},
                                    "scene": {"desc": "show searches episodes by scene numbering"}
                                    },
             "SickGearCommand": "sg.show.addnew",
            }

    valid_languages = {
        'el': 20, 'en': 7, 'zh': 27, 'it': 15, 'cs': 28, 'es': 16, 'ru': 22,
        'nl': 13, 'pt': 26, 'no': 9, 'tr': 21, 'pl': 18, 'fr': 17, 'hr': 31,
        'de': 14, 'da': 10, 'fi': 11, 'hu': 19, 'ja': 25, 'he': 24, 'ko': 32,
        'sv': 8, 'sl': 30}

    def __init__(self, handler, args, kwargs):
        kwargs['indexer'] = INDEXER_TVDB
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
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ check sickgear's cache to see if the banner or poster image for a show is valid """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        #TODO: catch if cache dir is missing/invalid.. so it doesn't break show/show.cache
        #return {"poster": 0, "banner": 0}

        cache_obj = image_cache.ImageCache()

        has_poster = 0
        has_banner = 0

        if ek.ek(os.path.isfile, cache_obj.poster_path(showObj.indexerid)):
            has_poster = 1
        if ek.ek(os.path.isfile, cache_obj.banner_path(showObj.indexerid)):
            has_banner = 1

        return _responds(RESULT_SUCCESS, {"poster": has_poster, "banner": has_banner})


class CMD_ShowCache(CMD_SickGearShowCache):
    _help = {"desc": "check sickgear's cache to see if the banner or poster image for a show is valid",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.cache",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowCache.__init__(self, handler, args, kwargs)


class CMD_SickGearShowDelete(ApiCall):
    _help = {"desc": "delete a show in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ delete a show in sickgear """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        if sickbeard.showQueueScheduler.action.isBeingAdded(
                showObj) or sickbeard.showQueueScheduler.action.isBeingUpdated(showObj):  #@UndefinedVariable
            return _responds(RESULT_FAILURE, msg="Show can not be deleted while being added or updated")

        showObj.deleteShow()
        return _responds(RESULT_SUCCESS, msg=str(showObj.name) + " has been deleted")


class CMD_ShowDelete(CMD_SickGearShowDelete):
    _help = {"desc": "delete a show in sickgear",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.delete",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowDelete.__init__(self, handler, args, kwargs)


class CMD_SickGearShowGetQuality(ApiCall):
    _help = {"desc": "get quality setting for a show in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get quality setting for a show in sickgear """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        anyQualities, bestQualities = _mapQuality(showObj.quality)

        data = {"initial": anyQualities, "archive": bestQualities}

        if not self.sickbeard_call:
            data['upgrade_once'] = showObj.upgrade_once

        return _responds(RESULT_SUCCESS, data)


class CMD_ShowGetQuality(CMD_SickGearShowGetQuality):
    _help = {"desc": "get quality setting for a show in sickgear",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.getquality",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = INDEXER_TVDB
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
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the poster for a show in sickgear """
        return {'outputType': 'image', 'image': self.handler.showPoster(self.indexerid, 'poster', True)}


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
        kwargs['indexer'] = INDEXER_TVDB
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
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the banner for a show in sickgear """
        return {'outputType': 'image', 'image': self.handler.showPoster(self.indexerid, 'banner', True)}


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
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowGetBanner.__init__(self, handler, args, kwargs)


class CMD_SickGearShowListFanart(ApiCall):
    _help = {"desc": "list the fanart's stored for a show in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ list the fanart's for a show in sickgear """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        fanart = []
        rating_names = {10: 'group', 20: 'favorite', 30: 'avoid'}
        cache_obj = image_cache.ImageCache()
        for img in ek.ek(glob.glob, cache_obj.fanart_path(showObj.indexerid).replace('fanart.jpg', '*')) or []:
            match = re.search(r'\.(\d+(?:\.(\w*?(\d*)))?\.(?:\w{5,8}))\.fanart\.', img, re.I)
            if match and match.group(1):
                fanart += [(match.group(1), rating_names.get(sickbeard.FANART_RATINGS.get(str(self.indexerid), {}).get(match.group(1), ''), ''))]

        return _responds(RESULT_SUCCESS, fanart)


class CMD_SickGearShowRateFanart(ApiCall):
    _help = {"desc": "rate the fanart's stored for a show in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    "fanartname": {"desc": "fanart name form sg.show.listfanart"},
                                    "rating": {"desc": "rate: unrate, group, favorite, avoid"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        self.fanartname, args = self.check_params(args, kwargs, "fanartname", None, True, "string", [])
        self.rating, args = self.check_params(args, kwargs, "rating", None, True, "string",
                                              ['unrate', 'group', 'favorite', 'avoid'])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ rate the fanart's for a show in sickgear """
        cache_obj = image_cache.ImageCache()
        fanartfile = cache_obj.fanart_path(self.indexerid).replace('fanart.jpg', '%s.fanart.jpg' % self.fanartname)
        if not ek.ek(os.path.isfile, fanartfile):
            return _responds(RESULT_FAILURE, msg='Unknown Fanart')
        fan_ratings = {'unrate': 0, 'group': 10, 'favorite': 20, 'avoid': 30}
        if 'unrate' == self.rating and str(self.indexerid) in sickbeard.FANART_RATINGS \
                and self.fanartname in sickbeard.FANART_RATINGS[str(self.indexerid)]:
            del sickbeard.FANART_RATINGS[str(self.indexerid)][self.fanartname]
        else:
            sickbeard.FANART_RATINGS[str(self.indexerid)][self.fanartname] = fan_ratings[self.rating]
        sickbeard.save_config()
        return _responds(RESULT_SUCCESS, msg='Rated Fanart: %s = %s' % (self.fanartname, self.rating))


class CMD_SickGearShowGetFanart(ApiCall):
    _help = {"desc": "get the fanart stored for a show in sickgear. X-Fanartname response header resturns Fanart name or default for not found",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"fanartname": {"desc": "fanart name form sg.show.listfanart"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.fanartname, args = self.check_params(args, kwargs, "fanartname", None, False, "string", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ get the fanart for a show in sickgear """
        cache_obj = image_cache.ImageCache()
        default_fanartfile = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick', 'images', 'trans.png')
        fanartfile = default_fanartfile
        used_fanart = 'default'
        if self.fanartname:
            fanartfile = cache_obj.fanart_path(self.indexerid).replace('fanart.jpg', '%s.fanart.jpg' % self.fanartname)
            if not ek.ek(os.path.isfile, fanartfile):
                fanartfile = default_fanartfile
                used_fanart = self.fanartname
        else:
            fanart = []
            for img in ek.ek(glob.glob, cache_obj.fanart_path(self.indexerid).replace('fanart.jpg', '*')) or []:
                if not ek.ek(os.path.isfile, img):
                    continue
                match = re.search(r'\.(\d+(?:\.(\w*?(\d*)))?\.(?:\w{5,8}))\.fanart\.', img, re.I)
                if match and match.group(1):
                    fanart += [(img, match.group(1), sickbeard.FANART_RATINGS.get(str(self.indexerid), {}).get(match.group(1), 0))]
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
    _help = {"desc": "set a show's paused state in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"pause": {"desc": "set the pause state of the show"}
                                    }
            }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.pause, args = self.check_params(args, kwargs, "pause", 0, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ set a show's paused state in sickgear """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        if self.pause:
            showObj.paused = 1
            return _responds(RESULT_SUCCESS, msg=str(showObj.name) + " has been paused")
        else:
            showObj.paused = 0
            return _responds(RESULT_SUCCESS, msg=str(showObj.name) + " has been unpaused")

        return _responds(RESULT_FAILURE, msg=str(showObj.name) + " was unable to be paused")


class CMD_ShowPause(CMD_SickGearShowPause):
    _help = {"desc": "set a show's paused state in sickgear",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "optionalParameters": {"pause": {"desc": "set the pause state of the show"}
                                    },
             "SickGearCommand": "sg.show.pause",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowPause.__init__(self, handler, args, kwargs)


class CMD_SickGearShowRefresh(ApiCall):
    _help = {"desc": "refresh a show in sickgear",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},},
            }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ refresh a show in sickgear """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        try:
            sickbeard.showQueueScheduler.action.refreshShow(showObj)  #@UndefinedVariable
            return _responds(RESULT_SUCCESS, msg=str(showObj.name) + " has queued to be refreshed")
        except exceptions.CantRefreshException:
            # TODO: log the excption
            return _responds(RESULT_FAILURE, msg="Unable to refresh " + str(showObj.name))


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
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowRefresh.__init__(self, handler, args, kwargs)


class CMD_SickGearShowSeasonList(ApiCall):
    _help = {"desc": "display the season list for a given show",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"sort": {"desc": "change the sort order from descending to ascending"}
                                    }
            }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.sort, args = self.check_params(args, kwargs, "sort", "desc", False, "string",
                                            ["asc", "desc"])  # "asc" and "desc" default and fallback is "desc"
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display the season list for a given show """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        myDB = db.DBConnection(row_type="dict")
        if self.sort == "asc":
            sqlResults = myDB.select("SELECT DISTINCT season FROM tv_episodes WHERE showid = ? AND indexer = ? "
                                     "ORDER BY season ASC",
                                     [self.indexerid, self.indexer])
        else:
            sqlResults = myDB.select("SELECT DISTINCT season FROM tv_episodes WHERE showid = ? AND indexer = ? "
                                     "ORDER BY season DESC",
                                     [self.indexerid, self.indexer])
        seasonList = []  # a list with all season numbers
        for row in sqlResults:
            seasonList.append(int(row["season"]))

        return _responds(RESULT_SUCCESS, seasonList)


class CMD_ShowSeasonList(CMD_SickGearShowSeasonList):
    _help = {"desc": "display the season list for a given show",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "optionalParameters": {"sort": {"desc": "change the sort order from descending to ascending"}
                                    },
             "SickGearCommand": "sg.show.seasonlist",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowSeasonList.__init__(self, handler, args, kwargs)


class CMD_SickGearShowSeasons(ApiCall):
    _help = {"desc": "display a listing of episodes for all or a given season",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             "optionalParameters": {"season": {"desc": "the season number"},
                                    }
            }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        self.season, args = self.check_params(args, kwargs, "season", None, False, "int", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display a listing of episodes for all or a given show """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        myDB = db.DBConnection(row_type="dict")

        if self.season == None:
            sqlResults = myDB.select("SELECT name, description, absolute_number, scene_absolute_number, episode, "
                                     "scene_episode, scene_season, airdate, status, season FROM tv_episodes "
                                     "WHERE showid = ? AND indexer = ?",
                                     [self.indexerid, self.indexer])
            seasons = {}
            for row in sqlResults:
                status, quality = Quality.splitCompositeStatus(int(row["status"]))
                row["status"] = _get_status_Strings(status)
                row["quality"] = _get_quality_string(quality)
                timezone, row['timezone'] = network_timezones.get_network_timezone(showObj.network, return_name=True)
                dtEpisodeAirs = sbdatetime.sbdatetime.convert_to_setting(network_timezones.parse_date_time(
                    row['airdate'], showObj.airs, timezone))
                row['airdate'] = sbdatetime.sbdatetime.sbfdate(dtEpisodeAirs, d_preset=dateFormat)
                row['scene_episode'] = helpers.tryInt(row['scene_episode'])
                row['scene_season'] = helpers.tryInt(row['scene_season'])
                row['absolute_number'] = helpers.tryInt(row['absolute_number'])
                row['scene_absolute_number'] = helpers.tryInt(row['scene_absolute_number'])
                curSeason = int(row["season"])
                curEpisode = int(row["episode"])
                del row["season"]
                del row["episode"]
                if not curSeason in seasons:
                    seasons[curSeason] = {}
                seasons[curSeason][curEpisode] = row

        else:
            sqlResults = myDB.select(
                "SELECT name, description, absolute_number, scene_absolute_number, episode, scene_episode, "
                "scene_season, airdate, status FROM tv_episodes WHERE showid = ? AND indexer = ? AND season = ?",
                [self.indexerid, self.indexer, self.season])
            if len(sqlResults) is 0:
                return _responds(RESULT_FAILURE, msg="Season not found")
            seasons = {}
            for row in sqlResults:
                curEpisode = int(row["episode"])
                del row["episode"]
                status, quality = Quality.splitCompositeStatus(int(row["status"]))
                row["status"] = _get_status_Strings(status)
                row["quality"] = _get_quality_string(quality)
                timezone, row['timezone'] = network_timezones.get_network_timezone(showObj.network, return_name=True)
                dtEpisodeAirs = sbdatetime.sbdatetime.convert_to_setting(network_timezones.parse_date_time(
                    row['airdate'], showObj.airs, timezone))
                row['airdate'] = sbdatetime.sbdatetime.sbfdate(dtEpisodeAirs, d_preset=dateFormat)
                row['scene_episode'] = helpers.tryInt(row['scene_episode'])
                row['scene_season'] = helpers.tryInt(row['scene_season'])
                row['absolute_number'] = helpers.tryInt(row['absolute_number'])
                row['scene_absolute_number'] = helpers.tryInt(row['scene_absolute_number'])
                if not curEpisode in seasons:
                    seasons[curEpisode] = {}
                seasons[curEpisode] = row

        return _responds(RESULT_SUCCESS, seasons)


class CMD_ShowSeasons(CMD_SickGearShowSeasons):
    _help = {"desc": "display a listing of episodes for all or a given season",
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
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowSeasons.__init__(self, handler, args, kwargs)


class CMD_SickGearShowSetQuality(ApiCall):
    _help = {
        "desc": "set desired quality of a show in sickgear. if neither initial or archive are provided then the config default quality will be used",
        "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                               "indexerid": {"desc": "unique id of a show"}
                              },
        "optionalParameters": {"initial": {"desc": "initial quality for the show"},
                               "archive": {"desc": "archive quality for the show"},
                               "upgrade_once": {"desc": "upgrade only once"}
                              }
            }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # this for whatever reason removes hdbluray not sdtv... which is just wrong. reverting to previous code.. plus we didnt use the new code everywhere.
        # self.archive, args = self.check_params(args, kwargs, "archive", None, False, "list", _getQualityMap().values()[1:])
        self.initial, args = self.check_params(args, kwargs, "initial", None, False, "list", [q for q in quality_map])
        self.archive, args = self.check_params(args, kwargs, "archive", None, False, "list", [q for q in quality_map])
        self.upgradeonce, args = self.check_params(args, kwargs, "upgrade_once", False, False, "bool", [])
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ set the quality for a show in sickgear by taking in a deliminated
            string of qualities, map to their value and combine for new values
        """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        #use default quality as a failsafe
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
        showObj.quality = newQuality

        showObj.upgrade_once = self.upgradeonce

        showObj.saveToDB()

        return _responds(RESULT_SUCCESS,
                         msg=showObj.name + " quality has been changed to " + _get_quality_string(showObj.quality))


class CMD_ShowSetQuality(CMD_SickGearShowSetQuality):
    _help = {
        "desc": "set desired quality of a show in sickgear. if neither initial or archive are provided then the config default quality will be used",
        "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"}
                              },
        "optionalParameters": {"initial": {"desc": "initial quality for the show"},
                               "archive": {"desc": "archive quality for the show"}
                              },
        "SickGearCommand": "sg.show.setquality",
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help

        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowSetQuality.__init__(self, handler, args, kwargs)


class CMD_SickGearShowStats(ApiCall):
    _help = {"desc": "display episode statistics for a given show",
             "requiredParameters": {"indexer": {"desc": "indexer of a show"},
                                    "indexerid": {"desc": "unique id of a show"},
                                    },
             }

    def __init__(self, handler, args, kwargs):
        # required
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display episode statistics for a given show """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        # show stats
        episode_status_counts_total = {}
        episode_status_counts_total["total"] = 0
        for status in statusStrings.statusStrings.keys():
            if status in SNATCHED_ANY + [UNKNOWN, DOWNLOADED]:
                continue
            episode_status_counts_total[status] = 0

        # add all the downloaded qualities
        episode_qualities_counts_download = {}
        episode_qualities_counts_download["total"] = 0
        for statusCode in Quality.DOWNLOADED:
            status, quality = Quality.splitCompositeStatus(statusCode)
            if quality in [Quality.NONE]:
                continue
            episode_qualities_counts_download[statusCode] = 0

        # add all snatched qualities
        episode_qualities_counts_snatch = {}
        episode_qualities_counts_snatch["total"] = 0
        for statusCode in Quality.SNATCHED_ANY:
            status, quality = Quality.splitCompositeStatus(statusCode)
            if quality in [Quality.NONE]:
                continue
            episode_qualities_counts_snatch[statusCode] = 0

        myDB = db.DBConnection(row_type="dict")
        sqlResults = myDB.select("SELECT status, season FROM tv_episodes WHERE season != 0 AND showid = ? "
                                 "AND indexer = ?",
                                 [self.indexerid, self.indexer])
        # the main loop that goes through all episodes
        for row in sqlResults:
            status, quality = Quality.splitCompositeStatus(int(row["status"]))

            episode_status_counts_total["total"] += 1

            if status in Quality.DOWNLOADED:
                episode_qualities_counts_download["total"] += 1
                episode_qualities_counts_download[int(row["status"])] += 1
            elif status in Quality.SNATCHED_ANY:
                episode_qualities_counts_snatch["total"] += 1
                episode_qualities_counts_snatch[int(row["status"])] += 1
            elif status == 0:  # we dont count NONE = 0 = N/A
                pass
            else:
                episode_status_counts_total[status] += 1

        # the outgoing container
        episodes_stats = {}
        episodes_stats["downloaded"] = {}
        # truning codes into strings
        for statusCode in episode_qualities_counts_download:
            if statusCode == "total":
                episodes_stats["downloaded"]["total"] = episode_qualities_counts_download[statusCode]
                continue
            status, quality = Quality.splitCompositeStatus(int(statusCode))
            statusString = Quality.qualityStrings[quality].lower().replace(" ", "_").replace("(", "").replace(")", "")
            episodes_stats["downloaded"][statusString] = episode_qualities_counts_download[statusCode]

        episodes_stats["snatched"] = {}
        # truning codes into strings
        # and combining proper and normal
        for statusCode in episode_qualities_counts_snatch:
            if statusCode == "total":
                episodes_stats["snatched"]["total"] = episode_qualities_counts_snatch[statusCode]
                continue
            status, quality = Quality.splitCompositeStatus(int(statusCode))
            statusString = Quality.qualityStrings[quality].lower().replace(" ", "_").replace("(", "").replace(")", "")
            if Quality.qualityStrings[quality] in episodes_stats["snatched"]:
                episodes_stats["snatched"][statusString] += episode_qualities_counts_snatch[statusCode]
            else:
                episodes_stats["snatched"][statusString] = episode_qualities_counts_snatch[statusCode]

        #episodes_stats["total"] = {}
        for statusCode in episode_status_counts_total:
            if statusCode == "total":
                episodes_stats["total"] = episode_status_counts_total[statusCode]
                continue
            status, quality = Quality.splitCompositeStatus(int(statusCode))
            statusString = statusStrings.statusStrings[statusCode].lower().replace(" ", "_").replace("(", "").replace(
                ")", "")
            episodes_stats[statusString] = episode_status_counts_total[statusCode]

        return _responds(RESULT_SUCCESS, episodes_stats)


class CMD_ShowStats(CMD_SickGearShowStats):
    _help = {"desc": "display episode statistics for a given show",
             "requiredParameters": {"indexerid": {"desc": "thetvdb.com id of a show"},
                                    },
             "SickGearCommand": "sg.show.stats",
             }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        kwargs['indexer'] = INDEXER_TVDB
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
        self.indexer, args = self.check_params(args, kwargs, "indexer", None, True, "int",
                                               [i for i in indexer_api.indexerApi().search_indexers])
        self.indexerid, args = self.check_params(args, kwargs, "indexerid", None, True, "int", [])
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ update a show in sickgear """
        showObj = helpers.find_show_by_id(sickbeard.showList, {self.indexer: self.indexerid})
        if not showObj:
            return _responds(RESULT_FAILURE, msg="Show not found")

        try:
            sickbeard.showQueueScheduler.action.updateShow(showObj, True)  #@UndefinedVariable
            return _responds(RESULT_SUCCESS, msg=str(showObj.name) + " has queued to be updated")
        except exceptions.CantUpdateException as e:
            logger.log(u"API:: Unable to update " + str(showObj.name) + ". " + str(ex(e)), logger.ERROR)
            return _responds(RESULT_FAILURE, msg="Unable to update " + str(showObj.name))


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
        kwargs['indexer'] = INDEXER_TVDB
        self.sickbeard_call = True
        CMD_SickGearShowUpdate.__init__(self, handler, args, kwargs)


class CMD_SickGearShows(ApiCall):
    _help = {"desc": "display all shows in sickgear",
             "optionalParameters": {"sort": {"desc": "sort the list of shows by show name instead of indexerid"},
                                    "paused": {"desc": "only show the shows that are set to paused"},
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
        """ display_is_int_multi( self.indexerid )shows in sickgear """
        shows = {}

        for curShow in sickbeard.showList:

            if self.sickbeard_call and INDEXER_TVDB != curShow.indexer:
                continue

            if self.paused is not None and bool(self.paused) != bool(curShow.paused):
                continue

            showDict = {
                "paused": curShow.paused,
                "quality": _get_quality_string(curShow.quality),
                "language": curShow.lang,
                "air_by_date": curShow.air_by_date,
                "sports": curShow.sports,
                "anime": curShow.anime,
                "indexerid": curShow.indexerid,
                "indexer": curShow.indexer,
                "tvdbid": curShow.ids.get(INDEXER_TVDB , {'id': 0})['id'],
                'ids': {k: v.get('id') for k, v in curShow.ids.iteritems()},
                "tvrage_id": curShow.ids.get(INDEXER_TVRAGE, {'id': 0})['id'],
                "tvrage_name": curShow.name,
                "network": curShow.network,
                "show_name": curShow.name,
                "status": curShow.status,
                "subtitles": curShow.subtitles,
                "scenenumbering": curShow.is_scene,
                "upgrade_once": curShow.upgrade_once,
                "ignorewords": curShow.rls_ignore_words,
                "requirewords": curShow.rls_require_words,
                "tag": curShow.tag,
                "imdb_id": curShow.imdbid,
                "classification": curShow.classification,
                "runtime": curShow.runtime,
                "startyear": curShow.startyear,
            }

            if self.overview:
                showDict["overview"] = curShow.overview

            timezone, showDict['timezone'] = network_timezones.get_network_timezone(showDict['network'],
                                                                                    return_name=True)

            if curShow.nextaired:
                dtEpisodeAirs = sbdatetime.sbdatetime.convert_to_setting(network_timezones.parse_date_time(
                    curShow.nextaired, curShow.airs, timezone))
                showDict['next_ep_airdate'] = sbdatetime.sbdatetime.sbfdate(dtEpisodeAirs, d_preset=dateFormat)
            else:
                showDict['next_ep_airdate'] = ''

            showDict["cache"] = CMD_ShowCache(self.handler, (), {"indexerid": curShow.indexerid}).run()["data"]
            if not showDict["network"]:
                showDict["network"] = ""
            if self.sort == "name":
                shows[curShow.name] = showDict
            else:
                shows[curShow.indexerid] = showDict

        return _responds(RESULT_SUCCESS, shows)


class CMD_Shows(CMD_SickGearShows):
    _help = {"desc": "display all thetvdb.com shows in sickgear",
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
                                                        "see sg.listtraktaccounts"},
                                    },
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
                'newshows': '/calendars/all/shows/new/%s/%s?' % (sbdatetime.sbdatetime.sbfdate(
                        dt=datetime.datetime.now() + datetime.timedelta(days=-16), d_preset='%Y-%m-%d'), 32),
                'newseasons': '/calendars/all/shows/premieres/%s/%s?' % (sbdatetime.sbdatetime.sbfdate(
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
            urls['watchlist'] = 'users/%s/watchlist/shows?limit=%s&' % (sickbeard.TRAKT_ACCOUNTS[self.account].slug, 100)
        try:
            data, oldest, newest = NewHomeAddShows.get_trakt_data(urls[self.type], **kwargs)
        except Exception as e:
            return _responds(RESULT_FAILURE, msg=e.message)
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
        accounts = [{'name': v.name, 'account_id': v.account_id} for a, v in sickbeard.TRAKT_ACCOUNTS.iteritems()]
        return _responds(RESULT_SUCCESS, accounts)


class CMD_SickGearShowsForceUpdate(ApiCall):
    _help = {"desc": "force the daily show update now."}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ force the daily show update now """
        if sickbeard.showQueueScheduler.action.isShowUpdateRunning() or sickbeard.showUpdateScheduler.action.amActive:
            return _responds(RESULT_FAILURE, msg="show update already running.")

        result = sickbeard.showUpdateScheduler.forceRun()
        if result:
            return _responds(RESULT_SUCCESS, msg="daily show update started")
        return _responds(RESULT_FAILURE, msg="can't start show update currently")


class CMD_SickGearShowsQueue(ApiCall):
    _help = {"desc": "list the show update queue."}

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ list the show update queue """
        return _responds(RESULT_SUCCESS, sickbeard.showQueueScheduler.action.queue_length())


class CMD_SickGearShowsStats(ApiCall):
    _help = {"desc": "display the global shows and episode stats"
            }

    def __init__(self, handler, args, kwargs):
        # required
        # optional
        # super, missing, help
        ApiCall.__init__(self, handler, args, kwargs)

    def run(self):
        """ display the global shows and episode stats """
        stats = {}

        indexer_limit = ('', ' AND indexer = %s' % INDEXER_TVDB)[self.sickbeard_call]
        myDB = db.DBConnection()
        today = str(datetime.date.today().toordinal())
        stats["shows_total"] = (len(sickbeard.showList),
                                len([x for x in sickbeard.showList if x.indexer == INDEXER_TVDB]))[self.sickbeard_call]
        stats["shows_active"] = len(
            [show for show in sickbeard.showList if show.paused == 0 and show.status != "Ended"
             and (not self.sickbeard_call or show.indexer == INDEXER_TVDB)])
        stats["ep_downloaded"] = myDB.select("SELECT COUNT(*) FROM tv_episodes WHERE status IN (" + ",".join(
            [str(show) for show in
             Quality.DOWNLOADED + Quality.ARCHIVED]) + ") AND season != 0 and episode != 0 AND airdate <= " + today +
                                             indexer_limit)[0][0]
        stats["ep_total"] = myDB.select(
            "SELECT COUNT(*) FROM tv_episodes WHERE season != 0 AND episode != 0 AND (airdate != 1 OR status IN (" + ",".join(
                [str(show) for show in Quality.SNATCHED_ANY + Quality.DOWNLOADED + Quality.ARCHIVED]) +
            ")) AND airdate <= " + today + " AND status != " + str(IGNORED) + indexer_limit)[0][0]

        return _responds(RESULT_SUCCESS, stats)

# WARNING: never define a cmd call string that contains a "_" (underscore)
class CMD_ShowsStats(CMD_SickGearShowsStats):
    _help = {"desc": "display the global thetvdb.com shows and episode stats",
             "SickGearCommand": "sg.shows.stats",
             }
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
                  "sg.logs": CMD_Logs,
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
                  "sg.setscenenumber": CMD_SickGearSetSceneNumber,
                  "sg.activatescenenumbering": CMD_SickGearActivateSceneNumber,
                  "sg.getindexers": CMD_SickGearGetIndexers,
                  "sg.getindexericon": CMD_SickGearGetIndexerIcon,
                  "sg.getnetworkicon": CMD_SickGearGetNetworkIcon,
                  "sb.shutdown": CMD_SickBeardShutdown,
                  "sg.listignorewords": CMD_SickGearListIgnoreWords,
                  "sg.setignorewords": CMD_SickGearSetIgnoreWords,
                  "sg.listrequiredwords": CMD_SickGearListRequireWords,
                  "sg.setrequiredwords": CMD_SickGearSetRequrieWords,
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
