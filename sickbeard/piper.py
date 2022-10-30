import sys

# noinspection PyPep8Naming
import encodingKludge as ek

if ek.EXIT_BAD_ENCODING:
    print('Sorry, you MUST add the SickGear folder to the PYTHONPATH environment variable')
    print('or find another way to force Python to use %s for string encoding.' % ek.SYS_ENCODING)
    sys.exit(1)

# #################################
# Sanity check passed, can continue
# #################################
import io
import json
import os
import re

from sg_helpers import cmdline_runner, try_int

from _23 import filter_list, ordered_dict
from six import iteritems, PY2

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Tuple, Union


def is_pip_ok():
    # type: (...) -> bool
    """Check pip availability

    :return: True if pip is ok
    """
    pip_ok = '/' != ek.ek(os.path.expanduser, '~')
    if pip_ok:
        pip_version, _, _ = _get_pip_version()
        if not pip_version:
            pip_ok = False
            cmdline_runner([sys.executable, '-c', 'import ensurepip;ensurepip.bootstrap()'], suppress_stderr=True)
    return pip_ok


def _get_pip_version():
    return cmdline_runner([sys.executable, '-c', 'from pip import __version__ as v; print(v)'], suppress_stderr=True)


def run_pip(pip_cmd, suppress_stderr=False):
    # type: (List[AnyStr], bool) -> Tuple[AnyStr, Optional[AnyStr], int]
    """Run pip command

    :param pip_cmd:
    :param suppress_stderr:
    :return: out, err, returncode
    """
    if 'uninstall' == pip_cmd[0]:
        pip_cmd += ['-y']
    elif 'install' == pip_cmd[0]:
        pip_cmd += ['--progress-bar', 'off']

    new_pip_arg = ['--no-python-version-warning']
    if PY2:
        pip_version, _, _ = _get_pip_version()
        if pip_version and 20 > int(pip_version.split('.')[0]):
            new_pip_arg = []

    return cmdline_runner(
        [sys.executable, '-m', 'pip'] + new_pip_arg + ['--disable-pip-version-check'] + pip_cmd,
        suppress_stderr=suppress_stderr)


def initial_requirements():
    """Process requirements

    * Upgrades legacy Cheetah version 2 to version 3+
    """
    if is_pip_ok():
        try:
            # noinspection PyUnresolvedReferences,PyPackageRequirements
            from Cheetah import VersionTuple

            is_cheetah2 = (3, 0, 0) > VersionTuple[0:3]
            is_cheetah3py3 = not PY2 and (3, 3, 0) > VersionTuple[0:3]
            if not (is_cheetah2 or is_cheetah3py3):
                return

            for cur_mod in [_m for _m in set(sys.modules.keys()) if 'heetah' in _m]:
                del sys.modules[cur_mod]
                try:
                    del globals()[cur_mod]
                except KeyError:
                    pass
                try:
                    del locals()[cur_mod]
                except KeyError:
                    pass

            from gc import collect
            collect()

            if is_cheetah2:
                run_pip(['uninstall', 'cheetah', 'markdown'])
                raise ValueError
            elif is_cheetah3py3:
                run_pip(['uninstall', '-r', 'recommended-remove.txt'])
                raise ValueError
        except (BaseException, ImportError):
            run_pip(['install', '-U', '--user', '-r', 'requirements.txt'])
            module = 'Cheetah'
            try:
                locals()[module] = __import__(module)
                sys.modules[module] = __import__(module)
            except (BaseException, Exception) as e:
                pass


def extras_failed_filepath(data_dir):
    return ek.ek(os.path.join, data_dir, '.pip_req_spec_failed.txt')


def load_ignorables(data_dir):
    # type: (AnyStr) -> List[AnyStr]

    data = []

    filepath = extras_failed_filepath(data_dir)
    if ek.ek(os.path.isfile, filepath):
        try:
            with io.open(filepath, 'r', encoding='UTF8') as fp:
                data = fp.readlines()
        except (BaseException, Exception):
            pass

    return data


def save_ignorables(data_dir, data):
    # type: (AnyStr, List[AnyStr]) -> None

    try:
        with io.open(extras_failed_filepath(data_dir), 'w', encoding='UTF8') as fp:
            fp.writelines(data)
            fp.flush()
            os.fsync(fp.fileno())
    except (BaseException, Exception):
        pass


def check_pip_outdated(reset_fails=False):
    # type: (bool) -> Dict[Any]
    """Check outdated or missing Python performance packages"""
    _, work_todo, _, _ = _check_pip_env(pip_outdated=True, reset_fails=reset_fails)
    return work_todo


def check_pip_installed():
    # type: (...) -> Tuple[List[tuple], List[AnyStr]]
    """Return working installed Python performance packages"""
    input_reco, _, installed, _ = _check_pip_env()
    return installed, input_reco


