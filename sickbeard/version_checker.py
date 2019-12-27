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
import traceback
from . import gh_api as github

# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex

import sickbeard
from . import logger, notifiers, ui
from .helpers import cmdline_runner

# noinspection PyUnresolvedReferences
from six.moves import urllib


class CheckVersion(object):
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

        if self.check_for_new_version(force):
            if sickbeard.AUTO_UPDATE:
                logger.log(u'New update found for SickGear, starting auto-updater...')
                ui.notifications.message('New update found for SickGear, starting auto-updater')
                if sickbeard.versionCheckScheduler.action.update():
                    logger.log(u'Update was successful!')
                    ui.notifications.message('Update was successful')
                    sickbeard.events.put(sickbeard.events.SystemEvent.RESTART)

    @staticmethod
    def find_install_type():
        """
        Determines how this copy of sg was installed.

        returns: type of installation. Possible values are:
            'git': running from source using git
            'source': running from source without git
        """

        if os.path.isdir(ek.ek(os.path.join, sickbeard.PROG_DIR, u'.git')):
            return 'git'
        return 'source'

    def check_for_new_version(self, force=False):
        """
        Checks the internet for a newer version.

        returns: bool, True for new version or False for no new version.

        force: if true the VERSION_NOTIFY setting will be ignored and a check will be forced
        """

        if not sickbeard.VERSION_NOTIFY and not sickbeard.AUTO_UPDATE and not force:
            logger.log(u'Version checking is disabled, not checking for the newest version')
            return False

        if not sickbeard.AUTO_UPDATE:
            logger.log(u'Checking if %s needs an update' % self.install_type)
        if not self.updater.need_update():
            sickbeard.NEWEST_VERSION_STRING = None
            if not sickbeard.AUTO_UPDATE:
                logger.log(u'No update needed')

            if force:
                ui.notifications.message('No update needed')
            return False

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
        self._git_path = self._find_working_git()
        self.github_repo_user = self.get_github_repo_user()
        self.github_repo = self.get_github_repo()

        self.branch = sickbeard.BRANCH
        if '' == sickbeard.BRANCH:
            self.branch = self._find_installed_branch()

        self._cur_commit_hash = None
        self._newest_commit_hash = None
        self._num_commits_behind = 0
        self._num_commits_ahead = 0
        self._cur_pr_number = self.get_cur_pr_number()

    def _find_working_git(self):
        test_cmd = 'version'

        if sickbeard.GIT_PATH:
            main_git = '"%s"' % sickbeard.GIT_PATH
        else:
            main_git = 'git'

        logger.log(u'Checking if we can use git commands: %s %s' % (main_git, test_cmd), logger.DEBUG)
        output, err, exit_status = self._run_git(main_git, test_cmd)

        if 0 == exit_status:
            logger.log(u'Using: %s' % main_git, logger.DEBUG)
            return main_git
        else:
            logger.log(u'Not using: %s' % main_git, logger.DEBUG)

        # trying alternatives

        alternative_git = []

        # osx people who start sg from launchd have a broken path, so try a hail-mary attempt for them
        if 'darwin' == platform.system().lower():
            alternative_git.append('/usr/local/git/bin/git')

        if 'windows' == platform.system().lower():
            if main_git != main_git.lower():
                alternative_git.append(main_git.lower())

        if alternative_git:
            logger.log(u'Trying known alternative git locations', logger.DEBUG)

            for cur_git in alternative_git:
                logger.log(u'Checking if we can use git commands: ' + cur_git + ' ' + test_cmd, logger.DEBUG)
                output, err, exit_status = self._run_git(cur_git, test_cmd)

                if 0 == exit_status:
                    logger.log(u'Using: %s' % cur_git, logger.DEBUG)
                    return cur_git
                logger.log(u'Not using: %s' % cur_git, logger.DEBUG)

        # Still haven't found a working git
        error_message = 'Unable to find your git executable - Shutdown SickGear and EITHER set git_path' \
                        ' in your config.ini OR delete your .git folder and run from source to enable updates.'
        sickbeard.NEWEST_VERSION_STRING = error_message

    @staticmethod
    def _run_git(git_path, args):

        output = err = None
        exit_status = 1

        if not git_path:
            logger.log(u'No git specified, cannot use git commands', logger.ERROR)
            return output, err, exit_status

        cmd = '%s %s' % (git_path, args)

        try:
            logger.log(u'Executing %s with your shell in %s' % (cmd, sickbeard.PROG_DIR), logger.DEBUG)
            output, err, exit_status = cmdline_runner(cmd, shell=True)
            logger.log(u'git output: %s' % output, logger.DEBUG)

        except OSError:
            logger.log(u'Failed command: %s' % cmd)

        if 0 == exit_status:
            logger.log(u'Successful return: %s' % cmd, logger.DEBUG)
            exit_status = 0

        elif 1 == exit_status:
            logger.log(u'Failed: %s returned: %s' % (cmd, output), logger.ERROR)

        elif 128 == exit_status or 'fatal:' in output or err:
            logger.log(u'Fatal: %s returned: %s' % (cmd, output), logger.ERROR)
            exit_status = 128

        else:
            logger.log(u'Treat as error for now, command: %s returned: %s' % (cmd, output), logger.ERROR)

        return output, err, exit_status

    def _find_installed_version(self):
        """
        Attempts to find the currently installed version of SickGear.
        Uses git show to get commit version.
        Returns: True for success or False for failure
        """

        output, err, exit_status = self._run_git(self._git_path, 'rev-parse HEAD')

        if 0 == exit_status and output:
            cur_commit_hash = output.strip()
            if not re.match(r'^[a-z0-9]+$', cur_commit_hash):
                logger.log(u'Output doesn\'t look like a hash, not using it', logger.ERROR)
                return False
            self._cur_commit_hash = cur_commit_hash
            sickbeard.CUR_COMMIT_HASH = str(cur_commit_hash)
            return True
        return False

    def _find_installed_branch(self):
        branch_info, err, exit_status = self._run_git(self._git_path, 'symbolic-ref -q HEAD')
        if 0 == exit_status and branch_info:
            branch = branch_info.strip().replace('refs/heads/', '', 1)
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
        output, err, exit_status = self._run_git(self._git_path, 'fetch %s' % sickbeard.GIT_REMOTE)

        if 0 != exit_status:
            logger.log(u'Unable to contact github, can\'t check for update', logger.ERROR)
            return

        if not self._cur_pr_number:

            # get latest commit_hash from remote
            output, err, exit_status = self._run_git(self._git_path, 'rev-parse --verify --quiet "@{upstream}"')

            if 0 == exit_status and output:
                cur_commit_hash = output.strip()

                if not re.match('^[a-z0-9]+$', cur_commit_hash):
                    logger.log(u'Output doesn\'t look like a hash, not using it', logger.DEBUG)
                    return

                else:
                    self._newest_commit_hash = cur_commit_hash
            else:
                logger.log(u'git didn\'t return newest commit hash', logger.DEBUG)
                return

            # get number of commits behind and ahead (option --count not supported git < 1.7.2)
            output, err, exit_status = self._run_git(self._git_path, 'rev-list --left-right "@{upstream}"...HEAD')

            if 0 == exit_status and output:

                try:
                    self._num_commits_behind = int(output.count('<'))
                    self._num_commits_ahead = int(output.count('>'))

                except (BaseException, Exception):
                    logger.log(u'git didn\'t return numbers for behind and ahead, not using it', logger.DEBUG)
                    return

            logger.log(u'cur_commit = %s, newest_commit = %s, num_commits_behind = %s, num_commits_ahead = %s' % (
                self._cur_commit_hash, self._newest_commit_hash, self._num_commits_behind, self._num_commits_ahead),
                       logger.DEBUG)
        else:
            # we need to treat pull requests specially as it doesn't seem possible to set their "@{upstream}" tag
            output, err, exit_status = self._run_git(self._git_path, 'ls-remote %s refs/pull/%s/head'
                                                     % (sickbeard.GIT_REMOTE, self._cur_pr_number))
            self._newest_commit_hash = re.findall('(.*)\t', output)[0]

    def set_newest_text(self):
        # if we're up to date then don't set this
        newest_text = None
        url = 'http://github.com/%s/%s' % (self.github_repo_user, self.github_repo)

        if self._num_commits_ahead:
            logger.log(u'Local branch is ahead of %s. Automatic update not possible.' % self.branch, logger.ERROR)
            newest_text = 'Local branch is ahead of %s. Automatic update not possible.' % self.branch

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
            logger.log(u'Branch checkout: %s->%s' % (self._find_installed_branch(), self.branch), logger.DEBUG)
            return True

        self._find_installed_version()
        if not self._cur_commit_hash:
            return True
        else:
            try:
                self._check_github_for_update()
            except (BaseException, Exception) as e:
                logger.log(u'Unable to contact github, can\'t check for update: %r' % e, logger.ERROR)
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
                output, err, exit_status = self._run_git(self._git_path, 'pull -f %s %s'
                                                         % (sickbeard.GIT_REMOTE, self.branch))
            else:
                output, err, exit_status = self._run_git(self._git_path, 'pull -f %s pull/%s/head:%s'
                                                         % (sickbeard.GIT_REMOTE, self._cur_pr_number, self.branch))

        else:
            output, err, exit_status = self._run_git(self._git_path, 'checkout -f %s'
                                                     % self.branch)

        if 0 == exit_status:
            self._find_installed_version()

            # Notify update successful
            notifiers.notify_git_update(sickbeard.CUR_COMMIT_HASH if sickbeard.CUR_COMMIT_HASH else '')
            return True

        return False

    def list_remote_branches(self):
        branches, err, exit_status = self._run_git(self._git_path, 'ls-remote --heads %s'
                                                   % sickbeard.GIT_REMOTE)
        if 0 == exit_status and branches:
            return re.findall(r'\S+\Wrefs/heads/(.*)', branches)
        return []

    def list_remote_pulls(self):
        gh = github.GitHub(self.github_repo_user, self.github_repo, self.branch)
        return gh.pull_requests()

    def fetch(self, pull_request):
        output, err, exit_status = self._run_git(self._git_path, 'fetch -f %s %s'
                                                 % (sickbeard.GIT_REMOTE, pull_request))
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
            logger.log(u'Unable to contact github, can\'t check for update: %r' % e, logger.ERROR)
            return False

        if self.branch != self._find_installed_branch():
            logger.log(u'Branch checkout: %s->%s' % (self._find_installed_branch(), self.branch), logger.DEBUG)
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

        logger.log(u'cur_commit = %s, newest_commit = %s, num_commits_behind = %s'
                   % (self._cur_commit_hash, self._newest_commit_hash, self._num_commits_behind), logger.DEBUG)

    def set_newest_text(self):

        # if we're up to date then don't set this
        newest_text = None

        if not self._cur_commit_hash:
            logger.log(u'Unknown current version number, don\'t know if we should update or not', logger.DEBUG)

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
                logger.log(u'Unable to retrieve new version from %s, can\'t update' % tar_download_url, logger.ERROR)
                return False

            if not ek.ek(tarfile.is_tarfile, tar_download_path):
                logger.log(u'Retrieved version from %s is corrupt, can\'t update' % tar_download_url, logger.ERROR)
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
                logger.log(u'Invalid update data, update failed: %s' % update_dir_contents, logger.ERROR)
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
                            logger.log(u'Unable to update %s: %s' % (new_path, ex(e)), logger.DEBUG)
                            os.remove(old_path)  # Trash the updated file without moving in new path
                        continue

                    if os.path.isfile(new_path):
                        os.remove(new_path)
                    os.renames(old_path, new_path)

            sickbeard.CUR_COMMIT_HASH = self._newest_commit_hash
            sickbeard.CUR_COMMIT_BRANCH = self.branch

        except (BaseException, Exception) as e:
            logger.log(u'Error while trying to update: %s' % ex(e), logger.ERROR)
            logger.log(u'Traceback: %s' % traceback.format_exc(), logger.DEBUG)
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
