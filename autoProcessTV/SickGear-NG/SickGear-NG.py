#!/usr/bin/env python
#
# ##############################################################################
# ##############################################################################
#
# SickGear Process Media extension for NZBGet
# ===========================================
#
# If NZBGet v17+ is installed on the same system as SickGear then as a local install,
#
# 1) Add the location of this extension to NZBGet Settings/PATHS/ScriptDir
#
# 2) Navigate to any named TV category at Settings/Categories, click "Choose" Category.Extensions then Apply SickGear-NG
#
# This is the best set up to automatically get script updates from SickGear
#
# #############
#
# NZBGet version 16 and earlier are no longer supported, please upgrade
#
# ############
#
# Notes:
# Debian doesn't have pip, _if_ requests is needed, try "apt install python-requests"
# -----
# Enjoy
#
# ##############################################################################
# ##############################################################################
#
# Copyright (C) 2016 SickGear Developers
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

##############################################################################
### NZBGET QUEUE/POST-PROCESSING SCRIPT                                    ###
### QUEUE EVENTS: NZB_ADDED, NZB_DELETED, URL_COMPLETED, NZB_MARKED        ###

# Send "Process Media" requests to SickGear
#
# Process Media extension version: 2.7.
# <!--
# For more info and updates please visit forum topic at
# -->
# <span style="display:block;position:absolute;right:20px;top:105px;width:138px;height:74px;background:url(https://raw.githubusercontent.com/SickGear/SickGear/master/gui/slick/images/sickgear.png)"></span>
# <span id="steps-btn" style="display:inline-block;margin-top:10px;padding:5px 10px;cursor:pointer" class="label label-important" onclick="var steps$ = $('#setup-steps'), isShown=-1 !== $('#steps-btn').html().search('View'), ngVersion = parseInt(/^\d+/.exec(Options.option('version'))[0], 10); $('#ng-version').html('v'+ngVersion); (16 < ngVersion) && $('#sgng-newer').show() || $('#sgng-older').show() && $('#sgng-step2').hide(); !isShown ? steps$.hide() && $(this).html('View setup guide') && $(this).removeClass('label-info') && $(this).addClass('label-important'): steps$.show() && $(this).html('Hide setup guide') && $(this).removeClass('label-important') && $(this).addClass('label-info'); return !1;">View setup guide</span>
# <span id="setup-steps" style="display:none;color:#666">
# <span style="display:block;padding:7px 4px;margin-top:3px;background-color:#efefef;border:1px solid #ccc;-webkit-border-radius:3px;-moz-border-radius:3px;border-radius:3px">
# <span style="width:1em;float:left;padding:3px 0 0 3px">
# <span class="label label-important">1</span>
# </span>
# <span style="display:block;margin-left:1.75em;padding:3px 3px 3px 0">
# <span id="sgng-newer" style="display:none">
# With this <span style="font-weight:bold">NZBGet <span id="ng-version"></span></span> installed on the same system as SickGear,
# add the location of this extension to NZBGet Settings/PATHS/ScriptDir
# </span>
# <span id="sgng-older" style="display:none">
# <!-- if python <a href="https://pypi.python.org/pypi/requests" title="requests library page" target="_blank">requests library</a>
# is not installed, then <strong style="font-weight:bold;color:#128D12 !important">sg_base_path</strong> must be set -->
# NZBGet 17.0 or later required, please upgrade.
# </span>
# </span>
# </span>
# <span id="sgng-step2">
# <span style="display:block;padding:7px 4px;margin-top:3px;background-color:#efefef;border:1px solid #ccc;-webkit-border-radius:3px;-moz-border-radius:3px;border-radius:3px">
# <span style="width:1em;float:left;padding:3px 0 0 3px">
# <span class="label label-important">2</span>
# </span>
# <span style="display:block;margin-left:1.75em;padding-left: 0">
# For a TV Category at NZBGet Settings/CATEGORIES, click <span class="btn" style="vertical-align:text-bottom;padding:1px 5px 0;line-height:16px">Choose</span>, enable "<span style="color:#222">SickGear-NG</span>", apply, save all changes, and reload NZBGet
# </span>
# </span> <!-- /sgng-step2 -->
# </span>
# </span> <!-- /setup-steps -->
##############################################################################
### OPTIONS                                                                ###
#
#Test connection@Test SickGear connection
#
# <!-- commented out as no longer supported
# <span class="label label-info">
# Optional</span>
# SickGear <span style="font-weight:bold;color:#128D12 !important">base installation path</span>.
# use where NZBGet v16 or older is installed on the same system as SickGear, and no python requests library is installed
# (use "pip list" to check installed modules)
# #sg_base_path=
# -->

