# -*- Mode: Python; test-case-name: whipper.test.test_common_program -*-
# vi:si:et:sw=4:sts=4:ts=4


import os
import shutil
import unittest

from tempfile import NamedTemporaryFile
from whipper.common import color, program, mbngs, config
from whipper.command.cd import DEFAULT_DISC_TEMPLATE


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


class ReleaseDifferencesTestCase(unittest.TestCase):

    @staticmethod
    def _release(mbid, barcode='194399566428', countries=('United States',)):
        md = mbngs.DiscMetadata()
        md.artist = 'Alicia Keys'
        md.releaseTitle = 'KEYS (Disc 2 of 2): Unlocked'
        md.duration = 2206423
        md.url = 'https://musicbrainz.org/release/' + mbid
        md.mbid = mbid
        md.releaseType = 'Album'
        md.barcode = barcode
        md.countries = list(countries)
        md.catalogNumbers = ['19439-95664-2']
        return program.releaseFields(md)

    def testEqual(self):
        releases = [self._release('f7c03888'), self._release('2c159974')]
        self.assertEqual(program.releaseDifferences(releases), {})

    def testGroupsInOrderOfAppearance(self):
        releases = [self._release('a', countries=['Europe']),
                    self._release('b', countries=['United States']),
                    self._release('c', countries=['Europe'])]
        self.assertEqual(program.releaseDifferences(releases),
                         {'Country': {'Europe': 1, 'United States': 2}})

    def testMissingIsAValue(self):
        releases = [self._release('a'), self._release('b', barcode=None)]
        self.assertEqual(program.releaseDifferences(releases),
                         {'Barcode': {'194399566428': 1, None: 2}})


class FormatFieldTestCase(unittest.TestCase):

    def tearDown(self):
        color.set_mode('never')

    def testPlain(self):
        self.assertEqual(program.formatField('Country', 'Europe'),
                         'Country  : Europe')

    def testMarked(self):
        groups = {'United States': 1, 'Europe': 2}
        self.assertEqual(program.formatField('Country', 'Europe', groups,
                                             marked=True),
                         '* Country  : Europe [2]')
        self.assertEqual(program.formatField('Type', 'Album', marked=True),
                         '  Type     : Album')

    def testMissing(self):
        self.assertEqual(program.formatField('Barcode', None, {'1': 1,
                                                               None: 2}),
                         'Barcode  : - [2]')

    def testColored(self):
        color.set_mode('always')
        groups = {'United States': 1, 'Europe': 2}
        self.assertEqual(program.formatField('Country', 'Europe', groups),
                         '\033[33mCountry  \033[0m: \033[35mEurope\033[0m')
        self.assertEqual(program.formatField('Type', 'Album'),
                         'Type     : Album')

    def testColorsRepeat(self):
        color.set_mode('always')
        groups = {str(n): n for n in range(1, 7)}
        self.assertEqual(program.formatField('Country', '6', groups),
                         '\033[33mCountry  \033[0m: \033[36m6\033[0m')


def _metadata(name, codes=(), countries=None, barcode=None, catnos=()):
    md = mbngs.DiscMetadata()
    md.releaseTitle = name
    md.countryCodes = list(codes)
    md.countries = list(codes if countries is None else countries)
    md.barcode = barcode
    md.catalogNumbers = list(catnos)
    return md


class CountryRankTestCase(unittest.TestCase):

    def testOrder(self):
        self.assertEqual(program.countryRank(['DE'], 'DE'), 0)
        self.assertEqual(program.countryRank(['XE'], 'DE'), 1)
        self.assertEqual(program.countryRank(['XW'], 'DE'), 2)
        self.assertEqual(program.countryRank(['US'], 'DE'), 3)
        self.assertEqual(program.countryRank([], 'DE'), 3)

    def testBestOfSeveralCountries(self):
        self.assertEqual(program.countryRank(['XW', 'DE'], 'DE'), 0)

    def testEuropeIsNotTheContinentOfOthers(self):
        self.assertEqual(program.countryRank(['XE'], 'US'), 3)


class SortReleasesTestCase(unittest.TestCase):

    def titles(self, metadatas):
        return [md.releaseTitle for md in metadatas]

    def testPreferredCountryFirst(self):
        metadatas = [_metadata('us', ['US'], ['United States']),
                     _metadata('xw', ['XW'], ['[Worldwide]']),
                     _metadata('none'),
                     _metadata('xe', ['XE'], ['Europe']),
                     _metadata('de', ['DE'], ['Germany']),
                     _metadata('fr', ['FR'], ['France'])]
        self.assertEqual(
            self.titles(program.sortReleases(metadatas, 'de')),
            ['de', 'xe', 'xw', 'fr', 'us', 'none'])

    def testAlphabeticalWithoutCountry(self):
        metadatas = [_metadata('xw', ['XW'], ['[Worldwide]']),
                     _metadata('us', ['US'], ['United States']),
                     _metadata('none'),
                     _metadata('xe', ['XE'], ['Europe'])]
        self.assertEqual(self.titles(program.sortReleases(metadatas, '')),
                         ['xe', 'us', 'xw', 'none'])


class GroupReleasesTestCase(unittest.TestCase):

    def testCatalogGroupsStayTogether(self):
        metadatas = [_metadata('a', barcode='1', catnos=['A']),
                     _metadata('b', barcode='2', catnos=['B']),
                     _metadata('c', barcode='1', catnos=['C']),
                     _metadata('d', barcode='1', catnos=['A']),
                     _metadata('e')]
        groups = program.groupReleases(metadatas)
        self.assertEqual(
            [(key, [md.releaseTitle for md in members])
             for key, members in groups],
            [(('1', ('A',)), ['a', 'd']), (('1', ('C',)), ['c']),
             (('2', ('B',)), ['b']), ((None, ()), ['e'])])

    def testSortedGroupsComeFirst(self):
        metadatas = [_metadata('us', ['US'], ['United States'], '1'),
                     _metadata('jp', ['JP'], ['Japan'], '2'),
                     _metadata('xe', ['XE'], ['Europe'], '1'),
                     _metadata('de', ['DE'], ['Germany'], '2')]
        groups = program.groupReleases(
            program.sortReleases(metadatas, 'DE'))
        self.assertEqual(
            [[md.releaseTitle for md in members] for _, members in groups],
            [['de', 'jp'], ['xe', 'us']])

    def testHeader(self):
        self.assertEqual(program.groupHeader(('1', ('A', 'B')), 2),
                         '== Barcode 1, Cat no(s) A, B (2 releases)')
        self.assertEqual(program.groupHeader((None, ()), 1),
                         '== Barcode -, Cat no(s) - (1 release)')
