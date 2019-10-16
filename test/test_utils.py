import unittest
from hyputils.hypothesis import HypothesisUtils
from hyputils.hypothesis import api_token, username, group

h = HypothesisUtils(username, api_token, group)


class TestCreateAnno(unittest.TestCase):
    def test_payload(self):
        kwargs = (('url', 'this is a url i swear'),
                  ('prefix', 'some prefix text'),
                  ('exact', 'my exact text'),
                  ('suffix', 'some suffix text'),
                  ('text', 'angry words being written about the exact text'),
                  ('tags', 'TEST:WHYHAVEYOUDONETHIS'),
                  ('document', None),
                  ('extra', None),)
        args = tuple(b for a, b in kwargs)
        payload = h.make_annotation_payload_with_target_using_only_text_quote(*args)


class TestHTTP(unittest.TestCase):
    anno_id = 'lCCu3LNFEeiAz7v-JjOpjQ'
    tags = ['RRID:AB_303684']

    def test_head(self):
        resp = h.head_annotation(self.anno_id)

    def test_get(self):
        resp = h.get_annotation(self.anno_id)
        assert resp.json()['tags'] == self.tags
