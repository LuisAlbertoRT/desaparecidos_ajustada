# 7. Llaves de cruce entre BANCI y RNPDNO

Las metodologías de matching (ver [3. Metodología de Matching](3_metodologia_de_matching.md))
viven dentro del pipeline: producen conteos e indicadores, pero el resultado no se puede
usar desde fuera. Quien tiene los archivos de origen —BANCI y RNPDNO tal como los entregan
el Secretariado y la Comisión Nacional— no tiene forma de saber qué carpeta corresponde a
qué reporte de búsqueda.

Esta capa cierra esa brecha: devuelve **los mismos archivos**, con una columna que aparea
las dos bases y unas columnas más que explican **cómo** se decidió cada apareo.

```text
src/pipeline/exportacion_llaves.py              el módulo
notebooks/7_Exportacion_Bases_Con_Llave.ipynb   la invocación
output/bases_con_llave/<perfil>/                la salida
```

La salida se separa **por perfil** porque los archivos llevan el mismo nombre que su
origen y contenido distinto según lo que se cruce:

| Perfil | Universo | Carpetas con cruce | Personas con cruce |
|---|---|---:|---:|
| `reporte_diario` | desaparecidos del sexenio | 7,253 | 7,171 |
| `cruce_total` | **todo contra todo** | **25,438** | **24,899** |

---

## 7.1. Qué se entrega

| Archivo | Qué es |
|---|---|
| `SUBIR_R_<corte>.xlsx` | el BANCI de origen, idéntico, **+14 columnas** en la hoja `Victimas` |
| `reporte_personas_completo_<corte>.parquet` (o `reporte_personas_<corte>.xlsx`) | el RNPDNO de origen, idéntico, **+11 columnas** al final |
| `mapa_cruce_<corte>.parquet` / `.csv` | la tabla puente: sólo los pares, sin el resto de las bases |
| `manifiesto_<corte>.json` | qué archivos se usaron, con qué reglas y qué salió |

**Cada base sale en el formato en que entró.** BANCI es un Excel de varias hojas y sale como
Excel. El RNPDNO puede entrar de dos formas (`config.formato_rnpdno`, por la extensión de
`config.RNPDNO_LOCAL_FILE`): si es el Parquet de tabla única sale como Parquet; si es el Excel
de tres hojas sale como Excel, con el bloque de columnas en cada hoja. En los dos casos las
columnas se aparean por FUB, no por posición.

**Idéntico quiere decir idéntico:** mismas filas y en el mismo orden, mismas columnas con el
mismo nombre, y el mismo nombre de archivo. En BANCI, además, las mismas hojas y en el mismo
orden (la `Hoja1` se copia tal cual, sin columnas nuevas). Lo único que cambia es el bloque
de columnas añadido al final.

Lo que **no** se conserva — **todo esto es de los Excel** (BANCI, y el RNPDNO cuando entra en
Excel). El RNPDNO en Parquet sale sin ninguna desviación: pandas conserva los dtypes tal cual
y `validar_export_parquet` lo comprueba columna por columna, dtype incluido.

| Qué | Por qué | Alcance en la corrida vigente |
|---|---|---|
| estilos, anchos de columna, tablas dinámicas | una reescritura no los mantiene | la `Hoja1` de BANCI queda con sus valores, sin el objeto dinámico |
| celdas con cadena vacía `''` → celda vacía | openpyxl no distingue una de otra | 149,586 celdas de BANCI (`COORD_X`, `COORD_Y`…). pandas lee las dos como `NaN` |
| decimales de 17 dígitos → 16 | openpyxl serializa con 16 significativos; **Excel guarda 15** | 219 celdas de BANCI. En coordenadas, 1e-10 metros |

Fue una decisión explícita: aquí importan los valores, no el formato. Las tres desviaciones
las **cuenta y reporta** `validar_export` en cada corrida; ninguna se silencia.

---

## 7.2. La llave es el FUB

`id_cruce` es el FUB del RNPDNO. En el RNPDNO es el propio FUB de la fila; en BANCI, el del
reporte con el que casó. Un `VLOOKUP` por esa columna entre los dos archivos basta.

**Por qué el FUB y no un identificador nuevo.** Es estable entre cortes, es legible y
cualquiera puede verificar un par a ojo. Inventar un identificador opaco es exactamente el
error que ya costó caro aquí: el `id_registro` sha1 que construía el Secretariado no se
podía reproducir desde el BANCI de origen, cruzar por él daba cero, y **561 confirmaciones
humanas nunca se aplicaban**. Una llave que no se puede regenerar desde los datos no
es una llave.

