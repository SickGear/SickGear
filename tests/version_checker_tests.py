import sys
import unittest
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from sickgear import logger
from sickgear.version_checker import log_output


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


if '__main__' == __name__:
    unittest.main()
