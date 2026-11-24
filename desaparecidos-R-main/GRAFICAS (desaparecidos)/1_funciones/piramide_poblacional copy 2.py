# EXPORTAR: gráfica de pirámide poblacional
        
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager
from pathlib import Path
import matplotlib.ticker as mticker
from matplotlib.ticker import FuncFormatter
from matplotlib.patches import Patch
import os

from funciones import limpiar_svg_con_scour, get_text_color_for_bg


def piramide_poblacional(
    # --- DATOS Y ESTRUCTURA ---
    df,                         # DataFrame de entrada con columna de edad y columna de sexo
    columna_edad='Edad',        # Nombre de la columna que contiene las edades
    columna_sexo='Sexo',        # Nombre de la columna que contiene el sexo/género
    ancho_categoria=5,          # Ancho de categoría: agrupa edades en rangos (ej: 5 = 0-4, 5-9, 10-14, etc.)
    etiqueta_izquierda='Hombres',  # Etiqueta para el lado izquierdo de la pirámide
    etiqueta_derecha='Mujeres',    # Etiqueta para el lado derecho de la pirámide
    valor_izquierda=None,       # Valor en columna_sexo para lado izquierdo (si None, usa etiqueta_izquierda)
    valor_derecha=None,         # Valor en columna_sexo para lado derecho (si None, usa etiqueta_derecha)
    edad_max=None,              # Edad máxima para categorías (si None, usa el máximo del df)

    # --- GRÁFICA GENERAL ---
    nombre="piramide_poblacional", # Nombre base para archivos de salida
    tipo_letra='Montserrat',    # Tipo de letra para todo el texto en la gráfica
    ancho_fig=12,               # Ancho de la figura 
    alto_fig=10,                # Alto de la figura
    grillas=True,               # Muestra u oculta las grillas verticales
    fondo='transparent',        # Color de fondo de la figura ('transparent', 'white')

    # --- BARRAS ---
    ancho_barra=0.8,            # Ancho de cada barra
    tam_letra_valor_barra=12,   # Tamaño de letra para valores dentro de las barras
    weight_valor_barra='bold',  # Grosor de letra para valores dentro de las barras
    color_valor_barra=None,     # Color del texto de valor en barra (None = automático)
    tam_letra_porce_barra=10,   # Tamaño de letra para porcentajes dentro de las barras
    weight_porce_barra='medium',# Grosor de letra para porcentajes dentro de las barras
    color_porce_barra=None,     # Color de letra para porcentajes dentro de las barras
    paleta_colores=None,        # Lista de 2 colores [izquierda, derecha]
    valor_barra=False,          # Mostrar valor numérico en la barra
    porce_barra=False,          # Mostrar porcentaje en la barra
    porce_al_lado=True,         # Mostrar porcentaje al lado del valor dentro de la barra

    # --- LEYENDA ---
    mostrar_leyenda=True,       # Mostrar u ocultar la leyenda
    pos_leyenda='arriba',       # Posición de la leyenda ('arriba', 'abajo')
    tam_letra_leyenda=14,       # Tamaño de letra para la leyenda
    weight_letra_leyenda='medium', # Grosor de letra para la leyenda
    color_letra_leyenda='#767676', # Color de letra para la leyenda

    # --- EJE Y (ETIQUETAS DE EDAD) ---
    tam_letra_ejeY=12,          # Tamaño de letra para etiquetas eje Y
    weight_letra_ejeY='medium', # Grosor de letra para etiquetas eje Y
    color_letra_ejeY="#000000", # Color de letra para etiquetas eje Y
    nombre_eje_y='Grupo de edad', # Nombre del eje Y
    tam_letra_nombre_eje_y=14,  # Tamaño de letra para nombre del eje Y
    weight_letra_nombre_eje_y='bold', # Grosor de letra para nombre del eje Y
    color_letra_nombre_eje_y='#000000', # Color de letra para nombre del eje Y
    formato_etiqueta_edad='{inicio}-{fin}',  # Formato para etiquetas de categorías de edad

    # --- EJE X (VALORES) ---
    tam_letra_ejeX=12,          # Tamaño de letra para etiquetas eje X
    weight_letra_ejeX='medium', # Grosor de letra para etiquetas eje X
    color_letra_ejeX="#000000", # Color de letra para etiquetas eje X
    nombre_eje_x='Población',   # Nombre del eje X
    tam_letra_nombre_eje_x=14,  # Tamaño de letra para nombre del eje X
    weight_letra_nombre_eje_x='bold', # Grosor de letra para nombre del eje X
    color_letra_nombre_eje_x='#000000', # Color de letra para nombre del eje X
    x_limits=None,              # Límites del eje X [min, max] (si None, automático)
    mostrar_valores_absolutos=True,  # Mostrar valores absolutos en eje X (sin signo negativo)
    porcentaje_ejeX=False,      # Mostrar porcentaje en lugar de valores absolutos en eje X

    # --- GUARDAR ---
    guardar_fig=True,           # Guardar la figura
    mostrar_fig=True,           # Mostrar la figura
):
    """
    Genera una pirámide poblacional (gráfico de barras horizontales divergentes).

    Esta función toma un DataFrame con datos individuales (cada fila es una persona con su edad y sexo)
    y genera una pirámide poblacional donde las categorías de edad se crean automáticamente según
    el parámetro ancho_categoria.

    Parámetros principales:
    - df: DataFrame con al menos columna de edad y columna de sexo
    - columna_edad: Nombre de la columna con las edades numéricas
    - columna_sexo: Nombre de la columna con el sexo/género
    - ancho_categoria: Ancho de cada grupo de edad. Por ejemplo:
        - Si ancho_categoria=5: 0-4, 5-9, 10-14, 15-19, etc.
        - Si ancho_categoria=10: 0-9, 10-19, 20-29, etc.
    
    Ejemplo de uso:
    ```python
    df = pd.DataFrame({
        'Edad': [23, 45, 12, 67, 34, ...],
        'Sexo': ['Hombre', 'Mujer', 'Hombre', 'Mujer', 'Hombre', ...]
    })
    piramide_poblacional(df, columna_edad='Edad', columna_sexo='Sexo', ancho_categoria=5)
    ```
    """
    
    # --- 1. CONFIGURACIÓN INICIAL ---
    plt.rcParams['svg.fonttype'] = 'none'
    font_dirs = [Path("../0_fonts")]
    font_files = font_manager.findSystemFonts(fontpaths=font_dirs)
    for font_file in font_files:
        font_manager.fontManager.addfont(font_file)
    plt.rc('font', family=tipo_letra)

    # Colores por defecto para la pirámide [izquierda, derecha]
    colores = paleta_colores or ["#4C6A67", "#9B2247"]
    color_izq = colores[0]
    color_der = colores[1] if len(colores) > 1 else colores[0]

    font_config = {
        'family': tipo_letra,
        'variable_y': {'size': tam_letra_ejeY, 'weight': weight_letra_ejeY, 'color': color_letra_ejeY},
        'variable_x': {'size': tam_letra_ejeX, 'weight': weight_letra_ejeX, 'color': color_letra_ejeX},
        'nombre_eje_y': {'size': tam_letra_nombre_eje_y, 'weight': weight_letra_nombre_eje_y, 'color': color_letra_nombre_eje_y},
        'nombre_eje_x': {'size': tam_letra_nombre_eje_x, 'weight': weight_letra_nombre_eje_x, 'color': color_letra_nombre_eje_x},
        'valor_barra': {'size': tam_letra_valor_barra, 'weight': weight_valor_barra, 'color': color_valor_barra},
        'porce_barra': {'size': tam_letra_porce_barra, 'weight': weight_porce_barra, 'color': color_porce_barra},
        'leyenda': {'size': tam_letra_leyenda, 'weight': weight_letra_leyenda, 'color': color_letra_leyenda}
    }

    # --- 2. VALIDACIÓN Y PREPARACIÓN DE DATOS ---
    if not isinstance(df, pd.DataFrame):
        raise ValueError("El argumento df debe ser un DataFrame de pandas.")
    
    if columna_edad not in df.columns:
        raise ValueError(f"La columna '{columna_edad}' no existe en el DataFrame.")
    
    if columna_sexo not in df.columns:
        raise ValueError(f"La columna '{columna_sexo}' no existe en el DataFrame.")
    
    df = df.copy()
    
    # Convertir edades a numérico (maneja strings con punto decimal como "25.0")
    df[columna_edad] = pd.to_numeric(df[columna_edad], errors='coerce')
    df = df.dropna(subset=[columna_edad])
    # Redondear y convertir a entero para manejar valores decimales
    df[columna_edad] = df[columna_edad].round().astype(int)

    # Determinar valores para izquierda y derecha
    val_izq = valor_izquierda if valor_izquierda is not None else etiqueta_izquierda
    val_der = valor_derecha if valor_derecha is not None else etiqueta_derecha

    # --- 3. CREAR CATEGORÍAS DE EDAD ---
    if ancho_categoria is None or ancho_categoria <= 0:
        raise ValueError("ancho_categoria debe ser un número positivo.")
    
    # Determinar el rango de edades
    edad_minima = 0  # Siempre empezamos desde 0
    edad_maxima = edad_max if edad_max is not None else df[columna_edad].max()
    
    # Crear los bins para las categorías
    # Si ancho_categoria=5, queremos: 0-4, 5-9, 10-14, etc.
    # Esto significa bins: [0, 5, 10, 15, ...]
    bins = list(range(0, int(edad_maxima) + ancho_categoria + 1, ancho_categoria))
    
    # Crear etiquetas para las categorías
    etiquetas_categorias = []
    for i in range(len(bins) - 1):
        inicio = bins[i]
        fin = bins[i + 1] - 1
        etiqueta = formato_etiqueta_edad.format(inicio=inicio, fin=fin)
        etiquetas_categorias.append(etiqueta)
    
    # Asignar cada edad a su categoría
    df['categoria_edad'] = pd.cut(
        df[columna_edad], 
        bins=bins, 
        labels=etiquetas_categorias, 
        right=False,  # Intervalo cerrado a la izquierda [inicio, fin)
        include_lowest=True
    )

    # --- 4. CONTAR POBLACIÓN POR CATEGORÍA Y SEXO ---
    # Filtrar por cada grupo
    df_izq = df[df[columna_sexo] == val_izq]
    df_der = df[df[columna_sexo] == val_der]
    
    # Contar por categoría
    conteo_izq = df_izq.groupby('categoria_edad', observed=False).size()
    conteo_der = df_der.groupby('categoria_edad', observed=False).size()
    
    # Crear DataFrame resumen
    df_piramide = pd.DataFrame({
        'categoria': etiquetas_categorias,
        'izquierda': [conteo_izq.get(cat, 0) for cat in etiquetas_categorias],
        'derecha': [conteo_der.get(cat, 0) for cat in etiquetas_categorias]
    })
    
    # Calcular totales para porcentajes
    total_general = df_piramide['izquierda'].sum() + df_piramide['derecha'].sum()
    total_izq = df_piramide['izquierda'].sum()
    total_der = df_piramide['derecha'].sum()

    # --- 5. CREAR LA FIGURA ---
    fig, ax = plt.subplots(figsize=(ancho_fig, alto_fig), dpi=300)

    if fondo == 'transparent':
        fig.patch.set_alpha(0)
        ax.patch.set_alpha(0)
    else:
        fig.patch.set_facecolor(fondo)
        ax.patch.set_facecolor(fondo)

    # --- 6. DIBUJAR LAS BARRAS ---
    posiciones = np.arange(len(df_piramide))
    
    # Barras izquierda (valores negativos para que vayan hacia la izquierda)
    valores_izq = -df_piramide['izquierda'].values  # Negativo para ir a la izquierda
    valores_der = df_piramide['derecha'].values
    
    barras_izq = ax.barh(posiciones, valores_izq, height=ancho_barra, color=color_izq, 
                         label=etiqueta_izquierda, zorder=2)
    barras_der = ax.barh(posiciones, valores_der, height=ancho_barra, color=color_der, 
                         label=etiqueta_derecha, zorder=2)

    # --- 7. AÑADIR TEXTO EN LAS BARRAS (si está habilitado) ---
    if valor_barra or porce_barra:
        for i, (val_i, val_d) in enumerate(zip(df_piramide['izquierda'], df_piramide['derecha'])):
            # Textos para lado izquierdo
            if val_i > 0:
                texto_izq = ""
                if valor_barra:
                    texto_izq += f"{val_i:,}"
                if porce_barra:
                    porce = (val_i / total_general) * 100 if total_general > 0 else 0
                    if porce_al_lado and valor_barra:
                        texto_izq += f" ({porce:.1f}%)"
                    elif not valor_barra:
                        texto_izq = f"{porce:.1f}%"
                    else:
                        texto_izq += f"\n{porce:.1f}%"
                
                color_texto = color_valor_barra or get_text_color_for_bg(color_izq)
                ax.text(-val_i/2, i, texto_izq, ha='center', va='center',
                       fontsize=font_config['valor_barra']['size'],
                       fontweight=font_config['valor_barra']['weight'],
                       color=color_texto, fontfamily=tipo_letra)
            
            # Textos para lado derecho
            if val_d > 0:
                texto_der = ""
                if valor_barra:
                    texto_der += f"{val_d:,}"
                if porce_barra:
                    porce = (val_d / total_general) * 100 if total_general > 0 else 0
                    if porce_al_lado and valor_barra:
                        texto_der += f" ({porce:.1f}%)"
                    elif not valor_barra:
                        texto_der = f"{porce:.1f}%"
                    else:
                        texto_der += f"\n{porce:.1f}%"
                
                color_texto = color_valor_barra or get_text_color_for_bg(color_der)
                ax.text(val_d/2, i, texto_der, ha='center', va='center',
                       fontsize=font_config['valor_barra']['size'],
                       fontweight=font_config['valor_barra']['weight'],
                       color=color_texto, fontfamily=tipo_letra)

    # --- 8. CONFIGURAR EJES ---
    # Eje Y (categorías de edad)
    ax.set_yticks(posiciones)
    ax.set_yticklabels(df_piramide['categoria'], 
                       fontsize=font_config['variable_y']['size'],
                       fontweight=font_config['variable_y']['weight'],
                       color=font_config['variable_y']['color'],
                       fontfamily=tipo_letra)
    
    if nombre_eje_y:
        ax.set_ylabel(nombre_eje_y, 
                     fontsize=font_config['nombre_eje_y']['size'],
                     fontweight=font_config['nombre_eje_y']['weight'],
                     color=font_config['nombre_eje_y']['color'],
                     fontfamily=tipo_letra)

    # Eje X
    if x_limits:
        ax.set_xlim(x_limits)
    else:
        max_val = max(df_piramide['izquierda'].max(), df_piramide['derecha'].max()) * 1.15
        ax.set_xlim(-max_val, max_val)

    # Formatear etiquetas del eje X
    if mostrar_valores_absolutos:
        def formato_absoluto(x, pos):
            valor = abs(int(x))
            if porcentaje_ejeX:
                porce = (valor / total_general) * 100 if total_general > 0 else 0
                return f"{porce:.1f}%"
            return f"{valor:,}"
        ax.xaxis.set_major_formatter(FuncFormatter(formato_absoluto))
    
    ax.tick_params(axis='x', 
                   labelsize=font_config['variable_x']['size'],
                   labelcolor=font_config['variable_x']['color'])
    
    if nombre_eje_x:
        ax.set_xlabel(nombre_eje_x,
                     fontsize=font_config['nombre_eje_x']['size'],
                     fontweight=font_config['nombre_eje_x']['weight'],
                     color=font_config['nombre_eje_x']['color'],
                     fontfamily=tipo_letra)

    # --- 9. GRILLAS ---
    if grillas:
        ax.xaxis.grid(True, linestyle='--', alpha=0.7, zorder=0)
        ax.set_axisbelow(True)
    
    # Línea central en x=0
    ax.axvline(x=0, color='black', linewidth=0.8, zorder=1)

    # --- 10. LEYENDA ---
    if mostrar_leyenda:
        handles = [
            Patch(facecolor=color_izq, label=etiqueta_izquierda),
            Patch(facecolor=color_der, label=etiqueta_derecha)
        ]
        
        if pos_leyenda == 'arriba':
            loc = 'upper center'
            bbox = (0.5, 1.05)
        else:
            loc = 'lower center'
            bbox = (0.5, -0.1)
        
        legend = ax.legend(handles=handles, loc=loc, bbox_to_anchor=bbox, ncol=2,
                          fontsize=font_config['leyenda']['size'],
                          frameon=False)
        for text in legend.get_texts():
            text.set_fontweight(font_config['leyenda']['weight'])
            text.set_color(font_config['leyenda']['color'])

    # Remover bordes superiores y derechos
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # --- 11. GUARDADO Y VISUALIZACIÓN ---
    if guardar_fig:
        os.makedirs("output", exist_ok=True)
        plt.tight_layout()
        
        base_path = f"output/{nombre}"
        original_svg_path = f"{base_path}.svg"
        scour_svg_path = f"{base_path}_scour.svg"
        plt.savefig(original_svg_path, format='svg', bbox_inches='tight', dpi=300, 
                   transparent=(fondo == 'transparent'))
        plt.savefig(f"{base_path}.png", format='png', bbox_inches='tight', dpi=300, 
                   transparent=(fondo == 'transparent'))

        try:
            limpiar_svg_con_scour(original_svg_path, scour_svg_path)
            os.remove(original_svg_path)
        except Exception as e:
            print(f"Error al optimizar o eliminar el SVG: {e}")

    if mostrar_fig:
        plt.show()
    
    return fig, ax, df_piramide