# -*- Mode: Python; test-case-name: whipper.test.test_common_program -*-
# vi:si:et:sw=4:sts=4:ts=4


import builtins
import os
import shutil
import tempfile
import unittest

from tempfile import NamedTemporaryFile
from whipper.common import program, mbngs, config
from whipper.command.cd import DEFAULT_DISC_TEMPLATE, DEFAULT_TRACK_TEMPLATE
from whipper.image.toc import TocFile
from whipper.program import cdrdao
from whipper.program.cdrdao import saved_toc_path


class SavedTableTestCase(unittest.TestCase):
    """Reusing the TOC an earlier rip saved (rip --tracks)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.toc_path = os.path.join(self.dir, 'Artist - Album')
        fixture = os.path.join(os.path.dirname(__file__), 'bloc.toc')
        shutil.copy(fixture, self.toc_path + '.toc')
        toc = TocFile(fixture)
        toc.parse()
        self.cddb = toc.table.getCDDBDiscId()
        self.mb = toc.table.getMusicBrainzDiscId()
        self.prog = program.Program(config.Config())
        self.prog.getRipResult()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def testSavedPathMatchesReadTOCTask(self):
        self.assertEqual(saved_toc_path(self.toc_path), self.toc_path + '.toc')
        self.assertIsNone(saved_toc_path('/does/not/exist/disc'))

    def testMatchingSavedTableIsLoaded(self):
        table = program.Program.loadSavedTable(self.toc_path, self.cddb,
                                               self.mb)
        self.assertEqual(table.getMusicBrainzDiscId(), self.mb)

    def testOtherDiscIsRejected(self):
        self.assertIsNone(program.Program.loadSavedTable(
            self.toc_path, self.cddb, 'another-mb-disc-id'))

    def testMissingIsRejected(self):
        os.unlink(self.toc_path + '.toc')
        self.assertIsNone(program.Program.loadSavedTable(
            self.toc_path, self.cddb, self.mb))

    def testUnparsableIsRejected(self):
        with open(self.toc_path + '.toc', 'w') as f:
            f.write('not a toc file {{{')
        self.assertIsNone(program.Program.loadSavedTable(
            self.toc_path, self.cddb, self.mb))

    def getTable(self, reuse_toc, mb=None):
        """Run getTable with a runner that records whether it read the disc."""
        runs = []
        fixture = os.path.join(os.path.dirname(__file__), 'bloc.toc')

        class Runner:
            @staticmethod
            def run(t):
                runs.append(t)
                t.toc = TocFile(fixture)
                t.toc.parse()

        table = self.prog.getTable(Runner, self.cddb, mb or self.mb,
                                   '/dev/null', 0, self.toc_path,
                                   reuse_toc=reuse_toc)
        return table, runs

    def testReuseSkipsTheDisc(self):
        table, runs = self.getTable(reuse_toc=True)
        self.assertEqual(runs, [])
        self.assertEqual(table.getMusicBrainzDiscId(), self.mb)

    def testNoReuseReadsTheDisc(self):
        _, runs = self.getTable(reuse_toc=False)
        self.assertEqual(len(runs), 1)

    def testReuseFallsBackToTheDisc(self):
        _, runs = self.getTable(reuse_toc=True, mb='another-mb-disc-id')
        self.assertEqual(len(runs), 1)


class PathTestCase(unittest.TestCase):

    def testStandardTemplateEmpty(self):
        prog = program.Program(config.Config())

        path = prog.getPath('/tmp', DEFAULT_DISC_TEMPLATE,
                            'mbdiscid', None)
        self.assertEqual(path, ('/tmp/unknown/Unknown Artist - mbdiscid/'
                                'Unknown Artist - mbdiscid'))

    def testStandardTemplateFilled(self):
        prog = program.Program(config.Config())
        md = mbngs.DiscMetadata()
        md.artist = md.sortName = 'Jeff Buckley'
        md.releaseTitle = 'Grace'

        path = prog.getPath('/tmp', DEFAULT_DISC_TEMPLATE,
                            'mbdiscid', md, 0)
        self.assertEqual(path, ('/tmp/unknown/Jeff Buckley - Grace/'
                                'Jeff Buckley - Grace'))

    def testIssue66TemplateFilled(self):
        prog = program.Program(config.Config())
        md = mbngs.DiscMetadata()
        md.artist = md.sortName = 'Jeff Buckley'
        md.releaseTitle = 'Grace'

        path = prog.getPath('/tmp', '%A/%d', 'mbdiscid', md, 0)
        self.assertEqual(path,
                         '/tmp/Jeff Buckley/Grace')


# TODO: Test cover art embedding too.
class CoverArtTestCase(unittest.TestCase):

    @staticmethod
    def _mock_get_front_image(release_id):
        """
        Mock `musicbrainzngs.get_front_image` function.

        Reads a local cover art image and returns its binary data.

        :param release_id: a release id (self.program.metadata.mbid)
        :type  release_id: str
        :returns: the binary content of the local cover art image
        :rtype: bytes
        """
        filename = '%s.jpg' % release_id
        path = os.path.join(os.path.dirname(__file__), filename)
        with open(path, 'rb') as f:
            return f.read()

    def _mock_getCoverArt(self, path, release_id):
        """
        Mock `common.program.getCoverArt` function.

        :param path: where to store the fetched image
        :type  path: str
        :param release_id: a release id (self.program.metadata.mbid)
        :type  release_id: str
        :returns: path to the downloaded cover art
        :rtype: str
        """
        cover_art_path = os.path.join(path, 'cover.jpg')

        data = self._mock_get_front_image(release_id)

        with NamedTemporaryFile(suffix='.cover.jpg', delete=False) as f:
            f.write(data)
        os.chmod(f.name, 0o644)
        shutil.move(f.name, cover_art_path)
        return cover_art_path

    def testCoverArtPath(self):
        """Test whether a fetched cover art is saved properly."""
        # Using: Dummy by Portishead
        # https://musicbrainz.org/release/76df3287-6cda-33eb-8e9a-044b5e15ffdd
        path = os.path.dirname(__file__)
        release_id = "76df3287-6cda-33eb-8e9a-044b5e15ffdd"
        coverArtPath = self._mock_getCoverArt(path, release_id)
        self.assertTrue(os.path.isfile(coverArtPath))


class GetTableTestCase(unittest.TestCase):

    def testWaitsForBackgroundScan(self):
        toc = TocFile(os.path.join(os.path.dirname(__file__), 'bloc.toc'))
        toc.parse()

        class Scan:
            def join(self):
                t = cdrdao.ReadTOCTask('/dev/fake')
                t.toc, t.toc_data = toc, b'CD_DA\n'
                return t

        class Runner:
            def run(self, t):
                raise AssertionError('read the disc again')

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        toc_path = os.path.join(tmp, 'Artist - Album', 'Artist - Album')
        prog = program.Program(config.Config())
        prog.getRipResult()
        itable = prog.getTable(Runner(), 'cddb', 'mb', '/dev/fake', 0,
                               toc_path, scan=Scan())
        self.assertIs(itable, toc.table)
        with open(toc_path + '.toc', 'rb') as f:
            self.assertEqual(f.read(), b'CD_DA\n')


# gnudb's record for Elvis Presley, Where No One Stands Alone (bf0a610e),
# as getCDDB returns it: values stripped, several left empty
ELVIS_RECORD = {
    'DISCID': 'bf0a610e',
    'DTITLE': 'Elvis Presley / Where No One Stands Alone',
    'DYEAR': '2018',
    'DGENRE': 'Blues',
    'EXTD': 'YEAR: 2018',
    'PLAYORDER': '',
}
ELVIS_RECORD.update(('TTITLE%d' % i, title) for i, title in enumerate([
    "I've Got Confidence", 'Where No One Stands Alone', 'Saved',
    'Crying In the Chapel', 'So High', 'Stand By Me', 'Bosom of Abraham',
    'How Great Thou Art', 'I, John', "You'll Never Walk Alone",
    'He Touched Me', 'In the Garden', 'He Is My Everything',
    'Amazing Grace']))
ELVIS_RECORD.update(('EXTT%d' % i, '') for i in range(14))


class CDDBMetadataTestCase(unittest.TestCase):

    def metadata(self, track_count=14, **fields):
        record = dict(ELVIS_RECORD, **fields)
        return program.Program.cddbToMetadata(record, track_count)

    def testDiscArtistAndTitle(self):
        md = self.metadata()
        self.assertEqual(md.artist, 'Elvis Presley')
        self.assertEqual(md.sortName, 'Elvis Presley')
        self.assertEqual(md.title, 'Where No One Stands Alone')
        self.assertEqual(md.releaseTitle, 'Where No One Stands Alone')
        self.assertEqual(md.release, '2018')
        self.assertIsNone(md.mbid)

    def testTitleWithoutSeparatorNamesBoth(self):
        md = self.metadata(DTITLE='Elvis Presley')
        self.assertEqual((md.artist, md.title),
                         ('Elvis Presley', 'Elvis Presley'))

    def testInvalidYearIsDropped(self):
        self.assertIsNone(self.metadata(DYEAR='').release)
        self.assertIsNone(self.metadata(DYEAR='18').release)

    def testTracks(self):
        md = self.metadata()
        self.assertEqual(len(md.tracks), 14)
        self.assertEqual(md.tracks[0].title, "I've Got Confidence")
        self.assertEqual(md.tracks[0].artist, 'Elvis Presley')
        self.assertEqual(md.tracks[13].title, 'Amazing Grace')

    def testCompilationTrackNamesItsArtist(self):
        md = self.metadata(DTITLE='Various / Gospel',
                           TTITLE1='Mahalia Jackson / Precious Lord')
        self.assertEqual((md.tracks[1].artist, md.tracks[1].title),
                         ('Mahalia Jackson', 'Precious Lord'))
        self.assertEqual(md.tracks[0].artist, 'Various')

    def testMissingTracksArePlaceholders(self):
        md = self.metadata(track_count=16, TTITLE2='')
        self.assertEqual(len(md.tracks), 16)
        self.assertEqual(md.tracks[2].title, 'Unknown Track 3')
        self.assertEqual(md.tracks[15].title, 'Unknown Track 16')

    def testPath(self):
        prog = program.Program(config.Config())
        path = prog.getPath('/tmp', DEFAULT_TRACK_TEMPLATE, 'mbdiscid',
                            self.metadata(), 1)
        self.assertEqual(path, ('/tmp/unknown/Elvis Presley - Where No One '
                                "Stands Alone/01. Elvis Presley - I've Got "
                                'Confidence'))

    def testTagsLeaveOutMusicBrainzIds(self):
        prog = program.Program(config.Config())
        prog.metadata = self.metadata()
        tags = prog.getTagList(1, 'mbdiscid')
        self.assertEqual(tags['ALBUMARTIST'], 'Elvis Presley')
        self.assertEqual(tags['ARTIST'], 'Elvis Presley')
        self.assertEqual(tags['ALBUM'], 'Where No One Stands Alone')
        self.assertEqual(tags['TITLE'], "I've Got Confidence")
        self.assertEqual(tags['DATE'], '2018')
        self.assertEqual(tags['TRACKTOTAL'], '14')
        self.assertNotIn('MUSICBRAINZ_ALBUMID', tags)
        self.assertNotIn(None, tags.values())


class ChooseCDDBTestCase(unittest.TestCase):

    def choose(self, *answers):
        records = [ELVIS_RECORD,
                   dict(ELVIS_RECORD, DTITLE='Elvis / Other Pressing')]
        replies = list(answers)
        prompts = []

        def fake_input(prompt):
            prompts.append(prompt)
            return replies.pop(0)
        old_input, old_print = builtins.input, builtins.print
        builtins.input, builtins.print = fake_input, lambda *a, **kw: None
        try:
            md = program.Program(config.Config()).chooseCDDB(records, 14)
        finally:
            builtins.input, builtins.print = old_input, old_print
        return md, prompts

    def testDefaultIsFirst(self):
        md, _ = self.choose('')
        self.assertEqual(md.title, 'Where No One Stands Alone')

    def testPickByNumber(self):
        md, _ = self.choose('2')
        self.assertEqual(md.title, 'Other Pressing')

    def testNone(self):
        md, _ = self.choose('N')
        self.assertIsNone(md)

    def testAsksAgainOnInvalidAnswer(self):
        md, prompts = self.choose('3', 'x', '1')
        self.assertEqual(len(prompts), 3)
        self.assertEqual(md.artist, 'Elvis Presley')
