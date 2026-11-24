# 1. Fuentes de Información y Catálogos

Insumos que consume el pipeline. Todos viven bajo `input/`, que está en `.gitignore`: son
archivos que llegan de fuera y **no se versionan**.

## Fuentes principales

### RNPDNO — Registro Nacional de Personas Desaparecidas y No Localizadas

```
input/rnpdno/reporte_personas_completo_DDMMAAAA.parquet   ← el que baja el modo drive
input/rnpdno/reporte_personas_DDMMAAAA.xlsx               ← el Excel de tres hojas (modo local)
```

El reporte de búsqueda que levantan las comisiones. Es el universo de **personas**
(408,459 registros en el corte vigente). Lo procesa `1_Procesamiento_ETL_RNPDNO.ipynb`;
el notebook oficial escribe `output/Resultado_1_Procesamiento_ETL_RNPDNO.parquet` y el
pipeline lector usa `output/Resultado_1_Procesamiento_ETL_RNPDNO_autonomo.parquet`.

En modo `local` el archivo concreto se fija en `config.RNPDNO_LOCAL_FILE` — control
estricto, sin búsqueda por patrón, para que una corrida sea reproducible. En modo `drive`
el notebook baja el corte del día y lee el más reciente de `input/rnpdno/`.

El notebook acepta las dos presentaciones del RNPDNO y reconoce cuál es por la extensión
(`config.formato_rnpdno`):

| Formato | Cómo salen las tres hojas |
|---|---|
| Parquet (`.parquet`) | una tabla con las hojas apiladas; se reconstruyen con `estatus` + `conidentidad` |
| Excel (`.xlsx`) | se leen tal cual las hojas `ACTUALIZACION_PENDIENTE`, `LOCALIZADAS` y `DESAPARECIDAS` |

Los dos dejan la misma tabla para el resto del flujo (`src/lectura_rnpdno.py`): el Excel se
lee como texto, igual que el Parquet, y dos columnas se renombran a como vienen en el Parquet
(`curp_victima` → `curp_vic`, `expediente` → `Expedientes`; ver
`config.RNPDNO_EXCEL_A_PARQUET`). El mismo renombre se aplica al Parquet sin distinguir
mayúsculas, porque según el corte ha traído `expediente`, `Expediente` o `Expedientes`; si
no, la copia saldría como `expediente_rnpdno` y el notebook 1 se detendría al exportar
(`KeyError: ['expedientes_rnpdno'] not in index`). Una diferencia de contenido, no de lectura: el
`Expedientes` del Parquet puede juntar varias carpetas (`… @| …`) y viene lleno más seguido
que el `expediente` del Excel, que trae una sola.

### BANCI — Banco Nacional de Carpetas de Investigación

```
input/banci/
```

Las carpetas de investigación abiertas por las fiscalías. Es el universo **judicial**
(34,777 registros). Lo procesa `2_Procesamiento_ETL_BANCI.ipynb`; el pipeline lector usa
`output/Resultado_2_Procesamiento_ETL_BANCI_autonomo.parquet`.

### PUI — Plataforma Única de Identidad

Coincidencias con registros administrativos de otras instituciones (IMSS, SAT, RENAPO,
SEBIEN…) posteriores a la fecha de desaparición: son los **indicios de vida**. Son tres
archivos, no uno:

| Constante en `config.py` | Objeto en el script de R | Qué aporta |
|---|---|---|
| `PUI_COINCIDENCIAS_FILE` | `coincidencias_admin_con_inactivas` | un renglón por evento detectado en otra institución (CSV, 16 columnas exigidas) |
| `PUI_REGISTROS_FILE` | `registros` (confrontas manuales) | las confrontas que se revisaron a mano (Excel, 5 columnas) |
| `PUI_DEFUNCIONES_FILE` | `defunciones_df` | actas de defunción por institución (Excel, 2 columnas) |

Los tres los procesa `3_Procesamiento_ETL_PUI.ipynb`, que escribe
`output/Resultado_3_Procesamiento_ETL_PUI.parquet`. El pipeline lector apunta por defecto
`config.CONFRONTAS_FILE` a `output/Resultado_3_Procesamiento_ETL_PUI_autonomo.parquet`.
El cuaderno PUI necesita además el Parquet autónomo del notebook 1 como `comprimido`, del
que toma `clasificacion_des`, `fecha_hechos_modificada` y la **CURP imputada**
(`curp_vic_derivada_rnpdno`): es la única dependencia entre notebooks de ETL.

El CSV de coincidencias llega comprimido desde una carpeta de Google Drive, bajo el patrón
`reporte_coincidencias_validas_YYYY-MM-DD.zip`. En modo `drive` —el de por omisión— el propio
cuaderno lo baja y lo descomprime en `input/pui/`; en modo `local` se lee el archivo que
declare `config.PUI_LOCAL_FILE`, sin tocar Drive. Los dos modos son excluyentes y se eligen
con `config.MODO_INSUMOS`; el detalle está en [9_credenciales_google_drive.md](9_credenciales_google_drive.md).
La fecha del nombre es también la que etiqueta la corrida, salvo que `config.PUI_FECHA_CORTE`
la fije a mano.

