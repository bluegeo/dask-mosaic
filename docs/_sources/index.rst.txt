.. Dask Mosaic documentation master file, created by
   sphinx-quickstart on Tue Nov 17 14:58:41 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Dask Mosaic
===========

*Create lazy reads and alignment of a mosaic of rasters*

**Background**

Leveraging the power of dask and lazily reading raster data is an effective way of managing memory and taking advantage of parallelism. This can be done easily using `xarray`, `rasterio`, and `dask`, although this only works with a single raster
dataset. Dask Mosaic seeks to allow similar functionality using a number of rasters as the input, regardless of
extent, resolution, and spatial reference.

Typically a new raster would need to be created using the `merge`
functionality of `rasterio`, then openend using `xarray` to yield a dask array. A merged raster file would need to be
rectangular and could take a large amount of storage and time to create. If the alignment of rasters was also done
lazily, this step may be skipped.

*When should this library be used?*

Where a number of rasters have similar resolutions and spatial references, the merging of data for extraction of smaller
blocks will be performant. Otherwise, where large blocks/chunks may be used, this library will still be beneficial.

*When should this not be used?*

If many rasters are referenced that have diverse spatial references, alignment, and projections, reading of blocks may
be slow. As such, using small chunking to save memory may be prohibitively slow.

.. toctree::
    :hidden:

    mosaic
    raster
