import numpy as np
import dask.array as da
from osgeo import gdal
from .abstract import Raster
from .util import compare_projections, transform_extent, get_user_sr, get_highest_dtype, nearly_aligns, intersects


class Mosaic(object):

    gdal_resample_methods = [
        'near', 'bilinear', 'cubic', 'cubicspline', 'lanczos', 'average',
        'mode', 'max', 'min', 'med', 'q1', 'q3', 'sum', 'proportion'
    ]

    merge_methods = [
        'last', 'first', 'min', 'max', 'average', 'sum'
    ]

    def __init__(self, rasters, **kwargs):
        if len(rasters) == 0:
            raise ValueError('A Mosaic requires one or more rasters')

        self.rasters = [Raster(raster) for raster in rasters]

        #
        # Populate mosaic specifications
        #
        # Read options
        self.band_alignment = self._populate_band_alignment(kwargs.get('band_alignment', 'number'))
        self.resample_algs = self._populate_resample_algs(kwargs.get('resample_algs', None))
        self.merge_method = kwargs.get('merge_method', 'last').lower()
        if self.merge_method not in self.merge_methods:
            raise ValueError('Merge method must be one of those specified in Mosaic.merge_methods')

        # Spatial reference
        self.sr = self._populate_sr(kwargs.get('sr', 'first'))
        self.top, self.bottom, self.left, self.right = self._populate_extent(kwargs.get('extent', 'union'))
        self.csx, self.csy = self._populate_cs(kwargs.get('csx', 'smallest'), kwargs.get('csy', 'smallest'))
        self.shape = (
            self.bands,
            int(np.ceil((self.top - self.bottom) / self.csy)),
            int(np.ceil((self.right - self.left) / self.csx))
        )

        # Check for valid discretization
        if any([s < 1 for s in self.shape]):
            raise ValueError('A negative or zero-dimension mosaic resulted from the specified extent and cell size')

        # Adjust the extent using the input cell size
        self.bottom = self.top - (self.shape[1] * self.csy)
        self.right = self.left + (self.shape[2] * self.csx)

        # Data specifications
        self.dtype = self._populate_dtype(kwargs.get('dtype', 'highest'))
        self.nodata = self._populate_nodata(kwargs.get('nodata', None))

        # For Dask
        self.ndim = 3
        self.chunks = self._populate_chunks(kwargs.get('chunks', 2))

        # Internal
        self.band_cache = {}

    @property
    def bands(self):
        if self.band_alignment == 'number':
            return max([rast.bands for rast in self.rasters])
        else:
            return len(self.band_alignment)

    @property
    def extent(self):
        return self.top, self.bottom, self.left, self.right

    def _populate_band_alignment(self, data):
        if isinstance(data, dict):
            if any([len(vals) != len(self.rasters) for _, vals in data.items()]):
                raise ValueError('Band alignment numbers must match number of rasters in the mosaic')
        elif data.lower() != 'number':
            raise ValueError('Band alignment must be a correlation dict or the value "number"')
        else:
            return data.lower()

    def _populate_sr(self, data):
        if data == 'first':
            return self.rasters[0].sr
        elif data == 'last':
            return self.rasters[-1].sr
        else:
            return get_user_sr(data)

    def _populate_extent(self, data):
        if data == 'union':
            top, bottom, left, right = transform_extent(self.rasters[0].extent, self.rasters[0].sr, self.sr)
            for rast in self.rasters[1:]:
                next_top, next_bottom, next_left, next_right = transform_extent(rast.extent, rast.sr, self.sr)
                top = max(next_top, top)
                bottom = min(next_bottom, bottom)
                left = min(next_left, left)
                right = max(next_right, right)

        elif data == 'first':
            top, bottom, left, right = transform_extent(self.rasters[0].extent, self.rasters[0].sr, self.sr)

        elif data == 'last':
            top, bottom, left, right = transform_extent(self.rasters[-1].extent, self.rasters[-1].sr, self.sr)

        else:
            try:
                top, bottom, left, right = map(float, data)
            except ValueError:
                raise ValueError(
                    'Extent expected to be an iterable of floats with length 4 (top, bottom, left, right)'
                )

        return top, bottom, left, right

    def _populate_chunks(self, data):
        if isinstance(data, dict):
            if not all(['y' in data, 'x' in data, 'bands' in data]):
                raise ValueError('Chunks must specify bands, x, and y values')
            return data
        x, y = self.rasters[0].chunks[0]
        for rast in self.rasters:
            for chunk in rast.chunks:
                x = min(chunk[0], x)
                y = min(chunk[1], y)

        x = max(256, min(x * data, self.shape[2]))
        y = max(256, min(y * data, self.shape[1]))

        return {'bands': 1, 'x': x, 'y': y}

    def _populate_dtype(self, data):
        if data == 'highest':
            dtypes = []
            for rast in self.rasters:
                dtypes += rast.dtypes
            return get_highest_dtype(np.unique(dtypes))
        elif data == 'first':
            return self.rasters[0].dtypes[0]
        elif data == 'last':
            return self.rasters[-1].dtypes[-1]
        else:
            return np.dtype(data).name

    def _populate_cs(self, csx, csy):
        ret = []
        for cs, val in [('csx', csx), ('csy', csy)]:
            try:
                ret.append(abs(float(val)))
            except ValueError:
                sizes = []
                for rast in self.rasters:
                    # Convert the cell size to the target spatial reference
                    if not compare_projections(self.sr, rast.sr):
                        top, bottom, left, right = transform_extent(self.extent, self.sr, rast.sr)
                        if cs == 'csy':
                            sizes.append(
                                (self.extent[0] - self.extent[1]) / ((top - bottom) / rast.csy)
                            )
                        else:
                            sizes.append(
                                (self.extent[3] - self.extent[2]) / ((right - left) / rast.csx)
                            )
                    else:
                        sizes.append(getattr(rast, cs))

                if val == 'smallest':
                    ret.append(min(sizes))
                elif val == 'largest':
                    ret.append(max(sizes))
                elif val == 'average':
                    ret.append(sum(sizes) / len(sizes))
                else:
                    raise ValueError('Unrecognized {} input: "{}"'.format(cs, val))

        return ret

    def _populate_resample_algs(self, algs):
        if algs is None:
            return ['bilinear' if any(['float' in dt for dt in rast.dtypes]) else 'near' for rast in self.rasters]
        else:
            if len(algs) < len(self.rasters):
                raise ValueError('Number of resampling algorithms must match the number of input rasters')
            if any([alg not in self.gdal_resample_methods for alg in algs]):
                raise ValueError('Resample methods must be one of those included in Mosaic.gdal_resample_methods')
            return algs

    def _populate_nodata(self, data):
        if data is None:
            if self.dtype == 'bool':
                return False
            if 'u' in self.dtype:
                return np.iinfo(self.dtype).max
            elif 'int' in self.dtype:
                return np.iinfo(self.dtype).min
            else:
                return np.finfo(self.dtype).min
        else:
            return getattr(np, self.dtype)(data)

    def _raster_data(self, raster, band_index, j_start, i_start, shape_i, shape_j, resample_alg, band_cache):
        # Translate the slice to the raster dimensions
        xmin = self.left + (j_start * self.csx)
        ymax = self.top - (i_start * self.csy)
        ymin = ymax - shape_i * self.csy
        xmax = xmin + shape_j * self.csx

        rast_ymax, rast_ymin, rast_xmin, rast_xmax = transform_extent((ymax, ymin, xmin, xmax), self.sr, raster.sr)

        # If the band index does not exist, or the extents do not intersect, return no data
        if band_index > raster.bands or not intersects((rast_ymax, rast_ymin, rast_xmin, rast_xmax), raster.extent):
            return np.full((shape_i, shape_j), self.nodata, self.dtype), np.zeros((shape_i, shape_j), 'bool')

        # If the mosaic and the raster both align a simple slice may be used
        if nearly_aligns(self, raster):
            # Extraction dimensions
            e_i = int(round((raster.top - rast_ymin) / raster.csy))
            e_j = int(round((rast_xmin - raster.left) / raster.csx))
            e_i_shape = raster.shape[1]
            e_j_shape = raster.shape[2]

            # Find offset on raster and adjust insertion location in original slice
            if e_i < 0:
                i_start = abs(e_i)
                e_i = 0
            else:
                i_start = 0
                e_i_shape -= e_i
            if e_j < 0:
                j_start = abs(e_j)
                e_j = 0
            else:
                j_start = 0
                e_j_shape -= e_j

            # Adjust the shape for the opposite edge
            e_i_shape = min(shape_i, e_i_shape)
            e_j_shape = min(shape_j, e_j_shape)

            a = np.full((shape_i, shape_j), raster.nodata[band_index - 1], raster.dtypes[band_index - 1])
            a[i_start:i_start + e_i_shape, j_start:j_start + e_j_shape] = raster.read_as_array(
                band_index, e_j, e_i, e_j_shape, e_i_shape
            )
            a = a.astype(self.dtype)
            nodata = getattr(np, self.dtype)(raster.nodata[band_index - 1])

        # Otherwise a transformation should occur to align the grids
        else:
            # To avoid redundant warp operations, a band cache is first checked
            bc = band_cache[band_index]
            if bc is not None:
                print('Band cache used')
                a, nodata = bc
            else:
                ds = gdal.Warp(
                    'mem',
                    raster.source,
                    srcSRS=raster.sr,
                    dstSRS=self.sr,
                    outputBounds=(xmin, ymin, xmax, ymax),
                    format='MEM',
                    xRes=self.csx,
                    yRes=self.csy,
                    resampleAlg=resample_alg,
                    multithread=True
                )
                for bi in band_cache.keys():
                    band = ds.GetRasterBand(bi)
                    nodata = getattr(np, self.dtype)(band.GetNoDataValue())
                    a = band.ReadAsArray().astype(self.dtype)
                    band = None
                    band_cache[bi] = a, nodata
                ds = None
                a, nodata = band_cache[band_index]

        return a, a != nodata

    def _parse_slice(self, s):
        """
        Slices can:
            - Be a `slice` object
            - Be None
            - Be an Integer
            - vary from 0 to 3 in length

        :param s:
        :return:
        """
        if not hasattr(s, '__iter__'):
            s = [s]
        if len(s) > 3:
            raise IndexError(
                'Rasters must be indexed in a maximum of 3 dimensions')

        s = list(s)
        s += [slice(None, None, None)] * (3 - len(s))

        def check_index(item, i, start=True):
            if (item >= self.shape[i] and start) or (item > self.shape[i] and not start):
                raise IndexError('Index {} out for range for dimension {} of size {}'.format(
                    item, i, self.shape[i])
                )

        def get_slice_item(item, i):
            if isinstance(item, int):
                check_index(item, i)
                return item, item + 1
            elif isinstance(item, slice):
                start = item.start or 0
                check_index(start, i)
                stop = item.stop or self.shape[i]
                check_index(stop, i, False)
                return start, stop
            elif item is None:
                return 0, self.shape[i]
            else:
                raise IndexError(
                    'Unsupported slice format {}'.format(type(item).__name__))

        slicers = ()
        for i, item in enumerate(s):
            slicers += get_slice_item(item, i)

        return slicers

    def __getitem__(self, s):
        if s == (slice(0, 0, None), slice(0, 0, None), slice(0, 0, None)):
            # Dask calls with empty slices when using from_array
            return np.array([]).reshape((0, 0, 0))

        b_start, b_stop, i_start, i_stop, j_start, j_stop = self._parse_slice(s)

        if b_start > self.bands - 1:
            raise IndexError(
                'Band {} out of bounds for band count {}'.format(b_start, self.bands)
            )
        if i_start > self.shape[1] - 1:
            raise IndexError(
                'Index {} out of bounds for axis 0 with shape {}'.format(i_start, self.shape[1])
            )
        if j_start > self.shape[2] - 1:
            raise IndexError(
                'Index {} out of bounds for axis 1 with shape {}'.format(j_start, self.shape[2])
            )

        # Allocate output array
        shape = (b_stop - b_start, i_stop - i_start, j_stop - j_start)

        if self.merge_method == 'average':
            modals = np.zeros(shape, 'uint64')
            output = np.zeros(shape, self.dtype)
        else:
            output = np.full(shape, self.nodata, self.dtype)

        # Build a band list for each raster
        all_bands = []
        for ri in range(len(self.rasters)):
            bands = []
            for band in range(b_start, b_stop):
                if self.band_alignment == 'number':
                    bands.append(band)
                else:
                    bands.append(self.band_alignment[band][ri] - 1)
            all_bands.append(bands)

        for raster, bands, alg in zip(self.rasters, all_bands, self.resample_algs):
            band_cache = {band + 1: None for band in bands}
            for band in bands:
                band_index = band + 1

                a, in_mask = self._raster_data(
                    raster, band_index, j_start, i_start, shape[1], shape[2], alg, band_cache
                )

                if self.merge_method == 'last':
                    output[band, ...][in_mask] = a[in_mask]
                elif self.merge_method == 'first':
                    m = (output[band, ...] == self.nodata) & in_mask
                    output[band, ...][m] = a[m] 
                elif self.merge_method == 'average':
                    modals[band, ...][in_mask] += 1
                    output[band, ...][in_mask] += a[in_mask]
                else:
                    m = (output[band, ...] == self.nodata) & in_mask
                    output[band, ...][m] = a[m]
                    if self.merge_method == 'sum':
                        m = ~m & in_mask
                        output[band, ...][m] += a[m]
                    elif self.merge_method == 'min':
                        m = (output[band, ...] != self.nodata) & in_mask
                        output[band, ...][m] = np.minimum(output[band, ...][m], a[m])
                    elif self.merge_method == 'max':
                        m = (output[band, ...] != self.nodata) & in_mask
                        output[band, ...][m] = np.maximum(output[band, ...][m], a[m])

        if self.merge_method == 'average':
            output = np.where(modals > 0, output / modals, self.nodata)

        return output

    def slice(self, extent):
        top, bottom, left, right = extent
        if top <= bottom or right <= left:
            raise ValueError('Cannot slice with negative or zero dimensions')
        
        if top > self.top:
            raise IndexError('Top of extent exceeds mosaic boundary')
        if left < self.left:
            raise IndexError('Left of extent exceeds mosaic boundary')
        if right > self.right:
            raise IndexError('Right of extent exceeds mosaic boundary')
        if bottom < self.bottom:
            raise IndexError('Bottom of extent exceeds mosaic boundary')

        i_fr = int(np.floor((self.top - top) / self.csy))
        i_to = int(np.ceil((self.top - bottom) / self.csy))
        j_fr = int(np.floor((left - self.left) / self.csx))
        j_to = int(np.ceil((right - self.left) / self.csx))

        return da.ma.masked_equal(
            da.from_array(
                self,
                chunks=(self.chunks['bands'], self.chunks['y'], self.chunks['x'])
            )[i_fr:i_to, j_fr:j_to],
            self.nodata
        )

    def __repr__(self):
        return '<daskaic of {} rasters, shape={}, dtype={}, left={}, top={}, csx={}, csy={} chunks={}>'.format(
            len(self.rasters),
            self.shape,
            self.dtype,
            self.left,
            self.top,
            self.csx,
            self.csy,
            self.chunks
        )


def open_mosaic(rasters, **kwargs):
    return Mosaic(rasters, **kwargs)


def open_dask(rasters, **kwargs):
    mosaic = open_mosaic(rasters, **kwargs)
    return da.ma.masked_equal(
        da.from_array(mosaic, chunks=(mosaic.chunks['bands'], mosaic.chunks['y'], mosaic.chunks['x'])),
        mosaic.nodata
    )
