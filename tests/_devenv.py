# /tests/_devenv.py
#
# To trigger dev env
#
# import _devenv as devenv
#

__remotedebug__ = True

if __remotedebug__:
    import sys
    sys.path.append('C:\Program Files\JetBrains\PyCharm 2017.2.1\debug-eggs\pycharm-debug.egg')
    import pydevd


    def setup_devenv(state):
        pydevd.settrace('localhost', port=(65001, 65000)[bool(state)], stdoutToServer=True, stderrToServer=True,
                        suspend=False)


def stop():
    pydevd.stoptrace()