# <span class="label label-info">
# Optional</span>
# SickGear server ipaddress [default:127.0.0.1 aka localhost].
# change if SickGear is not installed on the same localhost as NZBGet
#sg_host=localhost

# <span class="label label-info">
# Optional</span>
# SickGear HTTP Port [default:8081] (1025-65535).
#sg_port=8081

# <span class="label label-info">
# Optional</span>
# SickGear Username.
#sg_username=

# <span class="label label-info">
# Optional</span>
# SickGear Password.
#sg_password=

# <span class="label label-info">
# Optional</span>
# SickGear has SSL enabled [default:No] (yes, no).
#sg_ssl=no

# <span class="label label-warning">
# Advanced use</span>
# SickGear Web Root.
# change if using a custom SickGear web_root setting (e.g. for a reverse proxy)
#sg_web_root=

# <span class="label label-info">
# Optional</span>
# Print more logging messages [default:No] (yes, no).
# For debugging or if you need to report a bug.
#sg_verbose=no

### NZBGET QUEUE/POST-PROCESSING SCRIPT                                    ###
##############################################################################
import locale
import os
import re
import sys
import warnings

# set the version number in the comments above (the old __version__ var is deprecated)
with open(os.path.join(os.path.dirname(__file__), __file__)) as fp:
    __version__ = (
        re.compile(r""".*version: (\d+\.\d+)""", re.S).match(fp.read()).group(1)
    )

PY2 = 2 == sys.version_info[0]

if not PY2:
    string_types = str,
    binary_type = bytes
    text_type = str

    def iteritems(d, **kw):
        return iter(d.items(**kw))
else:
    # noinspection PyUnresolvedReferences,PyCompatibility
    string_types = basestring,
    binary_type = str
    # noinspection PyUnresolvedReferences
    text_type = unicode

    def iteritems(d, **kw):
        # noinspection PyCompatibility
        return d.iteritems(**kw)

verbose = 0 or 'yes' == os.environ.get('NZBPO_SG_VERBOSE', 'no')

warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')
warnings.filterwarnings('ignore', module=r'.*ssl_.*', message='.*SSLContext object.*')

# NZBGet exit codes for post-processing scripts (Queue-scripts don't have any special exit codes).
POSTPROCESS_SUCCESS, POSTPROCESS_ERROR, POSTPROCESS_NONE = 93, 94, 95

failed = False

# define minimum dir size, downloads under this size will be handled as failure
min_dir_size = 20 * 1024 * 1024


class Logger(object):
    INFO, DETAIL, ERROR, WARNING = 'INFO', 'DETAIL', 'ERROR', 'WARNING'
    # '[NZB]' send a command message to NZBGet (no log)
    NZB = 'NZB'

    def __init__(self):
        pass

    @staticmethod
    def decode_str(s, encoding='utf-8', errors=None):
        if isinstance(s, binary_type):
            if None is errors:
                return s.decode(encoding)
            return s.decode(encoding, errors)
        return s

    @staticmethod
    def safe_print(msg_type, message):
        if not PY2:
            print('[%s] %s' % (msg_type, Logger.decode_str(message, encoding=SYS_ENCODING, errors='replace')))
        else:
            try:
                print('[%s] %s' % (msg_type, message.encode(SYS_ENCODING)))
            except (BaseException, Exception):
                try:
                    print('[%s] %s' % (msg_type, message))
                except (BaseException, Exception):
                    try:
                        print('[%s] %s' % (msg_type, repr(message)))
                    except (BaseException, Exception):
                        pass

    @staticmethod
    def log(message, msg_type=INFO):
        size = 900
        if size > len(message):
            Logger.safe_print(msg_type, message)
        else:
            for group in [message[pos:pos + size] for pos in range(0, len(message), size)]:
                Logger.safe_print(msg_type, group)


