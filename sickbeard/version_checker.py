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
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import os
import platform
import re
import shutil
import stat
import tarfile
import time
import traceback
from . import gh_api as github

# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex

import sickbeard
from . import logger, notifiers, ui
from .piper import check_pip_outdated
from sg_helpers import cmdline_runner

# noinspection PyUnresolvedReferences
from six.moves import urllib
from _23 import list_keys


class PackagesUpdater(object):

    def __init__(self):
        self.install_type = 'Python package updates'

    def run(self, force=False):
        if not sickbeard.EXT_UPDATES \
                and self.check_for_new_version(force) \
                and sickbeard.UPDATE_PACKAGES_AUTO:
            msg = 'Automatic %s enabled, restarting to update...' % self.install_type
            logger.log(msg)
            ui.notifications.message(msg)
            time.sleep(3)
            sickbeard.restart(soft=False)

    def check_for_new_version(self, force=False):
        """
        Checks for available Python package installs/updates

        :param force: ignore the UPDATE_PACKAGES_NOTIFY setting

        :returns: True when package install/updates are available
        """
        if force and not sickbeard.UPDATE_PACKAGES_MENU:
            logger.log('Checking not enabled from menu action for %s' % self.install_type)
            return False

        if not sickbeard.UPDATE_PACKAGES_NOTIFY and not sickbeard.UPDATE_PACKAGES_AUTO and not force:
            logger.log('Checking not enabled for %s' % self.install_type)
            return False

        logger.log('Checking for %s%s' % (self.install_type, ('', ' (from menu)')[force]))
        sickbeard.UPDATES_TODO = check_pip_outdated(force)
        if not sickbeard.UPDATES_TODO:
            msg = 'No %s needed' % self.install_type
            logger.log(msg)

            if force:
                ui.notifications.message(msg)
            return False

        logger.log('Update(s) for %s found %s' % (self.install_type, list_keys(sickbeard.UPDATES_TODO)))

        # save updates_todo to config to be loaded after restart
        sickbeard.save_config()

        if not sickbeard.UPDATE_PACKAGES_AUTO:
            msg = '%s available &mdash; <a href="%s">Update Now</a>' % (
                    self.install_type, '%s/home/restart/?update_pkg=1&pid=%s' % (sickbeard.WEB_ROOT, sickbeard.PID))
            if None is sickbeard.NEWEST_VERSION_STRING:
                sickbeard.NEWEST_VERSION_STRING = ''
            if msg not in sickbeard.NEWEST_VERSION_STRING:
                if sickbeard.NEWEST_VERSION_STRING:
                    sickbeard.NEWEST_VERSION_STRING += '<br>Also, '
                sickbeard.NEWEST_VERSION_STRING += msg

        return True


class SoftwareUpdater(object):
    """
    Version check class meant to run as a thread object with the sg scheduler.
    """

    def __init__(self):
        self.install_type = self.find_install_type()

        if 'git' == self.install_type:
            self.updater = GitUpdateManager()
        elif 'source' == self.install_type:
            self.updater = SourceUpdateManager()
        else:
            self.updater = None

    def run(self, force=False):
        # set current branch version
        sickbeard.BRANCH = self.get_branch()

        if not sickbeard.EXT_UPDATES \
                and self.check_for_new_version(force) \
                and sickbeard.UPDATE_AUTO \
                and sickbeard.update_software_scheduler.action.update():
            msg = 'Automatic software updates enabled, restarting with updated...'
            logger.log(msg)
            ui.notifications.message(msg)
            time.sleep(3)
            sickbeard.restart(soft=False)

    @staticmethod
    def find_install_type():
        """
        Determines how this copy of sg was installed.

        returns: type of installation. Possible values are:
            'git': running from source using git
            'source': running from source without git
        """
        return ('source', 'git')[os.path.isdir(ek.ek(os.path.join, sickbeard.PROG_DIR, '.git'))]

    def check_for_new_version(self, force=False):
        """
        Checks for a new software release

        :param force: ignore the UPDATE_NOTIFY setting

        :returns: True when a new software version is available
        """

        if not sickbeard.UPDATE_NOTIFY and not sickbeard.UPDATE_AUTO and not force:
            logger.log('Checking not enabled for software updates')
            return False

        logger.log('Checking for "%s" software update%s' % (self.install_type, ('', ' (from menu)')[force]))
        if not self.updater.need_update():
            sickbeard.NEWEST_VERSION_STRING = None
            msg = 'No "%s" software update needed' % self.install_type
            logger.log(msg)

            if force:
                ui.notifications.message(msg)
            return False

        if not sickbeard.UPDATE_AUTO:
            self.updater.set_newest_text()

        return True

    def update(self):
        # update branch with current config branch value
        self.updater.branch = sickbeard.BRANCH

        # check for updates
        if self.updater.need_update():
            return self.updater.update()

    def fetch(self, pull_request):
        return self.updater.fetch(pull_request)

    def list_remote_branches(self):
        return self.updater.list_remote_branches()

    def list_remote_pulls(self):
        return self.updater.list_remote_pulls()

    def get_branch(self):
        return self.updater.branch


