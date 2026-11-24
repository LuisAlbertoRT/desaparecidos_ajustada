# EXPORTAR: gráfica de dispersión

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager
from pathlib import Path
import matplotlib.ticker as mticker
from matplotlib.ticker import FuncFormatter
import subprocess

from funciones import (
    limpiar_svg_con_scour,
    formato_fechas,
    get_text_color_for_bg,
    num_decimales,
    elimina_ceros_no_significativos,
    exportar_grafica
)

def dispersion(
    # --- DATOS Y ESTRUCTURA ---
    df,                         # DataFrame de entrada con 2 columnas (eje X, eje Y)
    col_categorias=None,        # Columna para categorizar y colorear los puntos
    asignar_etiquetas=None,     # Columna para etiquetas personalizadas de los puntos

    # --- GRÁFICA GENERAL ---
    nombre="dispersion",        # Nombre base para archivos de salida
    tipo_letra='Montserrat',    # Tipo de letra para todo el texto en la gráfica
    paleta_colores=None,        # Lista de colores para los puntos
    ancho_fig=None,             # Ancho de la figura 
    alto_fig=None,              # Alto de la figura
    grillas=True,               # Mostrar grillas
    fondo='transparent',        # Color de fondo de la figura ('transparent' o 'white')
    decimales=None,             # Número de decimales a mostrar en los valores
    mostrar_fig=True,           # Mostrar la figura
    guardar_fig=True,           # Guardar la figura

    # --- PUNTOS (MARCADORES) ---
    tam_punto=100,              # Tamaño de los puntos en el gráfico
    estilo_punto='o',           # Estilo de los marcadores (puntos)
    alpha_punto=1.0,            # Transparencia de los puntos

    # --- ETIQUETAS DE PUNTOS (CÁPSULAS) ---
    valor_capsu=True,           # Mostrar etiqueta con valor en cada punto
    tam_letra_valor_capsu=12,   # Tamaño de letra para valores en las etiquetas
    weight_valor_capsu='bold',  # Grosor de letra para valores en las etiquetas
    color_valor_capsu='#000000',# Color de letra para valores en las etiquetas
    color_borde_capsu='#002F2A',# Color del borde de la etiqueta
    weight_borde_capsu=1.5,     # Grosor del borde de la etiqueta
    quitar_capsu=False,         # Quitar la etiqueta de valor
    ajusta_pos_capsu=0.0,       # Ajuste vertical de la posición de la etiqueta

    # --- LEYENDA ---
    leyenda=None,               # Título de la leyenda
    pos_leyenda='arriba',       # Posición de la leyenda ('arriba' o 'abajo')
    aumenta_sep_leyenda=0.0,    # Espacio extra para la leyenda
    ncol_leyenda=None,          # Número de columnas en la leyenda
    tam_letra_leyenda=24,       # Tamaño de letra para la leyenda
    weight_letra_leyenda='medium', # Grosor de letra para la leyenda
    color_letra_leyenda='#767676', # Color de letra para la leyenda

    # --- EJE X ---
    tam_letra_ejeX=25,          # Tamaño de letra para etiquetas eje X
    weight_letra_ejeX='medium', # Grosor de letra para etiquetas eje X
    color_letra_ejeX="#000000", # Color de letra para etiquetas eje X
    nombre_eje_x=None,          # Nombre del eje x
    tam_letra_nombre_eje_x=25,  # Tamaño de letra para nombre del eje x
    weight_letra_nombre_eje_x='medium', # Grosor de letra para nombre del eje x
    color_letra_nombre_eje_x='#000000', # Color de letra para nombre del eje x
    orientacion_etiqu_ejeX=None,# Orientación de etiquetas eje x ('horizontal' o 'vertical')
    x_limits=None,              # Límites del eje x

    # --- EJE Y ---
    tam_letra_ejeY=25,          # Tamaño de letra para etiquetas eje Y
    weight_letra_ejeY='medium', # Grosor de letra para etiquetas eje Y
    color_letra_ejeY="#000000", # Color de letra para etiquetas eje Y
    nombre_eje_y=None,          # Nombre del eje y
    tam_letra_nombre_eje_y=22,  # Tamaño de letra para nombre del eje y
    weight_letra_nombre_eje_y='medium', # Grosor de letra para nombre del eje y
    color_letra_nombre_eje_y='#000000', # Color de letra para nombre del eje y
    y_limits=None,              # Límites del eje y
    ejeY_positivo=False,        # Eje Y solo muestra valores positivos
    div_ejeY=False,             # División personalizada del eje y
):
    """
    Genera un gráfico de dispersión personalizable.

    Esta función toma un DataFrame de pandas con dos columnas (para los ejes X e Y)
    y crea un gráfico de dispersión. Permite una amplia personalización que incluye
    colores, tamaño de puntos, etiquetas, leyendas y formato de los ejes.
    """
    # --- 1. CONFIGURACIÓN INICIAL ---
    espacio = "\u00A0"

    # Configuración global de la fuente
    plt.rcParams['font.family'] = tipo_letra

    font_config = {
        'family': tipo_letra,
        'variable_x': {'size': tam_letra_ejeX, 'weight': weight_letra_ejeX, 'color': color_letra_ejeX},
        'variable_y': {'size': tam_letra_ejeY, 'weight': weight_letra_ejeY, 'color': color_letra_ejeY},
        'nombre_eje_x': {'size': tam_letra_nombre_eje_x, 'weight': weight_letra_nombre_eje_x, 'color': color_letra_nombre_eje_x},
        'nombre_eje_y': {'size': tam_letra_nombre_eje_y, 'weight': weight_letra_nombre_eje_y, 'color': color_letra_nombre_eje_y},
        'valor_capsula': {'size': tam_letra_valor_capsu, 'weight': weight_valor_capsu, 'color': color_valor_capsu},
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
    if len(df.columns) < 2:
        raise ValueError("El DataFrame debe tener al menos dos columnas para los ejes X e Y.")

    df = df.copy()
    col_x = df.columns[0]
    col_y = df.columns[1]

    # --- 3. CREACIÓN DE LA GRÁFICA ---
    fig, ax = plt.subplots()
    if ancho_fig and alto_fig:
        fig.set_size_inches(ancho_fig, alto_fig)

    # --- 4. GRAFICAR PUNTOS ---
    if col_categorias and col_categorias in df.columns:
        categorias_unicas = df[col_categorias].unique()
        mapa_color_categoria = {cat: colores_asignados[i % len(colores_asignados)] for i, cat in enumerate(categorias_unicas)}
        
        for i, categoria in enumerate(categorias_unicas):
            df_categoria = df[df[col_categorias] == categoria]
            ax.scatter(df_categoria[col_x], df_categoria[col_y], 
                       s=tam_punto, 
                       color=mapa_color_categoria[categoria], 
                       label=categoria,
                       marker=estilo_punto,
                       edgecolor='none',
                       alpha=alpha_punto, 
                       zorder=3)
        
        if leyenda:
            handles, labels = ax.get_legend_handles_labels()
            ax.legend(handles=handles, labels=labels, title=leyenda,
                      loc='upper center', bbox_to_anchor=(0.5, 1.15 + aumenta_sep_leyenda),
                      ncol=ncol_leyenda or len(categorias_unicas), frameon=False,
                      prop={'family': font_config['family'], 'size': font_config['leyenda']['size'], 'weight': font_config['leyenda']['weight']},
                      labelcolor=font_config['leyenda']['color'])

    else:
        ax.scatter(df[col_x], df[col_y], 
                   s=tam_punto, 
                   color=colores_asignados[0],
                   marker=estilo_punto,
                   edgecolor='none', 
                   alpha=alpha_punto, 
                   zorder=3
                   )

        # --- 5. CONFIGURACIÓN DE EJES Y ESTILO ---
    if fondo != 'transparent':
        ax.set_facecolor(fondo)
        fig.patch.set_facecolor(fondo)
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#B0B0B0')
    ax.spines['bottom'].set_color('#B0B0B0')

    if grillas:
        ax.grid(axis='y', color='#E0E0E0', linestyle='--', linewidth=0.7, zorder=0)
    ax.grid(axis='x', visible=False)

    # Eje Y
    ax.set_ylabel(nombre_eje_y, fontdict={'family': font_config['family'], **font_config['nombre_eje_y']}, labelpad=15)
    ax.tick_params(axis='y', which='major', labelsize=font_config['variable_y']['size'], colors=font_config['variable_y']['color'])
    
    if y_limits:
        ax.set_ylim(y_limits)
    if ejeY_positivo:
        ax.set_ylim(bottom=0)
    if div_ejeY:
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=div_ejeY, integer=True))

    # Eje X
    ax.set_xlabel(nombre_eje_x, fontdict={'family': font_config['family'], **font_config['nombre_eje_x']}, labelpad=15)
    ax.tick_params(axis='x', which='major', labelsize=font_config['variable_x']['size'], colors=font_config['variable_x']['color'], rotation=orientacion_etiqu_ejeX or 0)
    
    if x_limits:
        ax.set_xlim(x_limits)

    # Formato de fechas en eje X si aplica
    if pd.api.types.is_datetime64_any_dtype(df[col_x]):
        fechas_a_formatear = df[col_x]
        mapa_fechas = dict(zip(fechas_a_formatear, formato_fechas(fechas_a_formatear)))
        ax.set_xticklabels([mapa_fechas.get(pd.Timestamp(t), '') for t in ax.get_xticks()])

    plt.tight_layout()

    # --- 6. GUARDAR Y MOSTRAR LA GRÁFICA ---
    if guardar_fig:
        exportar_grafica(nombre, limpiar_svg_con_scour)

    if mostrar_fig:
        plt.show()
    
    plt.close(fig)

    # --- 6. CONFIGURACIÓN DE EJES Y ESTILO ---
    if fondo != 'transparent':
        ax.set_facecolor(fondo)
        fig.patch.set_facecolor(fondo)
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#B0B0B0')
    ax.spines['bottom'].set_color('#B0B0B0')

    if grillas:
        ax.grid(axis='y', color='#E0E0E0', linestyle='--', linewidth=0.7, zorder=0)
    ax.grid(axis='x', visible=False)

    # Eje Y
    ax.set_ylabel(nombre_eje_y, fontdict={'family': font_config['family'], **font_config['nombre_eje_y']}, labelpad=15)
    ax.tick_params(axis='y', which='major', labelsize=font_config['variable_y']['size'], colors=font_config['variable_y']['color'])
    
    if y_limits:
        ax.set_ylim(y_limits)
    if ejeY_positivo:
        ax.set_ylim(bottom=0)
    if div_ejeY:
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=div_ejeY, integer=True))

    # Eje X
    ax.set_xlabel(nombre_eje_x, fontdict={'family': font_config['family'], **font_config['nombre_eje_x']}, labelpad=15)
    ax.tick_params(axis='x', which='major', labelsize=font_config['variable_x']['size'], colors=font_config['variable_x']['color'], rotation=orientacion_etiqu_ejeX or 0)
    
    if x_limits:
        ax.set_xlim(x_limits)

    # Formato de fechas en eje X si aplica
    if pd.api.types.is_datetime64_any_dtype(df[col_x]):
        fechas_a_formatear = df[col_x]
        mapa_fechas = dict(zip(fechas_a_formatear, formato_fechas(fechas_a_formatear)))
        ax.set_xticklabels([mapa_fechas.get(pd.Timestamp(t), '') for t in ax.get_xticks()])

    plt.tight_layout()

    # --- 7. GUARDAR Y MOSTRAR LA GRÁFICA ---
    if guardar_fig:
        ruta_salida_svg = Path(f"../{nombre}.svg")
        plt.savefig(ruta_salida_svg, format='svg', bbox_inches='tight', pad_inches=0.1, transparent=(fondo == 'transparent'))
        #limpiar_svg_con_scour(ruta_salida_svg, ruta_salida_svg)
        #print(f"Gráfica guardada y optimizada en: {ruta_salida_svg}")

    if mostrar_fig:
        plt.show()
    
    plt.close(fig)