class EnvVar(object):
    def __init__(self):
        pass

    def __getitem__(self, key):
        return os.environ[key]

    @staticmethod
    def get(key, default=None):
        return os.environ.get(key, default)


if not PY2:
    env_var = EnvVar()

elif 'nt' == os.name:
    from ctypes import windll, create_unicode_buffer

    # noinspection PyCompatibility
    class WinEnvVar(EnvVar):

        @staticmethod
        def get_environment_variable(name):
            name = text_type(name)  # ensures string argument is unicode
            n = windll.kernel32.GetEnvironmentVariableW(name, None, 0)
            env_value = None
            if n:
                buf = create_unicode_buffer(u'\0' * n)
                windll.kernel32.GetEnvironmentVariableW(name, buf, n)
                env_value = buf.value
            verbose and Logger.log('Get var(%s) = %s' % (name, env_value or n))
            return env_value

        def __getitem__(self, key):
            return self.get_environment_variable(key)

        def get(self, key, default=None):
            r = self.get_environment_variable(key)
            return r if None is not r else default

    env_var = WinEnvVar()
else:
    class LinuxEnvVar(EnvVar):
        # noinspection PyMissingConstructor
        def __init__(self, environ):
            self.environ = environ

        def __getitem__(self, key):
            v = self.environ.get(key)
            try:
                return v if not isinstance(v, str) else v.decode(SYS_ENCODING)
            except (UnicodeDecodeError, UnicodeEncodeError):
                return v

        def get(self, key, default=None):
            v = self[key]
            return v if None is not v else default

    env_var = LinuxEnvVar(os.environ)


SYS_ENCODING = None
try:
    locale.setlocale(locale.LC_ALL, '')
except (locale.Error, IOError):
    pass
try:
    SYS_ENCODING = locale.getpreferredencoding()
except (locale.Error, IOError):
    pass
if not SYS_ENCODING or SYS_ENCODING in ('ANSI_X3.4-1968', 'US-ASCII', 'ASCII'):
    SYS_ENCODING = 'UTF-8'


verbose and Logger.log('%s(%s) env dump = %s' % (('posix', 'nt')['nt' == os.name], SYS_ENCODING, os.environ))


# noinspection PyCompatibility
class Ek(object):
    def __init__(self):
        pass

    @staticmethod
    def fix_string_encoding(x):
        if not PY2:
            return x

        if str == type(x):
            try:
                return x.decode(SYS_ENCODING)
            except UnicodeDecodeError:
                pass
        elif text_type == type(x):
            return x

    @staticmethod
    def fix_out_encoding(x):
        if PY2 and isinstance(x, string_types):
            return Ek.fix_string_encoding(x)
        return x

    @staticmethod
    def fix_list_encoding(x):
        if not PY2:
            return x

        if type(x) not in (list, tuple):
            return x
        return filter(lambda i: None is not i, map(Ek.fix_out_encoding, x))

    @staticmethod
    def encode_item(x):
        if not PY2:
            return x

        try:
            return x.encode(SYS_ENCODING)
        except UnicodeEncodeError:
            return x.encode(SYS_ENCODING, 'ignore')

    @staticmethod
    def win_encode_unicode(x):
        if PY2 and isinstance(x, str):
            try:
                return x.decode('UTF-8')
            except UnicodeDecodeError:
                pass
        return x

    @staticmethod
    def ek(func, *args, **kwargs):
        if not PY2:
            return func(*args, **kwargs)

        if 'nt' == os.name:
            # convert all str parameter values to unicode
            args = tuple([x if not isinstance(x, str) else Ek.win_encode_unicode(x) for x in args])
            kwargs = {k: x if not isinstance(x, str) else Ek.win_encode_unicode(x) for k, x in iteritems(kwargs)}
            func_result = func(*args, **kwargs)
        else:
            func_result = func(*[Ek.encode_item(x) if type(x) == str else x for x in args], **kwargs)

        if type(func_result) in (list, tuple):
            return Ek.fix_list_encoding(func_result)
        elif str == type(func_result):
            return Ek.fix_string_encoding(func_result)
        return func_result