> ⚠️ **No confundir** `registros_con_pui_DDMMYYYY.xlsx` (insumo, 5 columnas) con
> `registros_con_pui_activos_*.xlsx`, que son salidas antiguas del flujo en R.

El recorrido completo —qué hace el cuaderno con cada archivo y cómo termina siendo la
bandera `cind`— está en [8. Indicios de vida](8_indicios_de_vida.md).

### Revisiones del SESNSP *(opcionales)*

```
input/input_reporte_diario/matches_verif_fecha_hechos_SESNSP.xlsx
input/input_reporte_diario/revision_manual_score_SESNSP.xlsx
```

Pares BANCI–RNPDNO que una persona revisó y dictaminó. Alimentan el motor **manual** y los
descuentos del **refinado** (ver [3. Metodología de Matching](3_metodologia_de_matching.md)).
Si no existen, el pipeline no falla: el descuento se omite y el motor manual no aporta.

## Todos los insumos se declaran en `config.py`

**No hay autodetección.** Ningún notebook busca "el archivo más reciente" ni resuelve rutas
por patrón: cada insumo es una constante con el archivo exacto, igual que
`RNPDNO_LOCAL_FILE` y `BANCI_FILE`. Copiar un archivo nuevo a `input/` no cambia lo que
lee el pipeline mientras no se edite `config.py`.

Cada insumo tabular lleva además su **mapeo de columnas exigidas**, con la misma estructura
que `RNPDNO_COLUMN_MAPPING` y `BANCI_COLUMN_MAPPING` — `'nombre_interno': ['alias', ...]`:

```python
PUI_REGISTROS_COLUMN_MAPPING = {
    'fub':                            ['fub'],
    'curp_victima':                   ['curp_victima', 'curp'],
    'indicadora_indicio_de_vida':     ['indicadora_indicio_de_vida'],
    'institucion_indicadora_de_vida': ['institucion_indicadora_de_vida'],
    'numero_instituciones':           ['numero_instituciones'],
}
```

`src/validacion.py` es lo que lo hace cumplir. Si falta **el archivo, la hoja o una
columna**, el proceso se detiene con un error que dice qué falta y qué hay en su lugar:

```
❌ A defunciones por institución le faltan 1 columna(s) exigida(s).
   Archivo: input/pui/tabla_defunciones_por_institucion_05052026.xlsx
     - tipo_defuncion: se buscó ['tipo_defuncion', 'tipo_def']
   El archivo trae estas columnas (2):
     ['fub', 'tipo_defuncion_institucion']
   Si el archivo cambió de nombres, actualiza el mapeo en config.py.
```

El mapeo fija el **mínimo exigido**, no el máximo: una columna extra en el archivo no
estorba. Y el DataFrame vuelve con las columnas renombradas al nombre interno, de modo que
el cuaderno no tiene que saber qué alias traía la entrega de ese mes.

### Al cambiar de BANCI

Las columnas no bastan: un archivo equivocado —más viejo, recortado, de otra ventana de
fechas— trae las mismas columnas y cambiaría las cifras sin que nadie lo notara. Por eso el
notebook 2 revisa además el **contenido** de la entrega y lo compara con la última que
procesó ([`src/validacion_banci.py`](../src/validacion_banci.py)).

La **fecha de corte** de una entrega es su fecha de inicio (`FHA_DE_INI`) más reciente, que
siempre cae en el último día del mes que cubre. Con ella se distingue una entrega de otra
fecha de una versión corregida del mismo corte. Una fecha de inicio posterior al día en que
se procesa es un error de captura y no cuenta: la entrega de agosto de 2026 trajo un 5 de
octubre, que habría hecho parecer más vieja a la de septiembre.

| Revisión | Detiene | Avisa |
|---|---|---|
| Registros | el archivo viene vacío; **de un corte a otro la base no crece** | crece más de 50 %; mismo corte con distinto número de registros (¿versión corregida?) |
| Fecha de corte | es **anterior** a la de la última entrega procesada; no se puede leer ninguna | hay más de un mes entre cortes (¿falta una entrega?); cambia la fecha de inicio más antigua (otra ventana) |
| Entidades | alguna **desaparece** (tenía 10 o más registros); un valor sin clave INEGI | alguna baja más de 5 % y al menos 10 registros |
| Estatus | un valor distinto de `LOCALIZADA` / `NO LOCALIZADA`, o vacío: se contaría en silencio como desaparecido | — |
| `LLAVE` | más de 5 % vacía | alguna vacía |
| Otros | — | categorías de sexo nuevas; fechas de inicio posteriores a hoy; fechas de hechos posteriores al corte (el notebook les resta años) |

