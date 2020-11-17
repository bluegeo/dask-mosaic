from contextlib import contextmanager
import numpy as np
from osgeo import gdal


class Raster(object):
    """
    Open a raster dataset to read specifications and access data as numpy arrays
    """
    def __init__(self, data):
        self.source = data

        with self.ds as ds:
            sr = ds.GetProjectionRef()
            if sr is None:
                raise ValueError(
                    'Input raster sources must have a defined spatial reference'
                )
            self.sr = sr
            gt = ds.GetGeoTransform()
            self.left = gt[0]
            self.csx = gt[1]
            self.top = gt[3]
            self.csy = abs(gt[5])
            self.bands = ds.RasterCount
            self.shape = (self.bands, ds.RasterYSize, ds.RasterXSize)
            self.ndim = 3
            self.bottom = self.top - (self.csy * self.shape[1])
            self.right = self.left + (self.csx * self.shape[2])
            self.chunks = []
            self.nodata = []
            self.dtypes = []
            for i in range(1, self.bands + 1):
                band = ds.GetRasterBand(i)

                self.chunks.append(band.GetBlockSize())

                dtype = gdal.GetDataTypeName(band.DataType).lower()
                if dtype == 'byte':
                    dtype = 'uint8'
                self.dtypes.append(dtype)

                nd = band.GetNoDataValue()
                if nd is None:
                    self.nodata.append(np.nan)
                else:
                    self.nodata.append(nd)

    @property
    @contextmanager
    def ds(self):
        ds = gdal.Open(self.source)
        if ds is None:
            raise IOError(
                'Unable to open data source "{}"'.format(self.source)
            )
        yield ds
        ds = None

    @property
    def extent(self):
        return self.top, self.bottom, self.left, self.right

    def read_as_array(self, band, xoff=None, yoff=None, win_xsize=None, win_ysize=None):
        """
        Wrapper for ``gdal.ReadAsArray()``

        :param int band: Raster band index (starts from 1)
        :param int xoff: Index offset in the x-direction
        :param int yoff: Index offset in the y-direction
        :param int win_xsize: Shape of the extracted data block in the x-direction
        :param int win_ysize: Shape of the extracted data block in the y-direction
        """
        with self.ds as ds:
            a = ds.GetRasterBand(band).ReadAsArray(xoff=xoff, yoff=yoff, win_xsize=win_xsize, win_ysize=win_ysize)
        return a


def open_raster(raster_path):
    """
    Open a raster dataset from a specified path

    .. highlight:: python
    .. code-block:: python

        from daskaic import open_raster

        r = open_raster('raster_1.tif')
        numpy_array = r.read_as_array(1)
    """
    return Raster(raster_path)
