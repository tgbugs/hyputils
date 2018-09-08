import unittest
from hyputils.hypothesis import Memoizer
from hyputils.hypothesis import api_token, username, group

get_annos = Memoizer('/tmp/test-memfile.pickle', api_token, username, group)

class TestMemoize(unittest.TestCase):
    def test_get_start(self):
        annos = get_annos.get_annos_from_api(max_results=400)
        get_annos.memoize_annos(annos)

    def test_get_file(self):
        annos = get_annos.get_annos_from_file()

    def test_get_rest(self):
        annos = get_annos()