def long_path(path):
    """add long path prefix for Windows"""
    if 'win32' == sys.platform and 260 < len(path) and not path.startswith('\\\\?\\') and Ek.ek(os.path.isabs, path):
        return '\\\\?\\' + path
    return path


def ex(e):
    """Returns a unicode string from the exception text if it exists"""

    if not PY2:
        return str(e)

    e_message = u''

    if not e or not e.args:
        return e_message

    for arg in e.args:

        if None is not arg:
            if isinstance(arg, (str, text_type)):
                fixed_arg = Ek.fix_string_encoding(arg)

            else:
                try:
                    fixed_arg = u'error ' + Ek.fix_string_encoding(str(arg))

                except (BaseException, Exception):
                    fixed_arg = None

            if fixed_arg:
                if not e_message:
                    e_message = fixed_arg

                else:
                    e_message = e_message + ' : ' + fixed_arg

    return e_message


# Depending on the mode in which the script was called (queue-script NZBNA_DELETESTATUS
# or post-processing-script) a different set of parameters (env. vars)
# is passed. They also have different prefixes:
#   - NZBNA in queue-script mode;
#   - NZBPP in pp-script mode.
env_run_mode = ('PP', 'NA')['NZBNA_EVENT' in os.environ]


def nzbget_var(name, default='', namespace=env_run_mode):
    return env_var.get('NZB%s_%s' % (namespace, name), default)


def nzbget_opt(name, default=''):
    return nzbget_var(name, default, 'OP')


def nzbget_plugin_opt(name, default=''):
    return nzbget_var('SG_%s' % name, default, 'PO')


sg_path = nzbget_plugin_opt('BASE_PATH')
if not sg_path or not Ek.ek(os.path.isdir, sg_path):
    try:
        script_path = Ek.ek(os.path.dirname, __file__)
        sg_path = Ek.ek(os.path.dirname, Ek.ek(os.path.dirname, script_path))
    except (BaseException, Exception):
        pass
if sg_path and Ek.ek(os.path.isdir, Ek.ek(os.path.join, sg_path, 'lib')):
    sys.path.insert(1, Ek.ek(os.path.join, sg_path, 'lib'))


try:
    import requests
except ImportError:
    # Logger.log('You must set SickGear sg_base_path in script config or install python requests library', Logger.ERROR)
    Logger.log('You must install python requests library', Logger.ERROR)
    sys.exit(1)


def get_size(start_path='.'):
    if Ek.ek(os.path.isfile, long_path(start_path)):
        return Ek.ek(os.path.getsize, long_path(start_path))
    total_size = 0
    for dirpath, dirnames, filenames in Ek.ek(os.walk, long_path(start_path)):
        for f in filenames:
            if not f.lower().endswith(('.nzb', '.jpg', '.jpeg', '.gif', '.png', '.tif', '.nfo', '.txt', '.srt', '.sub',
                                       '.sbv', '.idx', '.bat', '.sh', '.exe', '.pdf')):
                fh = Ek.ek(os.path.join, long_path(dirpath), f)
                total_size += Ek.ek(os.path.getsize, long_path(fh))
    return total_size


def try_int(s, s_default=0):
    try:
        return int(s)
    except (BaseException, Exception):
        return s_default


def try_float(s, s_default=0):
    try:
        return float(s)
    except (BaseException, Exception):
        return s_default


class ExitReason(object):
    def __init__(self):
        pass
    PP_SUCCESS = 0
    FAIL_SUCCESS = 1
    MARKED_BAD_SUCCESS = 2
    DELETED = 5
    SAME_DUPEKEY = 10
    UNFINISHED_DOWNLOAD = 11
    NONE = 20
    NONE_SG = 21
    PP_ERROR = 25
    FAIL_ERROR = 26
    MARKED_BAD_ERROR = 27


def script_exit(status, reason, runmode=None):
    Logger.log('NZBPR_SICKGEAR_PROCESSED=%s_%s_%s' % (status, runmode or env_run_mode, reason), Logger.NZB)
    sys.exit(status)


