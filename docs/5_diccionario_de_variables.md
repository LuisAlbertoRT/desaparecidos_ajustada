# 5. Diccionario de Variables

Columnas de los dos DataFrames que produce `Universo.construir(cfg)`: `u.rn` (RNPDNO,
409,966 filas) y `u.ba` (BANCI, 34,777). Son las que consumen los `Slice` y las que se
materializan en `output/Resultados_4_Generacion_Indicadores/`.

Para la nomenclatura de los **indicadores** (`reg_rn_01oct24-max_des`…) ver
[`catalogo_abreviaturas.md`](../catalogo_abreviaturas.md).

> Este diccionario cubre las columnas del **universo en memoria** (`u.rn` y `u.ba`) y las
> del caché de matching. Las columnas que se añaden a los archivos exportados —`id_cruce`,
> `metodo_match`, `estatus_match`…— son otras y viven en
> [7. Llaves de cruce §7.3](7_llaves_de_cruce.md).

## Convención de sufijos

Toda columna, en todo archivo del flujo, dice de dónde viene **sólo con su sufijo**:

| Sufijo | Significado |
|---|---|
| `_rnpdno` · `_banci` · `_pui` | el valor tal como vino de esa fuente |
| `_derivada_rnpdno` · `_derivada_banci` · `_derivada_pui` | se construyó a partir de esa fuente (limpieza, conversión, imputación, normalización, cálculo) |
| `_derivada_<fuentes>` | se construyó cruzando varias fuentes, listadas siempre en el orden rnpdno → banci → pui: `_derivada_rnpdno_banci` (el cruce de los motores), `_derivada_rnpdno_pui`, `_derivada_rnpdno_banci_pui` |

No hay columnas sin sufijo ni alias: un mismo dato vive en **una** columna con **un**
nombre de principio a fin. Los motores de match sí trabajan con los nombres del script
de R (`fub`, `fechahechos`, `llave`…), pero sólo dentro de `motores._correr_motor`, que
les entrega una copia renombrada; lo que devuelven son sus columnas de resultado y
ningún nombre interno llega a un archivo.

Los Parquet del ETL exportan un contrato fijo de columnas, y `carga.py` se niega a cargar
uno que no lo cumpla:

| Archivo | Contrato | Columnas |
|---|---|---|
| `Resultado_1_Procesamiento_ETL_RNPDNO.parquet` | `config.RNPDNO_OUTPUT_COLUMNS` | 33: las 19 del RNPDNO tal como vinieron (fechas y claves como texto) y 14 derivadas |
| `Resultado_2_Procesamiento_ETL_BANCI.parquet` | `config.BANCI_OUTPUT_COLUMNS` | 32: las 19 de BANCI tal como vinieron del Excel y 13 derivadas |
| `Resultado_3_Procesamiento_ETL_PUI.parquet` | `config.PUI_NOMBRES_EXPORTADOS` | 10, todas derivadas. El notebook 3 trabaja con los nombres del script de R y los renombra sólo al exportar |

> ⚠️ El recuadro "Datos faltantes" de las plantillas se cuenta **siempre sobre la columna
> sin rellenar**. Las derivadas rellenan (`fecha_hechos_modificada_derivada_rnpdno`
> completa los huecos con percato/captura) o concatenan con `fillna("")`, y taparían justo
> el hueco que se quiere medir. Por eso `sfdes` se cuenta sobre
> `fechahechos_derivada_rnpdno`, no sobre `fecha_hechos_modificada_derivada_rnpdno`.

## RNPDNO (`u.rn`)

### Identidad

| Columna | Tipo | Descripción |
|---|---|---|
| `fub_rnpdno` | str | Folio Único de Búsqueda. **La llave de persona** en todo el pipeline |
| `expedientes_rnpdno` | str | expediente (carpeta de investigación o folio) tal como viene, con sus espacios. Es el campo que juzgan `cfval` / `cfvac`; viaja para que lo lleve toda base exportada |
| `nombre_vic_rnpdno`, `primerapellido_vic_rnpdno`, `segundoapellido_vic_rnpdno` | str | los tres campos del nombre tal como vienen; son los que cuenta `snomb` |
| `sexo_rnpdno` | cat | sexo de la persona |
| `fechanacimiento_derivada_rnpdno` | date | fecha de nacimiento, convertida a fecha |
| `curp_vic_valida_derivada_rnpdno` | bool | la CURP **imputada** pasa la validación estructural; el rebanado la lee como `ccurp` |

> La CURP imputada (`curp_vic_derivada_rnpdno`) y la cruda (`curp_vic_rnpdno`) no viajan a
> `u.rn`: se quedan en el Parquet del notebook 1, donde el notebook 3 usa la imputada. Por
> eso `curp_vic_valida_derivada_rnpdno` puede ser `True` con `curp_vic_rnpdno` vacía: son
> los registros que sólo tienen CURP por imputación.

