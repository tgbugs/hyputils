import unittest
from hyputils.hypothesis import Memoizer, HypothesisHelper
from hyputils.hypothesis import api_token, username, group

get_annos = Memoizer('/tmp/test-memfile.pickle', api_token, username, group)


class TestZHelper(unittest.TestCase):
    def test_helper(self):
        annos = get_annos()
        [HypothesisHelper(a, annos) for a in annos]
        hh = list(HypothesisHelper)
        assert len(hh) > 800
        r = repr(hh)