def get_old_status():
    old_status = env_var.get('NZBPR_SICKGEAR_PROCESSED', '')
    status_regex = re.compile(r'(\d+)_(\w\w)_(\d+)')
    if old_status and None is not status_regex.search(old_status):
        s = status_regex.match(old_status)
        return try_int(s.group(1)), s.group(2), try_int(s.group(3))
    return POSTPROCESS_NONE, env_run_mode, ExitReason.NONE


markbad = 'NZB_MARKED' == env_var.get('NZBNA_EVENT') and 'BAD' == env_var.get('NZBNA_MARKSTATUS')

good_statuses = [(POSTPROCESS_SUCCESS, 'PP', ExitReason.FAIL_SUCCESS),  # successfully failed pp'ed
                 (POSTPROCESS_SUCCESS, 'NA', ExitReason.FAIL_SUCCESS),  # queue, successfully failed sent
                 (POSTPROCESS_SUCCESS, 'NA', ExitReason.MARKED_BAD_SUCCESS)]  # queue, mark bad+successfully failed sent

if not markbad:
    good_statuses.append((POSTPROCESS_SUCCESS, 'PP', ExitReason.PP_SUCCESS))  # successfully pp'ed


# Start up checks
def start_check():

    # Check if the script is called from a compatible NZBGet version (as queue-script or as pp-script)
    nzbget_version = re.search(r'^(\d+\.\d+)', nzbget_opt('VERSION', '0.1'))
    nzbget_version = nzbget_version.group(1) if nzbget_version and 1 <= len(nzbget_version.groups()) else '0.1'
    nzbget_version = try_float(nzbget_version)
    if 17 > nzbget_version:
        Logger.log('This script is designed to be called from NZBGet 17.0 or later.')
        sys.exit(0)

    if 'NZB_ADDED' == env_var.get('NZBNA_EVENT'):
        Logger.log('NZBPR_SICKGEAR_PROCESSED=', Logger.NZB)  # reset var in case of Download Again
        sys.exit(0)

    # This script processes only certain queue events.
    # For compatibility with newer NZBGet versions it ignores event types it doesn't know
    if env_var.get('NZBNA_EVENT') not in ['NZB_DELETED', 'URL_COMPLETED', 'NZB_MARKED', None]:
        sys.exit(0)

    if 'NZB_MARKED' == env_var.get('NZBNA_EVENT') and 'BAD' != env_var.get('NZBNA_MARKSTATUS'):
        Logger.log('Marked as [%s], nothing to do, exiting' % env_var.get('NZBNA_MARKSTATUS', ''))
        sys.exit(0)

    old_exit_status = get_old_status()
    if old_exit_status in good_statuses and not (
            ExitReason.FAIL_SUCCESS == old_exit_status[2] and 'SUCCESS' == nzbget_var('TOTALSTATUS')):
        Logger.log('Found result from a previous completed run, exiting')
        script_exit(old_exit_status[0], old_exit_status[2], old_exit_status[1])

    # If called via "Post-process again" from history details dialog the download may not exist anymore
    if 'NZBNA_EVENT' not in os.environ and 'NZBPP_DIRECTORY' in os.environ:
        directory = nzbget_var('DIRECTORY')
        if not directory or not Ek.ek(os.path.exists, long_path(directory)):
            Logger.log('No files for postprocessor, look back in your NZBGet logs if required, exiting')
            script_exit(POSTPROCESS_NONE, ExitReason.NONE)


def call_nzbget_direct(url_command):
    # Connect to NZBGet and call an RPC-API method without using python's XML-RPC which is slow for large amount of data
    # First we need connection info: host, port and password of NZBGet server, NZBGet passes configuration options to
    # scripts using environment variables
    host, port, username, password = [nzbget_opt('CONTROL%s' % name) for name in ('IP', 'PORT', 'USERNAME', 'PASSWORD')]
    url = 'http://%s:%s/jsonrpc/%s' % ((host, '127.0.0.1')['0.0.0.0' == host], port, url_command)

    try:
        response = requests.get(url, auth=(username, password))
    except requests.RequestException:
        return ''

    return response.text if response.ok else ''