### Estatus y clasificación

| Columna | Valores | Descripción |
|---|---|---|
| `clasificacion_des_derivada_rnpdno` | `Desaparecidos` · `Localizados` · `Pendientes` | clasificación del RNPDNO |
| `estatus_loc_derivada_rnpdno` | `des` (130,909) · `loc` (279,057) | colapsa la anterior a la dimensión de rebanada |
| `dependencia_origen_derivada_rnpdno_banci` | str | dependencia que reportó; `actualizar_rn_con_banci` la sobrescribe con `FISCALIA GENERAL (BANCI MATCH)` si BANCI reclamó el FUB. Sin esa regla entra `dependencia_origen_rnpdno`, tal como vino. Es la base de `fis` / `com` / `por` |

### Fechas

| Columna | Descripción |
|---|---|
| `fecha_hechos_modificada_derivada_rnpdno` | **la que rebana el período**: fecha de hechos con huecos rellenados por percato/captura; llega sin nulos |
| `fechahechos_derivada_rnpdno` | fecha de hechos **sin rellenar**, ya convertida a fecha: la única que conserva los huecos. Es la que cuenta `sfdes` |
| `fechacaptura_derivada_rnpdno`, `fechalocaliza_derivada_rnpdno` | captura y localización; las exporta el notebook 4. `fechalocaliza` sólo la traen los localizados |

### Geografía

| Columna | Descripción |
|---|---|
| `idestado_derivada_rnpdno` | clave INEGI de entidad. **Dimensión de rebanada**, no filtro previo |
| `nombre_entidad_derivada_rnpdno` | nombre de la entidad, derivado de la clave |
| `estado_final_nuevo`, `idestado_final_nuevo` | nombre y clave de la entidad mencionada de manera inequívoca en `dependencia_origen_rnpdno`, incluso si BANCI modifica la dependencia derivada. Se reconocen nombres y alias completos en cualquier posición; si no hay una entidad reconocible o hay varias distintas, se usa `idestado_derivada_rnpdno` como respaldo. Si tampoco es válido, quedan nulos |
| `idmunicipio_derivada_rnpdno` | clave municipal numérica. El texto original (`"75.0"`) queda en `idmunicipio_rnpdno` del Parquet del ETL |

Cuando `USAR_ESTADO_EXTRAIDO_EN_PRESENTACIONES` está activado, las rebanadas por
entidad utilizan `idestado_final_nuevo`. Los municipios y CVEGEO del notebook 4
siguen correspondiendo a `idestado_derivada_rnpdno`, no a la entidad de la
dependencia.

### Resultado del matching

| Columna | Descripción |
|---|---|
| `in_banci_derivada_rnpdno_banci` | bool: el FUB fue reclamado por algún motor |
| `tipo_match_derivada_rnpdno_banci` | métodos que lo sostienen, en orden de cascada (`"manual, estandar"`), o `sin_match` |

## BANCI (`u.ba`)

| Columna | Descripción |
|---|---|
| `sexo_banci` | sexo de la víctima |
| `id_mun_hchos_banci` | clave municipal del lugar de los hechos |
| `fha_de_hchos_derivada_banci` | fecha de hechos; **la que rebana el período** en BANCI |
| `cve_entidad_derivada_banci`, `nombre_entidad_derivada_banci` | clave INEGI y nombre de la entidad, a partir de `entidad_derivada_banci` |
| `localizado_o_no_localizado_derivada_banci` | estatus; el refinado sólo ve los no localizados |
| `estatus_loc_derivada_banci` | `des` (12,153) · `loc` (22,624): la anterior colapsada a la dimensión de rebanada |
| `curp_valida_derivada_banci` | la CURP pasa la validación estructural; el rebanado la lee como `ccurp` |
| `in_rnpdno_derivada_rnpdno_banci` | bool: la fila casó con algún FUB |
| `fub_derivada_rnpdno_banci` | FUB emparejado, o nulo |
| `tipo_match_derivada_rnpdno_banci` | motores que sostienen ese FUB (`estandar, refinado`), o `sin_match` |
| `fubs_confirmados_manual_derivada_rnpdno_banci` | todos los FUB validados a mano para esa fila, separados por coma |

## Dimensiones de rebanada

El rebanado lee la fecha, la entidad y el estatus de columnas distintas en cada base
(`DIMENSIONES` en `src/pipeline/derivadas.py`). Desde un notebook se piden por nombre de
dimensión, sin escribir la columna:

