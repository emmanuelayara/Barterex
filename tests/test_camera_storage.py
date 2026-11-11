import io
import unittest

from PIL import Image

from file_upload_validator import optimize_image_for_storage


class CameraStorageTests(unittest.TestCase):
    def encode(self, size, extension='jpeg'):
        source = Image.new('RGB', size, (55, 120, 185))
        data = io.BytesIO()
        source.save(data, format=extension)
        return optimize_image_for_storage(data.getvalue(), extension)

    def test_large_photo_preserves_6000_pixels_instead_of_4096(self):
        stored = Image.open(io.BytesIO(self.encode((6000, 4000))))
        self.assertEqual(stored.size, (6000, 4000))
        self.assertEqual(stored.format, 'JPEG')
        # Pillow's standard quality-95 luminance quantization table begins at 2.
        self.assertEqual(stored.quantization[0][0], 2)

    def test_portrait_photo_preserves_aspect_ratio(self):
        stored = Image.open(io.BytesIO(self.encode((3000, 4500))))
        self.assertEqual(stored.size, (3000, 4500))

    def test_very_large_photo_is_bounded_to_6144_pixels(self):
        stored = Image.open(io.BytesIO(self.encode((7000, 3500))))
        self.assertEqual(stored.size, (6144, 3072))

    def test_smaller_photos_are_not_upscaled(self):
        for extension in ('jpeg', 'png', 'webp'):
            with self.subTest(extension=extension):
                stored = Image.open(io.BytesIO(self.encode((640, 480), extension)))
                self.assertEqual(stored.size, (640, 480))

    def test_camera_metadata_is_not_saved(self):
        image = Image.new('RGB', (100, 80))
        exif = Image.Exif()
        exif[270] = 'Private camera metadata'
        source = io.BytesIO()
        image.save(source, format='JPEG', exif=exif)
        stored = Image.open(io.BytesIO(optimize_image_for_storage(source.getvalue(), 'jpeg')))
        self.assertFalse(stored.getexif())
