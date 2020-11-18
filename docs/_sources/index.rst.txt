.. Dask Mosaic documentation master file, created by
   sphinx-quickstart on Tue Nov 17 14:58:41 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Dask Mosaic
===========

*Create lazy reads and alignment of a mosaic of rasters*

Background
##########

Leveraging the power of dask and lazily reading raster data is an effective way of managing memory and taking advantage of parallelism.
This can be done easily using `xarray, rasterio, and dask <https://examples.dask.org/applications/satellite-imagery-geotiff.html>`_,
although this only works with a single raster dataset. Dask Mosaic seeks to allow similar functionality using a number of rasters as the input, regardless of
extent, resolution, and spatial reference.

Typically a new raster would need to be created using the `rasterio.merge <https://rasterio.readthedocs.io/en/latest/api/rasterio.merge.html>`_
method, then openend using `xarray <http://xarray.pydata.org/en/stable/generated/xarray.open_rasterio.html>`_ to yield a dask array.
A merged raster file would need to be rectangular and could take a large amount of storage and time to create. If the alignment of rasters was also done
lazily, this step may be skipped.

*When should this library be used?*

Where a number of rasters have similar resolutions and spatial references, the merging of data for extraction of smaller
blocks will be performant. Otherwise, where large blocks/chunks may be used, this library will still be beneficial.

*When should this not be used?*

If many rasters are referenced that have diverse spatial references, alignment, and projections, reading of blocks may
be slow. As such, using small chunking to save memory may be prohibitively slow.

Quickstart
##########
Compute topogrpahic slope from 3 rasters that exist throughout a study area

Create a mosaic and combine rasters that overlap with a mean calculation.
Also, set a desired spatial reference and resolution.

.. code-block:: python

   from daskaic import open_mosaic
   import dask.array as da
   import numpy as np
   

   rasters = [
      '/home/user/my_elevation.tif',  # Local
      '/vsis3_streaming/my-terrain-bucket/elevation.tif',  # COG on an S3 bucket
      '/shared/client_dem.tif'  # Local
   ]
   mosaic = open_mosaic(rasters, merge_method='average', sr=26911, csx=15, csy=15)

Collect the dask array (lazy data reading) from the mosaic and calculate slope in degrees

.. code-block:: python

   a = mosaic.dask

   # Remove first dimension because we're dealing with only one band
   a = da.squeeze(a)

   # Calculate gradient in the x and y-directions
   dx = ((a[:-2, :-2] + (2 * a[1:-1, :-2]) + a[2:, :-2]) - (a[:-2, 2:] + (2 * a[1:-1, 2:]) + a[2:, 2:]))
   dx /= (8 * mosaic.csx)
   dy = ((a[:-2, :-2] + (2 * a[:-2, 1:-1]) + a[:-2, 2:]) - (a[2:, :-2] + (2 * a[2:, 1:-1]) + a[2:, 2:]))
   dy /= (8 * mosaic.csy)

   # Calculate slope in degrees
   slope = da.arctan(da.sqrt((dx**2) + (dy**2))) * (180 / np.pi)

   # Important - the dask shape must match the original mosaic
   slope = da.pad(
       slope, ((1, 1), (1, 1)),
       mode='constant', constant_values=mosaic.nodata
   )

   # Save the output to a GeoTiff
   mosaic.store(slope, '/home/user/slope_from_mosaic.tif')

.. toctree::
    :hidden:

    installation
    mosaic
    raster