```python
d[u.columna(s, "fecha")]      # fecha_hechos_modificada_derivada_rnpdno · fha_de_hchos_derivada_banci
d[u.columna(s, "entidad")]    # nombre_entidad_derivada_rnpdno · nombre_entidad_derivada_banci
d[u.columna(s, "cve_ent")]    # idestado_derivada_rnpdno · cve_entidad_derivada_banci
d[u.columna(s, "estatus_loc")]
d[u.columna_bandera(s, "fis")]  # la columna is_fis_* de la base de la rebanada
```

## Banderas `is_*` (CAPA B)

Booleanas, y son lo que consume el `subfiltro` de un `Slice`. Un subfiltro compuesto se
resuelve como AND: `sfval_sfvac` = `sfval & sfvac`. Como toda columna, cada bandera lleva
el sufijo de las fuentes de las que sale: `is_cind_derivada_pui`,
`is_sisf_derivada_rnpdno_pui`… El rebanado la encuentra por el token (`cind`), así que el
sufijo no se escribe nunca al filtrar.

Cada partición se guarda **una sola vez**:

- Si una bandera es la negación exacta de otra, no se guarda: el rebanado la resuelve
  negando la guardada (`NEGACIONES`).
- La validez de CURP no se copia a una `is_*`: el rebanado lee `ccurp` de la columna que
  ya entrega el ETL (`BANDERAS_ETL`).
- Las banderas que en BANCI son constantes por construcción tampoco se guardan: todo
  registro de BANCI es una carpeta de fiscalía con registro administrativo y folio, y el
  rebanado devuelve el valor directamente (`CONSTANTES`).

Para quien filtra no cambia nada —`subfiltro="scurp"` funciona igual—; lo único es que esas
banderas no aparecen como columna en los Parquet por rebanada.

| Grupo | Subfiltros | Columna en `u.rn` | Columna en `u.ba` | Se resuelve al filtrar |
|---|---|---|---|---|
| Delito | `cdel` · `sdel` | `is_cdel_derivada_rnpdno` | `is_cdel_derivada_banci` | `sdel` = no `cdel` |
| Estado de vida | `cvid` · `svid` | `is_cvid_derivada_rnpdno`, `is_svid_derivada_rnpdno` | `is_cvid_derivada_rnpdno_banci`, `is_svid_derivada_rnpdno_banci` | — no son complemento: un desaparecido no es ninguna |
| Indicios de vida | `cind` · `sind` | `is_cind_derivada_pui` | constante `True` | `sind` = no `cind` |
| Información suficiente | `sisf` · `cisf` | `is_sisf_derivada_rnpdno_pui` | `is_sisf_derivada_rnpdno_banci_pui` | `cisf` = no `sisf` |
| CURP | `ccurp` · `scurp` | `curp_vic_valida_derivada_rnpdno` | `curp_valida_derivada_banci` | `scurp` = no `ccurp` |
| Folio válido | `cfval` · `sfval` | `is_cfval_derivada_rnpdno` | constante `True` | `sfval` = no `cfval` |
| Folio vacío | `cfvac` · `sfvac` | `is_cfvac_derivada_rnpdno` | constante `False` | `sfvac` = no `cfvac`; transversal a la anterior |
| Tipo de desaparición | `dfor` · `cpar` | `is_dfor_*`, `is_cpar_*` (¹) | `is_dfor_derivada_banci`, `is_cpar_derivada_banci` | — sólo en bases matcheadas |
| Institución que reporta | `fis` · `com` · `por` | `is_fis_*`, `is_com_*`, `is_por_*` (²) | constantes `True` · `False` · `False` | — `por` es el residuo |

(¹) `_derivada_rnpdno_banci` cuando el perfil propaga el delito desde BANCI
(`propagar_delito_banci`); si no, `_derivada_rnpdno`.
(²) `_derivada_rnpdno_banci` cuando la dependencia es la corregida por el cruce; si no,
`_derivada_rnpdno`.

En BANCI, `cvid`, `svid` y `sisf` de las filas matcheadas los manda el RNPDNO: por eso
llevan `_rnpdno_banci`.

### Dos relaciones que conviene tener presentes

**Folio válido y folio vacío son particiones distintas y se cruzan.** `cfval` = el
expediente cumple el criterio de la modalidad configurada o la revisión manual lo da
por válido; `cfvac` = el campo viene vacío.
Como `cfval = (válido AND no-vacío) OR revisión manual`, un campo vacío sólo es válido si
la revisión manual lo incluye (`MODALIDAD_MANUAL_CLASIFICACION_CARPETA`):

```
cfvac AND no-manual  ⟹  sfval     por tanto   sfval_cfvac ⊆ cfvac
cfval + sfval_sfvac + sfval_cfvac = total
```

Las plantillas cuentan el folio vacío con `sfval_cfvac`, nunca con `cfvac` a secas, así
que esa excepción no las descuadra.

**`is_por` es el residuo.** Ni fiscalía ni comisión, así que `fis + com + por` siempre
reconstruye el total de la rama.

