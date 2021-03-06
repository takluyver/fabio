# coding: utf-8
#
#    Project: FabIO X-ray image reader
#
#    Copyright (C) 2010-2016 European Synchrotron Radiation Facility
#                       Grenoble, France
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

"""
FabIO class for dealing with TIFF images.
In facts wraps TiffIO from V. Armando Solé (available in PyMca) or falls back to PIL

Authors:
........
* Henning O. Sorensen & Erik Knudsen:
  Center for Fundamental Research: Metal Structures in Four Dimensions;
  Risoe National Laboratory;
  Frederiksborgvej 399;
  DK-4000 Roskilde;
  email:erik.knudsen@risoe.dk
* Jérôme Kieffer:
  European Synchrotron Radiation Facility;
  Grenoble (France)

License: MIT
"""
# Get ready for python3:
from __future__ import with_statement, print_function, division

__authors__ = ["Jérôme Kieffer", "Henning O. Sorensen", "Erik Knudsen"]
__date__ = "02/03/2018"
__license__ = "MIT"
__copyright__ = "ESRF, Grenoble & Risoe National Laboratory"
__status__ = "stable"

import time
import logging
logger = logging.getLogger(__name__)

try:
    from PIL import Image
except ImportError:
    Image = None
import numpy
from .utils import pilutils
from .fabioimage import FabioImage
from . import TiffIO


class TiffFrame(object):
    """Frame container for TIFF format"""

    def __init__(self, data, tiff_header):
        self.tiff_header = tiff_header
        self.data = data

    @property
    def header(self):
        """Default header exposed by fabio"""
        return self.tiff_header


class TifImage(FabioImage):
    """
    Images in TIF format
    Wraps TiffIO
    """
    DESCRIPTION = "Tagged image file format"

    DEFAULT_EXTENSIONS = ["tif", "tiff"]

    _need_a_seek_to_read = True

    def __init__(self, *args, **kwds):
        """ Tifimage constructor adds an nbits member attribute """
        self.nbits = None
        FabioImage.__init__(self, *args, **kwds)
        self._tiffio = None
        self.lib = None

    def _readheader(self, infile):
        """
        Try to read Tiff images header...
        """
        header = numpy.fromstring(infile.read(64), numpy.uint16)
        self.dim1 = int(header[9])
        self.dim2 = int(header[15])
        # nbits is not a FabioImage attribute...
        self.nbits = int(header[21])  # number of bits

    def _create_frame(self, image_data, tiff_header):
        """Create exposed data from TIFF information"""
        return TiffFrame(image_data, tiff_header)

    def _read_header_from_pil(self, image):
        header = self.check_header()
        for num, name in TiffIO.TAG_ID.items():
            if num in image.tag:
                name = name[0].lower() + name[1:]
                value = image.tag[num]
                # For some PIL version the tag content is a tuple
                if isinstance(value, tuple) and len(value) == 1:
                    value = value[0]
                header[name] = value

        return header

    def read(self, fname, frame=None):
        """
        Wrapper for TiffIO.
        """
        infile = self._open(fname, "rb")
        self._readheader(infile)
        infile.seek(0)
        self.lib = None
        try:
            tiffIO = TiffIO.TiffIO(infile)
            self.nframes = tiffIO.getNumberOfImages()
            if tiffIO.getNumberOfImages() > 0:
                # No support for now of multi-frame tiff images
                header = tiffIO.getInfo(0)
                data = tiffIO.getData(0)
                frame = self._create_frame(data, header)
                self.header = frame.header
                self.data = frame.data
            self._tiffio = tiffIO
        except Exception as error:
            logger.warning("Unable to read %s with TiffIO due to %s, trying PIL" % (fname, error))
            logger.debug("Backtrace", exc_info=True)
        else:
            if self.data.ndim == 2:
                self.dim2, self.dim1 = self.data.shape
            elif self.data.ndim == 3:
                self.dim2, self.dim1, _ = self.data.shape
                logger.warning("Third dimension is the color")
            else:
                logger.warning("dataset has %s dimensions (%s), check for errors !!!!", self.data.ndim, self.data.shape)
            self.lib = "TiffIO"

        if (self.lib is None):
            if Image:
                try:
                    infile.seek(0)
                    self.pilimage = Image.open(infile)
                except Exception:
                    logger.error("Error in opening %s  with PIL" % fname)
                    self.lib = None
                    infile.seek(0)
                else:
                    self.lib = "PIL"
                    header = self._read_header_from_pil(self.pilimage)
                    data = pilutils.get_numpy_array(self.pilimage)
                    frame = self._create_frame(data, header)
                    self.header = frame.header
                    self.data = frame.data
            else:
                logger.error("Error in opening %s: no tiff reader managed to read the file.", fname)
                self.lib = None
                infile.seek(0)

        self.resetvals()
        return self

    def write(self, fname):
        """
        Overrides the FabioImage.write method and provides a simple TIFF image writer.

        :param str fname: name of the file to save the image to
        """
        with TiffIO.TiffIO(fname, mode="w") as tiff_file:
            tiff_file.writeImage(self.data,
                                 info=self.header,
                                 software="fabio.tifimage",
                                 date=time.ctime())

    def close(self):
        if self._tiffio is not None:
            self._tiffio.close()
            self._tiffio = None
        super(TifImage, self).close()

    def getframe(self, num):
        """Returns the frame `num`.

        This frame is not cached on the image structure.
        """
        if self._tiffio is None:
            raise NotImplementedError("getframe is only implemented for TiffIO lib")

        if 0 <= num < self.nframes:
            image_data = self._tiffio.getData(num)
            tiff_header = self._tiffio.getInfo(num)
            return self._create_frame(image_data, tiff_header)
        raise Exception("getframe out of range")


tifimage = TifImage
