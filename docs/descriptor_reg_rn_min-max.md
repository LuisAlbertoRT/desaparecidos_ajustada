# Descriptor de variables: `reg_rn_min-max.parquet`

## 1. Alcance del archivo

Este descriptor corresponde al archivo `output/Resultados_4_Generacion_Indicadores/reg_rn_min-max.parquet` inspeccionado el **21 de octubre de 2026**.

| Propiedad | Valor observado |
|---|---:|
| Filas | 412,526 |
| Columnas | 32 |
| FUB nulo | 0 |
| FUB único | 412,526 |
| FUB duplicado | 0 filas |
| Periodo del nombre | `min-max`: sin filtro temporal |
| Estatus | Todos: desaparecidos, pendientes y localizados |
| Fecha de consulta máxima del RNPDNO | 19 de octubre de 2026, según el corte de entrada revisado |

Es una base del universo RNPDNO enriquecida con variables de matching y clasificación. No es un archivo de personas sólo desaparecidas ni una base que aplique por sí misma el filtro desde octubre de 2024.

### Procedencia y reglas generales

- La base se genera en la sección de exportación del Notebook 4, a partir del universo RNPDNO; la lectura, el matching y la derivación de columnas ocurren en las capas del pipeline.
- Las columnas terminadas en `_rnpdno` conservan valores reportados por RNPDNO; `_derivada_rnpdno` identifica una transformación basada en ese origen; `_derivada_rnpdno_banci` señala una variable construida o corregida con información del cruce RNPDNO–BANCI; `_derivada_pui` identifica información de PUI.
- Las filas se mantienen por FUB; el FUB es la llave de persona de esta exportación y no presenta duplicados en el archivo inspeccionado.
- Los conteos y faltantes de las secciones siguientes describen **esta copia concreta** del Parquet. Cambian si se regenera el universo con otro corte, perfil o configuración.

## Linaje de variables: fuente original y columnas utilizadas

La columna “origen/columnas de entrada” indica de dónde viene el valor antes de entrar en esta base. Cuando dice **ETL RNPDNO**, se refiere al Parquet de salida del notebook 1; éste lee el corte RNPDNO configurado y normaliza los encabezados según `config.RNPDNO_COLUMN_MAPPING`. Por ello puede haber alias de encabezado entre cortes. Las columnas listadas son los nombres canónicos usados por el pipeline; los nombres originales aceptados pueden consultarse en `config.py`.

