# remove this file when no longer needed

import os
import shutil

parent_dir = os.path.abspath(os.path.dirname(__file__))
cleaned_file = os.path.abspath(os.path.join(parent_dir, '.cleaned004.tmp'))
test = os.path.abspath(os.path.join(parent_dir, 'lib', 'requests', 'packages'))
if not os.path.isfile(cleaned_file) or os.path.exists(test):
    dead_dirs = [os.path.abspath(os.path.join(parent_dir, *d)) for d in [
        ('lib', 'requests', 'packages'),
        ('lib', 'pynma')
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

cleaned_file = os.path.abspath(os.path.join(parent_dir, '.cleaned003.tmp'))
test = os.path.abspath(os.path.join(parent_dir, 'lib', 'imdb'))
if not os.path.isfile(cleaned_file) or os.path.exists(test):
    dead_dirs = [os.path.abspath(os.path.join(parent_dir, *d)) for d in [
        ('lib', 'imdb'),
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

cleaned_file = os.path.abspath(os.path.join(parent_dir, '.cleaned002.tmp'))
test = os.path.abspath(os.path.join(parent_dir, 'lib', 'hachoir_core'))
if not os.path.isfile(cleaned_file) or os.path.exists(test):
    dead_dirs = [os.path.abspath(os.path.join(parent_dir, *d)) for d in [
        ('.cleaned.tmp',),
        ('tornado',),
        ('lib', 'feedcache'),
        ('lib', 'hachoir_core'), ('lib', 'hachoir_metadata'), ('lib', 'hachoir_parser'),
        ('lib', 'jsonrpclib'),
        ('lib', 'shove'),
        ('lib', 'trakt'),
        ('lib', 'tvrage_api'),
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

cleaned_file = os.path.abspath(os.path.join(parent_dir, '.cleaned_html5lib.tmp'))
test = os.path.abspath(os.path.join(parent_dir, 'lib', 'html5lib', 'treebuilders', '_base.pyc'))
danger_output = os.path.abspath(os.path.join(parent_dir, '__README-DANGER.txt'))
bad_files = []
if not os.path.isfile(cleaned_file) or os.path.exists(test):
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
            name = '%s.py%s' % (os.path.splitext(dead_file)[:-1][0], ext)
            if os.path.exists(name):
                try:
                    os.remove(name)
                except (StandardError, Exception):
                    bad_files += [name]
    if any(bad_files):
        swap_name = cleaned_file
        cleaned_file = danger_output
        danger_output = swap_name
        msg = 'Failed (permissions?) to delete file(s). You must manually delete:\r\n%s' % '\r\n'.join(bad_files)
        print(msg)
    else:
        msg = 'This file exists to prevent a rerun delete of dead lib/html5lib files'

    with open(cleaned_file, 'wb') as fp:
        fp.write(msg)
        fp.flush()
        os.fsync(fp.fileno())

try:
    os.remove(danger_output)
except (StandardError, Exception):
    pass
