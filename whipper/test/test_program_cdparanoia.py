# -*- Mode: Python; test-case-name: whipper.test.test_program_cdparanoia -*-
# vi:si:et:sw=4:sts=4:ts=4

import os
import shutil
import tempfile
import time

from whipper.extern.task import task

from whipper.program import cdparanoia

from whipper.test import common


class ParseTestCase(common.TestCase):

    def setUp(self):
        # report from Afghan Whigs - Sweet Son Of A Bitch
        path = os.path.join(os.path.dirname(__file__),
                            'cdparanoia.progress')
        self._parser = cdparanoia.ProgressParser(start=45990, stop=47719)

        self._handle = open(path)

    def testParse(self):
        for line in self._handle.readlines():
            self._parser.parse(line)

        q = '%.01f %%' % (self._parser.getTrackQuality() * 100.0, )
        self.assertEqual(q, '99.6 %')


class Parse1FrameTestCase(common.TestCase):

    def setUp(self):
        path = os.path.join(os.path.dirname(__file__),
                            'cdparanoia.progress.strokes')
        self._parser = cdparanoia.ProgressParser(start=0, stop=0)

        self._handle = open(path)

    def testParse(self):
        for line in self._handle.readlines():
            self._parser.parse(line)

        q = '%.01f %%' % (self._parser.getTrackQuality() * 100.0, )
        self.assertEqual(q, '100.0 %')


class ErrorTestCase(common.TestCase):

    def setUp(self):
        # report from a rip with offset -1164 causing scsi errors
        path = os.path.join(os.path.dirname(__file__),
                            'cdparanoia.progress.error')
        self._parser = cdparanoia.ProgressParser(start=0, stop=10800)

        self._handle = open(path)

    def testParse(self):
        for line in self._handle.readlines():
            self._parser.parse(line)

        q = '%.01f %%' % (self._parser.getTrackQuality() * 100.0, )
        self.assertEqual(q, '79.6 %')


class VersionTestCase(common.TestCase):

    def testGetVersion(self):
        v = cdparanoia.getCdParanoiaVersion()
        self.assertTrue(v)


class AnalyzeFileTask(cdparanoia.AnalyzeTask):

    def __init__(self, path):
        self.command = ['cat', path]

    def readbytesout(self, bytes_stdout):
        self.readbyteserr(bytes_stdout)


class AcceptedChecksumTestCase(common.TestCase):

    def testMatchingReads(self):
        self.assertEqual(cdparanoia.accepted_checksum(1, 1, set()), 1)

    def testMismatch(self):
        self.assertIsNone(cdparanoia.accepted_checksum(1, 2, set()))

    def testCopyMatchesEarlierTry(self):
        self.assertEqual(cdparanoia.accepted_checksum(1, 2, {3, 2}), 2)

    def testOnlyTestMatchesEarlierTry(self):
        # the copy read is what gets encoded, so it must be the one matching
        self.assertIsNone(cdparanoia.accepted_checksum(1, 2, {1}))


class FakeTask:

    def __init__(self, checksum=None):
        self.checksum = checksum
        self.quality = 1.0
        self.speed = 1.0
        self.duration = 1.0
        self.peak = 0


class ReadVerifyAcrossTriesTestCase(common.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'track.flac')
        self.earlier = set()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def tryRead(self, test, copy):
        """Run the checksum step of one try, with the given read checksums."""
        t = cdparanoia.ReadVerifyTrackTask(self.path, None, 0, 1, False,
                                           earlier_checksums=self.earlier)
        t.tasks = [FakeTask(), FakeTask(test), FakeTask(), FakeTask(copy),
                   FakeTask(), FakeTask(copy), FakeTask()]
        t.runner = object()
        t.stop()
        return t

    def testMismatchFailsAndIsRemembered(self):
        t = self.tryRead(0x11, 0x22)
        self.assertIsInstance(t.exception, cdparanoia.ChecksumException)
        self.assertEqual(self.earlier, {0x11, 0x22})
        self.assertFalse(os.path.exists(self.path))

    def testCopyMatchingEarlierTryIsKept(self):
        self.tryRead(0x11, 0x22)
        t = self.tryRead(0x33, 0x22)
        self.assertIsNone(t.exception)
        self.assertEqual(t.checksum, 0x22)
        self.assertEqual(t.testchecksum, t.copychecksum)
        self.assertTrue(os.path.exists(self.path))

    def testNewMismatchStillFails(self):
        self.tryRead(0x11, 0x22)
        t = self.tryRead(0x33, 0x44)
        self.assertIsInstance(t.exception, cdparanoia.ChecksumException)


class CacheTestCase(common.TestCase):

    def testDefeatsCache(self):
        self.runner = task.SyncRunner(verbose=False)

        path = os.path.join(os.path.dirname(__file__),
                            'cdparanoia', 'PX-L890SA.cdparanoia-A.stderr')
        t = AnalyzeFileTask(path)
        self.runner.run(t)
        self.assertTrue(t.defeatsCache)


class FakeTable:
    tracks = []


class ReadTimeoutTestCase(common.TestCase):
    """Run ReadTrackTask against a stand-in cd-paranoia on PATH."""

    def setUp(self):
        self.bindir = tempfile.mkdtemp()
        fd, self.wav = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        self.path = os.environ['PATH']
        os.environ['PATH'] = self.bindir + os.pathsep + self.path

    def tearDown(self):
        os.environ['PATH'] = self.path
        shutil.rmtree(self.bindir)
        os.unlink(self.wav)

    def _fake(self, script):
        fake = os.path.join(self.bindir, 'cd-paranoia')
        with open(fake, 'w') as f:
            f.write('#!/bin/sh\n' + script + '\n')
        os.chmod(fake, 0o755)

    def _read(self, timeout):
        t = cdparanoia.ReadTrackTask(self.wav, FakeTable(), 0, 74, False,
                                     timeout=timeout)
        started = time.time()
        try:
            task.SyncRunner(verbose=False).run(t)
        except task.TaskException as e:
            return e.exception, time.time() - started
        self.fail('the read did not fail')

    def testHangingReadTimesOut(self):
        self._fake('exec sleep 60')
        e, took = self._read(timeout=1)
        self.assertIsInstance(e, cdparanoia.ReadTimeoutError)
        self.assertLess(took, 10)

    def testFinishedReadIsNotATimeout(self):
        # exits at once without writing audio: a failure, but not a timeout,
        # although the task only looks at it after the timeout has passed
        self._fake('exit 0')
        e, _ = self._read(timeout=0.5)
        self.assertNotIsInstance(e, cdparanoia.ReadTimeoutError)