| Variable en este Parquet | Fuente original | Origen/columnas de entrada y construcción |
|---|---|---|
| `fub_rnpdno` | RNPDNO | `fub` (o alias `folio_fub`, `folio_rnpdno`, `folio`), conservado como identificador de persona. |
| `expedientes_rnpdno` | RNPDNO | `expediente`/`Expedientes` (incluye alias singular/plural); valor del expediente conservado como texto. |
| `sexo_rnpdno` | RNPDNO | `sexo`; valor reportado conservado y categorizado para reducir memoria. |
| `fechanacimiento_derivada_rnpdno` | RNPDNO, ETL | `fechanacimiento` (alias `fecha_nacimiento`, `fha_nac`); convertida a fecha. |
| `idmunicipio_derivada_rnpdno` | RNPDNO, ETL | `idmunicipio`; conversión del código a tipo numérico. La clave sólo identifica municipio al combinarla con la entidad. |
| `clasificacion_des_derivada_rnpdno` | RNPDNO, ETL | `clasificacion_des`; clasificación normalizada/producida por el ETL RNPDNO y conservada en el universo. |
| `dependencia_origen_derivada_rnpdno_banci` | RNPDNO + resultado BANCI | Parte de `dependencia_origen`; para los FUB presentes en el conjunto de matches BANCI, la regla `actualizar_rn_con_banci` la reemplaza por `FISCALIA GENERAL (BANCI MATCH)`. La versión original no se conserva en este archivo si se aplicó la corrección. |
| `fecha_hechos_modificada_derivada_rnpdno` | RNPDNO, ETL | `fechahechos` más las fechas de respaldo `fechapercato` y `fechacaptura`; el ETL crea la fecha modificada y rellena los huecos. Es la fecha que se usa para periodos. |
| `fechahechos_derivada_rnpdno` | RNPDNO, ETL | `fechahechos`; conversión a fecha sin imputar huecos. |
| `fechacaptura_derivada_rnpdno` | RNPDNO, ETL | `fechacaptura`; conversión a fecha. |
| `fechalocaliza_derivada_rnpdno` | RNPDNO, ETL | `fechalocaliza`; conversión a fecha. |
| `curp_vic_valida_derivada_rnpdno` | RNPDNO + archivos auxiliares RENAPO | Se valida `curp_vic_derivada_rnpdno`: CURP RNPDNO y CURP imputadas desde las tablas RENAPO, cruzadas por `fub`. El Parquet conserva la bandera, no la CURP. |
| `nombre_vic_rnpdno` | RNPDNO | `nombre_vic` (alias `nombre`); texto reportado, sin volver a calcularlo en esta capa. |
| `primerapellido_vic_rnpdno` | RNPDNO | `primerapellido_vic` (alias `primer_apellido`); texto reportado. |
| `segundoapellido_vic_rnpdno` | RNPDNO | `segundoapellido_vic` (alias `segundo_apellido`); texto reportado. |
| `idestado_derivada_rnpdno` | RNPDNO, ETL | `idestado` (aliases `cve_ent`, `estado_id`, `entidad_id`); clave de entidad convertida a número. |
| `in_banci_derivada_rnpdno_banci` | RNPDNO + BANCI | `fub_rnpdno` contrastado con el conjunto de FUB aceptados por la cascada de motores BANCI. `TRUE` si el FUB fue reclamado. |
| `tipo_match_derivada_rnpdno_banci` | Resultado de matching RNPDNO–BANCI | Mapa de FUB a métodos ganadores de la cascada (estándar, manual, refinado); `sin_match` cuando no hay FUB reclamado. No se reconstruye a partir de las columnas de identificación de esta salida. |
| `nombre_entidad_derivada_rnpdno` | RNPDNO + catálogo de entidades | `idestado_derivada_rnpdno` traducido mediante el catálogo `config.ENTIDADES`. |
| `estatus_loc_derivada_rnpdno` | RNPDNO, ETL | `clasificacion_des_derivada_rnpdno`: `Localizados` → `loc`; `Desaparecidos` y `Pendientes` → `des`. |
| `is_cvid_derivada_rnpdno` | RNPDNO | `estatus_rnpdno`; `TRUE` si el texto del estatus contiene “con vida”. |
| `is_svid_derivada_rnpdno` | RNPDNO | `estatus_rnpdno`; `TRUE` si contiene “sin vida”. No es el complemento de `is_cvid`. |
| `is_cdel_derivada_rnpdno` | RNPDNO | `delitolocalizacion`; `TRUE` si contiene texto no vacío tras quitar espacios. |
| `is_dfor_derivada_rnpdno_banci` | RNPDNO y, para matches, BANCI | Inicialmente `delitolocalizacion`; para FUB matcheados se propaga `delito_hom_banci`. `TRUE` si la clasificación contiene “forzada”. |
| `is_cpar_derivada_rnpdno_banci` | RNPDNO y, para matches, BANCI | Inicialmente `delitolocalizacion`; para FUB matcheados se propaga `delito_hom_banci`. `TRUE` si la clasificación contiene “particular”. |
| `is_cind_derivada_pui` | PUI (`Resultado_3_Procesamiento_ETL_PUI.parquet`) + RNPDNO | Se integra la columna PUI `indicadora_indicio_de_vida_derivada_pui` por `fub_rnpdno`; si no hay FUB en PUI se asigna “sin registro administrativo”. `TRUE` salvo que ese sea el valor. |
| `is_sisf_derivada_rnpdno_pui` | RNPDNO + PUI | AND lógico de `!curp_vic_valida_derivada_rnpdno` y `!is_cind_derivada_pui`: sin CURP válida y sin registro administrativo PUI. |
| `is_cfvac_derivada_rnpdno` | RNPDNO | `expedientes_rnpdno`; `TRUE` si el expediente está nulo o vacío después de quitar espacios. |
| `is_cfval_derivada_rnpdno` | RNPDNO + configuración de regex + revisión manual | `expedientes_rnpdno` y `idestado_derivada_rnpdno` se evalúan con la modalidad de clasificación de carpeta; se OR-ean con los FUB aprobados en la revisión manual de `input/carpetas_manuales`. Depende de la modalidad/perfil de la corrida. |
| `is_fis_derivada_rnpdno_banci` | RNPDNO, con dependencia corregida por BANCI cuando aplica | `dependencia_origen_derivada_rnpdno_banci`; patrones de texto de fiscalía/procuraduría. |
| `is_com_derivada_rnpdno_banci` | RNPDNO, con dependencia corregida por BANCI cuando aplica | `dependencia_origen_derivada_rnpdno_banci`; patrones de texto de comisión. |
| `is_por_derivada_rnpdno_banci` | RNPDNO, con dependencia corregida por BANCI cuando aplica | Residuo booleano: `!is_fis_derivada_rnpdno_banci & !is_com_derivada_rnpdno_banci`. |