> ⚠️ **La relación es N:1.** Varias carpetas de BANCI pueden apuntar a la misma persona:
> en la corrida vigente son 79 FUB. Cruzar de RNPDNO hacia BANCI **multiplica filas** en
> esos casos. `n_registros_banci` dice cuántas esperar y `id_registro_banci_principal`
> apunta al registro representativo si se quiere un 1:1.
>
> Ese número era 4,663 antes de corregir la atribución del motor estándar: la
> multiplicidad era casi toda artefacto de que el mismo FUB se pegaba a carpetas que no le
> correspondían.

### `id_registro_banci`: por qué BANCI necesita identidad propia

BANCI **no tiene llave única**: 34,777 filas contra 31,744 valores distintos de `LLAVE`.
La diferencia son las carpetas colectivas —varias víctimas en un mismo expediente—, así que
cruzar por `LLAVE` duplica filas silenciosamente.

`id_registro_banci` = identificador de carpeta + ordinal de la víctima dentro de la carpeta,
en el orden del archivo:

```text
GUERRERO/12022510900117040725#01
└──────────── carpeta ────────┘ └┘ ordinal
```

Se puede regenerar desde el Excel de origen sin correr el pipeline. Ésa es la propiedad que
hace confiable a una llave, y la que le faltaba al sha1 del Secretariado.

---

## 7.3. Diccionario de columnas

### BANCI · hoja `Victimas`

| Columna | Valores | Qué dice |
|---|---|---|
| `id_registro_banci` | `ENTIDAD/carpeta#NN` | identidad de la fila |
| `fila_origen_banci` | entero | renglón físico en la hoja de origen (ancla de auditoría) |
| **`id_cruce`** | FUB · **vacío** | **la llave.** Vacío = esta carpeta no se apareó con nadie |
| `estatus_match` | `con_cruce` · `candidato_revision_manual` · `sin_cruce` | siempre tiene valor |
| `metodo_match` | `manual` · `estandar` · `refinado` | el motor que ganó la cascada |
| `submetodo_match` | `match_fub` · `match_curp` · `match_nombre` · `match_confirmado_sesnsp` · `definitivo` · `parcial (algun caracter distinto)` | el criterio exacto |
| `nivel_match` | `1` · `2` · `3` | el escalón del embudo del motor estándar (§3.2) |
| `metodos_concurrentes` | `"estandar, refinado"` | **todos** los motores que sostienen ese mismo FUB. Con `cascada_en_ejecucion = true` (§3.1) siempre nombra a uno solo: el motor que resolvió la fila sacó a los demás de la jugada |
| `fub_candidato_revision` | FUB | el que propuso el refinado y **no** se confirmó |
| `fubs_adicionales_manual` | FUB separados por `;` | otras personas validadas en la misma revisión |
| `score_match` | 0–100 | score del motor ganador |
| `evidencia_match` | texto | las variables que sostuvieron el match |
| `corte_match` | `AAAA-MM-DD` | corte de los datos |
| `version_match` | hash de 16 caracteres | `clave_matching`: identifica la corrida exacta |

### RNPDNO · tabla única (las tres hojas apiladas; `estatus` las distingue)

| Columna | Qué dice |
|---|---|
| **`id_cruce`** | el propio FUB si alguna carpeta de BANCI lo reclamó; vacío si no |
| `estatus_match` | `con_cruce` · `candidato_revision_manual` · vacío |
| `metodo_match`, `submetodo_match`, `nivel_match` | los del registro principal de BANCI |
| `metodos_concurrentes` | todos los métodos que alcanzaron este FUB, desde cualquier carpeta |
| `n_registros_banci` | cuántas filas de BANCI apuntan aquí (**el aviso de N:1**) |
| `id_registro_banci_principal` | el registro representativo: mayor prioridad en la cascada y, a igualdad, el primero del archivo |
| `carpeta_banci_principal` | su carpeta, sin el ordinal de víctima |
| `corte_match`, `version_match` | igual que en BANCI |

---

## 7.4. `revision manual`: sin cruce, pero no "nada"

El motor refinado propone candidatos que no alcanzan a ser match y que en
`normalizar_folios_v6.py` van a un Excel para que una persona los valide. La regla
`excluir_revision_manual` los retira de la oferta antes de la cascada (§3.5).

