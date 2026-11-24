# EXPORTAR: gráfica de barras horizontales
        
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager
from pathlib import Path
import matplotlib.ticker as mticker
from matplotlib.ticker import FuncFormatter
from statistics import mode
import subprocess
from matplotlib.patches import Patch
import os

from funciones import limpiar_svg_con_scour, formato_fechas, get_text_color_for_bg, unir_barras 


def piramide_poblacional(
    # --- DATOS Y ESTRUCTURA ---
    df,                         # DataFrame de entrada
    ancho_categoria=None,       # NUEVO: Ancho de categoría para pirámide poblacional


    # --- GRÁFICA GENERAL ---
    nombre="barras_verticales", # Nombre base para archivos de salida
    tipo_letra='Montserrat',    # Tipo de letra para todo el texto en la gráfica
    ancho_fig=None,             # Ancho de la figura 
    alto_fig=None,              # Alto de la figura
    grillas=True,               # Muestra u oculta las grillas horizontales
    fondo='transparent',        # Color de fondo de la figura ('transparent', 'white')

    # --- BARRAS ---
    ancho_barra=0.85,            # Ancho de cada barra
    tam_letra_valor_barra=20,   # Tamaño de letra para valores dentro de las barras
    weight_valor_barra='bold',  # Grosor de letra para valores dentro de las barras
    color_valor_barra=None,     # Color del texto de valor en barra
    tam_letra_porce_barra=15,   # Tamaño de letra para porcentajes dentro de las barras
    weight_porce_barra='bold',  # Grosor de letra para porcentajes dentro de las barras
    color_porce_barra=None,     # Color de letra para porcentajes dentro de las barras
    paleta_colores=None,        # Lista de colores para las barras
    valor_barra=True,           # Mostrar valor numérico en la barra
    porce_barra=True,           # Mostrar porcentaje en la barra
    porce_al_lado=True,         # Mostrar porcentaje al lado del valor dentro de la barra
    porce_diver=False,          # Porcentaje respecto a suma absoluta (divergente)
    alinea_texto_barra=False,   # Alinear el texto dentro de la barra horizontalmente


    # --- LEYENDA ---
    leyenda=None,               # Título de la leyenda
    pos_leyenda='arriba',       # Posición de la leyenda ('arriba', 'abajo')
    aumenta_sep_leyenda=0.0,    # Espacio extra para la leyenda
    ncol_leyenda=None,          # Número de columnas en la leyenda
    tam_letra_leyenda=24,       # Tamaño de letra para la leyenda
    weight_letra_leyenda='medium', # Grosor de letra para la leyenda
    color_letra_leyenda='#767676', # Color de letra para la leyenda

    # --- EJE Y (ETIQUETAS) ---
    tam_letra_ejeY=35,          # Tamaño de letra para etiquetas eje Y
    weight_letra_ejeY='medium', # Grosor de letra para etiquetas eje Y
    color_letra_ejeY="#000000", # Color de letra para etiquetas eje Y
    espacio_inicio=0,           # Espacio extra al inicio del eje Y
    nombre_eje_y=None,          # Nombre del eje Y
    tam_letra_nombre_eje_y=25,  # Tamaño de letra para nombre del eje Y
    weight_letra_nombre_eje_y='medium', # Grosor de letra para nombre del eje Y
    color_letra_nombre_eje_y='#000000', # Color de letra para nombre del eje Y
    sustituir_etiquetas=None,   # Lista para sustituir etiquetas del eje Y
    orientacion_etiqu_ejeY=None,# Orientación de etiquetas eje Y ('vertical' o None)
    aumenta_sep_eje_y=0.0,      # Aumenta separación en eje Y
    resaltar_etiquetas=None,    # Lista de etiquetas a resaltar
    color_resalt_etique="#a3173e", # Color para el resaltado de etiquetas
    color_borde_resalt='none',  # Color del borde de resaltado de etiquetas
    ejeY_der=False,             # Colocar el eje Y a la derecha

    # --- EJE X (VALORES) ---
    tam_letra_ejeX=30,          # Tamaño de letra para etiquetas eje X
    weight_letra_ejeX='medium', # Grosor de letra para etiquetas eje X
    color_letra_ejeX="#000000", # Color de letra para etiquetas eje X
    nombre_eje_x=None,          # Nombre del eje X
    tam_letra_nombre_eje_x=22,  # Tamaño de letra para nombre del eje X
    weight_letra_nombre_eje_x='medium', # Grosor de letra para nombre del eje X
    color_letra_nombre_eje_x='#000000', # Color de letra para nombre del eje X
    x_limits=None,              # Límites del eje X
    ejeX_positivo=False,        # Eje X solo muestra valores positivos
    porcentaje_ejeX=False,      # Añade el símbolo de porcentaje a los números del eje X
    div_ejeX=False,             # División personalizada del eje X
    graf_resp_porce=False,      # Graficar con respecto al porcentaje en el eje X


):
    """
    Genera un gráfico de barras horizontales apiladas, personalizable y con múltiples opciones de formato.

    Esta función toma un DataFrame de pandas y crea un gráfico de barras horizontales. Permite una amplia
    personalización que incluye el orden de las barras, colores, etiquetas, leyendas, y la capacidad
    de agregar datos adicionales o resaltar barras específicas. Está diseñada para ser flexible y
    cubrir una variedad de casos de uso para la visualización de datos.
    """
    # --- 1. CONFIGURACIÓN INICIAL ---
    hay_annotations_externas = False
    espacio = "\u00A0"

    font_config = {
        'family': tipo_letra,
        'variable_y': {'size': tam_letra_ejeY, 'weight': weight_letra_ejeY, 'color': color_letra_ejeY},
        'variable_x': {'size': tam_letra_ejeX, 'weight': weight_letra_ejeX, 'color': color_letra_ejeX},
        'nombre_eje_y': {'size': tam_letra_nombre_eje_y, 'weight': weight_letra_nombre_eje_y, 'color': color_letra_nombre_eje_y},
        'nombre_eje_x': {'size': tam_letra_nombre_eje_x, 'weight': weight_letra_nombre_eje_x, 'color': color_letra_nombre_eje_x},
        'valor_capsula': {'size': tam_letra_valor_capsu, 'weight': weight_valor_capsu, 'color': color_valor_capsu},
        'valor_porcentaje_barra': {'size': tam_letra_valor_barra, 'weight': weight_valor_barra, 'color': color_valor_barra},
        'valor_porcentaje_barra_porcentaje': {'size': tam_letra_porce_barra, 'weight': weight_porce_barra, 'color': color_porce_barra},
        'porcentaje_total': {'size': tam_porce_total, 'weight': weight_porce_total, 'color': color_porce_total},
        'leyenda': {'size': tam_letra_leyenda, 'weight': weight_letra_leyenda, 'color': color_letra_leyenda}
    }

    plt.rcParams['svg.fonttype'] = 'none'
    font_dirs = [Path("../0_fonts")]
    font_files = font_manager.findSystemFonts(fontpaths=font_dirs)
    for font_file in font_files:
        font_manager.fontManager.addfont(font_file)

    colores_asignados = paleta_colores or ["#10302C", "#4C6A67", "#8FA8A6", "#A3C9A8"]

    # --- 2. PREPARACIÓN DE DATOS ---
    if not isinstance(df, pd.DataFrame):
        raise ValueError("El argumento df debe ser un DataFrame de pandas.")
    
    df = df.copy()














    # --- 9. GUARDADO Y VISUALIZACIÓN ---
    os.makedirs("output", exist_ok=True)
    plt.tight_layout()
    
    base_path = f"output/{nombre}"
    original_svg_path = f"{base_path}.svg"
    scour_svg_path = f"{base_path}_scour.svg"
    plt.savefig(original_svg_path, format='svg', bbox_inches='tight', dpi=300, transparent=(fondo == 'transparent'))
    plt.savefig(f"{base_path}.png", format='png', bbox_inches='tight', dpi=300, transparent=(fondo == 'transparent'))

    try:
        limpiar_svg_con_scour(original_svg_path, scour_svg_path)
        os.remove(original_svg_path)
    except Exception as e:
        print(f"Error al optimizar o eliminar el SVG: {e}")

    plt.show()