La entrega anterior no se vuelve a leer: el notebook guarda un resumen de cada entrega
(registros, corte, conteo por entidad) en los metadatos de `Resultado_2_…parquet`, y la
siguiente corrida compara contra él. **Si se borra `output/`, se pierde esa referencia** y la
entrega siguiente se procesa sin compararse (el notebook lo dice: "sin entrega anterior"). `LLAVE` no se compara entre entregas porque el
Secretariado la regenera cada vez, y las entidades se comparan por clave INEGI porque su
nombre cambia de una entrega a otra ("MÉXICO", "ESTADO DE MÉXICO", "MEXICO").

Los umbrales se calibraron con las siete entregas de enero a julio de 2026: el cambio real
de junio a julio pasa sin observaciones; la entrega de febrero, que llegó con el 89 % de
`LLAVE` vacía, se habría detenido; y la de mayo, que cambió la ventana de fechas y llegó
sin la de abril antes, pasa con cuatro avisos.

Si la entrega es correcta y aun así no cumple (por ejemplo, el Secretariado depuró
registros), `config.VALIDACION_BANCI_ESTRICTA = False` la deja pasar con los errores
convertidos en avisos. Hay que volver a ponerlo en `True` después.

## Catálogos complementarios

| Ruta | Uso |
|---|---|
| `input/catalogos_inegi/catalogo_municipios_inegi.csv` | traduce `CVE_ENT` + `CVE_MUN` → `NOM_MUN`. Sin él, el motor refinado no puede usar el municipio: compara **nombres**, no claves |
| `input/cruces_curp/` | cruces determinísticos por CURP; alimenta la **imputación** de CURP del ETL (`src.cleaning.imputar_curp`) |
| `input/datos_marzo/` | corte congelado del 25/03/2026, un Excel por marcador. **No pasa por el pipeline**: se cuenta aparte y se resta (`config.CORTE_25MAR26_FILES`) |
| `input/datos_julio/` | corte congelado del 01/07/2026, mismas tres rebanadas y mismo uso que el de marzo; trae el identificador como `fub_rnpdno` (`config.CORTE_01JUL26_FILES`) |
| `input/plantillas/` | plantillas PPTX con los marcadores `{{...}}`; se declaran en `PLANTILLA_REPORTE_DIARIO` y `PLANTILLA_REPORTE_ESTATAL` |

## Insumos externos que no pasan por el pipeline

Dos archivos alimentan láminas del reporte diario sin entrar al matching ni a las banderas:
su población no sale del RNPDNO ni de BANCI, y lo único que se le pide al universo es el
**estatus vigente de cada `fub`**.

| Ruta y constante | Alimenta | Detalle |
|---|---|---|
| `input/domicilios_y_numeros_contacto/Directorio_nacional_18112026_insumo.xlsx` — `DIRECTORIO_INDICIOS_FILE` | lámina 12: indicios ya formalizados como localización (`*_loc_fmz`) | archivo con fecha 18/11/2026; de sus 37 columnas sólo se usan `FUB` y `Estado de Desaparición`. Se mantienen los marcadores `24jun26` de la plantilla. Ver [8.6](8_indicios_de_vida.md) |
| `input/mj/MJ y RIPS (1062).xlsx` — `MJ_RIPS_FILE` | última lámina: detenciones penitenciarias (`reg_mr_*`) | dos hojas, `MJ UNICOS` y `RIPS UNICOS`, que se concatenan sin deduplicar |

## Salidas del ETL

Los ETL oficiales mantienen sus Parquet de salida; las corridas autónomas generan además
Parquet separados. La CAPA A lee por defecto las versiones `_autonomo`:

| Constante | Archivo |
|---|---|
| `ETL_RNPDNO_OUTPUT_FILE` | `output/Resultado_1_Procesamiento_ETL_RNPDNO.parquet` (destino del ETL oficial) |
| `ETL_BANCI_OUTPUT_FILE` | `output/Resultado_2_Procesamiento_ETL_BANCI.parquet` (destino del ETL oficial) |
| `ETL_PUI_OUTPUT_FILE` | `output/Resultado_3_Procesamiento_ETL_PUI.parquet` (destino del ETL oficial) |
| `ETL_RNPDNO_INPUT_FILE` | `output/Resultado_1_Procesamiento_ETL_RNPDNO_autonomo.parquet` (lectura aguas abajo) |
| `ETL_BANCI_INPUT_FILE` | `output/Resultado_2_Procesamiento_ETL_BANCI_autonomo.parquet` (lectura aguas abajo) |
| `ETL_PUI_INPUT_FILE` / `CONFRONTAS_FILE` | `output/Resultado_3_Procesamiento_ETL_PUI_autonomo.parquet` (lectura aguas abajo) |

Las presentaciones también: `PPT_DIARIO_FILE` y `PPT_ESTATAL_DIR`.
