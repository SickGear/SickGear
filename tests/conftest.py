# pytest, e.g. as an IDE runs tests, imports these as modules of the tests package, so add their folder to the path
# for their plain imports, e.g. import test_lib
import sys
from os.path import abspath, dirname

sys.path.insert(1, dirname(abspath(__file__)))
