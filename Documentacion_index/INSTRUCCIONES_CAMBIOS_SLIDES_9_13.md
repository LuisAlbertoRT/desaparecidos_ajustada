# 📊 Instrucciones de Implementación: Filtrado por Fecha BANCI (Slides 9-13)

## 🎯 Objetivo

Recortar automáticamente los gráficos de las **slides 9-13** hasta la última fecha reportada por BANCI, y agregar un mensaje dinámico que indique qué meses no se están contemplando y cuántos casos corresponden a cada uno.

## ✅ Cambios Realizados

### En `notebooks/6_PPT_Reporte_Diario.ipynb`

Los cambios deben ejecutarse desde el notebook de `notebooks/`, **nunca** desde `notebooks luis/`.

1. **Celda 15 - Funciones auxiliares**: Se mantienen las 3 funciones existentes
   - `fecha_max_banci()` → Obtiene la última fecha de BANCI
   - `serie_mensual_hasta_banci()` → Filtra series mensuales por fecha
   - `generar_mensaje_fechas_no_contempladas()` → Crea el mensaje dinámico

2. **Celda 15 - Regeneración de gráficos**: Se amplió la tupla `_graficas_banci` de 2 a 5 gráficos:
   - **Diapositiva 9**: `gr_mes_rn-si-ba_01oct24-max_des` (casos con BANCI)
   - **Diapositiva 10**: `gr_mes_rn-no-ba_01oct24-max_des_cfval` (folio válido)
   - **Diapositiva 11**: `gr_mes_rn-no-ba_01oct24-max_des_sfval` (sin folio válido completo)
   - **Diapositiva 12**: `gr_mes_rn-no-ba_01oct24-max_des_sfval_sfvac` (folio inválido)
   - **Diapositiva 13**: `gr_mes_rn-no-ba_01oct24-max_des_sfval_cfvac` (campo de folio vacío)

3. **Comportamiento**: 
   - Todos los gráficos se filtran automáticamente al corte de BANCI
   - Los totales `{{reg_...}}` permanecen intactos (sin filtrar)
   - Solo se agrega mensaje informativo en la diapositiva 10 (sin cambios en pies de página de 11-13)

## ▶️ Cómo ejecutar los cambios

En VS Code/Jupyter, selecciona **Reiniciar kernel y ejecutar todas las celdas**. No ejecutes únicamente la celda del armado del PowerPoint: las gráficas y el mensaje dependen de las celdas anteriores.

En la salida confirma:
- `📅 Fecha máxima en BANCI: ...` 
- `📊 gr_mes_rn-si-ba_01oct24-max_des: ... casos; corte ...`
- `📊 gr_mes_rn-no-ba_01oct24-max_des_cfval: ... casos; corte ...`
- `📊 gr_mes_rn-no-ba_01oct24-max_des_sfval: ... casos; corte ...`
- `📊 gr_mes_rn-no-ba_01oct24-max_des_sfval_sfvac: ... casos; corte ...`
- `📊 gr_mes_rn-no-ba_01oct24-max_des_sfval_cfvac: ... casos; corte ...`
- `Mensaje BANCI: ...`

Todos los totales deben conservar su valor original. Si la plantilla no sustituye el marcador, el armado se detiene con un error explícito.

## 🔧 Cómo Funciona

### Filtrado Automático de Gráficos

Cuando ejecutas el notebook:

```
📅 Fecha máxima en BANCI: 2026-09-30
```

Los gráficos de slides 9-13 se cortarán automáticamente en esa fecha: las filas posteriores se quitan antes del agrupamiento, y no solo del eje.

### Colores de cada gráfico (automáticos):

- **Slide 9** (con BANCI): `#af5967ff` (rosa)
- **Slide 10** (folio válido): `#9b2347ff` (rojo oscuro)
- **Slide 11** (sin folio válido): `#595959ff` (gris oscuro)
- **Slide 12** (folio inválido): `#757575ff` (gris medio)
- **Slide 13** (campo vacío): `#888888ff` (gris claro)

### Mensaje Dinámico (solo en slide 10)

El mensaje se genera automáticamente y se ve como:

```
No se muestran 479 casos de octubre y 42 correspondientes a noviembre
ya que están por ser verificados con BANCI
```

## 🖥️ Integración con PowerPoint

### Opción 1: Usar la plantilla actual (recomendado)

Si la plantilla ya tiene el marcador `{{msg_fechas_no_cont}}`:

1. Solo ejecuta el notebook normalmente
2. El mensaje aparecerá automáticamente en la slide 10

### Opción 2: Agregar el marcador a la plantilla (si es necesario)

Si quieres agregar el mensaje a una slide específica:

1. Abre `input/plantillas/reporte_diario.pptx` en PowerPoint
2. En la slide deseada, agrega un cuadro de texto
3. Escribe: `{{msg_fechas_no_cont}}`
4. Guarda la plantilla

El mensaje se reemplazará automáticamente con el contenido dinámico.

## 📈 Ejemplo de Resultados

