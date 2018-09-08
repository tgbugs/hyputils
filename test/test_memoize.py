import unittest
from hyputils.hypothesis import Memoizer
from hyputils.hypothesis import api_token, username, group

get_annos = Memoizer('/tmp/test-memfile.pickle', api_token, username, group)


class TestMemoize(unittest.TestCase):
    def test_0_get_start(self):
        annos = get_annos.get_annos_from_api(max_results=400)
        get_annos.memoize_annos(annos)

    def test_1_get_file(self):
        annos, lsu = get_annos.get_annos_from_file()

    def test_2_add_missin(self):
        annos, lsu = get_annos.get_annos_from_file()
        more_annos = get_annos.add_missing_annos(annos, lsu)
        assert len(more_annos) > 800 > len(annos)

    def test_3_get_rest(self):
        annos = get_annos.get_annos_from_api(max_results=400)
        get_annos.memoize_annos(annos)
        more_annos = get_annos()
        assert len(more_annos) > 800 > len(annos)
