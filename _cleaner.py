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

cleaned_file = os.path.abspath(os.path.join(parent_dir, r'.cleaned_html5lib.tmp'))
if not os.path.isfile(cleaned_file):
    for dead_path in [os.path.abspath(os.path.join(parent_dir, *d)) for d in [
        ('lib', 'html5lib', 'trie'),
        ('lib', 'html5lib', 'serializer')
    ]]:
        try:
            shutil.rmtree(dead_path)
        except (StandardError, Exception):
            pass

    for dead_file in [os.path.abspath(os.path.join(parent_dir, *d)) for d in [
        ('lib', 'html5lib', 'ihatexml.py'),
        ('lib', 'html5lib', 'inputstream.py'),
        ('lib', 'html5lib', 'tokenizer.py'),
        ('lib', 'html5lib', 'utils.py'),
        ('lib', 'html5lib', 'filters', '_base.py'),
        ('lib', 'html5lib', 'sanitizer.py'),
        ('lib', 'html5lib', 'treebuilders', '_base.py'),
        ('lib', 'html5lib', 'treewalkers', '_base.py'),
        ('lib', 'html5lib', 'treewalkers', 'lxmletree.py'),
        ('lib', 'html5lib', 'treewalkers', 'genshistream.py'),
    ]]:
        for ext in ['', 'c', 'o']:
            try:
                os.remove('%s.py%s' % (os.path.splitext(dead_file)[:-1][0], ext))
            except (StandardError, Exception):
                pass

    with open(cleaned_file, 'wb') as fp:
        fp.write('This file exists to prevent a rerun delete of dead lib/html5lib files')
        fp.flush()
        os.fsync(fp.fileno())
