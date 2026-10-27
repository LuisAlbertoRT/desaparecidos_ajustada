import unittest

import pandas as pd

import config
from src.pipeline.derivadas import (
    _id_estado_extraido,
    _resolver_estado_extraido,
    columna_dimension,
)
from src.settings import Settings


class ResolverEstadoExtraidoTests(unittest.TestCase):
    def resolver(self, dependencias, ids):
        return _resolver_estado_extraido(
            pd.Series(dependencias, dtype="object"),
            pd.Series(ids, dtype="object"),
        )

    def test_mexico_y_ciudad_de_mexico_no_se_confunden(self):
        final, texto, _ = self.resolver(
            ["Fiscalía, Estado de México", "Agencia, Ciudad de México"], [9, 15]
        )
        self.assertEqual(texto.tolist(), [config.ENTIDADES[15], config.ENTIDADES[9]])
        self.assertEqual(final.tolist(), [config.ENTIDADES[15], config.ENTIDADES[9]])

    def test_id_extraido_alimenta_dimensiones_estatales(self):
        estados = pd.Series([config.ENTIDADES[15], config.ENTIDADES[9], pd.NA])
        ids = _id_estado_extraido(estados)
        self.assertEqual(ids.iloc[:2].tolist(), [15, 9])
        self.assertTrue(pd.isna(ids.iloc[2]))
        usar_estado_extraido = config.USAR_ESTADO_EXTRAIDO_EN_PRESENTACIONES
        try:
            config.USAR_ESTADO_EXTRAIDO_EN_PRESENTACIONES = True
            self.assertEqual(columna_dimension("rn", "cve_ent"), "idestado_final_nuevo")
            self.assertEqual(columna_dimension("rn", "entidad"), "estado_final_nuevo")
            config.USAR_ESTADO_EXTRAIDO_EN_PRESENTACIONES = False
            self.assertEqual(columna_dimension("rn", "cve_ent"), "idestado_derivada_rnpdno")
            self.assertEqual(columna_dimension("rn", "entidad"), "nombre_entidad_derivada_rnpdno")
        finally:
            config.USAR_ESTADO_EXTRAIDO_EN_PRESENTACIONES = usar_estado_extraido

    def test_aliases_de_mexico_y_ciudad_de_mexico(self):
        final, _, _ = self.resolver(
            [
                "Fiscalía Edomex.",
                "Fiscalía CDMX",
                "Agencia, Distrito Federal",
                "Agencia, D.F.",
            ],
            [None, None, None, None],
        )
        self.assertEqual(
            final.tolist(),
            [
                config.ENTIDADES[15], config.ENTIDADES[9],
                config.ENTIDADES[9], config.ENTIDADES[9],
            ],
        )

    def test_nombres_largos_acentos_puntuacion_y_mayusculas(self):
        final, _, _ = self.resolver(
            [
                "FISCALIA EN BAJA CALIFORNIA SUR.",
                "Agencia de SAN LUIS POTOSÍ;",
                "FISCALÍA REGIONAL, NUEVO LEON!!!",
                "Fiscalía, Coahuila de Zaragoza.",
            ],
            [None, None, None, None],
        )
        self.assertEqual(
            final.tolist(),
            [
                config.ENTIDADES[3], config.ENTIDADES[24],
                config.ENTIDADES[19], config.ENTIDADES[5],
            ],
        )

    def test_solo_extrae_estado_al_final_y_no_subcadenas(self):
        final, _, _ = self.resolver(
            ["Oficina de Jalisco, sede central", "Fiscalía de Chihuahua"],
            [17, 8],
        )
        self.assertEqual(final.tolist(), [config.ENTIDADES[17], config.ENTIDADES[8]])

    def test_fallback_valido_y_valores_no_resueltos(self):
        final, texto, respaldo = self.resolver(
            [None, "Dependencia sin estado", "Dependencia", "Dependencia"],
            [1, 32, 33, "id-invalido"],
        )
        self.assertEqual(texto.isna().tolist(), [True, True, True, True])
        self.assertEqual(respaldo.iloc[:2].tolist(), [config.ENTIDADES[1], config.ENTIDADES[32]])
        self.assertEqual(final.iloc[:2].tolist(), [config.ENTIDADES[1], config.ENTIDADES[32]])
        self.assertTrue(final.iloc[2:].isna().all())

    def test_dependencia_categorica_con_faltantes(self):
        final, texto, respaldo = _resolver_estado_extraido(
            pd.Series(pd.Categorical([None, "Fiscalía de CDMX"])),
            pd.Series([1, 15]),
        )
        self.assertEqual(final.iloc[0], config.ENTIDADES[1])
        self.assertEqual(texto.iloc[1], config.ENTIDADES[9])
        self.assertEqual(respaldo.iloc[1], config.ENTIDADES[15])

    def test_texto_tiene_prioridad_y_discrepancia_queda_detectable(self):
        final, texto, respaldo = self.resolver(
            ["Fiscalía de Estado de México"], [9]
        )
        self.assertEqual(final.iloc[0], config.ENTIDADES[15])
        self.assertEqual(texto.iloc[0], config.ENTIDADES[15])
        self.assertEqual(respaldo.iloc[0], config.ENTIDADES[9])
        self.assertNotEqual(texto.iloc[0], respaldo.iloc[0])

    def test_estado_extraido_para_clasificar_carpeta_es_configurable(self):
        anterior = config.USAR_ESTADO_EXTRAIDO_PARA_CLASIFICAR_CARPETA
        try:
            config.USAR_ESTADO_EXTRAIDO_PARA_CLASIFICAR_CARPETA = False
            self.assertFalse(
                Settings.desde_dict({}).usar_estado_extraido_para_clasificar_carpeta
            )
            config.USAR_ESTADO_EXTRAIDO_PARA_CLASIFICAR_CARPETA = True
            self.assertTrue(
                Settings.desde_dict({}).usar_estado_extraido_para_clasificar_carpeta
            )
        finally:
            config.USAR_ESTADO_EXTRAIDO_PARA_CLASIFICAR_CARPETA = anterior

    def test_cambiar_estado_de_clasificacion_invalida_cache_de_derivadas(self):
        estado_rnpdno = Settings.desde_dict({
            "usar_estado_extraido_para_clasificar_carpeta": False,
        })
        estado_extraido = Settings.desde_dict({
            "usar_estado_extraido_para_clasificar_carpeta": True,
        })
        self.assertNotEqual(estado_rnpdno.clave_universo, estado_extraido.clave_universo)


if __name__ == "__main__":
    unittest.main()