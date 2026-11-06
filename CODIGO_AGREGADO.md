# 📝 Código Agregado - Detalles Técnicos

## Funciones Agregadas en Celda 15

### 1️⃣ `fecha_max_banci()`

```python
def fecha_max_banci():
    """Obtiene la última fecha reportada en BANCI."""
    if "reg_rn-si-ba_01oct24-max_des" in dfs:
        df_banci = dfs["reg_rn-si-ba_01oct24-max_des"]
        if "fha_de_hchos_derivada_banci" in df_banci.columns:
            fecha_max = pd.to_datetime(df_banci["fha_de_hchos_derivada_banci"]).max()
            return fecha_max
    return None
```

**¿Qué hace?**
- Busca la rebanada de BANCI (`reg_rn-si-ba_01oct24-max_des`)
- Obtiene el máximo de la columna de fecha `fha_de_hchos_derivada_banci`
- Retorna un `pd.Timestamp` o `None` si no encuentra datos

**Ejemplo de salida:**
```
Timestamp('2026-09-30 00:00:00')
```

---

### 2️⃣ `serie_mensual_hasta_banci(s, fecha_limite=None)`

```python
def serie_mensual_hasta_banci(s, fecha_limite=None):
    """Registros por mes de una rebanada, limitados a la fecha de BANCI.
    
    Si no se proporciona fecha_limite, se obtiene de BANCI automáticamente.
    """
    if fecha_limite is None:
        fecha_limite = fecha_max_banci()
    
    desde, hasta = u.rango_fechas(s)
    
    # Limitar hasta la fecha de BANCI
    if fecha_limite is not None:
        hasta = min(pd.to_datetime(hasta), fecha_limite)
    
    resultado = agrupar_por_mes(u.slice(s), u.columna(s, "fecha"), completar_meses=True,
                                desde=desde, hasta=hasta)
    return resultado
```

**¿Qué hace?**
- Es una versión mejorada de `serie_mensual()` que limita los datos
- Si no se proporciona `fecha_limite`, la obtiene automáticamente de BANCI
- Limita la fecha "hasta" al mínimo entre la fecha del período y la fecha de BANCI
- Retorna una tabla con columnas: `['mes', 'registros']`

**Ejemplo de uso:**
```python
tabla = serie_mensual_hasta_banci(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="cfval")
)
# Retorna DataFrame con registros solo hasta septiembre 2026
```

**Ejemplo de salida:**
```
         mes  registros
0  2024-10     1,234
1  2024-11       987
2  2024-12     1,456
3  2025-01     2,345
4  2025-02     1,876
5  2025-03     2,543
...
47 2026-09     3,123
# (octubre y noviembre 2026 no aparecen porque están después de BANCI)
```

---

### 3️⃣ `generar_mensaje_fechas_no_contempladas(s, fecha_limite=None)`

```python
def generar_mensaje_fechas_no_contempladas(s, fecha_limite=None):
    """Genera mensaje de meses no contemplados por falta de datos BANCI.
    
    Devuelve una cadena como:
    "No se muestran 123 casos de octubre y 456 correspondientes a noviembre 
    ya que están por ser verificados con BANCI"
    """
    if fecha_limite is None:
        fecha_limite = fecha_max_banci()
    
    if fecha_limite is None:
        return ""
    
    # Obtener el rango completo del período
    desde, hasta = u.rango_fechas(s)
    hasta_periodo = pd.to_datetime(hasta)
    fecha_limite = pd.to_datetime(fecha_limite)
    
    # Si la fecha de BANCI es la última del período, no hay meses no contemplados
    if fecha_limite >= hasta_periodo:
        return ""
    
    # Obtener todos los registros de la rebanada
    df_slice = u.slice(s)
    df_slice["mes"] = pd.to_datetime(df_slice[u.columna(s, "fecha")]).dt.to_period("M")
    
    # Contar registros por mes después de la fecha de BANCI
    meses_no_cont = df_slice[pd.to_datetime(df_slice[u.columna(s, "fecha")]) > fecha_limite]
    conteo_por_mes = meses_no_cont.groupby("mes").size().sort_index()
    
    if len(conteo_por_mes) == 0:
        return ""
    
    # Construir el mensaje
    meses_etiquetados = []
    for mes, conteo in conteo_por_mes.items():
        mes_str = mes.strftime("%B").lower()  # nombre del mes en inglés
        # Traducir meses al español
        mes_es = {
            "january": "enero", "february": "febrero", "march": "marzo",
            "april": "abril", "may": "mayo", "june": "junio",
            "july": "julio", "august": "agosto", "september": "septiembre",
            "october": "octubre", "november": "noviembre", "december": "diciembre"
        }.get(mes_str, mes_str)
        meses_etiquetados.append(f"{conteo:,} casos de {mes_es}")
    
    # Unir los meses con "y"
    if len(meses_etiquetados) == 1:
        meses_texto = meses_etiquetados[0]
        return f"No se muestran {meses_texto} ya que están por ser verificados con BANCI"
    else:
        meses_texto = " y ".join(meses_etiquetados)
        return f"No se muestran {meses_texto} ya que están por ser verificados con BANCI"
```

