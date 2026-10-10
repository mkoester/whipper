# -*- Mode: Python; test-case-name: whipper.test.test_command_cd -*-
# vi:si:et:sw=4:sts=4:ts=4

import types
import unittest

from whipper.command import cd
from whipper.common import drive, program
from whipper.program import cdrdao, utils


class CdrTestCase(unittest.TestCase):

    def patch(self, obj, name, value):
        old = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, old)

    def testCdrWithoutOptionStopsBeforeReadingTheDisc(self):
        self.patch(utils, 'load_device', lambda device: None)
        self.patch(utils, 'unmount_device', lambda device: None)
        self.patch(drive, 'get_cdrom_drive_status', lambda device: 0)
        self.patch(program.Program, 'getFastToc',
                   staticmethod(lambda runner, device: object()))
        self.patch(cdrdao, 'DetectCdr', lambda device: True)

        def scan(device):
            raise AssertionError('started the table scan')
        self.patch(cdrdao, 'BackgroundReadTOC', scan)

        # skip BaseCommand.__init__, which parses argv and reads the config
        cmd = cd.Info.__new__(cd.Info)
        cmd.options = types.SimpleNamespace(record=False, device='/dev/fake',
                                            drive_auto_close=False)
        self.assertEqual(cmd.do(), -1)