Antes se borraban sin dejar rastro, y quedaban **indistinguibles** de las filas donde ningún
motor encontró nada: se perdía justo la cola de trabajo que alguien tiene que revisar. Ahora
`_anular_motor` copia la oferta anulada a `tipo_match_<motor>_anulado` /
`id_match_<motor>_anulado` / `motivo_anulacion_<motor>` antes de borrarla. Esas columnas
**no participan en la cascada**: son evidencia, no oferta. Al caché de la capa A llegan las
dos primeras, como `tipo_match_<motor>_anulado_derivada_rnpdno_banci` /
`id_match_<motor>_anulado_derivada_rnpdno_banci`, que son las que lee la exportación; el
motivo no lo lee nadie y no se guarda.

En los archivos exportados eso se ve así:

| | `id_cruce` | `estatus_match` | `fub_candidato_revision` |
|---|---|---|---|
| match confirmado | el FUB | `con_cruce` | vacío |
| candidato sin validar | **vacío** | `candidato_revision_manual` | el FUB propuesto |
| nada | **vacío** | `sin_cruce` | vacío |

La llave nunca se ensucia: un candidato **no** es un cruce, y `id_cruce` sigue vacío. Para
trabajar la cola basta filtrar `estatus_match == "candidato_revision_manual"`.

---

## 7.5. El contrato de verificación

`validar_export` reabre los archivos escritos y **falla ruidosamente** si:

- cambian los nombres o el orden de las hojas (BANCI);
- cambia el número de filas;
- **alguna celda original no es idéntica** a la del archivo de origen (comparación completa,
  celda por celda, no muestreo). Las únicas tolerancias son las tres deformaciones de la
  tabla de §7.1, y están acotadas: la de decimales es exactamente el ancho del redondeo de
  openpyxl (1e-15 relativo), no un `isclose` genérico que pudiera tapar un error de
  conversión;
- aparecen columnas nuevas distintas de las declaradas, o en otro orden;
- algún `id_cruce` de BANCI no existe en el RNPDNO, o el conjunto de FUB apareados no
  coincide con `fubs_matcheados` de la CAPA A;
- algún FUB del mapa no aparece en el archivo del RNPDNO (señal de que la salida del notebook 1 y
  el archivo de origen son de cortes distintos).

No es paranoia. El valor de estos archivos depende por completo de que se puedan usar **en
lugar** de los originales; una diferencia silenciosa —una fecha convertida a texto, una fila
corrida— haría que todo lo que se cruce después estuviera mal sin que nadie se enterara.

---

## 7.6. Resultado de la corrida vigente

| BANCI (34,777 carpetas) | Registros |
|---|---:|
| `con_cruce` | 7,253 |
| `candidato_revision_manual` | 3,762 |
| `sin_cruce` | 23,762 |

| Método ganador | Registros | Subcriterios |
|---|---:|---|
| `estandar` | 6,121 | nivel 1 (FUB) 3,351 · nivel 2 (CURP) 1,410 · nivel 3 (nombre) 1,360 |
| `refinado` | 571 | `definitivo` 555 · `parcial` 16 |
| `manual` | 561 | `match_confirmado_sesnsp` 561 |

| RNPDNO (408,600 reportes) | Registros |
|---|---:|
| FUB con cruce | 7,171 |
| FUB marcados como candidato a revisión | 1,933 |
| FUB alcanzados por más de una carpeta | 79 |

Los 7,253 registros de BANCI apuntan a 7,167 personas distintas; los 4 FUB restantes hasta
7,171 vienen de `fubs_adicionales_manual` —personas validadas en una revisión que ninguna
fila puede llevar como `id_cruce`— y se reclaman sólo del lado del RNPDNO (§3.3).

> Cifras de la corrida del 7 de septiembre de 2026, ya con la atribución del motor estándar
> corregida. Cualquier exportación anterior a esa fecha tiene el `id_cruce`
> equivocado en las filas con `metodo_match = estandar` y debe regenerarse.

---

## 7.7. Cuándo hay que volver a exportar

La exportación **no calcula matches**: toma la CAPA A del universo que se construye en el
mismo notebook (`exportar_bases_con_llave(u)`), del caché si sigue valiendo. Hay que volver a
correr el notebook 7 cuando cambie cualquier cosa que mueva `clave_matching`: los archivos
de origen, las reglas del perfil, el orden de la cascada o las tolerancias. `version_match` viaja en cada fila exportada justamente para poder
distinguir de qué corrida salió una llave.

---

## 7.8. Bases para la revisión del Secretariado

[`src/pipeline/revision_sesnsp.py`](../src/pipeline/revision_sesnsp.py) escribe las dos bases
que antes se armaban a mano con las salidas del script de R y de `normalizar_folios_v6.py`,
y que el Secretariado devolvía contestadas:

