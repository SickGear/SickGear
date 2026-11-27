import shutil
import subprocess
import sys
import tempfile
import unittest
from os.path import abspath, dirname, join
from unittest import mock

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import sg_helpers
import sickgear
from sickgear import logger
from sickgear.version_checker import GitUpdateManager, log_output, remote_web_url


class LogOutputTests(unittest.TestCase):
    """ the output of a git command is one line in the log file, the log page splits it into its lines again """

    def test_one_line(self):
        self.assertEqual('7d0d5a0', log_output('7d0d5a0\n'))

    def test_lines_joined(self):
        self.assertEqual(f'a\tx{logger.JOINED_LINES}b', log_output('a\tx\n\nb\n'))
        self.assertEqual(' \\n ', logger.JOINED_LINES)

    def test_all_output_kept(self):
        heads = ''.join(f'{_n:040x}\trefs/heads/feature/Branch{_n}\n' for _n in range(32))
        result = log_output(heads)
        self.assertNotIn('\n', result)
        self.assertEqual(heads.splitlines(), result.split(logger.JOINED_LINES))

    def test_no_output(self):
        self.assertEqual('', log_output(None))
        self.assertEqual('', log_output(''))


class RemoteWebUrlTests(unittest.TestCase):
    """ the newer version link goes to the site of the git remote in use, a GitLab path has the /- part """

    def test_gitlab_ssh(self):
        self.assertEqual('https://gitlab.com/SickGear/SickGear/-',
                         remote_web_url('git@gitlab.com:SickGear/SickGear.git'))

    def test_github_https(self):
        self.assertEqual('https://github.com/SickGear/SickGear',
                         remote_web_url('https://github.com/SickGear/SickGear.git\n'))

    def test_ssh_url_with_user_and_port(self):
        self.assertEqual('https://gitlab.com/a/b/-', remote_web_url('ssh://git@gitlab.com:22/a/b.git'))

    def test_unknown_gives_github(self):
        for cur_url in (None, '', 'D:/local/repo'):
            self.assertEqual('https://github.com/SickGear/SickGear', remote_web_url(cur_url))


class RewrittenBranchTests(unittest.TestCase):
    """ a force push that rebuilt the remote branch with the same code leaves the local branch ahead and behind, the
    update resets to the remote branch when the local code is in it, a local change still stops the update """

    def git(self, cwd, *args):
        return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t'] + list(args), cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.remote, self.local = join(self.tmp, 'remote'), join(self.tmp, 'local')
        self.git(self.tmp, 'init', '-q', '-b', 'dev', self.remote)
        for cur_n in ('1', '2'):
            with open(join(self.remote, 'f.txt'), 'w') as fh:
                fh.write(cur_n)
            self.git(self.remote, 'add', 'f.txt')
            self.git(self.remote, 'commit', '-q', '-m', cur_n)
        self.git(self.tmp, 'clone', '-q', '-b', 'dev', self.remote, self.local)
        # rebuild the last remote commit with the same tree and another parent line, as a force push does
        first = self.git(self.remote, 'rev-list', '--max-parents=0', 'HEAD')
        twin = self.git(self.remote, 'commit-tree', f'{first}^{{tree}}', '-m', '1 again')
        self.git(self.remote, 'reset', '-q', '--hard',
                 self.git(self.remote, 'commit-tree', 'HEAD^{tree}', '-p', twin, '-m', '2 again'))
        self.patches = [mock.patch.object(sg_helpers, 'PROG_DIR', self.local),
                        mock.patch.multiple(sickgear, PROG_DIR=self.local, GIT_REMOTE='origin')]
        [cur_p.start() for cur_p in self.patches]
        self.gum = object.__new__(GitUpdateManager)
        self.gum.__dict__.update(unsafe=False, _git_path='git', branch='dev', _cur_pr_number=None, _rewritten=False,
                                 _cur_commit_hash=self.git(self.local, 'rev-parse', 'HEAD'), _newest_commit_hash=None,
                                 _old_commit_hash=None, _old_branch=None, _num_commits_behind=0, _num_commits_ahead=0)

    def tearDown(self):
        [cur_p.stop() for cur_p in self.patches]
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_code_updates(self):
        self.gum._check_github_for_update()
        self.assertEqual((2, 0), (self.gum._num_commits_behind, self.gum._num_commits_ahead))
        with mock.patch('sickgear.version_checker.notifiers'), \
                mock.patch.object(GitUpdateManager, '_is_python_supported', return_value=True):
            self.assertTrue(self.gum.update())
        self.assertEqual(self.git(self.remote, 'rev-parse', 'HEAD'), self.git(self.local, 'rev-parse', 'HEAD'))

    def test_local_change_stops_update(self):
        with open(join(self.local, 'f.txt'), 'w') as fh:
            fh.write('local')
        self.git(self.local, 'commit', '-q', '-am', 'local')
        self.gum._check_github_for_update()
        self.assertEqual(3, self.gum._num_commits_ahead)


if '__main__' == __name__:
    unittest.main()
