#!/usr/bin/env python
#
# ##############################################################################
# ##############################################################################
#
# SickGear PostProcessing script for NZBGet
# =========================================
#
# If NZBGet v17+ is installed on the same system as SickGear then as a local install,
#
# 1) Add the location of this script file to NZBGet Settings/PATHS/ScriptDir
#
# 2) Navigate to any named TV category at Settings/Categories, click "Choose" Category.Extensions then Apply SickGear-NG
#
# This is the best set up to automatically get script updates from SickGear
#
# #############
#
# If NZBGet v16 or earlier is installed, then as an older install,
#
# 1) Copy the directory with/or this single script file to path set in NZBGet Settings/PATHS/ScriptDir
#
# 2) Refresh the NZBGet page and navigate to Settings/SickGear-NG
#
# 3) Click View -> Compact to remove any tick and un hide tips and suggestions
#
# 4) The bare minimum change is the sg_base_path setting or enter `python -m pip install requests` at admin commandline
#
# 5) Navigate to any named TV category at Settings/Categories, click "Choose" Category.Extensions then Apply SickGear-NG
#
# You will need to manually update your script with this set up
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

# Send PostProcessing requests to SickGear
#
# PostProcessing-Script version: 1.3.
# <!--
# For more info and updates please visit forum topic at
# -->
# <span style="display:block;position:absolute;right:20px;top:105px;width:138px;height:74px;background:url(https://raw.githubusercontent.com/SickGear/SickGear/master/gui/slick/images/sickgear.png)"></span>
# <span style="display:inline-block;margin-top:10px" class="label label-important">
# Setup steps</span> <span class="label label-important" style="display:inline-block;cursor:pointer" data-toggle="modal" href="#InfoDialog">NZBGet Version</span>
# <span style="display:block;color:#666">
# <span style="display:block;padding:4px;margin-top:3px;background-color:#efefef;border:1px solid #ccc;-webkit-border-radius:3px;-moz-border-radius:3px;border-radius:3px">
# <span style="width:1em;float:left;padding:3px 0 0 3px">
# <span class="label label-important">1</span>
# </span>
# <span style="display:block;margin-left:1.75em;padding:3px 3px 3px 0">
# If <span style="font-weight:bold">NZBGet v17 or newer</span> is installed on the same system as SickGear, then add the
# location of this script file to NZBGet Settings/PATHS/ScriptDir
# <br /><br />
# Or, if <span style="font-weight:bold">NZBGet v16 or earlier</span> is installed on the same system as SickGear and
# if python <a href="https://pypi.python.org/pypi/requests" title="requests library page" target="_blank">requests library</a>
# is not installed, then <strong style="font-weight:bold;color:#128D12 !important">sg_base_path</strong> must be set
# </span>
# </span>
# <span style="display:block;padding:4px;margin-top:3px;background-color:#efefef;border:1px solid #ccc;-webkit-border-radius:3px;-moz-border-radius:3px;border-radius:3px">
# <span style="width:1em;float:left;padding:3px 0 0 3px">
# <span class="label label-important">2</span>
# </span>
# <span style="display:block;margin-left:1.75em;padding:3px 3px 3px 0">
# Then, for <span style="font-weight:bold">any install</span> type, click <span class="btn" style="padding:1px 5px 0;line-height:16px">Choose</span>
# then apply "<span style="color:#222">SickGear-NG</span>" in a TV Category at NZBGet Settings/CATEGORIES,
# save all changes and reload NZBGet
#
# </span>
# </span>
# </span>
#
# <span class="label label-warning">Note</span> This script requires Python 2.7+ and may not work with Python 3.x+
#
##############################################################################
### OPTIONS                                                                ###
#
#test connection@Test SickGear connection
#
# <span class="label label-info">
# Optional</span>
# SickGear <span style="font-weight:bold;color:#128D12 !important">base installation path</span>.
# use where NZBGet v16 or older is installed on the same system as SickGear, and no python requests library is installed
# (use "pip list" to check installed modules)
#sg_base_path=

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

__version__ = '1.3'

verbose = 0 or 'yes' == os.environ.get('NZBPO_SG_VERBOSE', 'no')

# NZBGet exit codes for post-processing scripts (Queue-scripts don't have any special exit codes).
POSTPROCESS_SUCCESS, POSTPROCESS_ERROR, POSTPROCESS_NONE = 93, 94, 95

failed = False

# define minimum dir size, downloads under this size will be handled as failure
min_dir_size = 20 * 1024 * 1024