# noinspection DuplicatedCode
def call_sickgear(nzb_name, dir_name, test=False):

    global failed
    ssl, host, port, username, password, webroot = [nzbget_plugin_opt(name, default) for name, default in
                                                    (('SSL', 'no'), ('HOST', 'localhost'), ('PORT', '8081'),
                                                    ('USERNAME', ''), ('PASSWORD', ''), ('WEB_ROOT', ''))]
    protocol = 'http%s://' % ('', 's')['yes' == ssl]
    webroot = any(webroot) and '/%s' % webroot.strip('/') or ''
    url = '%s%s:%s%s/home/process-media/files' % (protocol, host, port, webroot)

    dupescore = nzbget_var('DUPESCORE')
    dupekey = nzbget_var('DUPEKEY')
    nzbid = nzbget_var('NZBID')
    params = {'dir_name': dir_name, 'nzb_name': '%s.nzb' % (nzb_name and re.sub(r'(?i)\.nzb$', '', nzb_name) or None),
              'quiet': 1, 'force': 1, 'failed': int(failed), 'stream': 1, 'dupekey': dupekey, 'is_basedir': 0,
              'client': 'nzbget', 'dupescore': dupescore, 'nzbid': nzbid, 'pp_version': __version__}
    if test:
        params['test'] = '1'
    py_ver = '%s.%s.%s' % sys.version_info[0:3]
    Logger.log('Opening URL: %s with: py%s and params: %s' % (url, py_ver, params))
    try:
        s = requests.Session()
        if username or password:
            login = '%s%s:%s%s/login' % (protocol, host, port, webroot)
            r = s.get(login, verify=False)
            login_params = {'username': username, 'password': password}
            if 401 == r.status_code and r.cookies.get('_xsrf'):
                login_params['_xsrf'] = r.cookies.get('_xsrf')
            s.post(login, data=login_params, stream=True, verify=False)
        r = s.get(url, auth=(username, password), params=params, stream=True, verify=False, timeout=900)
    except (BaseException, Exception):
        Logger.log('Unable to open URL: %s' % url, Logger.ERROR)
        return False

    success = False
    try:
        if r.status_code not in [requests.codes.ok, requests.codes.created, requests.codes.accepted]:
            Logger.log('Server returned status %s' % str(r.status_code), Logger.ERROR)
            return False

        for line in r.iter_lines():
            if line:
                Logger.log(line.decode('utf-8'), Logger.DETAIL)
                if test:
                    if b'Connection success!' in line:
                        return True
                elif not failed and b'Failed download detected:' in line:
                    failed = True
                    global markbad
                    markbad = True
                    Logger.log('MARK=BAD', Logger.NZB)
                success = (b'Processing succeeded' in line or b'Successfully processed' in line or
                           (1 == failed and b'Successful failed download processing' in line))
    except (BaseException, Exception) as e:
        Logger.log(ex(e), Logger.ERROR)

    return success


def find_dupekey_history(dupekey, nzb_id):

    if not dupekey:
        return False
    data = call_nzbget_direct('history?hidden=true')
    cur_status = cur_dupekey = cur_id = ''
    cur_dupescore = 0
    for line in data.splitlines():
        if line.startswith('"NZBID" : '):
            cur_id = line[10:-1]
        elif line.startswith('"Status" : '):
            cur_status = line[12:-2]
        elif line.startswith('"DupeKey" : '):
            cur_dupekey = line[13:-2]
        elif line.startswith('"DupeScore" : '):
            cur_dupescore = try_int(line[14:-1])
        elif cur_id and line.startswith('}'):
            if (cur_status.startswith('SUCCESS') and dupekey == cur_dupekey and
                    cur_dupescore >= try_int(nzbget_var('DUPESCORE')) and cur_id != nzb_id):
                return True
            cur_status = cur_dupekey = cur_id = ''
            cur_dupescore = 0
    return False


