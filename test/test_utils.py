import unittest
from hyputils.hypothesis import HypothesisUtils
from hyputils.hypothesis import api_token, username, group

h = HypothesisUtils(username, api_token, group)


class TestHTTP(unittest.TestCase):
    anno_id = 'lCCu3LNFEeiAz7v-JjOpjQ'
    tags = ['RRID:AB_303684']

    def test_head(self):
        resp = h.head_annotation(self.anno_id)

    def test_get(self):
        resp = h.get_annotation(self.anno_id)
        assert resp.json()['tags'] == self.tags