| Base | Función | Qué pares | Respuesta | Vuelve como |
|---|---|---|---|---|
| Candidatos a revisión manual | `exportar_candidatos_revision` | el mejor candidato que el refinado propone para cada registro sin match (score 1–99) | `VALIDA` | `revision_manual_score_SESNSP.xlsx` |
| Verificación de fecha de hechos | `exportar_revision_fecha_hechos` | matches que la fecha de hechos no confirma (abajo) | `VALIDO` | `matches_verif_fecha_hechos_SESNSP.xlsx` |

Salen en `output/revision_sesnsp/<perfil>/`, con el corte del RNPDNO en el nombre.

### El perfil `revision_secretariado` (notebook 8)

Los candidatos tienen que salir con la lógica del flujo que se usaba antes: primero el
script de R y, **sobre lo que éste dejaba sin match**, `normalizar_folios`, buscando en
**todo** el RNPDNO. Eso es el perfil `perfiles/revision_secretariado.toml`, que usa el
notebook 8:

- **Motores en cadena** (`cascada_en_ejecucion = true`): el refinado sólo propone
  candidatos para los registros que el estándar no emparejó.
- **Sin `regla_r_desfase_dias`**: en R un match del estándar con fecha que difiere, o con
  FUB localizado, sigue siendo match, así que ese registro no pasa al refinado.
- **Todo el RNPDNO** (`filtrar_rnpdno_clasificacion = false`, `fecha_sexenio = "1900-01-01"`):
  localizados y todos los años. BANCI, sólo no localizados.

Se comprobó contra `resultado_unificado_para_revision_30092026.xlsx`, armado con ese flujo:
con esta lógica coinciden 86 % de sus registros de BANCI; con la de `reporte_diario`
coincidían 132 pares. El FUB propuesto coincide menos, porque los dos flujos desempatan
sin regla explícita cuando dos candidatos tienen el mismo score: es una decisión pendiente.

> No es un perfil para indicadores: abre el universo y quita una regla, así que sus
> matches no son los de `reporte_diario`. Tiene su propia llave de caché.

### Qué pares van a verificación de fecha

| Motor | Qué pares entran | Regla de origen |
|---|---|---|
| estándar | `match_definitivo == "DIFIERE"`: más de 10 días entre las dos fechas de hechos | script de R: la columna con que se partía su base en definitivos y a revisar |
| refinado | los definitivos cuya fecha no cupo en ±10 días o que no la tienen (`SIN DATO`), en las filas que sostiene el refinado | `normalizar_folios_v6.py` → `matches_verif_fecha_hechos_v6.xlsx` |

`motor_origen` dice de cuál viene cada par. Si los dos motores proponen el mismo par sale
una sola vez, como `estandar, refinado`, con la trazabilidad del estándar. No se mandan
pares cuyo FUB no está en el universo RNPDNO del motor manual: un SI ahí no tendría
efecto, porque el motor manual descarta ese FUB.

### Lo que no se vuelve a mandar

Lo que el Secretariado ya contestó, con la regla de v6, en las dos bases: en la
verificación de fecha el SI y el NO cierran el caso; en la revisión por score el SI lo
cierra y el NO sólo bloquea ese par; un FUB ya emparejado no se vuelve a proponer. Lo que
quedó **sin respuesta** se vuelve a mandar.

### Formato e ida y vuelta

Una hoja `revision`, un par por renglón, con la columna de respuesta vacía y las columnas
de los archivos que el Secretariado ya devolvió, en los nombres que reconoce
`leer_revisiones_sesnsp`. Del lado de BANCI van también `id_registro_banci` y
`fila_origen_banci` (§7.2). La hoja `resumen` dice cuántos pares propuso cada motor y
cuántos se descontaron.

Al escribirla se vuelve a leer como si ya estuviera contestada y se comprueba que cada
renglón se liga con su registro de BANCI por contenido (entidad + carpeta + CURP / nombre /
fecha de nacimiento), que es lo que hará el motor manual. Si alguno se ligara con otro
registro, la exportación falla; los que no se pueden ligar (carpetas colectivas sin llave
que distinga a la víctima) se reportan.

> Las bases **no cambian ningún resultado**: sólo leen la capa A del universo. Las respuestas
> entran por el motor manual, que hoy lee un archivo de cada tipo
> (`config.REFINADO_RUTA_VERIF_FECHA_HECHOS`, `config.REFINADO_RUTA_REVISION_MANUAL`): los
> renglones contestados hay que agregarlos a esos archivos, no reemplazarlos, o se perderían
> las respuestas anteriores.
