import os
import unittest
from time import sleep
import pytest
from hyputils.handlers import annotationSyncHandler
from hyputils.subscribe import AnnotationStream, preFilter
from hyputils.hypothesis import group

# TODO use our own little websocket server to send annos as if they came from hypothesis

class FakeMem:
    def memoize_annos(self, annos):
        print([anno._row for anno in annos])


class TestStream(unittest.TestCase):
    def test_0_stream(self):
        annos = []
        prefilter = preFilter(groups=['__world__', group], users=['tgbugstest']).export()
        annoStream = AnnotationStream(annos,
                                      prefilter,
                                      annotationSyncHandler)
        stream_thread, exit_loop = annoStream()
        stream_thread.start()
        sleep(1)
        exit_loop()
        stream_thread.join()

    @pytest.mark.skip(reason='local test interactive and blocks')
    def test_9999_get_from_ws(self):
        from IPython import embed
        fake_mem = FakeMem()
        annos = []
        prefilter = preFilter(groups=['__world__', group]).export()
        annoStream = AnnotationStream(annos,
                                      prefilter,
                                      annotationSyncHandler,
                                      memoizer=fake_mem)
        stream_thread, exit_loop = annoStream()
        stream_thread.start()
        embed()
        exit_loop()
        stream_thread.join()
