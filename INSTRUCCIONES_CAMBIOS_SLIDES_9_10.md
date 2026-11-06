# 📊 Instrucciones de Implementación: Filtrado por Fecha BANCI (Slides 9 y 10)

## 🎯 Objetivo

Recortar automáticamente los gráficos de las **slides 9 y 10** hasta la última fecha reportada por BANCI, y agregar un mensaje dinámico que indique qué meses no se están contemplando y cuántos casos corresponden a cada uno.

## ✅ Cambios Realizados

### En el Notebook `6_PPT_Reporte_Diario.ipynb`:

1. **Celda 15**: Se agregaron 3 nuevas funciones
   - `fecha_max_banci()` → Obtiene la última fecha de BANCI
   - `serie_mensual_hasta_banci()` → Filtra series mensuales por fecha
   - `generar_mensaje_fechas_no_contempladas()` → Crea el mensaje dinámico

2. **Celda 15**: Se modificaron las llamadas de gráficos
   - Slide 9 (`cfval`): Ahora usa `serie_mensual_hasta_banci()`
   - Slide 10 (`sfval`): Ahora usa `serie_mensual_hasta_banci()`

3. **Celda 11**: Se agregó la variable de plantilla
   - `"msg_fechas_no_cont"` disponible en `{{msg_fechas_no_cont}}`

## 🔧 Cómo Funciona

### Filtrado Automático de Gráficos

Cuando ejecutas el notebook:

```
📅 Fecha máxima en BANCI: 2026-09-30
```

Los gráficos de slides 9 y 10 se cortarán automáticamente en esa fecha. Si BANCI reporta hasta septiembre, los datos de octubre y noviembre no aparecerán en los gráficos.

### Mensaje Dinámico

El mensaje se genera automáticamente y se ve como:

```
No se muestran 1,234 casos de octubre y 5,678 correspondientes a noviembre 
ya que están por ser verificados con BANCI
```

## 🖥️ Integración con PowerPoint

### Opción 1: Usar la plantilla actual (recomendado)

Si la plantilla ya tiene el marcador `{{msg_fechas_no_cont}}`:

1. Solo ejecuta el notebook normalmente
2. El mensaje aparecerá automáticamente

### Opción 2: Agregar el marcador a la plantilla

Si quieres agregar el mensaje a una slide específica:

1. Abre `input/plantillas/reporte_diario.pptx` en PowerPoint
2. En la slide deseada, agrega un cuadro de texto
3. Escribe: `{{msg_fechas_no_cont}}`
4. Guarda la plantilla

El mensaje se reemplazará automáticamente con el contenido dinámico.

### Ubicaciones Sugeridas

- **Slide 10 (recomendado)**: Debajo o arriba del gráfico "Sin carpeta de investigación"
- **Slide 9 (opcional)**: Si también quieres un mensaje para folio válido

## 📈 Ejemplo de Resultados

### Antes (datos de todo el período):
```
Gráfico muestra: enero, febrero, marzo, abril, mayo, junio, julio, agosto, 
                 septiembre, octubre, noviembre
```

### Después (solo hasta BANCI):
```
Gráfico muestra: enero, febrero, marzo, abril, mayo, junio, julio, agosto, septiembre

Mensaje: "No se muestran 1,234 casos de octubre y 5,678 correspondientes a noviembre 
         ya que están por ser verificados con BANCI"
```

## 🔄 Escalabilidad (Cambiar Período)

### Para cambiar de período (ej: de octubre 2024 a enero 2025):

**Opción A: Hacerlo automático**
- Simplemente ejecuta el notebook con datos actualizados
- El código detecta automáticamente el nuevo período

**Opción B: Cambiar manualmente el período**

Edita la celda 6 del notebook:

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

### El mensaje no aparece
- **Causa**: Todos los meses están en BANCI
- **Solución**: Es correcto, significa que no hay meses sin contemplar

### Números muy grandes en el mensaje
- **Causa**: Hay muchos casos sin verificar
- **Solución**: Normal, revisa que sea correcto

### El mensaje sale vacío
- **Causa**: No hay registros después de la fecha de BANCI
- **Solución**: Es correcto, todos los datos están verificados

## 📝 Documentación Técnica

### Parámetros de las Funciones

#### `fecha_max_banci()`
```python
fecha_max_banci()
# Retorna: pd.Timestamp o None
# Ejemplo: Timestamp('2026-09-30 00:00:00')
```

#### `serie_mensual_hasta_banci(s, fecha_limite=None)`
```python
serie_mensual_hasta_banci(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="cfval"),
    fecha_limite=pd.Timestamp('2026-09-30')  # Opcional
)
# Retorna: DataFrame con columnas ['mes', 'registros']
```

#### `generar_mensaje_fechas_no_contempladas(s, fecha_limite=None)`
```python
generar_mensaje_fechas_no_contempladas(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="sfval"),
    fecha_limite=None  # Si no se proporciona, usa fecha_max_banci()
)
# Retorna: str
# Ejemplo: "No se muestran 1,234 casos de octubre y 5,678 correspondientes a noviembre ya que están por ser verificados con BANCI"
```

## ✨ Ventajas de Esta Implementación

✅ **Automática**: Se ejecuta sin intervención manual  
✅ **Escalable**: Funciona para cualquier período  
✅ **Dinámica**: Se actualiza cada vez que ejecutas el notebook  
✅ **Robusta**: Maneja datos faltantes y bordes  
✅ **Clara**: Mensajes en español con formato correcto  
✅ **Flexible**: Usa la fecha de BANCI directamente del dataset  

## 🚀 Próximos Pasos

1. ✅ El notebook ya está modificado (cambios realizados)
2. ⏭️ Ejecuta el notebook completo para probar
3. ⏭️ Verifica los gráficos de slides 9 y 10
4. ⏭️ Revisa que `{{msg_fechas_no_cont}}` aparezca en la presentación
5. ⏭️ Ajusta la plantilla si es necesario

¿Necesitas ayuda con algo específico? 📧
