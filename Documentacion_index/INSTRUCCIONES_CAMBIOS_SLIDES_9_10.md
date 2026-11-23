# 📊 Instrucciones de Implementación: Filtrado por Fecha BANCI (Slides 9 y 10)

## 🎯 Objetivo

Recortar automáticamente los gráficos de las **slides 9 y 10** hasta la última fecha reportada por BANCI, y agregar un mensaje dinámico que indique qué meses no se están contemplando y cuántos casos corresponden a cada uno.

## ✅ Cambios Realizados

### En `notebooks/6_PPT_Reporte_Diario.ipynb`

Los cambios deben ejecutarse desde el notebook de `notebooks/`, **nunca** desde `notebooks luis/`.

1. **Celda nueva después de la sección de gráficas**: se agregaron 3 funciones
   - `fecha_max_banci()` → Obtiene la última fecha de BANCI
   - `serie_mensual_hasta_banci()` → Filtra series mensuales por fecha
   - `generar_mensaje_fechas_no_contempladas()` → Crea el mensaje dinámico

2. **La misma celda nueva** regenera únicamente las imágenes de las diapositivas 9 y 10. Filtra las filas antes de agruparlas:
   - Diapositiva 9: `gr_mes_rn-si-ba_01oct24-max_des`
   - Diapositiva 10: `gr_mes_rn-no-ba_01oct24-max_des_cfval`
   - No cambia los totales `{{reg_rn-si-ba_01oct24-max_des}}` ni `{{reg_rn-no-ba_01oct24-max_des_cfval}}`.

3. Antes de generar la presentación se agrega `"msg_fechas_no_cont"` a `vars_ppt` y se comprueba que la plantilla lo haya sustituido.
   - El conteo corresponde a los casos de folio válido de la diapositiva 10 que quedan fuera del gráfico.

## ▶️ Cómo ejecutar los cambios

En VS Code/Jupyter, selecciona **Reiniciar kernel y ejecutar todas las celdas**. No ejecutes únicamente la celda del armado del PowerPoint: las gráficas y el mensaje dependen de las celdas anteriores.

En la salida confirma `📅 Fecha máxima en BANCI: ...` y `Mensaje BANCI: ...`. En los datos actuales el límite es 30 de septiembre de 2026; el gráfico de la diapositiva 10 excluye 479 casos de octubre y 42 de noviembre. Ambos totales deben conservar su valor original. Si la plantilla no sustituye el marcador, el armado se detiene con un error explícito.

## 🔧 Cómo Funciona

### Filtrado Automático de Gráficos

Cuando ejecutas el notebook:

```
📅 Fecha máxima en BANCI: 2026-09-30
```

Los gráficos de slides 9 y 10 se cortarán automáticamente en esa fecha: las filas posteriores se quitan antes del agrupamiento, y no solo del eje.

### Mensaje Dinámico

El mensaje se genera automáticamente y se ve como:

```
No se muestran 479 casos de octubre y 42 correspondientes a noviembre
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

- **Diapositiva 10**: El marcador ya está en la plantilla, junto al gráfico de folio válido.

## 📈 Ejemplo de Resultados

### Antes (datos de todo el período):
```
Gráfico muestra: enero, febrero, marzo, abril, mayo, junio, julio, agosto, 
                 septiembre, octubre, noviembre
```

### Después (solo hasta BANCI):
```
Gráfico muestra: enero, febrero, marzo, abril, mayo, junio, julio, agosto, septiembre

Mensaje: "No se muestran 479 casos de octubre y 42 correspondientes a noviembre
         ya que están por ser verificados con BANCI"
```

## 🔄 Escalabilidad (Cambiar Período)

### Para cambiar de período (ej: de octubre 2024 a enero 2025):

**Opción A: Hacerlo automático**
- Simplemente ejecuta el notebook con datos actualizados
- El código detecta automáticamente el nuevo período

**Opción B: Cambiar manualmente el período**

En la celda nueva de gráficas, cambia el período de las dos `Slice`:

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
```

#### `generar_mensaje_fechas_no_contempladas(s, fecha_limite)`
```python
generar_mensaje_fechas_no_contempladas(
    Slice("rn-no-ba", "01oct24-max", estatus="des", subfiltro="cfval"),
    fecha_limite=pd.Timestamp('2026-09-30')
)
# Retorna: str
# Ejemplo: "No se muestran 479 casos de octubre y 42 correspondientes a noviembre ya que están por ser verificados con BANCI"
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