**`cind` es "hay registro administrativo", no "está vivo".** Las actas de defunción entran al
Parquet del notebook 3 con la misma etiqueta que los indicios de vida (2,579 de 38,748 en el
corte del 29-sep-2026), así que un FUB puede ser `cind` por un acta de defunción. `cind` también
absorbe la distinción entre "sólo PUI" y "PUI + confronta manual", que existe en el Parquet
pero no llega al universo.

**`cind` participa en la partición de información suficiente.** `sisf` = sin CURP válida **y**
sin registro administrativo, de modo que basta una de las dos fuentes para caer en `cisf`:

```
sisf = ~ccurp & sind          cisf = ~sisf = ccurp | cind
cisf_cind = cind              cisf_sind = ccurp & sind
cisf_cind + cisf_sind = cisf  y  cisf + sisf = total
```

## Caché de matching (`cache/matching/<clave>/banci.parquet`)

Lo que devuelve la CAPA A y se guarda en caché; en memoria viaja como `u.matching.banci`.
`motores._salida` deja **sólo lo que leen las capas siguientes** —`derivar_banci` y la
exportación de llaves—, antes de escribir el caché, así que una corrida nueva y una lectura
del caché entregan los mismos valores. No se guardan el detalle de cada motor (`*_estandar`,
`*_manual`, `*_refinado`), ni las copias `*_consolidado` de la cascada, ni los motivos de
anulación.

| Columna | Descripción |
|---|---|
| `entidad_derivada_banci`, `id_carpeta_derivada_banci`, `sexo_banci`, `id_mun_hchos_banci`, `fha_de_hchos_derivada_banci`, `localizado_o_no_localizado_derivada_banci`, `fue_delito_banci`, `delito_hom_banci`, `curp_valida_derivada_banci` | las columnas del ETL de BANCI que se leen después (`motores.COLS_BANCI_SALIDA`) |
| `fub_derivada_rnpdno_banci` | FUB ganador de la cascada, o nulo. Es la llave `id_cruce` de la exportación |
| `tipo_match_derivada_rnpdno_banci` | motores que sostienen ese FUB, o `sin_match` |
| `metodo_origen_derivada_rnpdno_banci` | motor que ganó la fila en la cascada |
| `subcriterio_match_derivada_rnpdno_banci` | `match_fub` · `match_curp` · `match_nombre` · `definitivo` · `parcial (algun caracter distinto)` · `match_confirmado_sesnsp` |
| `score_derivada_rnpdno_banci` | puntaje del match ganador |
| `variables_match_derivada_rnpdno_banci` | evidencia del match ganador |
| `fubs_confirmados_manual_derivada_rnpdno_banci` | todos los FUB validados a mano para esa fila |
| `tipo_match_<motor>_anulado_derivada_rnpdno_banci`, `id_match_<motor>_anulado_derivada_rnpdno_banci` | la oferta que anuló una regla; de ahí salen los candidatos a revisión manual ([7. Llaves de cruce](7_llaves_de_cruce.md)) |

### Las colas de revisión (`verif_fecha.parquet`, `candidatos_revision.parquet`)

En la misma carpeta del caché (en memoria, `u.matching.verif_fecha` y
`u.matching.candidatos`), `motores._cola_verif_fecha` deja los pares que un motor
sostiene como match pero cuya fecha de hechos no lo confirma, y `motores._cola_candidatos`
el mejor candidato que el refinado propuso para cada registro sin match. Las dos tienen
las mismas columnas. Se calcula ahí porque es el
único momento en que existen las columnas de cada motor; la lee la base de revisión del
Secretariado ([7. Llaves de cruce §7.8](7_llaves_de_cruce.md#78-bases-para-la-revisión-del-secretariado)).
Un par (fila de BANCI, FUB) por renglón:

| Columna | Descripción |
|---|---|
| `fila_derivada_banci` | posición de la fila en BANCI (la misma en Resultado_2 y en `banci.parquet`) |
| `fub_derivada_rnpdno_banci` | el FUB propuesto |
| `motor_derivada_rnpdno_banci` | `estandar` · `refinado` · `estandar, refinado` |
| `evaluacion_match_…`, `score_…`, `variables_match_…`, `fecha_hechos_status_…`, `verif_nombre_…`, `verif_curp_…`, `verif_carpeta_…`, `verif_entidad_…`, `verif_sexo_…`, `verif_fecha_nac_…` (todas `_derivada_rnpdno_banci`) | la trazabilidad del motor que propone el par; si son los dos, la del estándar |

`motores.VERSION_MATCHING` entra en `clave_matching` y se sube al cambiar estas columnas o
sus nombres. El caché no depende de que se suba: su llave ya incluye el código de la capa
(ver [6. Arquitectura](6_arquitectura.md#qué-invalida-el-caché)).
