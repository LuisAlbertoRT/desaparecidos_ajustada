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

    def test_modalidad_5_acepta_coincidencia_con_entidad_rnpdno(self):
        resultado = clasificar_carpeta(
            pd.Series(["CI-ABC-12345-08-26"]),
            pd.Series([1]),
            modalidad=5,
            cve_entidad_alternativa=pd.Series([9]),
        )
        self.assertTrue(resultado.iloc[0])

    def test_modalidad_5_acepta_coincidencia_con_estado_extraido(self):
        resultado = clasificar_carpeta(
            pd.Series(["CI-ABC-12345-08-26"]),
            pd.Series([9]),
            modalidad=5,
            cve_entidad_alternativa=pd.Series([1]),
        )
        self.assertTrue(resultado.iloc[0])

    def test_modalidad_5_rechaza_si_no_coincide_con_ninguna_entidad(self):
        resultado = clasificar_carpeta(
            pd.Series(["CI-ABC-12345-08-26"]),
            pd.Series([9]),
            modalidad=5,
            cve_entidad_alternativa=pd.Series([32]),
        )
        self.assertFalse(resultado.iloc[0])


if __name__ == "__main__":
    unittest.main()
