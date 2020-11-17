#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import pkg_resources


version = '0.1'


def is_installed(name):
    try:
        pkg_resources.get_distribution(name)
        return True
    except:
        return False


packages = [
    'daskaic'
]


requires = [
    'gdal',
    'pyproj',
    'dask[complete]'
]

setup(name='dask-mosaic',
      version=version,
      description='Create lazy reads and alignment of a mosaic of rasters',
      url='https://github.com/bluegeo/dask-mosaic',
      author='Devin Cairns',
      install_requires=requires,
      author_email='devin.cairns@bluegeo.ca',
      license='MIT',
      packages=packages,
      zip_safe=False)
