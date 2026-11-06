# ✅ Checklist de Verificación

## 🔍 Verificación Rápida Post-Implementación

Utiliza este checklist para verificar que todo está funcionando correctamente.

### Fase 1: Verificación del Código ✓

- [ ] **Notebook modificado correctamente**
  ```bash
  grep -c "def fecha_max_banci()" ./notebooks\ luis/6_PPT_Reporte_Diario.ipynb
  # Debe retornar: 1
  ```

- [ ] **Todas las funciones presentes**
  ```bash
  grep -c "def serie_mensual_hasta_banci(" ./notebooks\ luis/6_PPT_Reporte_Diario.ipynb
  # Debe retornar: 1
  
  grep -c "def generar_mensaje_fechas_no_contempladas(" ./notebooks\ luis/6_PPT_Reporte_Diario.ipynb
  # Debe retornar: 1
  ```

- [ ] **Gráficos modificados**
  ```bash
  grep -c "serie_mensual_hasta_banci(" ./notebooks\ luis/6_PPT_Reporte_Diario.ipynb
  # Debe retornar: 2 (uno para cfval, otro para sfval)
  ```

- [ ] **Variable de plantilla agregada**
  ```bash
  grep -c "msg_fechas_no_cont" ./notebooks\ luis/6_PPT_Reporte_Diario.ipynb
  # Debe retornar: 1
  ```

### Fase 2: Ejecución del Notebook

- [ ] **Ejecutar notebook sin errores**
  - Abre Jupyter Notebook
  - Ejecuta `./notebooks luis/6_PPT_Reporte_Diario.ipynb`
  - Verifica que no haya errores en la salida

- [ ] **Verificar fecha BANCI en salida**
  - Busca en la salida: `📅 Fecha máxima en BANCI:`
  - Debe mostrar una fecha válida: `2026-09-30` (o la actual)
  - Si sale vacío o error, revisa los datos de BANCI

### Fase 3: Verificación de Gráficos

- [ ] **Gráfico Slide 9 (cfval) se corta correctamente**
  - El gráfico debe mostrar datos desde octubre 2024 hasta septiembre 2026
  - No debe haber datos de octubre o noviembre 2026
  - La última barra debe ser septiembre 2026

- [ ] **Gráfico Slide 10 (sfval) se corta correctamente**
  - El gráfico debe mostrar datos desde octubre 2024 hasta septiembre 2026
  - No debe haber datos de octubre o noviembre 2026
  - La última barra debe ser septiembre 2026

### Fase 4: Verificación de Mensaje

- [ ] **Mensaje se genera correctamente**
  - En la salida del notebook, verifica: `msg_fechas_no_cont`
  - Debe contener texto como: `"No se muestran X casos de octubre y Y de noviembre..."`

- [ ] **Formato del mensaje es correcto**
  - Comienza con: "No se muestran"
  - Contiene: números formateados con comas (1,234)
  - Contiene: nombres de meses en español (octubre, noviembre, etc.)
  - Termina con: "ya que están por ser verificados con BANCI"

- [ ] **Mensaje se reemplaza en PowerPoint**
  - Genera la presentación
  - En Slide 10, verifica que `{{msg_fechas_no_cont}}` sea reemplazado
  - El mensaje debe aparecer en lugar del marcador

### Fase 5: Verificación de Escalabilidad

- [ ] **Cambiar período de prueba**
  - Edita celda 6: cambia `"01oct24-max"` a `"01ene25-max"`
  - Ejecuta el notebook
  - Verifica que la fecha máxima se actualice
  - Verifica que los gráficos muestren el nuevo período

### Fase 6: Pruebas de Casos Especiales

- [ ] **Sin meses sin verificar**
  - Si BANCI reporta hasta la última fecha del período
  - El mensaje debe estar vacío
  - Los gráficos deben verse igual

- [ ] **Con muchos meses sin verificar**
  - Si hay 3+ meses sin verificar
  - El mensaje debe listarlos separados por "y"
  - Ejemplo: "X de enero y Y de febrero y Z de marzo..."

- [ ] **Datos faltantes**
  - Si faltan registros en algún mes
  - El notebook no debe fallar
  - Los gráficos deben mostrar ceros para ese mes

---

## 🐛 Troubleshooting Común

### Problema: "📅 Fecha máxima en BANCI: None"
**Causa**: BANCI no tiene datos o la columna no existe
**Solución**:
1. Verifica que `fha_de_hchos_derivada_banci` existe en los datos
2. Revisa que `reg_rn-si-ba_01oct24-max_des` esté cargado
3. Consulta la documentación de BANCI

### Problema: El gráfico no se corta
**Causa**: La fecha máxima se detectó pero no se aplicó
**Solución**:
1. Verifica que estés usando `serie_mensual_hasta_banci()` y no `serie_mensual()`
2. Revisa la salida: `print(tabla)` debe mostrar solo hasta BANCI
3. Regenera el gráfico forzando recálculo

### Problema: El mensaje aparece vacío en PowerPoint
**Causa**: No hay meses sin verificar, o la variable no se pasa
**Solución**:
1. Verifica si hay datos después de la fecha de BANCI
2. Revisa que `msg_fechas_no_cont` esté en `vars_ppt`
3. Asegúrate de que `{{msg_fechas_no_cont}}` existe en la plantilla

### Problema: Error "KeyError: 'fha_de_hchos_derivada_banci'"
**Causa**: El dataset no tiene esa columna
**Solución**:
1. Revisa que `derivadas.py` agregó esa columna
2. Ejecuta el ETL completo antes del notebook de gráficos
3. Verifica que BANCI esté siendo procesado correctamente

---

## 📊 Salida Esperada

### En el Notebook:
```
📅 Fecha máxima en BANCI: 2026-09-30
  📊 gr_mes_rn-no-ba_01oct24-max_des_cfval: 24,567 registros en 12 filas
  📊 gr_mes_rn-no-ba_01oct24-max_des_sfval: 54,321 registros en 12 filas
```

### En los Gráficos (PNG):
- Eje X: 12 meses (oct 2024 - sep 2026)
- Última barra: septiembre 2026
- Sin datos de octubre/noviembre 2026

### En PowerPoint:
**Slide 10:**
```
[Gráfico de sfval corto hasta septiembre 2026]

No se muestran 2,456 casos de octubre y 1,234 correspondientes 
a noviembre ya que están por ser verificados con BANCI
```

---

## ✨ Criterios de Aceptación

✅ **Gráficos de Slide 9 y 10 se cortan automáticamente en fecha BANCI**
✅ **Mensaje dinámico {{msg_fechas_no_cont}} aparece en Slide 10**
✅ **Mensaje contiene meses sin verificar con conteo de casos**
✅ **Formato: "No se muestran X casos de MES y Y casos de MES..."**
✅ **Funciona en español con números formateados**
✅ **Escalable para cualquier período (1 año o más)**
✅ **Se ejecuta sin errores cada vez que corre el notebook**
✅ **Documentación completa incluida**

---

## 📞 Soporte

Si encuentras algún problema no listado aquí:

1. Consulta `INSTRUCCIONES_CAMBIOS_SLIDES_9_10.md`
2. Revisa `CODIGO_AGREGADO.md` para detalles técnicos
3. Verifica `DIAGRAMA_FLUJO.txt` para entender el flujo
4. Contacta al equipo de desarrollo

