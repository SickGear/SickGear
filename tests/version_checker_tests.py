import sys
import unittest
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from sickgear import logger
from sickgear.version_checker import log_output, remote_web_url


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


if '__main__' == __name__:
    unittest.main()