Las reglas de las columnas fecha/nombre/ubicación convertidas también dependen del notebook 1 y sus mapeos ETL. Las banderas y columnas de estatus, entidad y matching se calculan en `src/pipeline/derivadas.py`, `src/pipeline/reglas.py`, `src/pipeline/carga.py` y `src/pipeline/motores.py`. Si cambia el perfil de matching, la modalidad de validación de carpetas o los archivos fuente, el valor derivado puede cambiar aunque la definición del campo se mantenga.

## 2. Identidad, expediente y datos reportados

| Variable | Tipo observado | Faltantes | Descripción e interpretación |
|---|---|---:|---|
| `fub_rnpdno` | Texto | 0 | Folio Único de Búsqueda. Identificador de persona y llave para los cruces. En esta copia: 412,526 valores distintos. Tratar como identificador, no como número. |
| `expedientes_rnpdno` | Texto | 174,549 | Expediente o folio informado por RNPDNO. Es el campo evaluado para las banderas de folio válido/vacío. Puede tener más de un expediente o variaciones de captura; no equivale a un cruce confirmado con BANCI. |
| `sexo_rnpdno` | Categórico | 0 | Sexo reportado. Valores observados: HOMBRE 248,175; MUJER 163,662; INDETERMINADO 689. |
| `nombre_vic_rnpdno` | Texto | 15 | Nombre reportado de la víctima. Dato personal; no publicar valores individuales. |
| `primerapellido_vic_rnpdno` | Texto | 158 | Primer apellido reportado. Dato personal; no publicar valores individuales. |
| `segundoapellido_vic_rnpdno` | Texto | 5,218 | Segundo apellido reportado. Dato personal; no publicar valores individuales. |
| `fechanacimiento_derivada_rnpdno` | Fecha/hora | 92,336 | Fecha de nacimiento convertida por el ETL. El rango observado va de 1882-08-13 a 2204-09-01; las fechas fuera de rango habitual requieren revisión y no deben asumirse correctas. |
| `idmunicipio_derivada_rnpdno` | Numérico decimal | 14,760 | Clave de municipio RNPDNO convertida a valor numérico. Se observa como decimal por la representación de faltantes; no es una clave municipal nacional por sí sola: se interpreta junto con la entidad. |
| `idestado_derivada_rnpdno` | Entero | 0 | Clave INEGI de entidad usada como dimensión geográfica. Tiene 33 claves distintas, incluida la categoría de nacimiento en el extranjero. |

## 3. Clasificación, estatus y fechas

| Variable | Tipo observado | Faltantes | Descripción e interpretación |
|---|---|---:|---|
| `clasificacion_des_derivada_rnpdno` | Categórico | 0 | Clasificación normalizada del universo RNPDNO. Valores observados: Localizados 282,056; Desaparecidos 84,013; Pendientes 46,457. |
| `estatus_loc_derivada_rnpdno` | Categórico (`loc`/`des`) | 0 | Dimensión compacta para filtrar. `loc` corresponde a Localizados (282,056); `des` incluye Desaparecidos y Pendientes (130,470). No confundir `des` con la categoría literal Desaparecidos: incluye Pendientes. |
| `fecha_hechos_modificada_derivada_rnpdno` | Fecha/hora | 0 | Fecha de hechos **que usa el filtro de periodo**. Se completan huecos usando fechas de respaldo conforme al ETL. Rango observado: 1952-12-31 a 2026-10-15. Para reproducir los periodos del pipeline, usar esta columna, no la fecha cruda. |
| `fechahechos_derivada_rnpdno` | Fecha/hora | 32,680 | Fecha de hechos convertida, sin rellenar los faltantes. Rango observado: 1952-12-31 a 2026-10-15. Se usa para analizar faltantes de la fecha original; no sustituirla por la fecha modificada al recrear periodos. |
| `fechacaptura_derivada_rnpdno` | Fecha/hora | 0 | Fecha de captura convertida. Rango observado: 2006-11-29 a 2026-10-16. Fecha administrativa, distinta de la fecha del hecho y de la fecha de consulta. |
| `fechalocaliza_derivada_rnpdno` | Fecha/hora | 218,668 | Fecha de localización convertida. Rango observado: 1900-01-01 a 2205-03-01; hay valores atípicos que deben validarse antes de usarse como fechas válidas. Su faltante es esperable principalmente en personas no localizadas. |

