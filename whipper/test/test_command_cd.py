# -*- Mode: Python; test-case-name: whipper.test.test_command_cd -*-
# vi:si:et:sw=4:sts=4:ts=4

import builtins
import types
import unittest

from whipper.command import cd
from whipper.common import drive, program
from whipper.program import cdrdao, utils
from whipper.test.test_common_program import ELVIS_RECORD


class FakeToc:
    tracks = [None] * 14

    def getCDDBDiscId(self):
        return 'bf0a610e'

    def getMusicBrainzDiscId(self):
        return 'ZAh257qBOtktGXsWHCxiFpSdgFg-'

    def getMusicBrainzSubmitURL(self):
        return 'https://musicbrainz.org/cdtoc/attach'

    def getCDDBValues(self):
        return None


class FreeDBFallbackTestCase(unittest.TestCase):

    def patch(self, obj, name, value):
        old = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, old)

    def setUp(self):
        self.patch(utils, 'load_device', lambda device: None)
        self.patch(utils, 'unmount_device', lambda device: None)
        self.patch(drive, 'get_cdrom_drive_status', lambda device: 0)
        self.patch(program.Program, 'getFastToc',
                   staticmethod(lambda runner, device: FakeToc()))
        self.patch(program.Program, 'getMusicBrainz',
                   lambda self, *a, **kw: None)
        self.patch(program.Program, 'getCDDB',
                   staticmethod(lambda cddbid: [ELVIS_RECORD]))
        # a CD-R without --cdr: do() stops right after the metadata step
        self.patch(cdrdao, 'DetectCdr', lambda device: True)
        self.prompts = []
        self.patch(builtins, 'input',
                   lambda prompt: self.prompts.append(prompt) or '')
        self.patch(builtins, 'print', lambda *a, **kw: None)

    def run_do(self, **options):
        # skip BaseCommand.__init__, which parses argv and reads the config
        cmd = cd.Info.__new__(cd.Info)
        cmd.options = types.SimpleNamespace(
            record=False, device='/dev/fake', drive_auto_close=False,
            release_id=None, country=None, prompt=False, **options)
        return cmd, cmd.do()

    def testWithoutUnknownDoesNotAsk(self):
        _, ret = self.run_do()
        self.assertEqual(ret, -1)
        self.assertEqual(self.prompts, [])

    def testWithUnknownOffersFreeDB(self):
        cmd, ret = self.run_do(unknown=True)
        self.assertEqual(ret, -1)  # the CD-R stop, after the metadata step
        self.assertEqual(len(self.prompts), 1)
        self.assertEqual(cmd.program.metadata.artist, 'Elvis Presley')
