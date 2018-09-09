import unittest
from hyputils.hypothesis import Memoizer, HypothesisHelper
from hyputils.hypothesis import api_token, username, group

get_annos = Memoizer('/tmp/test-memfile.pickle', api_token, username, group)

annos = get_annos()


class TestZHelper(unittest.TestCase):
    def test_0_partial(self):
        partial = [HypothesisHelper(a, annos) for a in annos[:100]]
        repr(partial)
        assert len(partial) == 100

    def test_1_helper(self):
        [HypothesisHelper(a, annos) for a in annos[100:]]
        hh = list(HypothesisHelper)
        assert len(hh) > 800
        repr(hh)

    def test_2_by_id(self):
        h = next(iter(HypothesisHelper))
        hanno = HypothesisHelper.byId(h.id)
        assert hanno == h  # that silent failure on passing in h instead of h.id though ...

    def test_3_by_id_missing(self):
        hanno = HypothesisHelper.byId('not a real id')
        assert hanno is None

    def test_4_by_tags(self):
        hannos = HypothesisHelper.byTags('RRIDCUR:Duplicate')
        assert all('RRIDCUR:Duplicate' in h.tags for h in hannos)

    def test_5_not_annos(self):
        HypothesisHelper(annos[0], annos[:10])