> El intervalo `01oct24-max` significa fecha modificada **mayor o igual a 2024-10-01**. El pipeline conserva las filas cuya fecha de periodo es nula en periodos acotados; en este archivo esa fecha modificada no tiene nulos.

## 4. Dependencia de origen y entidad

| Variable | Tipo observado | Faltantes | Descripción e interpretación |
|---|---|---:|---|
| `dependencia_origen_derivada_rnpdno_banci` | Categórico/texto | 0 | Dependencia usada tras incorporar, cuando aplica, la corrección del cruce BANCI. Tiene 75 categorías en esta copia. Es la fuente de las banderas `is_fis_*`, `is_com_*` e `is_por_*`; no es necesariamente idéntica al texto original de RNPDNO cuando hubo corrección. |
| `nombre_entidad_derivada_rnpdno` | Categórico | 0 | Nombre de entidad derivado de `idestado_derivada_rnpdno`. Valores observados: las 32 entidades y Nacido en el Extranjero; 33 categorías. |

La columna original `dependencia_origen_rnpdno` no está en las 32 columnas de esta copia. El ensamblado del universo conserva la dependencia corregida cuando está disponible y descarta la original en ese caso.

## 5. Cruce con BANCI

| Variable | Tipo observado | Faltantes | Descripción e interpretación |
|---|---|---:|---|
| `in_banci_derivada_rnpdno_banci` | Booleano | 0 | `TRUE` si el FUB fue reclamado/coincidió en la cascada de matching con BANCI. Conteo observado: 7,804 `TRUE`; 404,722 `FALSE`. No expresa el número de carpetas: una persona puede tener varias carpetas y la base mantiene registros de personas. |
| `tipo_match_derivada_rnpdno_banci` | Categórico | 0 | Métodos que respaldan el match, o `sin_match`. Valores observados: `sin_match` 404,722; `estandar, refinado` 5,803; `estandar` 909; `refinado` 553; `manual` 501; `manual, estandar` 38. Las combinaciones indican más de un método para el mismo FUB, no filas adicionales. |

## 6. Variables booleanas de clasificación

Para las columnas `is_*` e `in_*`, `TRUE` indica que se cumple el criterio, `FALSE` que no se cumple. El pipeline rellena estas banderas sin faltantes al ensamblar la capa derivada. Las banderas categorizan criterios analíticos; no deben interpretarse automáticamente como verificación independiente del dato de origen.

| Variable | TRUE | FALSE | Descripción |
|---|---:|---:|---|
| `curp_vic_valida_derivada_rnpdno` | 169,955 | 242,571 | La CURP de trabajo pasó las reglas estructurales del ETL. Puede incluir una CURP imputada; la columna de CURP no se exporta en este universo. No certifica por sí sola validación oficial ante RENAPO. |
| `is_cvid_derivada_rnpdno` | 257,086 | 155,440 | El estatus de origen contiene “con vida”. |
| `is_svid_derivada_rnpdno` | 24,970 | 387,556 | El estatus de origen contiene “sin vida”. No es complemento de `is_cvid`: los desaparecidos pueden tener ambas banderas en FALSE. |
| `is_cdel_derivada_rnpdno` | 13,783 | 398,743 | Hay texto no vacío en el campo de delito/localización del RNPDNO. |
| `is_dfor_derivada_rnpdno_banci` | 178 | 412,348 | Clasificación de desaparición forzada usada en el universo. Para los FUB con match, el tipo puede provenir de BANCI; los no matcheados conservan el RNPDNO. |
| `is_cpar_derivada_rnpdno_banci` | 9,901 | 402,625 | Clasificación de desaparición cometida por particulares. Fuente prioritaria BANCI en registros matcheados, RNPDNO en los no matcheados. |
| `is_cind_derivada_pui` | 38,374 | 374,152 | Hay registro administrativo/actividad identificada en PUI según la bandera calculada. No significa necesariamente que la persona esté con vida: puede incluir, por ejemplo, un acta de defunción. |
| `is_sisf_derivada_rnpdno_pui` | 236,340 | 176,186 | “Sin información suficiente”: no hay CURP válida y no hay registro administrativo PUI. Su complemento lógico (`cisf`) se calcula al filtrar; no es otra columna guardada. |
| `is_cfvac_derivada_rnpdno` | 174,549 | 237,977 | El campo de expediente/folio está vacío tras quitar espacios. |
| `is_cfval_derivada_rnpdno` | 120,988 | 291,538 | El expediente pasó la regla de validez de carpeta configurada o fue aprobado por revisión manual. En la configuración inspeccionada: modalidad de clasificación 4 y revisión manual activa. No significa que exista match BANCI. |
| `is_fis_derivada_rnpdno_banci` | 295,054 | 117,472 | La dependencia considerada corresponde a fiscalía/procuraduría, según patrones de texto. |
| `is_com_derivada_rnpdno_banci` | 103,414 | 309,112 | La dependencia considerada corresponde a comisión de búsqueda, según patrones de texto. |
| `is_por_derivada_rnpdno_banci` | 14,058 | 398,468 | Categoría residual: ni fiscalía ni comisión. En esta copia, fiscalía + comisión + portal suman las 412,526 filas. |