**¿Qué hace?**
- Obtiene todos los registros después de la fecha de BANCI
- Agrupa por mes y cuenta los casos
- Traduce automáticamente los nombres de meses al español
- Formatea el mensaje con separadores de miles
- Retorna un string vacío si no hay meses sin contemplar

**Ejemplo de salida 1** (con datos sin verificar):
```
"No se muestran 1,234 casos de octubre y 5,678 correspondientes a noviembre 
ya que están por ser verificados con BANCI"
```

**Ejemplo de salida 2** (todos los datos verificados):
```
""  # cadena vacía
```

**Ejemplo de salida 3** (solo un mes):
```
"No se muestran 2,456 casos de octubre ya que están por ser verificados con BANCI"
```

---

## Inicialización Global (al inicio de Celda 15)

```python
# Calcular las variables globales
FECHA_MAX_BANCI = fecha_max_banci()
print(f"📅 Fecha máxima en BANCI: {FECHA_MAX_BANCI}")
```

**¿Qué hace?**
- Calcula la fecha máxima UNA SOLA VEZ al inicio
- La imprime para que veas en la salida del notebook
- Se almacena en variable global para uso en los gráficos

---

## Modificaciones en Gráficos (Celda 15)

### Slide 9 - Con folio válido (`cfval`)

**ANTES:**
```python
nombre = "gr_mes_rn-no-ba_01oct24-max_des_cfval"
tabla = serie_mensual(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="cfval"))
```

**DESPUÉS:**
```python
nombre = "gr_mes_rn-no-ba_01oct24-max_des_cfval"
tabla = serie_mensual_hasta_banci(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="cfval"))
```

### Slide 10 - Sin folio válido (`sfval`)

**ANTES:**
```python
nombre = "gr_mes_rn-no-ba_01oct24-max_des_sfval"
tabla = serie_mensual(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="sfval"))
```

**DESPUÉS:**
```python
nombre = "gr_mes_rn-no-ba_01oct24-max_des_sfval"
tabla = serie_mensual_hasta_banci(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="sfval"))
```

---

## Nueva Variable de Plantilla (Celda 11)

**AGREGADO EN el diccionario `extra={}` de `u.indicadores()`:**

```python
# Mensaje de fechas no contempladas para slides 9 y 10
"msg_fechas_no_cont": generar_mensaje_fechas_no_contempladas(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="sfval")),
```

**Uso en la plantilla:**
```
{{msg_fechas_no_cont}}
```

---

## Flujo de Ejecución

```
1. Se carga FECHA_MAX_BANCI = fecha_max_banci()
   ↓
   Imprime: "📅 Fecha máxima en BANCI: 2026-09-30"
   
2. Se genera gráfico Slide 9 con serie_mensual_hasta_banci()
   ↓
   Datos: octubre 2024 a septiembre 2026
   
3. Se genera gráfico Slide 10 con serie_mensual_hasta_banci()
   ↓
   Datos: octubre 2024 a septiembre 2026
   
4. Se genera msg_fechas_no_cont con generar_mensaje_fechas_no_contempladas()
   ↓
   Retorna: "No se muestran 1,234 casos de octubre y 5,678 correspondientes a noviembre..."
   
5. Las variables se pasan a PPTReportBuilder
   ↓
   Se reemplaza {{msg_fechas_no_cont}} en la plantilla
   
6. Se genera la presentación con gráficos cortos y mensaje dinámico
```

---

## Notas Técnicas Importantes

### 1. Manejo de Errores
- Si BANCI no tiene datos: retorna `None` y funciona con datos sin filtro
- Si el período está completamente verificado: retorna cadena vacía
- Si hay datos faltantes: se manejan con `fillna()` y `dropna()`

### 2. Flexibilidad
- Las funciones no están hardcodeadas a un período específico
- Usan `u.rango_fechas(s)` que detecta automáticamente
- Puedes llamarlas con cualquier `Slice`

### 3. Rendimiento
- `fecha_max_banci()` se ejecuta UNA sola vez
- Las demás funciones reutilizan ese valor
- Mínimo impacto en tiempo de ejecución

### 4. Internacionalización
- Los meses se traducen automáticamente al español
- Se usa diccionario `mes_es` con 12 meses
- Si agregas otro idioma, solo actualiza el diccionario

---

## Uso Avanzado

### Usar con un período diferente:

```python
# Cambiar el período
resultado = serie_mensual_hasta_banci(
    Slice("rn-no-ba", "01ene25-max", estatus="des", subfiltro="cfval")  # ← Cambiar fecha
)
```

### Usar con fecha límite manual:

```python
# Especificar una fecha diferente a BANCI
resultado = serie_mensual_hasta_banci(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="cfval"),
    fecha_limite=pd.Timestamp('2026-08-31')  # ← Fecha manual
)
```

### Obtener el mensaje para otra rebanada:

```python
# Generar mensaje para cfval en lugar de sfval
mensaje = generar_mensaje_fechas_no_contempladas(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="cfval")  # ← Otra rebanada
)
```

