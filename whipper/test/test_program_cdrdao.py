# -*- Mode: Python; test-case-name: whipper.test.test_program_cdparanoia -*-
# vi:si:et:sw=4:sts=4:ts=4

import os

from whipper.program import cdrdao
from whipper.test import common

# TODO: Current test architecture makes testing cdrdao difficult. Revisit.


class VersionTestCase(common.TestCase):
    def testGetVersion(self):
        v = cdrdao.version()
        self.assertTrue(v)
        # make sure it starts with a digit
        self.assertTrue(int(v[0]))


class ErrorSummaryTestCase(common.TestCase):
    def testErrorLines(self):
        lines = ['Cdrdao version 1.2.5', '/dev/sr0: HL-DT-ST',
                 'ERROR: Unit not ready, giving up.',
                 'ERROR: Cannot setup device /dev/sr0.', '']
        self.assertEqual(cdrdao.error_summary(lines),
                         'ERROR: Unit not ready, giving up. '
                         'ERROR: Cannot setup device /dev/sr0.')

    def testLastLineWithoutErrorLines(self):
        self.assertEqual(cdrdao.error_summary(['a', 'b', '  ']), 'b')

    def testNoOutput(self):
        self.assertEqual(cdrdao.error_summary(['']), 'no output')


class _FailedPopen:
    returncode = 1


class ReadTOCFailureTestCase(common.TestCase):
    def testNoTocFile(self):
        t = cdrdao.ReadTOCTask('/dev/sr0')
        os.close(t.fd)
        os.unlink(t.tocfile)
        t._popen = _FailedPopen()
        t._lines = ['ERROR: Unit not ready, giving up.']
        t.runner = object()  # as if started; stop() resets it

        t._done()

        self.assertIsInstance(t.exception, cdrdao.ReadTOCError)
        self.assertEqual(t.exception.returncode, 1)
        self.assertIn('Unit not ready', str(t.exception))
        self.assertIsNone(t.toc)
        self.assertFalse(t.running)
