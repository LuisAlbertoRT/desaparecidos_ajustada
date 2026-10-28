import unittest
from unittest.mock import patch

import pandas as pd

import config
from src.directorio_indicios import indicios_formalizados


class IndiciosFormalizadosTests(unittest.TestCase):
    def test_cuenta_registros_sin_entidad_y_no_los_incluye_en_las_graficas(self):
        directorio = pd.DataFrame({
            "fub": ["FUB1", "FUB2", "FUB3", "FUB4", "FUB5", "FUB6"],
            "estado_de_desaparicion": [
                None,
                33,
                "33",
                "Nacido en el extranjero",
                "nAcIdO   En El ExTrAnJeRo",
                "Tamaulipas",
            ],
        })
        comprimido = pd.DataFrame({
            "fub_rnpdno": ["FUB1", "FUB2", "FUB3", "FUB4", "FUB5", "FUB6"],
            "clasificacion_des_derivada_rnpdno": [
                "Localizados",
                "Desaparecidos",
                "Desaparecidos",
                "Localizados",
                "Desaparecidos",
                "Localizados",
            ],
        })

        with patch("src.directorio_indicios.leer_excel", return_value=directorio):
            tabulado, tabulado_32, conteos = indicios_formalizados(
                comprimido, verbose=False
            )

        self.assertEqual(conteos["sin_estado"], 2)
        self.assertNotIn(
            config.DIRECTORIO_INDICIOS_SIN_ESTADO,
            tabulado["estado_de_desaparicion"].tolist(),
        )
        self.assertNotIn(
            config.DIRECTORIO_INDICIOS_SIN_ESTADO,
            tabulado_32["estado_de_desaparicion"].tolist(),
        )


if __name__ == "__main__":
    unittest.main()
