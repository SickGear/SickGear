# remove this file when no longer needed

import os
import shutil

parent_dir = os.path.abspath(os.path.dirname(__file__))
cleaned_file = os.path.abspath(os.path.join(parent_dir, r'.cleaned.tmp'))
if not os.path.isfile(cleaned_file):
    dead_dirs = [os.path.abspath(os.path.join(parent_dir, *d)) for d in [
        ('tornado',),
        ('lib', 'feedcache'),
        ('lib', 'jsonrpclib'),
        ('lib', 'shove'),
        ('lib', 'unrar2')
    ]]

    for dirpath, dirnames, filenames in os.walk(parent_dir):
        for dead_dir in filter(lambda x: x in dead_dirs, [os.path.abspath(os.path.join(dirpath, d)) for d in dirnames]):
            try:
                shutil.rmtree(dead_dir)
            except (StandardError, Exception):
                pass

        for filename in [fn for fn in filenames if os.path.splitext(fn)[-1].lower() in ('.pyc', '.pyo')]:
            try:
                os.remove(os.path.abspath(os.path.join(dirpath, filename)))
            except (StandardError, Exception):
                pass

    with open(cleaned_file, 'wb') as fp:
        fp.write('This file exists to prevent a rerun delete of *.pyc, *.pyo files')
        fp.flush()
        os.fsync(fp.fileno())
