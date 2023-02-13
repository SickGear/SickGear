# remove this file when no longer needed

import os
import importlib.util
import io
import shutil

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
    for pc in ['sickgear', 'lib']:
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
    ['.cleaned009.tmp', r'lib\scandir', [
        r'lib\scandir\__pycache__', r'lib\scandir',
    ]],
    ['.cleaned008.tmp', r'lib\tornado_py3', [
        r'lib\bs4_py2\builder\__pycache__', r'lib\bs4_py2\builder', r'lib\bs4_py2',
        r'lib\bs4_py3\builder\__pycache__', r'lib\bs4_py3\builder', r'lib\bs4_py3',
        r'lib\diskcache_py2\__pycache__', r'lib\diskcache_py2',
        r'lib\diskcache_py3\__pycache__', r'lib\diskcache_py3',
        r'lib\feedparser_py2\datetimes\__pycache__', r'lib\feedparser_py2\datetimes',
        r'lib\feedparser_py2\namespaces\__pycache__', r'lib\feedparser_py2\namespaces',
        r'lib\feedparser_py2\parsers\__pycache__', r'lib\feedparser_py2\parsers',
        r'lib\feedparser_py2\__pycache__', r'lib\feedparser_py2',
        r'lib\feedparser_py3\datetimes\__pycache__', r'lib\feedparser_py3\datetimes',
        r'lib\feedparser_py3\namespaces\__pycache__', r'lib\feedparser_py3\namespaces',
        r'lib\feedparser_py3\parsers\__pycache__', r'lib\feedparser_py3\parsers',
        r'lib\feedparser_py3\__pycache__', r'lib\feedparser_py3',
        r'lib\hachoir_py2\core\__pycache__', r'lib\hachoir_py2\core',
        r'lib\hachoir_py2\field\__pycache__', r'lib\hachoir_py2\field',
        r'lib\hachoir_py2\metadata\__pycache__', r'lib\hachoir_py2\metadata',
        r'lib\hachoir_py2\parser\__pycache__', r'lib\hachoir_py2\parser',
        r'lib\hachoir_py2\stream\__pycache__', r'lib\hachoir_py2\stream',
        r'lib\hachoir_py2\__pycache__', r'lib\hachoir_py2',
        r'lib\hachoir_py3\core\__pycache__', r'lib\hachoir_py3\core',
        r'lib\hachoir_py3\field\__pycache__', r'lib\hachoir_py3\field',
        r'lib\hachoir_py3\metadata\__pycache__', r'lib\hachoir_py3\metadata',
        r'lib\hachoir_py3\parser\__pycache__', r'lib\hachoir_py3\parser',
        r'lib\hachoir_py3\stream\__pycache__', r'lib\hachoir_py3\stream',
        r'lib\hachoir_py3\__pycache__', r'lib\hachoir_py3',
        r'lib\idna_py2\__pycache__', r'lib\idna_py2',
        r'lib\idna_py3\__pycache__', r'lib\idna_py3',
        r'lib\rarfile_py2\__pycache__', r'lib\rarfile_py2',
        r'lib\rarfile_py3\__pycache__', r'lib\rarfile_py3',
        r'lib\requests_py2\__pycache__', r'lib\requests_py2',
        r'lib\requests_py3\__pycache__', r'lib\requests_py3',
        r'lib\soupsieve_py2\__pycache__', r'lib\soupsieve_py2',
        r'lib\soupsieve_py3\__pycache__', r'lib\soupsieve_py3',
        r'lib\tornado_py2\platform\__pycache__', r'lib\tornado_py2\platform',
        r'lib\tornado_py2\__pycache__', r'lib\tornado_py2',
        r'lib\tornado_py3\platform\__pycache__', r'lib\tornado_py3\platform',
        r'lib\tornado_py3\__pycache__', r'lib\tornado_py3',
        r'lib\urllib3\packages\ssl_match_hostname\__pycache__', r'lib\urllib3\packages\ssl_match_hostname',
        r'sickbeard\clients\__pycache__', r'sickbeard\clients',
        r'sickbeard\databases\__pycache__', r'sickbeard\databases',
        r'sickbeard\indexers\__pycache__', r'sickbeard\indexers',
        r'sickbeard\metadata\__pycache__', r'sickbeard\metadata',
        r'sickbeard\name_parser\__pycache__', r'sickbeard\name_parser',
        r'sickbeard\notifiers\__pycache__', r'sickbeard\notifiers',
        r'sickbeard\providers\__pycache__', r'sickbeard\providers',
        r'sickbeard\__pycache__', r'sickbeard',
    ]],
    ['.cleaned007.tmp', r'lib\tvmaze_api', [
        r'lib\imdb_api\__pycache__', r'lib\imdb_api',
        r'lib\libtrakt\__pycache__', r'lib\libtrakt',
        r'lib\tvdb_api\__pycache__', r'lib\tvdb_api',
        r'lib\tvmaze_api\__pycache__', r'lib\tvmaze_api']],
    ['.cleaned006.tmp', r'lib\boto', [
        r'lib\boto', r'lib\growl',
        r'lib\httplib2\lib\oauth2\lib\pythontwitter\lib\tmdb_api']],
    ['.cleaned004.tmp', r'lib\requests\packages', [
        r'lib\requests\packages', r'lib\pynma']],
    ['.cleaned003.tmp', r'lib\imdb', [
        r'lib\imdb']],
    ['.cleaned002.tmp', r'lib\hachoir_core', [
        '.cleaned.tmp', 'tornado',
        r'lib\feedcache', r'lib\hachoir_core', r'lib\hachoir_metadata', r'lib\hachoir_parser',
        r'lib\jsonrpclib', r'lib\shove', r'lib\trakt', r'lib\tvrage_api', r'lib\unrar2']],
]
for cleaned_path, test_path, dir_list in cleanups:
    cleaned_file = os.path.abspath(os.path.join(parent_dir, cleaned_path))
    test = os.path.abspath(os.path.join(parent_dir, *test_path.split('\\')))

    if not os.path.isfile(cleaned_file) or os.path.exists(test):
        dead_dirs = [os.path.abspath(os.path.join(parent_dir, *d.split('\\'))) for d in dir_list]

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

        with io.open(cleaned_file, 'w+', encoding='utf-8') as fp:
            fp.write(u'This file exists to prevent a rerun delete of *.pyc, *.pyo files')
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
        msg = u'Failed (permissions?) to delete file(s). You must manually delete:\r\n%s' % '\r\n'.join(bad_files)
        print(msg)
    else:
        msg = u'This file exists to prevent a rerun delete of dead lib/html5lib files'

    with io.open(cleaned_file, 'w+', encoding='utf-8') as fp:
        fp.write(msg)
        fp.flush()
        os.fsync(fp.fileno())

try:
    os.remove(danger_output)
except (BaseException, Exception):
    pass
