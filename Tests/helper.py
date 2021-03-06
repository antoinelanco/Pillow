"""
Helper functions.
"""
from __future__ import print_function
import sys
import tempfile
import os
import unittest

from PIL import Image, ImageMath


def convert_to_comparable(a, b):
    new_a, new_b = a, b
    if a.mode == 'P':
        new_a = Image.new('L', a.size)
        new_b = Image.new('L', b.size)
        new_a.putdata(a.getdata())
        new_b.putdata(b.getdata())
    elif a.mode == 'I;16':
        new_a = a.convert('I')
        new_b = b.convert('I')
    return new_a, new_b


class PillowTestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)
        # holds last result object passed to run method:
        self.currentResult = None

    # Nicer output for --verbose
    def __str__(self):
        return self.__class__.__name__ + "." + self._testMethodName

    def run(self, result=None):
        self.currentResult = result  # remember result for use later
        unittest.TestCase.run(self, result)  # call superclass run method

    def delete_tempfile(self, path):
        try:
            ok = self.currentResult.wasSuccessful()
        except AttributeError:  # for nosetests
            proxy = self.currentResult
            ok = (len(proxy.errors) + len(proxy.failures) == 0)

        if ok:
            # only clean out tempfiles if test passed
            try:
                os.remove(path)
            except OSError:
                pass  # report?
        else:
            print("=== orphaned temp file: %s" % path)

    def assert_deep_equal(self, a, b, msg=None):
        try:
            self.assertEqual(
                len(a), len(b),
                msg or "got length %s, expected %s" % (len(a), len(b)))
            self.assertTrue(
                all(x == y for x, y in zip(a, b)),
                msg or "got %s, expected %s" % (a, b))
        except:
            self.assertEqual(a, b, msg)

    def assert_image(self, im, mode, size, msg=None):
        if mode is not None:
            self.assertEqual(
                im.mode, mode,
                msg or "got mode %r, expected %r" % (im.mode, mode))

        if size is not None:
            self.assertEqual(
                im.size, size,
                msg or "got size %r, expected %r" % (im.size, size))

    def assert_image_equal(self, a, b, msg=None):
        self.assertEqual(
            a.mode, b.mode,
            msg or "got mode %r, expected %r" % (a.mode, b.mode))
        self.assertEqual(
            a.size, b.size,
            msg or "got size %r, expected %r" % (a.size, b.size))
        if a.tobytes() != b.tobytes():
            self.fail(msg or "got different content")

    def assert_image_similar(self, a, b, epsilon, msg=None):
        epsilon = float(epsilon)
        self.assertEqual(
            a.mode, b.mode,
            msg or "got mode %r, expected %r" % (a.mode, b.mode))
        self.assertEqual(
            a.size, b.size,
            msg or "got size %r, expected %r" % (a.size, b.size))

        a, b = convert_to_comparable(a, b)

        diff = 0
        for ach, bch in zip(a.split(), b.split()):
            chdiff = ImageMath.eval("abs(a - b)", a=ach, b=bch).convert('L')
            diff += sum(i * num for i, num in enumerate(chdiff.histogram()))

        ave_diff = float(diff)/(a.size[0]*a.size[1])
        self.assertGreaterEqual(
            epsilon, ave_diff,
            (msg or '') +
            " average pixel value difference %.4f > epsilon %.4f" % (
                ave_diff, epsilon))

    def assert_warning(self, warn_class, func, *args, **kwargs):
        import warnings

        result = None
        with warnings.catch_warnings(record=True) as w:
            # Cause all warnings to always be triggered.
            warnings.simplefilter("always")

            # Hopefully trigger a warning.
            result = func(*args, **kwargs)

            # Verify some things.
            self.assertGreaterEqual(len(w), 1)
            found = False
            for v in w:
                if issubclass(v.category, warn_class):
                    found = True
                    break
            self.assertTrue(found)
        return result

    def skipKnownBadTest(self, msg=None, platform=None,
                         travis=None, interpreter=None):
        # Skip if platform/travis matches, and
        # PILLOW_RUN_KNOWN_BAD is not true in the environment.
        if bool(os.environ.get('PILLOW_RUN_KNOWN_BAD', False)):
            print(os.environ.get('PILLOW_RUN_KNOWN_BAD', False))
            return

        skip = True
        if platform is not None:
            skip = sys.platform.startswith(platform)
        if travis is not None:
            skip = skip and (travis == bool(os.environ.get('TRAVIS', False)))
        if interpreter is not None:
            skip = skip and (interpreter == 'pypy' and
                             hasattr(sys, 'pypy_version_info'))
        if skip:
            self.skipTest(msg or "Known Bad Test")

    def shortDescription(self):
        # Prevents `nose -v` printing docstrings
        return None

    def tempfile(self, template):
        assert template[:5] in ("temp.", "temp_")
        fd, path = tempfile.mkstemp(template[4:], template[:4])
        os.close(fd)

        self.addCleanup(self.delete_tempfile, path)
        return path

    def open_withImagemagick(self, f):
        if not imagemagick_available():
            raise IOError()

        outfile = self.tempfile("temp.png")
        if command_succeeds([IMCONVERT, f, outfile]):
            from PIL import Image
            return Image.open(outfile)
        raise IOError()