### Columnas de banderas que no se almacenan

El indicador de corte puede usar tokens como `sdel`, `sind`, `cisf`, `sfval` o `sfvac`, aunque no todos aparezcan como columna. El pipeline omite las banderas que son la negación exacta de otra y las calcula al filtrar:

- `sdel` = complemento de `is_cdel_derivada_rnpdno`.
- `sind` = complemento de `is_cind_derivada_pui`.
- `cisf` = complemento de `is_sisf_derivada_rnpdno_pui`.
- `sfval` = complemento de `is_cfval_derivada_rnpdno`.
- `sfvac` = complemento de `is_cfvac_derivada_rnpdno`.

`cvid` y `svid` no son complementos: hay registros que no tienen ninguna de esas dos condiciones.

## 7. Calidad, privacidad y uso

1. El archivo contiene nombres, apellidos, FUB, expedientes y fechas personales: resguardarlo como información sensible, restringir acceso y no compartir filas de ejemplo sin autorización.
2. No usar `fub_rnpdno` para cálculos aritméticos; conservarlo como texto.
3. Separar los conceptos **persona**, **expediente/carpeta** y **match BANCI**. `is_cfval` clasifica el folio; `in_banci` indica match; no son equivalentes.
4. Para filtros temporales usar `fecha_hechos_modificada_derivada_rnpdno`. Para medir fechas crudas faltantes usar `fechahechos_derivada_rnpdno`.
5. Los valores de fecha extrema de nacimiento/localización observados (años 2204/2205 y 1900) requieren regla de calidad antes de emplearse para edades o tendencias.
6. La fecha de última consulta observada en el corte de origen fue 2026-10-19; la fecha máxima de hechos modificados fue 2026-10-15. La fecha de consulta no está incluida en este Parquet.
7. Las cantidades son un perfil descriptivo del archivo inspeccionado, no cifras permanentes del sistema.

## 8. Comprobación en R

Este bloque permite verificar el esquema, los conteos y los faltantes del archivo local sin imprimir identificadores ni datos personales:

```r
library(arrow)
library(dplyr)

ruta <- "output/Resultados_4_Generacion_Indicadores/reg_rn_min-max.parquet"
rn <- read_parquet(ruta, as_data_frame = TRUE)

# Esquema y volumen
tibble(
  variable = names(rn),
  clase = vapply(rn, function(x) paste(class(x), collapse = "/"), character(1)),
  faltantes = vapply(rn, function(x) sum(is.na(x)), integer(1)),
  distintos = vapply(rn, function(x) dplyr::n_distinct(x, na.rm = TRUE), integer(1))
)

# Resumen de clasificación, estatus y banderas principales
rn %>% summarise(
  filas = n(),
  fub_unicos = n_distinct(fub_rnpdno),
  localizados = sum(estatus_loc_derivada_rnpdno == "loc"),
  desaparecidos_y_pendientes = sum(estatus_loc_derivada_rnpdno == "des"),
  con_match_banci = sum(in_banci_derivada_rnpdno_banci),
  curp_valida = sum(curp_vic_valida_derivada_rnpdno),
  con_folio_valido = sum(is_cfval_derivada_rnpdno),
  sin_info_suficiente = sum(is_sisf_derivada_rnpdno_pui)
)

# Distribuciones sin exponer identificadores
rn %>% count(clasificacion_des_derivada_rnpdno, sort = TRUE)
rn %>% count(sexo_rnpdno, sort = TRUE)
```
