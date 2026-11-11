import tempfile
import unittest
from pathlib import Path

from src.graficas_sin_datos import aviso_sin_datos


class AvisoSinDatosTests(unittest.TestCase):
    def test_guarda_png_y_svg_con_el_mismo_aviso(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio)

            aviso_sin_datos("grafica_vacia", 18, 12, ruta)

            self.assertTrue((ruta / "grafica_vacia.png").is_file())
            svg = ruta / "grafica_vacia_scour.svg"
            self.assertTrue(svg.is_file())
            self.assertIn("<svg", svg.read_text())


if __name__ == "__main__":
    unittest.main()