# helpers

py3 = (sys.version_info >= (3, 0))


def fromstring(data):
    from io import BytesIO
    from PIL import Image
    return Image.open(BytesIO(data))


def tostring(im, string_format, **options):
    from io import BytesIO
    out = BytesIO()
    im.save(out, string_format, **options)
    return out.getvalue()


def hopper(mode=None, cache={}):
    from PIL import Image
    if mode is None:
        # Always return fresh not-yet-loaded version of image.
        # Operations on not-yet-loaded images is separate class of errors
        # what we should catch.
        return Image.open("Tests/images/hopper.ppm")
    # Use caching to reduce reading from disk but so an original copy is
    # returned each time and the cached image isn't modified by tests
    # (for fast, isolated, repeatable tests).
    im = cache.get(mode)
    if im is None:
        if mode == "F":
            im = hopper("L").convert(mode)
        elif mode[:4] == "I;16":
            im = hopper("I").convert(mode)
        else:
            im = hopper().convert(mode)
        cache[mode] = im
    return im.copy()


def command_succeeds(cmd):
    """
    Runs the command, which must be a list of strings. Returns True if the
    command succeeds, or False if an OSError was raised by subprocess.Popen.
    """
    import subprocess
    with open(os.devnull, 'wb') as f:
        try:
            subprocess.call(cmd, stdout=f, stderr=subprocess.STDOUT)
        except OSError:
            return False
    return True


def djpeg_available():
    return command_succeeds(['djpeg', '-version'])


def cjpeg_available():
    return command_succeeds(['cjpeg', '-version'])


def netpbm_available():
    return (command_succeeds(["ppmquant", "--version"]) and
            command_succeeds(["ppmtogif", "--version"]))


def imagemagick_available():
    return IMCONVERT and command_succeeds([IMCONVERT, '-version'])


def on_appveyor():
    return 'APPVEYOR' in os.environ

if sys.platform == 'win32':
    IMCONVERT = os.environ.get('MAGICK_HOME', '')
    if IMCONVERT:
        IMCONVERT = os.path.join(IMCONVERT, 'convert.exe')
else:
    IMCONVERT = 'convert'

def distro():
    if os.path.exists('/etc/os-release'):
        with open('/etc/os-release', 'r') as f:
            for line in f:
                if 'ID=' in line:
                    return line.strip().split('=')[1]

class cached_property(object):
    def __init__(self, func):
        self.func = func

    def __get__(self, instance, cls=None):
        result = instance.__dict__[self.func.__name__] = self.func(instance)
        return result