def check_pip_env():
    # type: (...) -> Tuple[List[tuple], Dict[AnyStr, AnyStr], List[AnyStr]]
    """Return working installed Python performance packages, extra info, and failed packages, for ui"""

    _, _, installed, failed_names = _check_pip_env()

    py2_last = 'final py2 release'
    boost = 'performance boost'
    extra_info = dict({'Cheetah3': 'filled requirement', 'CT3': 'filled requirement',
                       'lxml': boost, 'python-Levenshtein': boost})
    extra_info.update((dict(cryptography=py2_last, pip='stable py2 release', regex=py2_last,
                            scandir=boost, setuptools=py2_last),
                       dict(regex=boost))[not PY2])
    return installed, extra_info, failed_names


def _check_pip_env(pip_outdated=False, reset_fails=False):
    # type: (bool, bool) -> Tuple[List[AnyStr], Dict[Dict[AnyStr, Union[bool, AnyStr]]], List[tuple], List[AnyStr]]
    """Checking Python requirements and recommendations for installed, outdated, and missing performance packages

    :param pip_outdated: do a Pip list outdated if True
    :param reset_fails: reset known failures if True
    :return combined required + recommended names,
            dictionary of work names:version info,
            combined required + recommended names with either installed version or '' if not installed,
            failed item names
    """
    if not is_pip_ok():
        return [], dict(), [], []

    input_reco = []
    from sickbeard import logger, PROG_DIR, DATA_DIR
    for cur_reco_file in ['requirements.txt', 'recommended.txt']:
        try:
            with io.open(ek.ek(os.path.join, PROG_DIR, cur_reco_file)) as fh:
                input_reco += ['%s\n' % line.strip() for line in fh]  # must ensure EOL marker
        except (BaseException, Exception):
            pass

    environment = {}
    # noinspection PyUnresolvedReferences
    import six.moves
    import pkg_resources
    six.moves.reload_module(pkg_resources)
    for cur_distinfo in pkg_resources.working_set:
        environment[cur_distinfo.project_name] = cur_distinfo.parsed_version

    save_failed = False
    known_failed = load_ignorables(DATA_DIR)
    if reset_fails and known_failed:
        known_failed = []
        save_failed = True
    failed_names = []
    output_reco = {}
    names_reco = []
    specifiers = {}
    requirement_update = set()
    from pkg_resources import parse_requirements
    for cur_line in input_reco:
        try:
            requirement = next(parse_requirements(cur_line))  # https://packaging.pypa.io/en/latest/requirements.html
        except ValueError as e:
            logger.error('Error [%s] with line: %s' % (e, cur_line))  # name@url ; whitespace/newline must follow url
            continue
        project_name = getattr(requirement, 'project_name', None)
        if cur_line in known_failed and project_name not in environment:
            failed_names += [project_name]
        else:
            marker = getattr(requirement, 'marker', None)
            if marker and not marker.evaluate():
                continue
            if project_name:
                # explicitly output the most recent line where project names repeat, i.e. max(line number)
                # therefore, position items with greater specificity _after_ items with a broad spec in requirements.txt
                output_reco[project_name] = cur_line
                if project_name not in names_reco:
                    names_reco += [project_name]
                if project_name in environment:
                    if environment[project_name] in requirement.specifier:
                        specifiers[project_name] = requirement.specifier  # requirement is met in the env
                        if cur_line in known_failed:
                            known_failed.remove(cur_line)  # manually installed item that previously failed
                            save_failed = True
                    else:
                        requirement_update.add(project_name)  # e.g. when '!=' matches an installed project to uninstall
    if save_failed:
        save_ignorables(DATA_DIR, known_failed)

    to_install = set(names_reco).difference(set(environment))
    fresh_install = len(to_install) == len(names_reco)
    installed = [(cur_name, getattr(environment.get(cur_name), 'public', '')) for cur_name in names_reco]

    to_update = set()
    names_outdated = dict()
    if pip_outdated and not fresh_install:
        output, err, exit_status = run_pip(['list', '--outdated', '--format', 'json'], suppress_stderr=True)
        try:
            names_outdated = dict({cur_item.get('name'): {k: cur_item.get(k) for k in ('version', 'latest_version')}
                                   for cur_item in json.loads(output)})
            to_update = set(filter_list(
                lambda name: name in specifiers and names_outdated[name]['latest_version'] in specifiers[name],
                set(names_reco).intersection(set(names_outdated))))

            # check whether to ignore direct reference specification updates if not dev mode
            if not int(os.environ.get('CHK_URL_SPECIFIERS', 0)):
                to_remove = set()
                for cur_name in to_update:
                    if '@' in output_reco[cur_name] and cur_name in specifiers:
                        # direct reference spec update, is for a package met in the env, so remove update
                        to_remove.add(cur_name)
                to_update = to_update.difference(to_remove)
        except (BaseException, Exception):
            pass

    updates_todo = ordered_dict()
    todo = to_install.union(to_update, requirement_update)
    for cur_name in [cur_n for cur_n in names_reco if cur_n in todo]:
        updates_todo[cur_name] = dict({
            _tuple[0]: _tuple[1] for _tuple in
            (cur_name in names_outdated and [('info', names_outdated[cur_name])] or [])
            + (cur_name in requirement_update and [('requirement', True)] or [])
            + [('require_spec', output_reco.get(cur_name, '%s>0.0.0\n' % cur_name))]})

    return input_reco, updates_todo, installed, failed_names


