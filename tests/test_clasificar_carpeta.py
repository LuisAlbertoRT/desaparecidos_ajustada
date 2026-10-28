import unittest

import pandas as pd

from src.cleaning import clasificar_carpeta


class ClasificarCarpetaTests(unittest.TestCase):
    def test_colapsa_espacios_repetidos_en_folio_de_ciudad_de_mexico(self):
        folio = "CI-E-FDMDFDBP/C/UI-1  C/D/02238/08-2026"
        resultado = clasificar_carpeta(
            pd.Series([folio]),
            pd.Series([9]),
            modalidad=4,
        )
        self.assertTrue(resultado.iloc[0])


if __name__ == "__main__":
    unittest.main()