def find_dupekey_queue(dupekey, nzb_id):

    if not dupekey:
        return False
    data = call_nzbget_direct('listgroups')
    cur_status = cur_dupekey = cur_id = ''
    for line in data.splitlines():
        if line.startswith('"NZBID" : '):
            cur_id = line[10:-1]
        elif line.startswith('"Status" : '):
            cur_status = line[12:-2]
        elif line.startswith('"DupeKey" : '):
            cur_dupekey = line[13:-2]
        elif cur_id and line.startswith('}'):
            if 'PAUSED' != cur_status and dupekey == cur_dupekey and cur_id != nzb_id:
                return True
            cur_status = cur_dupekey = cur_id = ''
    return False


def check_for_failure(directory):

    failure = True
    dupekey = nzbget_var('DUPEKEY')
    if 'PP' == env_run_mode:
        total_status = nzbget_var('TOTALSTATUS')
        status = nzbget_var('STATUS')
        if 'WARNING' == total_status and status in ['WARNING/REPAIRABLE', 'WARNING/SPACE', 'WARNING/DAMAGED']:
            Logger.log('WARNING/REPAIRABLE' == status and 'Download is damaged but probably can be repaired' or
                       'WARNING/SPACE' == status and 'Out of Diskspace' or
                       'Par-check is required but is disabled in settings', Logger.WARNING)
            script_exit(POSTPROCESS_ERROR, ExitReason.UNFINISHED_DOWNLOAD)
        elif 'DELETED' == total_status:
            Logger.log('Download was deleted and manually processed, nothing to do, exiting')
            script_exit(POSTPROCESS_NONE, ExitReason.DELETED)
        elif 'SUCCESS' == total_status:
            # check for min dir size
            if get_size(directory) > min_dir_size:
                failure = False
            else:
                Logger.log('MARK=BAD', Logger.NZB)
    else:
        nzb_id = nzbget_var('NZBID')
        if (not markbad and find_dupekey_queue(dupekey, nzb_id)) or find_dupekey_history(dupekey, nzb_id):
            Logger.log('Download with same Dupekey in download queue or history, exiting')
            script_exit(POSTPROCESS_NONE, ExitReason.SAME_DUPEKEY)
        nzb_delete_status = nzbget_var('DELETESTATUS')
        if 'MANUAL' == nzb_delete_status:
            Logger.log('Download was manually deleted, exiting')
            script_exit(POSTPROCESS_NONE, ExitReason.DELETED)

    # Check if it's a Failed Download not added by SickGear
    if failure and (not dupekey or not dupekey.startswith('SickGear-')):
        Logger.log('Failed download was not added by SickGear, exiting')
        script_exit(POSTPROCESS_NONE, ExitReason.NONE_SG)

    return failure


# Check if the script is executed from settings page with a custom command
command = os.environ.get('NZBCP_COMMAND')
if None is not command:
    if 'Test connection' == command:
        Logger.log('Test connection...')
        result = call_sickgear('', '', test=True)
        if True is result:
            Logger.log('Connection Test successful!')
            sys.exit(POSTPROCESS_SUCCESS)
        Logger.log('Connection Test failed!', Logger.ERROR)
        sys.exit(POSTPROCESS_ERROR)

    Logger.log('Invalid command passed to SickGear-NG: ' + command,  Logger.ERROR)
    sys.exit(POSTPROCESS_ERROR)


# Script body
def main():

    global failed
    # Do start up check
    start_check()

    # Read context (what nzb is currently being processed)
    directory = nzbget_var('DIRECTORY')
    nzbname = nzbget_var('NZBNAME')
    failed = check_for_failure(directory)

    if call_sickgear(nzbname, directory):
        Logger.log('Successfully post-processed %s' % nzbname)
        sys.stdout.flush()
        script_exit(POSTPROCESS_SUCCESS,
                    failed and (markbad and ExitReason.MARKED_BAD_SUCCESS or ExitReason.FAIL_SUCCESS) or
                    ExitReason.PP_SUCCESS)

    Logger.log('Failed to post-process %s' % nzbname, Logger.ERROR)
    sys.stdout.flush()
    script_exit(POSTPROCESS_ERROR,
                failed and (markbad and ExitReason.MARKED_BAD_ERROR or ExitReason.FAIL_ERROR) or
                ExitReason.PP_ERROR)


# Execute main script function
main()

script_exit(POSTPROCESS_NONE, ExitReason.NONE)
