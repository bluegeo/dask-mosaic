import os
from contextlib import contextmanager
import numpy as np
from osgeo import gdal


class Raster(object):
    """
    Open a raster dataset to read specifications and access data as numpy arrays
    """

    def __init__(self, data):
        self.source = data

        # Remote data cannot be opened in 'w' mode, assert whether data are local
        self.remote = True
        if os.path.isfile(data) or os.path.isdir(data):
            self.remote = False

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
                    self.nodata.append(None)
                else:
                    self.nodata.append(float(nd))

    @property
    @contextmanager
    def ds(self):
        if self.remote:
            ds = gdal.Open(self.source)
        else:
            ds = gdal.Open(self.source, 1)
        
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

    @staticmethod
    def _gdal_args_from_slice(s):
        """
        Collect the required parameters to insert data into a raster using GDAL

        :param s: slice
        :return:
        """
        if not hasattr(s, '__iter__'):
            s = [s]
        if len(s) > 3:
            raise IndexError(
                'Rasters slices cannot have more than 3 dimensions')

        s = list(s)
        s += [slice(None, None, None)] * (3 - len(s))

        band = s[0].start or 0
        yoff = s[1].start or 0
        xoff = s[2].start or 0

        return band + 1, xoff, yoff

    def __setitem__(self, s, a):
        band, xoff, yoff = self._gdal_args_from_slice(s)

        if band > self.bands:
            raise IndexError('Band {} out of range (raster has {} bands)'.format(band, self.bands))
        if xoff + a.shape[2] > self.shape[2] or yoff + a.shape[1] > self.shape[1]:
            raise IndexError(
                'Array of shape {} offset by ({}, {})  exceeds the raster with shape {}'.format(
                    a.shape, yoff, xoff, self.shape
                )
            )

        if hasattr(a, 'mask'):
            a[np.ma.getmaskarray(a)] = self.nodata[band - 1]
        a = np.squeeze(a, 0)

        with self.ds as ds:
            ds.GetRasterBand(band).WriteArray(a, xoff=xoff, yoff=yoff)
            ds.FlushCache()


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


def create_raster_source(raster_path, top, left, shape, csx, csy, sr, dtype, nodata, chunks):
    """
    Create a raster source at a specified path using the given spatial definition

    :param float top: Top coordinate
    :param float left: Left coordinate
    :param tuple shape: Shape
    :param float csx: Cell size in the x-direction
    :param float csy: Cell size in the y-direction
    :param str sr: Spatial Reference as a WKT
    :param str dtype: Data type - in ``numpy.dtype`` form
    :param number nodata: No Data value for each band
    """
    if raster_path.split('.')[-1].lower() == 'tif':
        driver = gdal.GetDriverByName('GTiff')
        dtype = 'Byte' if dtype in ['uint8', 'int8', 'bool'] else dtype
        dtype = 'int32' if dtype == 'int64' else dtype
        dtype = 'uint32' if dtype == 'uint64' else dtype
        comp = 'COMPRESS=LZW'
        if shape[1] > chunks['y'] and shape[2] > chunks['x']:
            blockxsize = 'BLOCKXSIZE=%s' % chunks['x']
            blockysize = 'BLOCKYSIZE=%s' % chunks['y']
            tiled = 'TILED=YES'
        else:
            blockxsize, blockysize, tiled = 'BLOCKXSIZE=0', 'BLOCKYSIZE=0', 'TILED=NO'
        creation_options = [tiled, blockysize, blockxsize, comp]
        dst = driver.Create(raster_path,
                            int(shape[2]),
                            int(shape[1]),
                            int(shape[0]),
                            gdal.GetDataTypeByName(dtype),
                            creation_options)
    else:
        dst = None

    if dst is None:
        raise IOError('Unable to save the file {}'.format(raster_path))

    dst.SetProjection(sr)
    dst.SetGeoTransform((left, csx, 0, top, 0, csy * -1))
    for bi in range(int(shape[0])):
        band = dst.GetRasterBand(bi + 1)
        band.SetNoDataValue(nodata)
        band = None
    dst = None

    return Raster(raster_path)