class UpdateManager(object):
    @staticmethod
    def get_github_repo_user():
        return 'SickGear'

    @staticmethod
    def get_github_repo():
        return 'SickGear'

    @staticmethod
    def get_update_url():
        return '%s/home/update/?pid=%s' % (sickbeard.WEB_ROOT, sickbeard.PID)


class GitUpdateManager(UpdateManager):
    def __init__(self):
        self.unsafe = False
        self._git_path = self._find_working_git()
        self.github_repo_user = self.get_github_repo_user()
        self.github_repo = self.get_github_repo()

        self.branch = self._find_installed_branch()
        if '' == self.branch:
            self.branch = sickbeard.BRANCH
        if self.branch and self.branch != sickbeard.BRANCH:
            sickbeard.BRANCH = self.branch

        self._cur_commit_hash = None
        self._newest_commit_hash = None
        self._num_commits_behind = 0
        self._num_commits_ahead = 0
        self._cur_pr_number = self.get_cur_pr_number()

    def _find_working_git(self):

        logger.debug(u'Checking if git commands are available')

        main_git = (sickbeard.GIT_PATH, 'git')[not sickbeard.GIT_PATH]

        _, _, exit_status = self._git_version(main_git)

        if 0 == exit_status:
            logger.debug(u'Using: %s' % main_git)
            return main_git

        logger.debug(u'Git not found: %s' % main_git)

        # trying alternatives

        alt_git_paths = []

        # osx users who start sg from launchd have a broken path, so try a possible location
        if 'darwin' == platform.system().lower():
            alt_git_paths.append('/usr/local/git/bin/git')

        if 'windows' == platform.system().lower():
            if main_git != main_git.lower():
                alt_git_paths.append(main_git.lower())
            if sickbeard.GIT_PATH:
                logger.debug(u'git.exe is missing, remove `git_path` from config.ini: %s' % main_git)
                if re.search(r' \(x86\)', main_git):
                    alt_git_paths.append(re.sub(r' \(x86\)', '', main_git))
                else:
                    alt_git_paths.append(re.sub('Program Files', 'Program Files (x86)', main_git))
                logger.debug(u'Until `git_path` is removed by a config.ini edit, trying: %s' % alt_git_paths[-1])

        if alt_git_paths:
            logger.debug('Trying known alternative git locations')

            for cur_git_path in alt_git_paths:
                _, _, exit_status = self._git_version(cur_git_path)

                if 0 == exit_status:
                    logger.debug(u'Using: %s' % cur_git_path)
                    return cur_git_path
                logger.debug(u'Not using: %s' % cur_git_path)

        # Still haven't found a working git
        error_message = 'Unable to find your git executable - Shutdown SickGear and EITHER set git_path' \
                        ' in your config.ini OR delete your .git folder and run from source to enable updates.'
        sickbeard.NEWEST_VERSION_STRING = error_message

    def _git_version(self, git_path):

        return self._run_git(['version'], git_path)

    def _run_git(self, arg_list, git_path=None, repeat=False):

        output = err = None
        exit_status = 1

        if None is git_path:
            git_path = self._git_path

        if not git_path:
            logger.error(u'No git specified, cannot use git commands')
            return output, err, exit_status

        cmd = ' '.join([git_path] + arg_list)

        try:
            logger.debug(u'Executing %s with your shell in %s' % (cmd, sickbeard.PROG_DIR))
            output, err, exit_status = cmdline_runner([git_path] + arg_list, env={'LANG': 'en_US.UTF-8'})
            logger.debug(u'git output: %s' % output)

        except OSError:
            logger.log('Failed command: %s' % cmd)

        except (BaseException, Exception) as e:
            logger.log('Failed command: %s, %s' % (cmd, ex(e)))

        if 0 == exit_status:
            logger.debug(u'Successful return: %s' % cmd)
            exit_status = 0
            self.unsafe = False

        elif 1 == exit_status:
            logger.error(u'Failed: %s returned: %s' % (cmd, output))

        elif 128 == exit_status or 'fatal:' in output or err:
            if 'unsafe repository' not in output and 'fatal:' in output:
                try:
                    outp, err, exit_status = cmdline_runner([git_path] + ['rev-parse', 'HEAD'], env={'LANG': 'en_US.UTF-8'})
                    if 'unsafe repository' in outp:
                        self.unsafe = True
                except (BaseException, Exception):
                    pass
            if 'unsafe repository' in output:
                self.unsafe = True
            if self.unsafe and not repeat:
                try:
                    outp, err, exit_status = cmdline_runner(
                        [git_path] + ['config', '--global', '--add',  'safe.directory',
                                      sickbeard.PROG_DIR.replace('\\', '/')], env={'LANG': 'en_US.UTF-8'})
                    if 0 == exit_status:
                        return self._run_git(arg_list, git_path, repeat=True)
                except (BaseException, Exception):
                    pass
            exit_status = 128
            msg = u'Fatal: %s returned: %s' % (cmd, output)
            if 'develop' in output.lower() or 'master' in output.lower():
                logger.error(msg)
            else:
                logger.debug(msg)

        else:
            logger.error(u'Treat as error for now, command: %s returned: %s' % (cmd, output))

        return output, err, exit_status

    def _find_installed_version(self):
        """
        Attempts to find the currently installed version of SickGear.
        Uses git show to get commit version.
        Returns: True for success or False for failure
        """

        output, _, exit_status = self._run_git(['rev-parse', 'HEAD'])

        if 0 == exit_status and output:
            cur_commit_hash = output.strip()
            if not re.match(r'^[a-z0-9]+$', cur_commit_hash):
                logger.error(u'Output doesn\'t look like a hash, not using it')
                return False
            self._cur_commit_hash = cur_commit_hash
            sickbeard.CUR_COMMIT_HASH = str(cur_commit_hash)
            return True
        return False

    def _find_installed_branch(self):
        output, _, exit_status = self._run_git(['symbolic-ref', '-q', 'HEAD'])
        if 0 == exit_status and output:
            branch = output.strip().replace('refs/heads/', '', 1)
            if branch:
                return branch

        return ''

    def _check_github_for_update(self):
        """
        Uses git commands to check if there is a newer version that the provided
        commit hash. If there is a newer version it sets _num_commits_behind.
        """

        self._num_commits_behind = 0
        self._num_commits_ahead = 0

        # get all new info from github
        _, _, exit_status = self._run_git(['fetch', '%s' % sickbeard.GIT_REMOTE])

        if 0 != exit_status:
            logger.error(u'Unable to contact github, can\'t check for update')
            return

        if not self._cur_pr_number:

            # get latest commit_hash from remote
            output, _, exit_status = self._run_git(['rev-parse', '--verify', '--quiet', '@{upstream}'])

            if 0 == exit_status and output:
                cur_commit_hash = output.strip()

                if not re.match('^[a-z0-9]+$', cur_commit_hash):
                    logger.debug(u'Output doesn\'t look like a hash, not using it')
                    return

                self._newest_commit_hash = cur_commit_hash
            else:
                logger.debug(u'git didn\'t return newest commit hash')
                return

            # get number of commits behind and ahead (option --count not supported git < 1.7.2)
            output, _, exit_status = self._run_git(['rev-list', '--left-right', '@{upstream}...HEAD'])

            if 0 == exit_status and output:

                try:
                    self._num_commits_behind = int(output.count('<'))
                    self._num_commits_ahead = int(output.count('>'))

                except (BaseException, Exception):
                    logger.debug(u'git didn\'t return numbers for behind and ahead, not using it')
                    return

            logger.debug(u'cur_commit = %s, newest_commit = %s, num_commits_behind = %s, num_commits_ahead = %s' % (
                self._cur_commit_hash, self._newest_commit_hash, self._num_commits_behind, self._num_commits_ahead))
        else:
            # we need to treat pull requests specially as it doesn't seem possible to set their "@{upstream}" tag
            output, _, _ = self._run_git(['ls-remote', '%s' % sickbeard.GIT_REMOTE,
                                          'refs/pull/%s/head' % self._cur_pr_number])
            self._newest_commit_hash = re.findall('(.*)\t', output)[0]

    def set_newest_text(self):
        # if we're up to date then don't set this
        newest_text = None
        url = 'http://github.com/%s/%s' % (self.github_repo_user, self.github_repo)

        if self._num_commits_ahead:
            newest_text = 'Local branch is ahead of %s. Automatic update not possible.' % self.branch
            logger.error(newest_text)

        elif 0 < self._num_commits_behind:

            if self._newest_commit_hash:
                url += '/compare/%s...%s' % (self._cur_commit_hash, self._newest_commit_hash)
            else:
                url += '/commits/'

            newest_text = 'There is a <a href="%s" onclick="window.open(this.href); return !1;">newer' \
                          ' version available</a> (you\'re %s commit%s behind) &mdash; <a href="%s">Update Now</a>' % \
                          (url, self._num_commits_behind,
                           ('', 's')[1 < self._num_commits_behind], self.get_update_url())

        elif self._cur_pr_number and (self._cur_commit_hash != self._newest_commit_hash):
            url += '/commit/%s' % self._newest_commit_hash

            newest_text = 'There is a <a href="%s" onclick="window.open(this.href); return !1;">newer' \
                          ' version available</a> &mdash; <a href="%s">Update Now</a>' % (url, self.get_update_url())

        sickbeard.NEWEST_VERSION_STRING = newest_text

    def need_update(self):

        if self.branch != self._find_installed_branch():
            logger.debug(u'Branch checkout: %s->%s' % (self._find_installed_branch(), self.branch))
            return True

        self._find_installed_version()
        if not self._cur_commit_hash:
            return True

        try:
            self._check_github_for_update()
        except (BaseException, Exception) as e:
            logger.error(u'Unable to contact github, can\'t check for update: %r' % e)
            return False

        if 0 < self._num_commits_behind:
            return True

        if self._cur_pr_number and self._cur_commit_hash != self._newest_commit_hash:
            return True

        return False

    def update(self):
        """
        Calls git pull origin <branch> in order to update SickGear. Returns a bool depending
        on the call's success.
        """

        if self.branch == self._find_installed_branch():
            if not self._cur_pr_number:
                _, _, exit_status = self._run_git(['pull', '-f', '%s' % sickbeard.GIT_REMOTE, '%s' % self.branch])
            else:
                _, _, exit_status = self._run_git(['pull', '-f', '%s' % sickbeard.GIT_REMOTE,
                                                   'pull/%s/head:%s' % (self._cur_pr_number, self.branch)])

        else:
            self._run_git(['fetch', '%s' % sickbeard.GIT_REMOTE])
            _, _, exit_status = self._run_git(['checkout', '-f', '-B', '%s' % self.branch,
                                               '%s/%s' % (sickbeard.GIT_REMOTE, self.branch)])

        if 0 == exit_status:
            self._find_installed_version()

            # Notify update successful
            notifiers.notify_git_update(sickbeard.CUR_COMMIT_HASH if sickbeard.CUR_COMMIT_HASH else '')
            return True

        return False

    def list_remote_branches(self):
        output, _, exit_status = self._run_git(['ls-remote', '--heads', '%s' % sickbeard.GIT_REMOTE])
        if 0 == exit_status and output:
            return re.findall(r'\S+\Wrefs/heads/(.*)', output)
        return []

    def list_remote_pulls(self):
        gh = github.GitHub(self.github_repo_user, self.github_repo, self.branch)
        return gh.pull_requests()

    def fetch(self, pull_request):
        _, _, exit_status = self._run_git(['fetch', '-f', '%s' % sickbeard.GIT_REMOTE, '%s' % pull_request])
        return 0 == exit_status

    def get_cur_pr_number(self):
        try:
            pull_number = int(self.branch.split('/')[1])
        except (BaseException, Exception):
            pull_number = None

        return pull_number


