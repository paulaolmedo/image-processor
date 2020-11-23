import rasterio
from rasterio import plot
from rasterio import crs
import matplotlib.pyplot as plt
import numpy as np
import gdal
from affine import Affine
from pyproj import Transformer
import json

from ..model import models

satellite_extensions = {
    'sentinel': '.jp2',
    'landsat8a': '.tif',
}

class NormalizedDifferenceIndex:
    def __init__(self, image_path, satellite):
        self.red_path = image_path + 'red' + satellite_extensions[satellite]
        self.nir10_path = image_path + 'nir_4' + satellite_extensions[satellite]
        self.nir20_path = image_path + 'nir_3' + satellite_extensions[satellite]
        self.swir_path = image_path + 'swir' + satellite_extensions[satellite]
        
        self.ndvi_path = image_path + 'ndvi.tiff'
        self.ndwi_path = image_path + 'ndwi.tiff'
        #self.red_path = image_path + 'B4' + satellite_extensions[satellite]
        
    @staticmethod
    def _load_image(path):
        return rasterio.open(path)

    def calculate_ndvi(self):
        red_frequency = self._load_image(self.red_path)
        nir_frequency = self._load_image(self.nir10_path)
        
        red = red_frequency.read(1).astype('float64')
        nir = nir_frequency.read(1).astype('float64')

        np.seterr(divide='ignore', invalid='ignore')
        #ndvi = 65536 * np.divide((nir-red),(nir+red)) -> it's not the same ¿?
        ndvi = np.where((nir - red)==0., 0, (nir-red)/(nir+red))
        dimensions = np.array([red_frequency.width, red_frequency.height, red_frequency.crs, red_frequency.transform])

        red_frequency.close()
        nir_frequency.close()
        
        return ndvi, dimensions

    def calculate_ndwi(self):
        swir_frequency = self._load_image(self.swir_path)
        nir_frequency = self._load_image(self.nir20_path)
        
        swir = swir_frequency.read(1).astype('float64')
        nir = nir_frequency.read(1).astype('float64')

        np.seterr(divide='ignore', invalid='ignore')
        ndwi = 65536 * np.divide((nir-swir),(nir+swir))
        dimensions = np.array([swir_frequency.width, swir_frequency.height, swir_frequency.crs, swir_frequency.transform])

        swir_frequency.close()
        nir_frequency.close()

        return ndwi, dimensions

    def write_ndvi_image(self):
        ndvi, dimensions = self.calculate_ndvi()
        
        ndviImage = rasterio.open(self.ndvi_path, 'w', driver='Gtiff',
                          width=dimensions[0], height=dimensions[1],
                          count=1,
                          crs=dimensions[2],
                          transform=dimensions[3],
                          dtype='float64'                  
                         )
        ndviImage.write(ndvi, 1)
        ndviImage.close()

    def write_ndwi_image(self):
        ndwi, dimensions = self.calculate_ndwi()

        ndviImage = rasterio.open(self.ndwi_path, 'w', driver='Gtiff',
                          width=dimensions[0], height=dimensions[1],
                          count=1,
                          crs=dimensions[2],
                          transform=dimensions[3],
                          dtype='float64'                  
                         )
        ndviImage.write(ndwi, 1)
        ndviImage.close()
    
    def plot_ndvi_image(self, plot_name):
        ndviImage = self._load_image(self.ndvi_path)
        
        plot.show(ndviImage, ' ')
        rasterio.plot.show_hist(ndviImage, bins=1000, masked=True, title=plot_name, ax=None)
        ndviImage.close()
    
    def plot_ndwi_image(self):
        ndwiImage = self._load_image(self.ndwi_path)
        plot.show(ndwiImage, ' ')
    
    def show_image_coordinates(self, src_path):
        src = self._load_image(src_path)
        
        transform_matrix = src.transform #devuelve la matriz de afinidad con las coordenadas correspondientes

        transformer = Transformer.from_crs("epsg:32720", "epsg:4326")
        return transformer.transform(transform_matrix[2], transform_matrix[5])

class InitInformation:
    def __init__(self, file_name):
        self.file_name = file_name

    def _init_ndvi(self):
        """
        Returns a NormalizedDifferenceIndex instance
        """
        #TODO paramentrizar el nombre del sate como se hizo en la clase de arriba
        return NormalizedDifferenceIndex(self.file_name, 'sentinel')

    def _init_satellite_image(self):
        ndvi_instance = self._init_ndvi()

        #TODO parametrizar fecha, tag, etc (estos sólo son datos de prueba)
        date_time = '2012-04-23T18:25:43.511Z'
        geographicInformation = models.GeographicInformation('test_tag', ndvi_instance.show_image_coordinates(self.file_name  + 'red.jp2'))
        
        ndvi, dimensions = ndvi_instance.calculate_ndvi()
        normalizedIndexes = models.NormalizedIndexes(ndvi.tolist(), 0)

        #temporalmente no muestro los índices porque es un array desastroso
        satelliteImageProcessed = models.SatelliteImageProcessed(self.file_name, json.dumps(geographicInformation.__dict__), date_time, 0)
        return satelliteImageProcessed.__dict__