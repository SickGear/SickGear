import gc
import shutil
import sys
import tempfile
import unittest
import weakref
from os.path import abspath, dirname, join
from unittest import mock

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from Cheetah.Template import Template

import sickgear
from sickgear.webserve import PageTemplate


class PageData(object):
    pass


class PageTemplateTests(unittest.TestCase):
    """ a page template is freed with its page data when the page is made, without a garbage collection """

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.file = join(self.tmp_dir, 'page.tmpl')
        with open(self.file, 'w') as f:
            f.write('#for $cur_line in $lines\n$cur_line\n#end for\n#include $join($tmp_dir, "inc.tmpl")\n')
        with open(join(self.tmp_dir, 'inc.tmpl'), 'w') as f:
            f.write('end\n')
        self.cache_dir = sickgear.CACHE_DIR
        sickgear.CACHE_DIR = self.tmp_dir
        self.web_handler = mock.Mock(**{'request.headers': {'Host': 'localhost:8081'},
                                        'xsrf_form_html.return_value': '<input/>',
                                        'application.is_loading_handler': True})
        gc.disable()

    def tearDown(self):
        gc.enable()
        sickgear.CACHE_DIR = self.cache_dir
        shutil.rmtree(self.tmp_dir)

    @staticmethod
    def templates():
        return len([cur_o for cur_o in gc.get_objects() if isinstance(cur_o, Template)])

    def test_page_data_is_freed(self):
        templates = self.templates()
        data = PageData()
        data.lines = ['line 1', 'line 2']
        ref_data = weakref.ref(data)
        t = PageTemplate(web_handler=self.web_handler, file=self.file,
                         searchList=[{'lines': data.lines, 'join': join, 'tmp_dir': self.tmp_dir}])
        t.data = data
        # a page value with the name of a template method, as the restart page has
        t.shutdown = True
        ref_t = weakref.ref(t)
        del data

        self.assertEqual(['line 1', 'line 2', 'end'], t.respond().splitlines())
        del t
        self.assertIsNone(ref_t())
        self.assertIsNone(ref_data())
        # the included template too
        self.assertEqual(templates, self.templates())


if '__main__' == __name__:
    suite = unittest.TestLoader().loadTestsFromTestCase(PageTemplateTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
