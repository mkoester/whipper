import os
import re
import tempfile
import threading
import subprocess
from subprocess import Popen, PIPE

from whipper.common import color
from whipper.common.common import truncate_filename
from whipper.image.toc import TocFile
from whipper.extern.task import task
from whipper.extern import asyncsub

import logging
logger = logging.getLogger(__name__)

CDRDAO = 'cdrdao'

_TRACK_RE = re.compile(r"^Analyzing track (?P<track>[0-9]*) \(AUDIO\): start (?P<start>[0-9]*:[0-9]*:[0-9]*), length (?P<length>[0-9]*:[0-9]*:[0-9]*)")  # noqa: E501
_CRC_RE = re.compile(
    r"Found (?P<channels>[0-9]*) Q sub-channels with CRC errors")
_BEGIN_CDRDAO_RE = re.compile(r"-" * 60)
_LAST_TRACK_RE = re.compile(r"^[ ]?(?P<track>[0-9]*)")
_LEADOUT_RE = re.compile(
    r"^Leadout AUDIO\s*[0-9]\s*[0-9]*:[0-9]*:[0-9]*\([0-9]*\)")
_SUBCODE_EMPHASIS_LINE = ("Pre-emphasis flag of track differs from TOC - "
                          "toc file contains TOC setting.")


class ReadTOCError(Exception):
    """cdrdao read-toc failed and wrote no TOC."""

    def __init__(self, returncode, message):
        self.args = (returncode, message)
        self.returncode = returncode
        self.message = message

    def __str__(self):
        return "cdrdao read-toc failed (exit code %s): %s" % (
            self.returncode, self.message)


def error_summary(lines):
    """
    Return the lines of cdrdao output that explain a failure.

    :param lines: cdrdao's stderr, one entry per line
    :type lines: list(str)
    :returns: its ERROR lines, else its last non-empty line, joined
    :rtype: str
    """
    lines = [line.strip() for line in lines if line.strip()]
    errors = [line for line in lines if line.startswith('ERROR:')]
    return ' '.join(errors or lines[-1:]) or 'no output'


class ProgressParser:
    tracks = 0
    currentTrack = 0
    oldline = ''  # for leadout/final track number detection

    def __init__(self, report=print):
        """
        :param report: called with each per-track summary line
        :type report: callable
        """
        self.report = report

    def parse(self, line):
        cdrdao_m = _BEGIN_CDRDAO_RE.match(line)

        if cdrdao_m:
            logger.debug("RE: Begin cdrdao toc-read")

        leadout_m = _LEADOUT_RE.match(line)

        if leadout_m:
            logger.debug("RE: Reached leadout")
            last_track_m = _LAST_TRACK_RE.match(self.oldline)
            if last_track_m:
                self.tracks = last_track_m.group('track')

        track_s = _TRACK_RE.search(line)
        if track_s:
            logger.debug("RE: Began reading track: %d",
                         int(track_s.group('track')))
            self.currentTrack = int(track_s.group('track'))

        crc_s = _CRC_RE.search(line)
        if crc_s:
            self.report("Track %d finished, "
                        "found %d Q sub-channels with CRC errors" %
                        (self.currentTrack, int(crc_s.group('channels'))))

        # TODO: add subcode pre-emphasis info for each track to logger too
        if _SUBCODE_EMPHASIS_LINE in line:
            logger.warning(_SUBCODE_EMPHASIS_LINE)

        self.oldline = line


def saved_toc_path(toc_path):
    """
    Return the path ReadTOCTask saves the TOC to for the given toc_path.

    :param toc_path: disc path (without extension) passed to ReadTOCTask
    :type toc_path: str
    :returns: path of the saved .toc file; None if its directory is missing
    :rtype: str or None
    """
    t_dirn = os.path.dirname(os.path.abspath(toc_path))
    if not os.path.isdir(t_dirn):
        return None
    return truncate_filename(os.path.abspath(toc_path) + '.toc')