class SourceUpdateManager(UpdateManager):
    def __init__(self):
        self.github_repo_user = self.get_github_repo_user()
        self.github_repo = self.get_github_repo()

        self.branch = sickbeard.BRANCH
        if '' == sickbeard.BRANCH:
            self.branch = self._find_installed_branch()

        self._cur_commit_hash = sickbeard.CUR_COMMIT_HASH
        self._newest_commit_hash = None
        self._num_commits_behind = 0

    @staticmethod
    def _find_installed_branch():
        if '' == sickbeard.CUR_COMMIT_BRANCH:
            return 'master'
        return sickbeard.CUR_COMMIT_BRANCH

    def need_update(self):
        # need this to run first to set self._newest_commit_hash
        try:
            self._check_github_for_update()
        except (BaseException, Exception) as e:
            logger.error(u'Unable to contact github, can\'t check for update: %r' % e)
            return False

        if self.branch != self._find_installed_branch():
            logger.debug(u'Branch checkout: %s->%s' % (self._find_installed_branch(), self.branch))
            return True

        if not self._cur_commit_hash or 0 < self._num_commits_behind:
            return True

        return False

    def _check_github_for_update(self):
        """
        Uses pygithub to ask github if there is a newer version that the provided
        commit hash. If there is a newer version it sets SickGear's version text.

        commit_hash: hash that we're checking against
        """

        self._num_commits_behind = 0
        self._newest_commit_hash = None

        gh = github.GitHub(self.github_repo_user, self.github_repo, self.branch)

        # try to get newest commit hash and commits behind directly by comparing branch and current commit
        if self._cur_commit_hash:
            branch_compared = gh.compare(base=self.branch, head=self._cur_commit_hash)

            if 'base_commit' in branch_compared:
                self._newest_commit_hash = branch_compared['base_commit']['sha']

            if 'behind_by' in branch_compared:
                self._num_commits_behind = int(branch_compared['behind_by'])

        # fall back and iterate over last 100 (items per page in gh_api) commits
        if not self._newest_commit_hash:

            for curCommit in gh.commits():
                if not self._newest_commit_hash:
                    self._newest_commit_hash = curCommit['sha']
                    if not self._cur_commit_hash:
                        break

                if curCommit['sha'] == self._cur_commit_hash:
                    break

                # when _cur_commit_hash doesn't match anything _num_commits_behind == 100
                self._num_commits_behind += 1

        logger.debug(u'cur_commit = %s, newest_commit = %s, num_commits_behind = %s'
                     % (self._cur_commit_hash, self._newest_commit_hash, self._num_commits_behind))

    def set_newest_text(self):

        # if we're up to date then don't set this
        newest_text = None

        if not self._cur_commit_hash:
            logger.debug(u'Unknown current version number, don\'t know if we should update or not')

            newest_text = 'Unknown current version number: If you\'ve never used the SickGear upgrade system' \
                          ' before then current version is not set. &mdash; <a href="%s">Update Now</a>' \
                          % self.get_update_url()

        elif 0 < self._num_commits_behind:
            url = 'http://github.com/%s/%s' % (self.github_repo_user, self.github_repo)
            if self._newest_commit_hash:
                url += '/compare/' + self._cur_commit_hash + '...' + self._newest_commit_hash
            else:
                url += '/commits/'

            newest_text = 'There is a <a href="%s" onclick="window.open(this.href); return false;">newer' \
                          ' version available</a> (you\'re %s commit%s behind) &mdash; <a href="%s">Update Now</a>' \
                          % (url, self._num_commits_behind,
                             ('', 's')[1 < self._num_commits_behind], self.get_update_url())

        sickbeard.NEWEST_VERSION_STRING = newest_text

    def update(self):
        """
        Downloads the latest source tarball from github and installs it over the existing version.
        """

        tar_download_url = 'http://github.com/%s/%s/tarball/%s'\
                           % (self.github_repo_user, self.github_repo, self.branch)

        try:
            # prepare the update dir
            sg_update_dir = ek.ek(os.path.join, sickbeard.PROG_DIR, u'sg-update')

            if os.path.isdir(sg_update_dir):
                logger.log(u'Clearing out update folder %s before extracting' % sg_update_dir)
                shutil.rmtree(sg_update_dir)

            logger.log(u'Creating update folder %s before extracting' % sg_update_dir)
            os.makedirs(sg_update_dir)

            # retrieve file
            logger.log(u'Downloading update from %r' % tar_download_url)
            tar_download_path = os.path.join(sg_update_dir, u'sg-update.tar')
            urllib.request.urlretrieve(tar_download_url, tar_download_path)

            if not ek.ek(os.path.isfile, tar_download_path):
                logger.error(u'Unable to retrieve new version from %s, can\'t update' % tar_download_url)
                return False

            if not ek.ek(tarfile.is_tarfile, tar_download_path):
                logger.error(u'Retrieved version from %s is corrupt, can\'t update' % tar_download_url)
                return False

            # extract to sg-update dir
            logger.log(u'Extracting file %s' % tar_download_path)
            tar = tarfile.open(tar_download_path)
            tar.extractall(sg_update_dir)
            tar.close()

            # delete .tar.gz
            logger.log(u'Deleting file %s' % tar_download_path)
            os.remove(tar_download_path)

            # find update dir name
            update_dir_contents = [x for x in os.listdir(sg_update_dir) if
                                   os.path.isdir(os.path.join(sg_update_dir, x))]
            if 1 != len(update_dir_contents):
                logger.error(u'Invalid update data, update failed: %s' % update_dir_contents)
                return False
            content_dir = os.path.join(sg_update_dir, update_dir_contents[0])

            # walk temp folder and move files to main folder
            logger.log(u'Moving files from %s to %s' % (content_dir, sickbeard.PROG_DIR))
            for dirname, dirnames, filenames in os.walk(content_dir):
                dirname = dirname[len(content_dir) + 1:]
                for curfile in filenames:
                    old_path = os.path.join(content_dir, dirname, curfile)
                    new_path = os.path.join(sickbeard.PROG_DIR, dirname, curfile)

                    # Avoid DLL access problem on WIN32/64
                    # These files needing to be updated manually
                    # or find a way to kill the access from memory
                    if curfile in ('unrar.dll', 'unrar64.dll'):
                        try:
                            os.chmod(new_path, stat.S_IWRITE)
                            os.remove(new_path)
                            os.renames(old_path, new_path)
                        except (BaseException, Exception) as e:
                            logger.debug(u'Unable to update %s: %s' % (new_path, ex(e)))
                            os.remove(old_path)  # Trash the updated file without moving in new path
                        continue

                    if os.path.isfile(new_path):
                        os.remove(new_path)
                    os.renames(old_path, new_path)

            sickbeard.CUR_COMMIT_HASH = self._newest_commit_hash
            sickbeard.CUR_COMMIT_BRANCH = self.branch

        except (BaseException, Exception) as e:
            logger.error(u'Error while trying to update: %s' % ex(e))
            logger.debug(u'Traceback: %s' % traceback.format_exc())
            return False

        # Notify update successful
        notifiers.notify_git_update(sickbeard.NEWEST_VERSION_STRING)

        return True

    def list_remote_branches(self):
        gh = github.GitHub(self.github_repo_user, self.github_repo, self.branch)
        return [x['name'] for x in gh.branches() if x and 'name' in x]

    @staticmethod
    def list_remote_pulls():
        # we don't care about testers that don't use git
        return []
