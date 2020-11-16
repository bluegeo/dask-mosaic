# Dask-Mosaic
Create lazy reads and alignment of a mosaic of rasters

## Background
Leveraging the power of dask and lazily reading raster data is an effective way of managing memory and taking advantage of parallelism. This can be done easily using `xarray`, `rasterio`, and `dask`, although this only works with a single raster
dataset. `daskaic` seeks to allow similar functionality using a number of rasters as the input, regardless of
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

data = daskaic.open_mosaic(['raster_1.tif', 'raster_2.tif', 'raster_3.tif'])

data
<daskaic of 3 rasters, shape=(2, 1239, 1089), dtype=float64, chunksize=(1, 1024, 1024)>
```
When no kwargs are used, the parameters are inferred. Defaults include:

| kwarg | Default Value | Description |
| ----- | ------------- | ----------- |
| `extent` | `'union'` | The processing extent. Defaults to the union of all rasters. |
| `chunks` | `{'bands': 1, 'x': [derived], 'y': [derived]}` | Chunks for computation. Defaults to 1 band and 2x the smallest chunk size of all rasters. |
| `band_alignment` | `'number'` | Alignment of raster bands. Default is all band numbers align. |
| `dtype` | `'float64'` | Data type of extracted data. Defaults to `float64` |
| `sr` | `'first'` | Extraction spatial reference. Defaults to the first input dataset. |
| `csx` | `'smallest'` | Extraction cell size in the x-direction. Defaults to the smallest of all inputs. |
| `csy` | `'smallest'` | Extraction cell size in the y-direction. Defaults to the smallest of all inputs. |

All kwargs may also be overidden by a STAC json
```python
data = daskaic.open_mosaic(['raster_1.tif', 'raster_2.tif', 'raster_3.tif'], mosaic_json='mj_stac_spec.json')
```