def pip_update(loading_msg, updates_todo, data_dir):
    # type: (AnyStr, Dict[Any], AnyStr) -> bool
    result = False
    if not is_pip_ok():
        return result

    from sickbeard import logger
    failed_lines = []
    input_reco = None

    piper_path = ek.ek(os.path.join, data_dir, '.pip_req_spec_temp.txt')
    for cur_project_name, cur_data in iteritems(updates_todo):
        msg = 'Installing package "%s"' % cur_project_name
        if cur_data.get('info'):
            info = dict(name=cur_project_name, ver=cur_data.get('info').get('version'))
            if not cur_data.get('requirement'):
                msg = 'Updating package "%(name)s" version %(ver)s to {}'.format(
                    cur_data.get('info').get('latest_version')) % info
            else:
                msg = 'Checking package "%(name)s" version %(ver)s with "{}"'.format(
                    re.sub(r',\b', ', ', cur_data.get('require_spec').strip())) % info
        loading_msg.set_msg_progress(msg, 'Installing...')

        try:
            with io.open(piper_path, 'w', encoding='utf-8') as fp:
                fp.writelines(cur_data.get('require_spec'))
                fp.flush()
                os.fsync(fp.fileno())
        except (BaseException, Exception):
            loading_msg.set_msg_progress(msg, 'Failed to save install data')
            continue

        # exclude Cheetah3 to prevent `No matching distro found` and fallback to its legacy setup.py installer
        output, err, exit_status = run_pip(['install', '-U']
                                           + ([], ['--only-binary=:all:'])[cur_project_name not in ('Cheetah3', )]
                                           + ['--user', '-r', piper_path])
        pip_version = None
        try:
            # ensure '-' in a project name is not escaped in order to convert the '-' into a `[_-]` regex
            find_name = re.escape(cur_project_name.replace(r'-', r'44894489')).replace(r'44894489', r'[_-]')
            parsed_name = re.findall(r'(?sim).*(%s[^\s]+)\.whl.*' % find_name, output) or \
                re.findall(r'(?sim).*Successfully installed.*?(%s[^\s]+)' % find_name, output)
            if not parsed_name:
                parsed_name = re.findall(r'(?sim)up-to-date[^\s]+\s*(%s).*?\s\(([^)]+)\)$' % find_name, output)
                parsed_name = ['' if not parsed_name else '-'.join(parsed_name[0])]
            pip_version = re.findall(r'%s-([\d.]+).*?' % find_name, ek.ek(os.path.basename, parsed_name[0]), re.I)[0]
        except (BaseException, Exception):
            pass

        # pip may output `...WinError 5 Access denied...` yet still install what appears a failure
        # therefore, for any apparent failure, recheck the environment to figure if the failure is actually true
        installed, input_reco = check_pip_installed()
        if 0 == exit_status or (cur_project_name, pip_version) in installed:
            result = True
            installed_version = pip_version or cur_data.get('info', {}).get('latest_version') or 'n/a'
            msg_result = 'Installed version: %s' % installed_version
            logger.log('Installed %s version: %s' % (cur_project_name, installed_version))
        else:
            failed_lines += [cur_data.get('require_spec')]
            msg_result = 'Failed to install'
            log_error = ''
            for cur_line in output.splitlines()[::-1]:
                if 'error' in cur_line.lower():
                    msg_result = re.sub(r'(?i)(\berror:\s*|\s*\(from.*)', '', cur_line)
                    log_error = ': %s' % msg_result
                    break
            logger.debug('Failed to install %s%s' % (cur_project_name, log_error))
        loading_msg.set_msg_progress(msg, msg_result)

    if failed_lines:
        # for example, python-Levenshtein failed due to no matching PyPI distro. A recheck at the next PY or SG upgrade
        # was considered, but an is_env_changed() helper doesn't exist which makes that idea outside this feature scope.
        # Therefore, prevent a re-attempt and present the missing pkg to the ui for the user to optionally handle.
        failed_lines += [cur_line for cur_line in load_ignorables(data_dir) if cur_line not in failed_lines]
        if None is input_reco:
            _, input_reco = check_pip_installed()  # known items in file content order
        sorted_failed = [cur_line for cur_line in input_reco if cur_line in failed_lines]
        save_ignorables(data_dir, sorted_failed)

    return result


if '__main__' == __name__:
    print('This module is supposed to be used as import in other scripts and not run standalone.')
    sys.exit(1)

initial_requirements()