### Antes (datos de todo el período):
```
Gráficos muestran: enero, febrero, marzo, abril, mayo, junio, julio, agosto, 
                   septiembre, octubre, noviembre (11 meses)
```

### Después (solo hasta BANCI):
```
Gráficos muestran: enero, febrero, marzo, abril, mayo, junio, julio, agosto, 
                   septiembre (9 meses)

Mensaje en slide 10: "No se muestran 479 casos de octubre y 42 correspondientes 
                      a noviembre ya que están por ser verificados con BANCI"
```

## 🔄 Escalabilidad (Cambiar Período)

### Para cambiar de período (ej: de octubre 2024 a enero 2025):

**Opción A: Hacerlo automático**
- Simplemente ejecuta el notebook con datos actualizados
- El código detecta automáticamente el nuevo período

**Opción B: Cambiar manualmente el período**

En la celda 15 de gráficas, cambia el período en los `Slice`:

```python
# Cambiar de esto:
Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="cfval")

# A esto:
Slice("rn-no-ba", "01ene25-max", estatus="des", subfiltro="cfval")
```

## 🐛 Troubleshooting

### El gráfico no se corta
- **Causa**: BANCI no tiene fecha en ese registro
- **Solución**: Verifica que `fha_de_hchos_derivada_banci` tenga datos válidos

### El mensaje no aparece en la slide 10
- **Causa**: Todos los meses están en BANCI
- **Solución**: Es correcto, significa que no hay meses sin contemplar

### Números muy grandes en el mensaje
- **Causa**: Hay muchos casos sin verificar
- **Solución**: Normal, revisa que sea correcto con los datos reales

### El mensaje sale vacío
- **Causa**: No hay registros después de la fecha de BANCI
- **Solución**: Es correcto, todos los datos están verificados

### Las slides 11-13 no se actualizan
- **Causa**: El notebook no se ejecutó completamente
- **Solución**: Reinicia kernel y ejecuta todas las celdas nuevamente

## 📝 Documentación Técnica

### Parámetros de las Funciones

#### `fecha_max_banci()`
```python
fecha_max_banci()
# Retorna: pd.Timestamp; lanza ValueError si no hay fechas válidas en BANCI
# Ejemplo: Timestamp('2026-09-30 00:00:00')
```

#### `serie_mensual_hasta_banci(s, fecha_limite)`
```python
serie_mensual_hasta_banci(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="cfval"),
    fecha_limite=pd.Timestamp('2026-09-30')
)
# Retorna: DataFrame con columnas ['mes', 'registros']
# Los registros posteriores a fecha_limite se filtran ANTES del agrupamiento
```

#### `generar_mensaje_fechas_no_contempladas(s, fecha_limite)`
```python
generar_mensaje_fechas_no_contempladas(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="cfval"),
    fecha_limite=pd.Timestamp('2026-09-30')
)
# Retorna: str
# Ejemplo: "No se muestran 479 casos de octubre y 42 correspondientes a noviembre 
#           ya que están por ser verificados con BANCI"
```

## ✨ Ventajas de Esta Implementación

✅ **Automática**: Se ejecuta sin intervención manual  
✅ **Escalable**: Funciona para cualquier período y para múltiples gráficos  
✅ **Dinámica**: Se actualiza cada vez que ejecutas el notebook  
✅ **Robusta**: Maneja datos faltantes y bordes  
✅ **Clara**: Mensajes en español con formato correcto  
✅ **Flexible**: Usa la fecha de BANCI directamente del dataset  
✅ **Consistente**: Todos los gráficos de BANCI usan la misma fecha de corte  

## 🚀 Próximos Pasos

1. ✅ El notebook ya está modificado (cambios realizados)
2. ⏭️ Ejecuta el notebook completo para probar
3. ⏭️ Verifica los gráficos de slides 9-13
4. ⏭️ Revisa que `{{msg_fechas_no_cont}}` aparezca en la presentación (slide 10)
5. ⏭️ Ajusta la plantilla si es necesario

## 📋 Resumen de Cambios

| Slide | Gráfico | Periodo | Color | Estado |
|-------|---------|---------|-------|--------|
| 9 | gr_mes_rn-si-ba_01oct24-max_des | Oct 2024 - BANCI | #af5967ff | ✅ Filtrado |
| 10 | gr_mes_rn-no-ba_01oct24-max_des_cfval | Oct 2024 - BANCI | #9b2347ff | ✅ Filtrado + Msg |
| 11 | gr_mes_rn-no-ba_01oct24-max_des_sfval | Oct 2024 - BANCI | #595959ff | ✅ Filtrado |
| 12 | gr_mes_rn-no-ba_01oct24-max_des_sfval_sfvac | Oct 2024 - BANCI | #757575ff | ✅ Filtrado |
| 13 | gr_mes_rn-no-ba_01oct24-max_des_sfval_cfvac | Oct 2024 - BANCI | #888888ff | ✅ Filtrado |

¿Necesitas ayuda con algo específico? 📧
