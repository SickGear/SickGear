import unittest

import subprocess
import os


class CompatibilityTests(unittest.TestCase):

    def test_except(self):
        path = os.path.abspath('..')
        pyfiles = []
        for rootdir in ['sickbeard', 'tests']:
            for dirpath, subdirs, files in os.walk(os.path.join(path, rootdir)):
                for x in files:
                    if x.endswith('.py'):
                        pyfiles.append(os.path.join(dirpath, x))

        pyfiles.append(os.path.join(path, 'sickgear.py'))

        output = subprocess.Popen('2to3'
                                  ' -f except'
                                  ' -f numliterals'
                                  ' %s' % ' '.join(pyfiles), shell=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE).communicate()[0]
        if output:
            print('Changes to be made for Python 2/3 compatibility as follows:')
            print(output)
            self.fail('Python 2/3 incompatibility detected')


if '__main__' == __name__:
    suite = unittest.TestLoader().loadTestsFromTestCase(QualityTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
