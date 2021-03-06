import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.mask import mask
from shapely.geometry import box
from fiona.crs import from_epsg
from pyproj import Transformer
import geopandas as gpd
from pycrs import parse
import json as js
import shapefile as sf
import io
import os


class Support:
    """
    Clase que tiene todos los métodos de soporte para manipular las imágenes
    """

    def __init__(self):
        pass

    @staticmethod
    def _load_image(path):
        return rasterio.open(path)

    def show_image_coordinates(self, src_path):
        """
        Devuelve las coordenadas en formato estándar (WS-84), apartir de la matriz de afinidad original.
        VORSICHT: Revisar si sigue haciendo falta porque mepa que no
        """
        src = self._load_image(src_path)

        transform_matrix = src.transform

        transformer = Transformer.from_crs("epsg:32720", "epsg:4326")
        return transformer.transform(transform_matrix[2], transform_matrix[5])

    def reprojection(self, final_crs, src_path, final_path):
        """
        Reproyecta una imagen al sistema de coordenadas que se le indique
        """
        src = self._load_image(src_path)

        original_width = src.width
        original_height = src.height

        transform, width, height = calculate_default_transform(src.crs, final_crs, original_width, original_height, *src.bounds)

        kwargs = src.meta.copy()
        kwargs.update({
            'crs': final_crs,
            'transform': transform,
            'width': width,
            'height': height})

        transformed_src = rasterio.open(final_path, 'w', **kwargs)
        for i in range(1, src.count + 1):
            reproject(
                source=rasterio.band(src, i),
                destination=rasterio.band(transformed_src, i),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=final_crs,
                resampling=Resampling.nearest)

    def crop_raster(self, coordinates, src_path, final_path):
        """
        Recorta la imagen a partir de un par de coordenadas (x,y) determinado.
        VORSICHT: quizás debería agregar el sistema de coordenadas como parámetro.
        Actualmente no está de esa manera porque todas las coordenadas con las que se trabajan son ws84 pero nunca se sabe...
        VORSICHT 2: debería controlar que las coordenadas estén dentro del rango de la imagen
        """
        src = self._load_image(src_path)

        polygon = box(coordinates[0], coordinates[1], coordinates[2], coordinates[3])
        geo_dataframe = gpd.GeoDataFrame({'geometry': polygon}, index=[0], crs=from_epsg(4326))
        geo_dataframe = geo_dataframe.to_crs(crs=src.crs.data)  # ponele

        polygon_coordinates = [js.loads(geo_dataframe.to_json())['features'][0]['geometry']]

        epsg_code = int(src.crs.data['init'][5:])

        out_img, out_transform = mask(src, shapes=polygon_coordinates, crop=True)

        metadata = src.meta.copy()

        cropped_crs = parse.from_epsg_code(epsg_code).to_proj4()

        metadata.update({"driver": "GTiff",
                         "height": out_img.shape[1],
                         "width": out_img.shape[2],
                         "transform": out_transform,
                         "crs": cropped_crs,
                         "dtype": rasterio.float32})

        with rasterio.open(final_path, "w", **metadata) as dest:
            dest.write(out_img)

    def parse_coordinates(self, json_path):
        dictionary = {}

        with open(json_path) as json_file:
            data = js.load(json_file)

            for i in data['features']:
                coordinates = i['geometry']['coordinates']
                title = i['properties']['Title']
                dictionary[title] = coordinates

        return dictionary

    def crop_process(self, images_path, src_name, data_path, datafile_name, encoding_type):
        original_image = images_path + '/' + src_name

        name, extension = os.path.splitext(datafile_name)

        if extension == '.json':
            json_path = data_path + datafile_name
            coordinates_dictionary = self.parse_coordinates(json_path)  # parseo un archivo de coordenadas con formato gmaps

            for i in coordinates_dictionary:
                cropped_path = images_path + '/' + i + '-' + src_name
                coordinates = coordinates_dictionary[i]  # deberían ser DOS pares de coordenadas, no uno solo
                print("Starting to crop at " + i)
                self.crop_raster(coordinates, original_image, cropped_path)

        else:  # agregar para uqe de alguna manera lo detecte como shape file... una condicion o algo que se fije de que en ese directorio están los tres archivos necesarios
            shapefile_path = data_path + datafile_name
            source = sf.Reader(shapefile_path, encoding=encoding_type)

            i = 0
            for item in source.iterShapeRecords():
                coordinates = item.shape.bbox
                cropped_path = images_path + '/' + str(i) + '-' + src_name
                i = i + 1
                self.crop_raster(coordinates, original_image, cropped_path)

    # esto tiene que tomar un raster ya reproyectado ¡!
    # TODO definir cuándo hacerlo
    # TODO testearlo acá (ver jupyter cualquier cosa)
    def get_coordinates_from_shapefile(self, data_path, shapefile_name, images_path, raster_name, encoding_type):
        shapefile_path = data_path + shapefile_name
        source = sf.Reader(shapefile_path, encoding=encoding_type)

        shape_type = source.shapeType

        shp = io.StringIO

        destination = sf.Writer(data_path + 'custom_coordinates', shp=shp, shapeType=shape_type, encoding=encoding_type)
        destination.fields = source.fields[1:]

        raster = rasterio.open(images_path + raster_name)
        border_coordinates = raster.bounds

        x_bound_min = abs(border_coordinates[0])
        y_bound_min = abs(border_coordinates[1])
        x_bound_max = abs(border_coordinates[2])
        y_bound_max = abs(border_coordinates[3])

        raster.close()

        for shaperec in source.iterShapeRecords():
            shp_borders = shaperec.shape.bbox

            x_min = abs(shp_borders[0])
            y_min = abs(shp_borders[1])
            x_max = abs(shp_borders[2])
            y_max = abs(shp_borders[2])

            # fijarse si hay alguna forma mejor de hacer esto
            if x_min <= x_bound_min and x_min >= x_bound_max and y_min <= y_bound_min and y_min >= y_bound_max:
                if x_max <= x_bound_min and x_max >= x_bound_max and y_max <= y_bound_min and y_max >= y_bound_max:
                    destination.record(*shaperec.record)
                    destination.shape(shaperec.shape)

        destination.close()
