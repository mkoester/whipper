# -*- Mode: Python; test-case-name: whipper.test.test_common_color -*-
# vi:si:et:sw=4:sts=4:ts=4

import os
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from whipper.common import color


class TTY(StringIO):
    def isatty(self):
        return True


class TestColor(TestCase):
    def tearDown(self):
        color.set_mode('never')

    def test_never_leaves_text_alone(self):
        self.assertEqual(color.bold('x', TTY()), 'x')
        self.assertEqual(color.quality(1.0, TTY()), '100.00%')

    def test_always_wraps_in_sgr_code(self):
        color.set_mode('always')
        self.assertEqual(color.bold('x', StringIO()), '\033[1mx\033[0m')
        self.assertEqual(color.good('x', StringIO()), '\033[32mx\033[0m')
        self.assertEqual(color.bad('x', StringIO()), '\033[31mx\033[0m')

    def test_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            color.set_mode('sometimes')

    @patch.dict(os.environ, clear=True)
    def test_auto_colours_only_a_terminal(self):
        color.set_mode('auto')
        self.assertTrue(color.enabled(TTY()))
        self.assertFalse(color.enabled(StringIO()))

    @patch.dict(os.environ, {'NO_COLOR': '1'}, clear=True)
    def test_auto_honours_no_color(self):
        color.set_mode('auto')
        self.assertFalse(color.enabled(TTY()))

    @patch.dict(os.environ, {'WHIPPER_LOGFILE': 'x.log'}, clear=True)
    def test_log_file_is_never_coloured(self):
        color.set_mode('always')
        with patch('sys.stderr', TTY()):
            self.assertFalse(color.enabled())
        self.assertTrue(color.enabled(TTY()))

    def test_quality_bands(self):
        color.set_mode('always')
        for fraction, code in ((1.0, '32'), (0.99996, '32'), (0.9999, '33'),
                               (0.95, '33'), (0.9499, '31')):
            self.assertTrue(
                color.quality(fraction, StringIO()).startswith(
                    '\033[%sm' % code),
                fraction)
