import numpy as np
from pyproj import CRS
from osgeo import osr


def transform_extent(extent, in_sr, out_sr):
    if compare_projections(in_sr, out_sr):
        return extent

    insr = osr.SpatialReference()
    insr.ImportFromWkt(get_user_sr(in_sr))
    outsr = osr.SpatialReference()
    outsr.ImportFromWkt(get_user_sr(out_sr))

    # Ensure resulting axes are still in the order x, y
    insr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    outsr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    coordTransform = osr.CoordinateTransformation(insr, outsr)
    left_1, top_1 = coordTransform.TransformPoint(extent[2], extent[0])[:2]
    right_1, top_2 = coordTransform.TransformPoint(extent[3], extent[0])[:2]
    right_2, bottom_1 = coordTransform.TransformPoint(extent[3], extent[1])[:2]
    left_2, bottom_2 = coordTransform.TransformPoint(extent[2], extent[1])[:2]

    coords = (max(top_1, top_2), min(bottom_1, bottom_2), min(left_1, left_2), max(right_1, right_2))
    if any([np.isinf(c) or np.isnan(c) for c in coords]):
        raise ValueError('Extent out of bounds for target spatial reference. Try a different mosaic extent.')

    return coords


def get_user_sr(input):
    return CRS.from_user_input(input).to_wkt()


def compare_projections(proj1, proj2):
    osr_proj1 = osr.SpatialReference()
    osr_proj2 = osr.SpatialReference()

    osr_proj1.ImportFromWkt(get_user_sr(proj1))
    osr_proj2.ImportFromWkt(get_user_sr(proj2))

    return osr_proj1.IsSame(osr_proj2)


def get_highest_dtype(dtypes):
    return dtypes[
        np.argmax([np.dtype(dt).itemsize * 1.5 if 'float' in dt else np.dtype(dt).itemsize for dt in dtypes])
    ]


def intersects(extent_1, extent_2):
    return not any([
        extent_1[0] <= extent_2[1],  # Top of 1 le to Bottom of 2
        extent_1[1] >= extent_2[0],  # Bottom of 1 ge to Top of 2
        extent_1[2] >= extent_2[3],  # Left of 1 ge to Right of 2
        extent_1[3] <= extent_2[2],  # Right of 1 le to Left of 2
    ])


def nearly_aligns(mosaic, raster):
    return all([
        compare_projections(mosaic.sr, raster.sr),  # Same spatial reference
        np.isclose(mosaic.csx, raster.csx),  # X-cell size
        np.isclose(mosaic.csy, raster.csy),  # Y-cell size
        any(np.isclose((mosaic.top - raster.top) % mosaic.csy, [0, mosaic.csy])),  # Y-coordinate
        any(np.isclose((raster.left - mosaic.left) % mosaic.csx, [0, mosaic.csx])),  # X-coordinate
    ])
