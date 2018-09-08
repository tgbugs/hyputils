import unittest
from hyputils.hypothesis import AnnoFetcher
from hyputils.hypothesis import api_token, username, group
from IPython import embed

get_annos = AnnoFetcher(api_token, username, group)


class TestFetch(unittest.TestCase):
    def test_max_results(self):
        annos = get_annos.get_annos_from_api(max_results=400)

    def test_stop_at(self):
        _annos = get_annos.get_annos_from_api(max_results=400)

        in_ = _annos[236]
        sanity = _annos[:237]
        assert in_ == sanity[-1]
        assert len(sanity) == 237

        stop_at = _annos[236].updated
        annos = get_annos.get_annos_from_api(stop_at=stop_at)

        assert len(annos) == 237

    def test_search_after(self):
        annos = get_annos.get_annos_from_api(max_results=200)
        stop_at = annos[100].updated
        search_after = annos[99].updated
        annos = get_annos.get_annos_from_api(search_after=search_after, stop_at=stop_at)
        assert len(annos) == 1

    def test_mr_lower(self):
        annos = get_annos.get_annos_from_api(max_results=200)
        stop_at = annos[150].updated
        annos = get_annos.get_annos_from_api(stop_at=stop_at, max_results=100)
        assert len(annos) == 100

    def test_sa_lower(self):
        annos = get_annos.get_annos_from_api(max_results=50)
        stop_at = annos[-1].updated
        annos = get_annos.get_annos_from_api(stop_at=stop_at, max_results=100)
        print(len(annos))
        assert len(annos) == 50

    def test_bad_stop(self):
        try:
            annos = get_annos.get_annos_from_api(max_results=50)
            stop_at = annos[-1]  # passing annotaiton instead of updated
            annos = get_annos.get_annos_from_api(stop_at=stop_at, max_results=100)
            raise AssertionError('should fail due to a type error from annos[-1]')
        except TypeError:
            pass
