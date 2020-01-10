# remove this file when no longer needed

import os
import io
import shutil
import sys

if 2 == sys.version_info[0]:
    # noinspection PyDeprecation
    import imp

    # noinspection PyDeprecation
    magic_number = imp.get_magic().encode('hex').decode('utf-8')
else:
    import importlib.util

    magic_number = importlib.util.MAGIC_NUMBER.hex()

parent_dir = os.path.abspath(os.path.dirname(__file__))
magic_number_file = os.path.join(parent_dir, '.python_magic.tmp')
old_magic = ''
try:
    if os.path.isfile(magic_number_file):
        with io.open(magic_number_file, 'r', encoding='utf-8') as mf:
            old_magic = mf.read()
except (BaseException, Exception):
    pass

if old_magic != magic_number:
    # print('Python magic changed: removing all .pyc, .pyo files')
    for pc in ['sickbeard', 'lib']:
        search_dir = os.path.join(parent_dir, pc)
        for dpath, dnames, fnames in os.walk(search_dir):
            for filename in [fn for fn in fnames if os.path.splitext(fn)[-1].lower() in ('.pyc', '.pyo')]:
                try:
                    os.remove(os.path.abspath(os.path.join(dpath, filename)))
                except (BaseException, Exception):
                    pass

    try:
        with io.open(magic_number_file, 'w+') as mf:
            mf.write(magic_number)
    except (BaseException, Exception):
        pass
    # print('finished')

# skip cleaned005 as used during dev by testers
cleanups = [
    ['.cleaned006.tmp', ('lib', 'bs4', 'builder'), [
        ('lib', 'boto'), ('lib', 'bs4', 'builder'), ('lib', 'growl'),
        ('lib', 'hachoir', 'core'), ('lib', 'hachoir', 'field'), ('lib', 'hachoir', 'metadata'),
        ('lib', 'hachoir', 'parser', 'archive'), ('lib', 'hachoir', 'parser', 'audio'),
        ('lib', 'hachoir', 'parser', 'common'), ('lib', 'hachoir', 'parser', 'container'),
        ('lib', 'hachoir', 'parser', 'image'), ('lib', 'hachoir', 'parser', 'misc'),
        ('lib', 'hachoir', 'parser', 'network'), ('lib', 'hachoir', 'parser', 'program'),
        ('lib', 'hachoir', 'parser', 'video'), ('lib', 'hachoir', 'parser'), ('lib', 'hachoir', 'stream'),
        ('lib', 'httplib2'), ('lib', 'oauth2'), ('lib', 'pythontwitter'), ('lib', 'tmdb_api')]],
    ['.cleaned004.tmp', ('lib', 'requests', 'packages'), [
        ('lib', 'requests', 'packages'), ('lib', 'pynma')]],
    ['.cleaned003.tmp', ('lib', 'imdb'), [
        ('lib', 'imdb')]],
    ['.cleaned002.tmp', ('lib', 'hachoir_core'), [
        ('.cleaned.tmp',), ('tornado',),
        ('lib', 'feedcache'), ('lib', 'hachoir_core'), ('lib', 'hachoir_metadata'), ('lib', 'hachoir_parser'),
        ('lib', 'jsonrpclib'), ('lib', 'shove'), ('lib', 'trakt'), ('lib', 'tvrage_api'), ('lib', 'unrar2')]],
]
for cleaned_path, test_path, dir_list in cleanups:
    cleaned_file = os.path.abspath(os.path.join(parent_dir, cleaned_path))
    test = os.path.abspath(os.path.join(parent_dir, *test_path))

    if not os.path.isfile(cleaned_file) or os.path.exists(test):
        dead_dirs = [os.path.abspath(os.path.join(parent_dir, *d)) for d in dir_list]

        for dpath, dnames, fnames in os.walk(parent_dir):
            for dead_dir in filter(lambda x: x in dead_dirs, [os.path.abspath(os.path.join(dpath, d)) for d in dnames]):
                try:
                    shutil.rmtree(dead_dir)
                except (BaseException, Exception):
                    pass

            for filename in [fn for fn in fnames if os.path.splitext(fn)[-1].lower() in ('.pyc', '.pyo')]:
                try:
                    os.remove(os.path.abspath(os.path.join(dpath, filename)))
                except (BaseException, Exception):
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
        except (BaseException, Exception):
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
                except (BaseException, Exception):
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
except (BaseException, Exception):
    pass