class Logger:
    INFO, DETAIL, ERROR, WARNING = 'INFO', 'DETAIL', 'ERROR', 'WARNING'
    # '[NZB]' send a command message to NZBGet (no log)
    NZB = 'NZB'

    def __init__(self):
        pass

    @staticmethod
    def safe_print(msg_type, message):
        try:
            print '[%s] %s' % (msg_type, message.encode(SYS_ENCODING))
        except (StandardError, Exception):
            try:
                print '[%s] %s' % (msg_type, message)
            except (StandardError, Exception):
                try:
                    print '[%s] %s' % (msg_type, repr(message))
                except (StandardError, Exception):
                    pass

    @staticmethod
    def log(message, msg_type=INFO):
        size = 900
        if size > len(message):
            Logger.safe_print(msg_type, message)
        else:
            for group in (message[pos:pos + size] for pos in xrange(0, len(message), size)):
                Logger.safe_print(msg_type, group)


if 'nt' == os.name:
    import ctypes

    class WinEnv:
        def __init__(self):
            pass

        @staticmethod
        def get_environment_variable(name):
            name = unicode(name)  # ensures string argument is unicode
            n = ctypes.windll.kernel32.GetEnvironmentVariableW(name, None, 0)
            env_value = None
            if n:
                buf = ctypes.create_unicode_buffer(u'\0'*n)
                ctypes.windll.kernel32.GetEnvironmentVariableW(name, buf, n)
                env_value = buf.value
            verbose and Logger.log('Get var(%s) = %s' % (name, env_value or n))
            return env_value

        def __getitem__(self, key):
            return self.get_environment_variable(key)

        def get(self, key, default=None):
            r = self.get_environment_variable(key)
            return r if r is not None else default

    env_var = WinEnv()
else:
    class LinuxEnv(object):
        def __init__(self, environ):
            self.environ = environ

        def __getitem__(self, key):
            v = self.environ.get(key)
            try:
                return v.decode(SYS_ENCODING) if isinstance(v, str) else v
            except (UnicodeDecodeError, UnicodeEncodeError):
                return v

        def get(self, key, default=None):
            v = self[key]
            return v if v is not None else default

    env_var = LinuxEnv(os.environ)


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


class Ek:
    def __init__(self):
        pass

    @staticmethod
    def fix_string_encoding(x):
        if str == type(x):
            try:
                return x.decode(SYS_ENCODING)
            except UnicodeDecodeError:
                return None
        elif unicode == type(x):
            return x
        return None

    @staticmethod
    def fix_list_encoding(x):
        if type(x) not in (list, tuple):
            return x
        return filter(lambda i: None is not i, map(Ek.fix_string_encoding, i))

    @staticmethod
    def encode_item(x):
        try:
            return x.encode(SYS_ENCODING)
        except UnicodeEncodeError:
            return x.encode(SYS_ENCODING, 'ignore')

    @staticmethod
    def ek(func, *args, **kwargs):
        if 'nt' == os.name:
            func_result = func(*args, **kwargs)
        else:
            func_result = func(*[Ek.encode_item(x) if type(x) == str else x for x in args], **kwargs)

        if type(func_result) in (list, tuple):
            return Ek.fix_list_encoding(func_result)
        elif str == type(func_result):
            return Ek.fix_string_encoding(func_result)
        return func_result


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
    except (StandardError, Exception):
        pass
if sg_path and Ek.ek(os.path.isdir, Ek.ek(os.path.join, sg_path, 'lib')):
    sys.path.insert(1, Ek.ek(os.path.join, sg_path, 'lib'))


try:
    import requests
except ImportError:
    Logger.log('You must set SickGear sg_base_path in script config or install python requests library', Logger.ERROR)
    sys.exit(1)


def get_size(start_path='.'):
    if Ek.ek(os.path.isfile, start_path):
        return Ek.ek(os.path.getsize, start_path)
    total_size = 0
    for dirpath, dirnames, filenames in Ek.ek(os.walk, start_path):
        for f in filenames:
            if not f.lower().endswith(('.nzb', '.jpg', '.jpeg', '.gif', '.png', '.tif', '.nfo', '.txt', '.srt', '.sub',
                                       '.sbv', '.idx', '.bat', '.sh', '.exe', '.pdf')):
                fp = Ek.ek(os.path.join, dirpath, f)
                total_size += Ek.ek(os.path.getsize, fp)
    return total_size


def try_int(s, s_default=0):
    try:
        return int(s)
    except (StandardError, Exception):
        return s_default


def try_float(s, s_default=0):
    try:
        return float(s)
    except (StandardError, Exception):
        return s_default


