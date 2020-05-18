import unittest
from pathlib import Path
from hyputils.hypothesis import Memoizer
from hyputils.hypothesis import api_token, username, group, group_to_memfile

bad_memfile = 'test-bad-memfile.json'


class TestMemoize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.get_annos = Memoizer(group_to_memfile(group), api_token, username, group)

        world_get = Memoizer(bad_memfile, api_token, username, '__world__')
        world_annos = world_get.get_annos_from_api(max_results=10)
        world_get.memoize_annos(world_annos)

    @classmethod
    def tearDownClass(cls):
        Path(bad_memfile).unlink()

    def test_0_get_start(self):
        annos = self.get_annos.get_annos_from_api(max_results=400)
        self.get_annos.memoize_annos(annos)
        assert len(annos) == 400

    def test_1_get_file(self):
        annos, lsu = self.get_annos.get_annos_from_file()
        assert len(annos) == 400

    def test_2_add_missing(self):
        annos, lsu = self.get_annos.get_annos_from_file()
        assert len(annos) == 400
        more_annos = self.get_annos.add_missing_annos(annos, lsu)
        assert len(more_annos) > 800

    def test_3_get_rest(self):
        annos = self.get_annos.get_annos_from_api(max_results=400)
        self.get_annos.memoize_annos(annos)
        more_annos = self.get_annos()
        assert len(more_annos) > 800 > len(annos)

    def test_4_group_mismatch_at_load_from_file(self):
        group_get = Memoizer(bad_memfile, api_token, username, group)
        try:
            world_annos = group_get.get_annos_from_file()
            raise AssertionError('should have failed due to group mismatch with __world__')
        except Memoizer.GroupMismatchError as e:
            pass

    def test_5_group_mismatch_at_add_missing(self):
        group_get = Memoizer(bad_memfile, api_token, username, group)
        try:
            group_get.get_annos()
            raise AssertionError('should have failed due to group mismatch with __world__')
        except Memoizer.GroupMismatchError as e:
            pass
