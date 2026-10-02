"""
Highlight important parts of whipper's console output.

Uses bold on the terminal's default foreground for emphasis and the
standard ANSI colours for good/bad, so the terminal theme decides the
actual shades and the output stays readable on dark and light themes.
"""

import os
import sys

MODES = ('auto', 'always', 'never')

_mode = 'never'

BOLD = '1'
RED = '31'
GREEN = '32'
YELLOW = '33'


def set_mode(mode):
    """Set the colour mode: one of ``MODES``."""
    global _mode
    if mode not in MODES:
        raise ValueError('invalid colour mode %r' % mode)
    _mode = mode


def enabled(stream=None):
    """
    Tell whether output written to stream should be coloured.

    :param stream: the stream the text is written to (default: stderr,
                   where log messages go)
    """
    if stream is None:
        stream = sys.stderr
    # log messages go to a file instead of stderr
    if stream is sys.stderr and 'WHIPPER_LOGFILE' in os.environ:
        return False
    if _mode == 'always':
        return True
    if _mode == 'never':
        return False
    if 'NO_COLOR' in os.environ:
        return False
    return hasattr(stream, 'isatty') and stream.isatty()


def style(text, code, stream=None):
    """Wrap text in the SGR code if output to stream is coloured."""
    if not enabled(stream):
        return text
    return '\033[%sm%s\033[0m' % (code, text)


def bold(text, stream=None):
    return style(text, BOLD, stream)


def good(text, stream=None):
    return style(text, GREEN, stream)


def bad(text, stream=None):
    return style(text, RED, stream)


def quality(fraction, stream=None):
    """Format a rip quality as a percentage, coloured by how good it is."""
    text = '{:.2%}'.format(fraction)
    # judge the value as shown, so "100.00%" is never yellow
    shown = round(fraction, 4)
    if shown >= 1.0:
        code = GREEN
    elif shown >= 0.95:
        code = YELLOW
    else:
        code = RED
    return style(text, code, stream)