class ExitReason:
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
    if old_status and status_regex.search(old_status) is not None:
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
    nzbget_version = nzbget_version.group(1) if nzbget_version and len(nzbget_version.groups()) >= 1 else '0.1'
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
        Logger.log('Marked as [%s], nothing to do, existing' % env_var.get('NZBNA_MARKSTATUS', ''))
        sys.exit(0)

    old_exit_status = get_old_status()
    if old_exit_status in good_statuses and not (
            ExitReason.FAIL_SUCCESS == old_exit_status[2] and 'SUCCESS' == nzbget_var('TOTALSTATUS')):
        Logger.log('Found result from a previous completed run, exiting')
        script_exit(old_exit_status[0], old_exit_status[2], old_exit_status[1])

    # If called via "Post-process again" from history details dialog the download may not exist anymore
    if 'NZBNA_EVENT' not in os.environ and 'NZBPP_DIRECTORY' in os.environ:
        directory = nzbget_var('DIRECTORY')
        if not directory or not Ek.ek(os.path.exists, directory):
            Logger.log('No files for postprocessor, look back in your NZBGet logs if required, exiting')
            script_exit(POSTPROCESS_NONE, ExitReason.NONE)


def call_nzbget_direct(url_command):
    # Connect to NZBGet and call an RPC-API method without using python's XML-RPC which is slow for large amount of data
    # First we need connection info: host, port and password of NZBGet server, NZBGet passes configuration options to
    # scripts using environment variables
    host, port, username, password = [nzbget_opt('CONTROL%s' % name) for name in 'IP', 'PORT', 'USERNAME', 'PASSWORD']
    url = 'http://%s:%s/jsonrpc/%s' % ((host, '127.0.0.1')['0.0.0.0' == host], port, url_command)

    try:
        response = requests.get(url, auth=(username, password))
    except requests.RequestException:
        return ''

    return response.content if response.ok else ''


def call_sickgear(nzb_name, dir_name, test=False):

    global failed
    ssl, host, port, username, password, webroot = [nzbget_plugin_opt(name, default) for name, default in
                                                    ('SSL', 'no'), ('HOST', 'localhost'), ('PORT', '8081'),
                                                    ('USERNAME', ''), ('PASSWORD', ''), ('WEB_ROOT', '')]
    protocol = 'http%s://' % ('', 's')['yes' == ssl]
    webroot = any(webroot) and '/%s' % webroot.strip('/') or ''
    url = '%s%s:%s%s/home/postprocess/processEpisode' % (protocol, host, port, webroot)

    dupescore = nzbget_var('DUPESCORE')
    dupekey = nzbget_var('DUPEKEY')
    nzbid = nzbget_var('NZBID')
    params = {'nzbName': '%s.nzb' % (nzb_name and re.sub('(?i)\.nzb$', '', nzb_name) or None), 'dir': dir_name,
              'failed': int(failed), 'quiet': 1, 'stream': 1, 'force': 1, 'dupekey': dupekey, 'dupescore': dupescore,
              'nzbid': nzbid, 'ppVersion': __version__, 'is_basedir': 0, 'client': 'nzbget'}
    if test:
        params['test'] = '1'
    Logger.log('Opening URL: %s with params: %s' % (url, params))
    try:
        s = requests.Session()
        if username or password:
            login = '%s%s:%s%s/login' % (protocol, host, port, webroot)
            r = s.get(login)
            login_params = {'username': username, 'password': password}
            if 401 == r.status_code and r.cookies.get('_xsrf'):
                login_params['_xsrf'] = r.cookies.get('_xsrf')
            s.post(login, data=login_params, stream=True, verify=False)
        r = s.get(url, auth=(username, password), params=params, stream=True, verify=False, timeout=900)
    except (StandardError, Exception):
        Logger.log('Unable to open URL: %s' % url, Logger.ERROR)
        return False

    success = False
    try:
        if r.status_code not in [requests.codes.ok, requests.codes.created, requests.codes.accepted]:
            Logger.log('Server returned status %s' % str(r.status_code), Logger.ERROR)
            return False

        for line in r.iter_lines():
            if line:
                Logger.log(line, Logger.DETAIL)
                if test:
                    if 'Connection success!' in line:
                        return True
                elif not failed and 'Failed download detected:' in line:
                    failed = True
                    global markbad
                    markbad = True
                    Logger.log('MARK=BAD', Logger.NZB)
                success = ('Processing succeeded' in line or 'Successfully processed' in line or
                           (1 == failed and 'Successful failed download processing' in line))
    except Exception as e:
        Logger.log(str(e), Logger.ERROR)

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
        nzb_id = nzbget_var('NZBID')
        if (not markbad and find_dupekey_queue(dupekey, nzb_id)) or find_dupekey_history(dupekey, nzb_id):
            Logger.log('Download with same Dupekey in download queue or history, exiting')
            script_exit(POSTPROCESS_NONE, ExitReason.SAME_DUPEKEY)
        nzb_delete_status = nzbget_var('DELETESTATUS')
        if nzb_delete_status == 'MANUAL':
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
    if 'test connection' == command:
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
