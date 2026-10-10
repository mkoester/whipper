# -*- Mode: Python; test-case-name: whipper.test.test_program_cdparanoia -*-
# vi:si:et:sw=4:sts=4:ts=4

import builtins
import os
import shutil
import tempfile
import time

from whipper.program import cdrdao
from whipper.test import common

# TODO: Current test architecture makes testing cdrdao difficult. Revisit.


class VersionTestCase(common.TestCase):
    def testGetVersion(self):
        v = cdrdao.version()
        self.assertTrue(v)
        # make sure it starts with a digit
        self.assertTrue(int(v[0]))


# a stand-in for "cdrdao read-toc ... TOCFILE": replays recorded progress
# on stderr, waiting for the gate file before the last part, then
# writes a recorded TOC
_FAKE_CDRDAO = """#!/usr/bin/env python3
import os, shutil, sys, time
progress, toc, gate = sys.argv[1:4]
with open(progress) as f:
    lines = f.readlines()
half = len(lines) // 2
sys.stderr.write(''.join(lines[:half]))
sys.stderr.flush()
deadline = time.time() + 5  # a test that never opens the gate fails
while not os.path.exists(gate):
    if time.time() > deadline:
        sys.exit(1)
    time.sleep(0.01)
sys.stderr.write(''.join(lines[half:]))
shutil.copy(toc, sys.argv[-1])
"""


class BackgroundReadTOCTestCase(common.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        here = os.path.dirname(__file__)
        self.progress = os.path.join(here, 'cdrdao.readtoc.progress')
        self.toc = os.path.join(here, 'bloc.toc')
        self.gate = os.path.join(self.dir, 'gate')
        script = os.path.join(self.dir, 'cdrdao')
        with open(script, 'w') as f:
            f.write(_FAKE_CDRDAO)
        os.chmod(script, 0o700)
        wrapper = os.path.join(self.dir, 'cdrdao-wrapper')
        with open(wrapper, 'w') as f:
            f.write('#!/bin/sh\nexec "%s" "%s" "%s" "%s" "$@"\n' % (
                script, self.progress, self.toc, self.gate))
        os.chmod(wrapper, 0o700)
        self.patch(cdrdao, 'CDRDAO', wrapper)
        self.printed = []
        self.patch(builtins, 'print',
                   lambda *a, **kw: self.printed.append(' '.join(a)))

    def patch(self, obj, name, value):
        old = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, old)

    def expectedLines(self):
        lines = []
        parser = cdrdao.ProgressParser(lines.append)
        with open(self.progress) as f:
            for line in f:
                parser.parse(line.rstrip('\n'))
        return lines

    def testHoldsTrackLinesUntilJoin(self):
        expected = self.expectedLines()
        self.assertTrue(expected)
        scan = cdrdao.BackgroundReadTOC('/dev/fake')
        scan.start()
        # the first half has been parsed once a track line is held
        deadline = time.time() + 10
        while not scan._held and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(scan._held)
        self.assertEqual(self.printed, [])
        open(self.gate, 'w').close()
        t = scan.join()
        track_lines = [p for p in self.printed if p.startswith('Track ')]
        self.assertEqual(track_lines, expected)
        self.assertTrue(t.toc.table.hasTOC())
        with open(self.toc, 'rb') as f:
            self.assertEqual(t.toc_data, f.read())

    def testCancelStopsCdrdaoQuietly(self):
        scan = cdrdao.BackgroundReadTOC('/dev/fake')
        scan.start()
        deadline = time.time() + 10
        while (getattr(scan.task, '_popen', None) is None and
               time.time() < deadline):
            time.sleep(0.01)
        with self.assertNoLogs('asyncio'):
            scan.cancel()
            t = scan.join()
        self.assertIsNotNone(t._popen.poll())
        self.assertIsNone(t.toc)
        self.assertFalse(os.path.exists(t.tocfile))

    def testCancelBeforeStart(self):
        scan = cdrdao.BackgroundReadTOC('/dev/fake')
        scan.cancel()
        scan.start()
        t = scan.join()
        self.assertIsNotNone(t._popen.poll())
        self.assertIsNone(t.toc)

    def testJoinRaisesTaskException(self):
        self.patch(cdrdao, 'CDRDAO', os.path.join(self.dir, 'missing'))
        scan = cdrdao.BackgroundReadTOC('/dev/fake')
        scan.start()
        self.assertRaises(Exception, scan.join)

    def testSaveTocCreatesDirectory(self):
        toc_path = os.path.join(self.dir, 'Artist - Album', 'Artist - Album')
        cdrdao.save_toc(b'CD_DA\n', toc_path)
        with open(toc_path + '.toc', 'rb') as f:
            self.assertEqual(f.read(), b'CD_DA\n')
