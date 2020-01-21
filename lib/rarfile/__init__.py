import sys

name = 'rarfile'

locals()[name] = __import__(name)
if None is not name:
    sub_name = name + '_py' + ('3', '2')[2 == sys.version_info[0]]
    sys.modules[name] = __import__(sub_name)
    package = __import__('%s.%s' % (sub_name, name), globals(), locals(), [], 0)
    sys.modules.update({name: package, 'lib.%s' % name: package})