class ReadTOCTask(task.Task):
    """Task that reads the TOC of the disc using cdrdao."""

    description = "Reading TOC"
    toc = None
    toc_data = None  # contents of the TOC file cdrdao wrote, as bytes

    def __init__(self, device, fast_toc=False, toc_path=None, report=print):
        """
        Read the TOC for ``device``.

        :param device: block device to read TOC from
        :type device: str
        :param fast_toc: whether to use fast-toc cdrdao mode
        :type fast_toc: bool
        :param toc_path: where to save TOC if wanted
        :type toc_path: str
        :param report: called with each per-track summary line
        :type report: callable
        """
        self.device = device
        self.fast_toc = fast_toc
        self.toc_path = toc_path
        self._buffer = ""  # accumulate characters
        self._lines = []  # stderr lines, to explain a failure
        self._parser = ProgressParser(report)
        self._aborted = False

        self.fd, self.tocfile = tempfile.mkstemp(
            suffix='.cdrdao.read-toc.whipper.task')

    def start(self, runner):
        task.Task.start(self, runner)
        os.close(self.fd)
        os.unlink(self.tocfile)

        cmd = ([CDRDAO, 'read-toc']
               + (['--fast-toc'] if self.fast_toc else [])
               + ['--device', self.device, self.tocfile])

        self._popen = asyncsub.Popen(cmd,
                                     bufsize=1024,
                                     stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,
                                     close_fds=True)
        if self._aborted:  # abort() ran in another thread before we started
            self._popen.terminate()

        self.schedule(0.01, self._read, runner)

    def _read(self, runner):
        ret = self._popen.recv_err()
        if not ret:
            if self._popen.poll() is not None:
                self._done()
                return
            self.schedule(0.01, self._read, runner)
            return
        self._buffer += ret.decode()

        # parse buffer into lines if possible, and parse them
        if "\n" in self._buffer:
            lines = self._buffer.split('\n')
            if lines[-1] != "\n":
                # last line didn't end yet
                self._buffer = lines[-1]
                del lines[-1]
            else:
                self._buffer = ""
            self._lines.extend(lines)
            for line in lines:
                self._parser.parse(line)
                if (self._parser.currentTrack != 0 and
                        self._parser.tracks != 0):
                    progress = (float('%d' % self._parser.currentTrack) /
                                float(self._parser.tracks))
                    if progress < 1.0:
                        self.setProgress(progress)

        # 0 does not give us output before we complete, 1.0 gives us output
        # too late
        self.schedule(0.01, self._read, runner)

    def _poll(self, runner):
        if self._popen.poll() is None:
            self.schedule(1.0, self._poll, runner)
            return

        self._done()

    def abort(self):
        """Stop cdrdao if it is still reading; the task then ends quietly."""
        self._aborted = True
        popen = getattr(self, '_popen', None)
        if popen is not None and popen.poll() is None:
            logger.debug('stopping cdrdao read-toc')
            popen.terminate()

    def _done(self):
        self.setProgress(1.0)
        if self._aborted:
            if os.path.exists(self.tocfile):
                os.unlink(self.tocfile)
            self.stop()
            return
        if self._popen.returncode != 0 or not os.path.exists(self.tocfile):
            # e.g. "ERROR: Unit not ready, giving up." while the drive spins up
            self.setExceptionAndTraceback(ReadTOCError(
                self._popen.returncode,
                error_summary(self._lines + [self._buffer])))
            if os.path.exists(self.tocfile):
                os.unlink(self.tocfile)
            self.stop()
            return
        self.toc = TocFile(self.tocfile)
        self.toc.parse()
        with open(self.tocfile, 'rb') as f:
            self.toc_data = f.read()
        if self.toc_path is not None:
            save_toc(self.toc_data, self.toc_path)
        os.unlink(self.tocfile)
        self.stop()
        return


def save_toc(toc_data, toc_path):
    """
    Save a TOC read by ReadTOCTask next to the rip, creating its directory.

    :param toc_data: contents of the TOC file cdrdao wrote
    :type toc_data: bytes
    :param toc_path: disc path (without extension) to save the TOC for
    :type toc_path: str
    """
    t_comp = os.path.abspath(toc_path).split(os.sep)
    t_dirn = os.sep.join(t_comp[:-1])
    # If the output path doesn't exist, make it recursively
    try:
        os.makedirs(t_dirn)
        logger.info("creating output directory %s", color.bold(t_dirn))
    except FileExistsError as e:
        logger.debug(e)
    with open(saved_toc_path(toc_path), 'wb') as f:
        f.write(toc_data)


class BackgroundReadTOC:
    """
    Read the full TOC in a background thread.

    The full read scans the whole disc, which takes minutes; it needs only
    the drive, so it can run while the user picks a release. Its per-track
    lines are held back until join(), so they don't break into a prompt.
    """

    def __init__(self, device):
        """
        :param device: block device to read TOC from
        :type device: str
        """
        self.task = ReadTOCTask(device, report=self._report)
        self.task.description = "Reading table"
        self._lock = threading.Lock()
        self._held = []  # per-track lines not printed yet; None once live
        self._exception = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _report(self, line):
        with self._lock:
            if self._held is not None:
                self._held.append(line)
                return
        print(line)

    def _run(self):
        try:
            # its own runner: SyncRunner runs a new event loop per task
            task.SyncRunner(verbose=False).run(self.task)
        # FIXME: catching too general exception (Exception); join() raises
        # whatever the read raised, in the thread that waits for it
        except Exception as e:
            self._exception = e

    def start(self):
        """Start reading the TOC."""
        self._thread.start()

    def join(self):
        """
        Wait for the read to finish, printing its per-track lines.

        :returns: the finished task
        :rtype: ReadTOCTask
        """
        # replay under the lock, so no live line overtakes a held one
        with self._lock:
            for line in self._held:
                print(line)
            self._held = None
            if self._thread.is_alive():
                print("Waiting for the table of contents scan to finish...")
        self._thread.join()
        if self._exception is not None:
            raise self._exception
        return self.task

    def cancel(self):
        """Stop cdrdao if it is still reading; harmless once finished."""
        self.task.abort()


def DetectCdr(device):
    """Whether cdrdao detects a CD-R for ``device``."""
    cmd = [CDRDAO, 'disk-info', '-v1', '--device', device]
    logger.debug("executing %r", cmd)
    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    return 'CD-R medium          : n/a' not in p.stdout.read().decode()


def version():
    """Return cdrdao version as a string."""
    cdrdao = Popen(CDRDAO, stderr=PIPE)
    _, err = cdrdao.communicate()
    if cdrdao.returncode != 1:
        logger.warning("cdrdao version detection failed: "
                       "return code is %s", cdrdao.returncode)
        return None
    m = re.compile(r'^Cdrdao version (?P<version>[^ ]*)').search(
        err.decode('utf-8'))
    if not m:
        logger.warning("cdrdao version detection failed: "
                       "could not find version")
        return None
    return m.group('version')
