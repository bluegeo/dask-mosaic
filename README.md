# Dask-Mosaic

Create lazy reads and alignment of a mosaic of rasters

## Background

Leveraging the power of dask and lazily reading raster data is an effective way of managing memory and taking advantage of parallelism. This can be done easily using `xarray`, `rasterio`, and `dask`, although this only works with a single raster
dataset. Dask Mosaic seeks to allow similar functionality using a number of rasters as the input, regardless of
extent, resolution, and spatial reference.

Typically a new raster would need to be created using the `merge`
functionality of `rasterio`, then openend using `xarray` to yield a dask array. A merged raster file would need to be
rectangular and could take a large amount of storage and time to create. If the alignment of rasters was also done
lazily, this step may be skipped.

_When should this library be used?_

Where a number of rasters have similar resolutions and spatial references, the merging of data for extraction of smaller
blocks will be performant. Otherwise, where large blocks/chunks may be used, this library will still be beneficial.

_When should this not be used?_

If many rasters are referenced that have diverse spatial references, alignment, and projections, reading of blocks may
be slow. As such, using small chunking to save memory may be prohibitively slow.

## Usage

To lazily load a mosaic of rasters

```python
import daskaic
import dask.array as da

# Open a mosaic of 3 rasters. Note the shape includes 1 band because all rasters have one  band,
# and the band alignment defaults to an intersection of numbers
rasters = ['raster_1.tif', 'raster_2.tif', 'raster_3.tif']
data = daskaic.open_mosaic(rasters)

data
<daskaic of 3 rasters, shape=(1, 11800, 9981), dtype=float32, left=244590.0, top=6156495.0, csx=60.0, csy=60.0 chunks={'bands': 1, 'x': 1024, 'y': 1024}>

# Create a dask array
da.from_array(data, chunks=(data.chunks['bands'], data.chunks['y'], data.chunks['x']))
dask.array<array, shape=(1, 11800, 9981), dtype=float32, chunksize=(1, 1024, 1024), chunktype=numpy.ndarray>

# Another method to create a dask array directly is the preferred option
data = daskaic.open_dask(rasters)
data
dask.array<masked_equal, shape=(1, 11800, 9981), dtype=float32, chunksize=(1, 1024, 1024), chunktype=numpy.MaskedArray>
# This method also masks the array where there are no data, which is helpful for numpy operations that support masked arrays
da.compute(data.min(), data.max(), data.mean(), data.sum(), data.var(), data.std())
(7.5, 185.2, 28.82051, 1043275500.0, 224.68655, 14.989548)
```

When no kwargs are used, the parameters are inferred. Defaults include:

| kwarg            | Default Value | Description                                                                                                |
| ---------------- | ------------- | ---------------------------------------------------------------------------------------------------------- |
| `extent`         | `'union'`     | The processing extent. Defaults to the union of all rasters.                                               |
| `chunks`         | `2`           | Chunks for computation. Defaults to 1 band and 2x the smallest chunk size of all rasters.                  |
| `band_alignment` | `'number'`    | Alignment of raster bands. Default is all band numbers align.                                              |
| `dtype`          | `'highest'`   | Data type of extracted data. Defaults to the highest precision.                                            |
| `resample_algs`  | `None`        | Resample methods for each raster. Defaults to `None`, where the alg. is guessed using the data type.       |
| `merge_method`   | `'last'`      | How to merge overlapping data. Defaults to `'last'`, which means data from the last input raster are used. |
| `sr`             | `'first'`     | Extraction spatial reference. Defaults to the first input dataset.                                         |
| `csx`            | `'smallest'`  | Extraction cell size in the x-direction. Defaults to the smallest of all inputs.                           |
| `csy`            | `'smallest'`  | Extraction cell size in the y-direction. Defaults to the smallest of all inputs.                           |
| `nodata`         | `None`        | Raster no data value. Defaults to `None`, and the value is derived from the data type.                     |

## Cloud support

Reading of rasters is automatically aligned with GDAL Cloud Optimized GeoTiff drivers. This is beneficial for
cloud-native applications that need to seek chunks from COGs.

Dask Mosaic also supports `store` operations that write to local GeoTiffs in COG format. In fact, whenever the GeoTiff driver is used,
a COG is created.
