import unittest
from hyputils.hypothesis import Memoizer, HypothesisHelper
from hyputils.hypothesis import api_token, username, group, group_to_memfile

get_annos = Memoizer(group_to_memfile(group), api_token, username, group)

annos = get_annos()


class TestZHelper(unittest.TestCase):
    """ NOTE these tests are stateful """

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

    def test_4_populate(self):
        [h.populateTags() for h in HypothesisHelper]

    def test_5_by_tags(self):
        test_tag = None
        max_tags = 0
        for tag, tset in HypothesisHelper._tagIndex.items():
            lt = len(tset)
            if lt > max_tags:
                max_tags = lt
                test_tag = tag
        hannos = HypothesisHelper.byTags(test_tag)
        assert all(test_tag in h.tags for h in hannos)

    def test_6_not_annos(self):
        HypothesisHelper(annos[0], annos[:10])
