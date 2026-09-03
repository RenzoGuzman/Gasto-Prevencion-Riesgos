"""
Dashboard de semaforizacion del gasto en prevencion de riesgos de desastres (PP 0068)
con filtro por zonas de influencia de las empresas de Breca.

TODO EN UN SOLO ARCHIVO:
  - Si no existe 'pp0068_diaria.csv', lo genera filtrando el CSV gigante (una vez).
  - Si ya existe, lo usa directo (arranque rapido).

COMO CORRERLO EN TU PC:
  1. py -m pip install --user streamlit pandas plotly requests
  2. En la MISMA carpeta: este script, breca_zonas.csv, y (la 1ra vez) 2026-Gasto-Diario.csv
  3. py -m streamlit run dashboard_prevencion.py
"""

import os
from datetime import datetime
import unicodedata
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Prevencion de riesgos - PP 0068", layout="wide")

# ----------------------------------------------------------------------
# Tema visual (estilo elegante: mono para titulos, tarjetas suaves)
# ----------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap');

    /* Fondo general y tipografia base */
    .stApp { background-color: #FBFBFA; }
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #1A1A1A; }

    /* Titulo principal y subtitulos en monoespaciada */
    h1, h2, h3 { font-family: 'IBM Plex Mono', monospace !important; letter-spacing: -0.5px; color: #14181F; }
    h1 { font-weight: 600 !important; font-size: 1.9rem !important; line-height: 1.15 !important; }

    /* Subheaders (secciones) como 'eyebrow': mayusculas, tracking, gris */
    [data-testid="stHeading"] h2, [data-testid="stHeading"] h3 {
        text-transform: uppercase;
        letter-spacing: 2px;
        font-size: 0.95rem !important;
        color: #5B6470 !important;
        font-weight: 600 !important;
    }

    /* Metricas (indicadores) mas grandes y limpias */
    [data-testid="stMetricValue"] { font-family: 'IBM Plex Mono', monospace; font-weight: 600; color: #14181F; font-size: 1.5rem !important; }
    [data-testid="stMetricLabel"] { text-transform: uppercase; letter-spacing: 1px; color: #5B6470; font-size: 0.8rem; }

    /* Barra lateral con fondo tenue y borde */
    [data-testid="stSidebar"] { background-color: #F4F4F2; border-right: 1px solid #E5E5E1; }
    [data-testid="stSidebar"] h2 { letter-spacing: 2px; }

    /* Tablas: bordes suaves */
    [data-testid="stDataFrame"] { border: 1px solid #E5E5E1; border-radius: 10px; overflow: hidden; }

    /* Divisores mas sutiles */
    hr { border-color: #E9E9E5 !important; }

    /* Ajuste de texto (wrap) en celdas */
    [data-testid="stDataFrame"] div[role="gridcell"] { white-space: normal !important; line-height: 1.3 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


ARCHIVO_GIGANTE = "2026-Gasto-Diario.csv"
ARCHIVO_FILTRADO = "pp0068_compacto.csv"
ARCHIVO_BRECA = "breca_zonas.csv"
GEOJSON_URL = "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_departamental_simple.geojson"

COLUMNAS = [
    "ANO_EJE", "MES_EJE", "NIVEL_GOBIERNO_NOMBRE",
    "SECTOR_NOMBRE", "PLIEGO_NOMBRE", "EJECUTORA_NOMBRE",
    "DEPARTAMENTO_EJECUTORA_NOMBRE", "PROVINCIA_EJECUTORA_NOMBRE",
    "DISTRITO_EJECUTORA_NOMBRE",
    "PROGRAMA_PPTO", "PROGRAMA_PPTO_NOMBRE",
    "PRODUCTO_PROYECTO", "PRODUCTO_PROYECTO_NOMBRE",
    "ACTIVIDAD_ACCION_OBRA_NOMBRE", "FUNCION_NOMBRE",
    "MONTO_PIA", "MONTO_PIM", "MONTO_CERTIFICADO",
    "MONTO_COMPROMETIDO", "MONTO_DEVENGADO", "MONTO_GIRADO",
]
MONTOS = ["MONTO_PIA", "MONTO_PIM", "MONTO_CERTIFICADO",
          "MONTO_COMPROMETIDO", "MONTO_DEVENGADO", "MONTO_GIRADO"]

# Proyectos a excluir del Top 10 (comparacion normalizada)
PROY_EXCLUIR = {"ACCIONES COMUNES",
                "ESTUDIOS PARA LA ESTIMACION DEL RIESGO DE DESASTRES"}


def normalizar(texto):
    if pd.isna(texto):
        return ""
    t = str(texto).strip().upper()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.split())


def soles(m):
    return f"S/ {m:,.0f}"

def mostrar_tabla(dataframe, columnas_texto_ancho=None, anchos=None):
    """Muestra un dataframe con ajuste de texto (wrap) en columnas de texto.
    - columnas_texto_ancho: lista de columnas de texto (se les da ancho 'medium').
    - anchos: dict opcional {columna: 'small'|'medium'|'large'} para control fino.
    Todas las columnas caben por defecto; el usuario puede arrastrar el borde de
    cualquier columna para agrandarla manualmente."""
    columnas_texto_ancho = columnas_texto_ancho or []
    anchos = anchos or {}
    config = {}
    for col in columnas_texto_ancho:
        if col in dataframe.columns:
            config[col] = st.column_config.TextColumn(width="medium")
    for col, w in anchos.items():
        if col in dataframe.columns:
            config[col] = st.column_config.TextColumn(width=w)
    st.dataframe(dataframe, use_container_width=True, hide_index=True,
                 column_config=config)


# CSS que fuerza el ajuste de texto (wrap) en las celdas de las tablas.
st.markdown(
    """
    <style>
    /* Ajuste de texto en celdas de st.dataframe */
    [data-testid="stDataFrame"] div[role="gridcell"] {
        white-space: normal !important;
        line-height: 1.3 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def generar_filtrado():
    trozos = []
    barra = st.progress(0, text="Procesando el archivo gigante por primera vez...")
    lector = pd.read_csv(ARCHIVO_GIGANTE, encoding="latin-1", sep=",", quotechar='"',
                         usecols=COLUMNAS, dtype=str, chunksize=200_000)
    for i, trozo in enumerate(lector, 1):
        trozo["PROGRAMA_PPTO"] = trozo["PROGRAMA_PPTO"].str.strip().str.zfill(4)
        f = trozo[trozo["PROGRAMA_PPTO"] == "0068"]
        if len(f):
            trozos.append(f)
        barra.progress(min(0.95, i / 40), text=f"Bloque {i} procesado...")
    barra.progress(1.0, text="Guardando archivo filtrado...")
    df68 = pd.concat(trozos, ignore_index=True)
    for col in MONTOS:
        df68[col] = pd.to_numeric(df68[col], errors="coerce").fillna(0)
    df68.to_csv(ARCHIVO_FILTRADO, index=False, encoding="utf-8-sig")
    barra.empty()
    return df68


@st.cache_data
def cargar_datos():
    if not os.path.exists(ARCHIVO_FILTRADO):
        return None
    df = pd.read_csv(ARCHIVO_FILTRADO, encoding="utf-8-sig", dtype=str)
    for col in MONTOS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["_DEP"] = df["DEPARTAMENTO_EJECUTORA_NOMBRE"].apply(normalizar)
    df["_PROV"] = df["PROVINCIA_EJECUTORA_NOMBRE"].apply(normalizar)
    df["_DIST"] = df["DISTRITO_EJECUTORA_NOMBRE"].apply(normalizar)
    return df


@st.cache_data
def cargar_breca():
    b = pd.read_csv(ARCHIVO_BRECA, encoding="utf-8", dtype=str).fillna("")
    b["_DEP"] = b["REGION"].apply(normalizar)
    b["_PROV"] = b["PROVINCIA"].apply(normalizar)
    b["_DIST"] = b["DISTRITO"].apply(normalizar)
    return b


@st.cache_data
def cargar_geojson():
    import json
    gj = None
    # 1) Intentar archivo LOCAL primero (no depende de internet)
    for nombre in ["peru_departamental.geojson", "peru_departamental_simple.geojson"]:
        if os.path.exists(nombre):
            try:
                with open(nombre, "r", encoding="utf-8") as f:
                    gj = json.load(f)
                break
            except Exception:
                gj = None
    # 2) Si no hay local, intentar descargar
    if gj is None:
        try:
            import requests
            r = requests.get(GEOJSON_URL, timeout=20)
            r.raise_for_status()
            gj = r.json()
        except Exception:
            return None
    # Detectar la clave del nombre de departamento y normalizar
    try:
        props = gj["features"][0]["properties"]
        clave = None
        for cand in ["NOMBDEP", "departamen", "DEPARTAMEN", "name", "NAME"]:
            if cand in props:
                clave = cand
                break
        for feat in gj["features"]:
            feat["properties"]["_DEP"] = normalizar(feat["properties"].get(clave, ""))
        return gj
    except Exception:
        return None


df = cargar_datos()

# Rellenar PLIEGO_NOMBRE vacio (tipico en Gobiernos Locales) con "MUNICIPALIDAD DE [DISTRITO]"
if df is not None and "PLIEGO_NOMBRE" in df.columns:
    _sin_pliego = df["PLIEGO_NOMBRE"].isna() | (df["PLIEGO_NOMBRE"].astype(str).str.strip() == "")
    _dist_up = df.loc[_sin_pliego, "DISTRITO_EJECUTORA_NOMBRE"].astype(str).str.strip().str.upper()
    df.loc[_sin_pliego, "PLIEGO_NOMBRE"] = "MUNICIPALIDAD DE " + _dist_up
    # Caso especial: el distrito de Lima se agrupa con la categoria ya existente
    _es_lima = _sin_pliego & (df["DISTRITO_EJECUTORA_NOMBRE"].astype(str).str.strip().str.upper() == "LIMA")
    df.loc[_es_lima, "PLIEGO_NOMBRE"] = "MUNICIPALIDAD METROPOLITANA DE LIMA"
    # Expandir abreviatura "M. " a "MINISTERIO " en los nombres de pliego
    df["PLIEGO_NOMBRE"] = df["PLIEGO_NOMBRE"].astype(str).str.replace(
        r"^M\.\s+", "MINISTERIO ", regex=True)
if df is None:
    st.error(f"No encontre '{ARCHIVO_FILTRADO}'. Debe estar junto al script.")
    st.stop()
try:
    breca = cargar_breca()
except FileNotFoundError:
    st.error(f"No encontre '{ARCHIVO_BRECA}'. Debe estar en la misma carpeta.")
    st.stop()


st.sidebar.header("Filtros")
empresas = sorted(breca["EMPRESA"].unique().tolist())
opciones = ["Todo el gasto (sin filtrar por zona)", "Todas las empresas Breca"] + empresas
seleccion = st.sidebar.selectbox("Zona de influencia", opciones)

df["_KEY"] = list(zip(df["_DEP"], df["_PROV"], df["_DIST"]))

def claves_de(sub):
    return set(zip(sub["_DEP"], sub["_PROV"], sub["_DIST"]))

if seleccion == "Todo el gasto (sin filtrar por zona)":
    df_f = df.copy(); zona = None
elif seleccion == "Todas las empresas Breca":
    df_f = df[df["_KEY"].isin(claves_de(breca))].copy(); zona = "Todas las empresas Breca"
else:
    sub = breca[breca["EMPRESA"] == seleccion]
    df_f = df[df["_KEY"].isin(claves_de(sub))].copy(); zona = seleccion

# --- Filtros geograficos encadenados (Departamento -> Provincia -> Distrito) ---
TODOS = "Todos"

deps = [TODOS] + sorted(d for d in df_f["DEPARTAMENTO_EJECUTORA_NOMBRE"].dropna().unique() if str(d).strip())
dep_sel = st.sidebar.selectbox("Departamento", deps)
if dep_sel != TODOS:
    df_f = df_f[df_f["DEPARTAMENTO_EJECUTORA_NOMBRE"] == dep_sel]

provs = [TODOS] + sorted(p for p in df_f["PROVINCIA_EJECUTORA_NOMBRE"].dropna().unique() if str(p).strip())
prov_sel = st.sidebar.selectbox("Provincia", provs)
if prov_sel != TODOS:
    df_f = df_f[df_f["PROVINCIA_EJECUTORA_NOMBRE"] == prov_sel]

dists = [TODOS] + sorted(d for d in df_f["DISTRITO_EJECUTORA_NOMBRE"].dropna().unique() if str(d).strip())
dist_sel = st.sidebar.selectbox("Distrito", dists)
if dist_sel != TODOS:
    df_f = df_f[df_f["DISTRITO_EJECUTORA_NOMBRE"] == dist_sel]

# Filtro por nivel de gobierno
if "NIVEL_GOBIERNO_NOMBRE" in df_f.columns:
    niveles = [TODOS] + sorted(n for n in df_f["NIVEL_GOBIERNO_NOMBRE"].dropna().unique() if str(n).strip())
    nivel_sel = st.sidebar.selectbox("Nivel de gobierno", niveles)
    if nivel_sel != TODOS:
        df_f = df_f[df_f["NIVEL_GOBIERNO_NOMBRE"] == nivel_sel]


st.title("Gasto en prevencion de riesgos de desastres")
st.caption("Programa Presupuestal 0068 - Reduccion de vulnerabilidad y atencion de emergencias por desastres")

# --- Fecha de actualizacion de los datos ---
def fecha_datos():
    """Fecha de la ultima vez que se genero/actualizo el archivo de datos filtrado."""
    meses = ["enero","febrero","marzo","abril","mayo","junio","julio",
             "agosto","septiembre","octubre","noviembre","diciembre"]
    try:
        ts = os.path.getmtime(ARCHIVO_FILTRADO)
        d = datetime.fromtimestamp(ts)
        return f"{d.day} de {meses[d.month-1]} de {d.year}, {d.strftime('%H:%M')}"
    except Exception:
        return "fecha no disponible"

st.caption(f"Datos actualizados al {fecha_datos()}")
if zona:
    st.info(f"Mostrando gasto en las zonas de influencia de: **{zona}**")

# Totales (incluyen TODO, incluso sector en blanco)
pim = df_f["MONTO_PIM"].sum()
dev = df_f["MONTO_DEVENGADO"].sum()
avance = (dev / pim * 100) if pim > 0 else 0
if avance >= 70:
    color, etiqueta = "green", "Buen avance"
elif avance >= 40:
    color, etiqueta = "orange", "Avance moderado"
else:
    color, etiqueta = "red", "Avance bajo"

c1, c2, c3, c4 = st.columns(4)
c1.metric("PIM (presupuesto)", soles(pim))
c2.metric("Devengado (ejecutado)", soles(dev))
c3.metric("Avance de ejecucion", f"{avance:.1f}%")
c4.markdown(f"<div style='padding-top:14px'><span style='background:{color};color:white;"
            f"padding:6px 14px;border-radius:6px;font-weight:600'>{etiqueta}</span></div>",
            unsafe_allow_html=True)

if pim == 0:
    st.warning("No hay gasto registrado del PP 0068 en esta zona.")
    st.stop()

st.divider()

# ----------------------------------------------------------------------
# MAPA con fronteras siempre visibles
# ----------------------------------------------------------------------
st.subheader("Avance de ejecucion por departamento")
por_dep = (df_f.groupby("DEPARTAMENTO_EJECUTORA_NOMBRE")
           .agg(PIM=("MONTO_PIM", "sum"), Devengado=("MONTO_DEVENGADO", "sum")).reset_index())
por_dep["Avance %"] = (por_dep["Devengado"] / por_dep["PIM"] * 100).round(1)
por_dep = por_dep[por_dep["PIM"] > 0]
por_dep["_DEP"] = por_dep["DEPARTAMENTO_EJECUTORA_NOMBRE"].apply(normalizar)

geojson = cargar_geojson()
if geojson is not None:
    valores = dict(zip(por_dep["_DEP"], por_dep["Avance %"]))
    nombres = dict(zip(por_dep["_DEP"], por_dep["DEPARTAMENTO_EJECUTORA_NOMBRE"]))

    todos_dep = [f["properties"]["_DEP"] for f in geojson["features"]]

    # Capa base: TODOS los departamentos en gris con borde (fronteras siempre visibles)
    fig_mapa = go.Figure()
    fig_mapa.add_trace(go.Choropleth(
        geojson=geojson, locations=todos_dep, featureidkey="properties._DEP",
        z=[0] * len(todos_dep),
        colorscale=[[0, "#EEEEEA"], [1, "#EEEEEA"]], showscale=False,
        marker_line_color="#999999", marker_line_width=0.6,
        hoverinfo="skip",
    ))
    # Capa de datos: solo los que tienen gasto, coloreados
    con_datos = [d for d in todos_dep if d in valores]
    fig_mapa.add_trace(go.Choropleth(
        geojson=geojson, locations=con_datos, featureidkey="properties._DEP",
        z=[valores[d] for d in con_datos],
        text=[nombres[d] for d in con_datos],
        colorscale=[[0, "#E05C34"], [0.5, "#C9873A"], [1, "#3E7C4F"]],
        zmin=0, zmax=100,
        marker_line_color="#666666", marker_line_width=0.6,
        colorbar=dict(title="Avance %"),
        hovertemplate="%{text}<br>Avance: %{z}%<extra></extra>",
    ))
    fig_mapa.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
    fig_mapa.update_layout(height=600, margin=dict(l=0, r=0, t=0, b=0), dragmode=False)
    fig_mapa.update_geos(projection_type="mercator")
    st.plotly_chart(fig_mapa, use_container_width=True,
                    config={"staticPlot": False, "scrollZoom": False, "displayModeBar": False,
                            "doubleClick": False})
    st.caption("Departamentos en gris no registran gasto del PP 0068 en la seleccion actual.")
else:
    st.warning("No se pudo cargar el mapa (sin internet). Mostrando barras.")
    pd_ord = por_dep.sort_values("Avance %")
    fig_bar = px.bar(pd_ord, x="Avance %", y="DEPARTAMENTO_EJECUTORA_NOMBRE",
                     orientation="h", text="Avance %")
    fig_bar.update_layout(yaxis_title="", height=max(400, 26 * len(pd_ord)))
    st.plotly_chart(fig_bar, use_container_width=True)

st.subheader("Detalle por departamento")
t_dep = por_dep.sort_values("Avance %").copy()
t_dep["PIM"] = t_dep["PIM"].apply(soles)
t_dep["Devengado"] = t_dep["Devengado"].apply(soles)
t_dep = t_dep.rename(columns={"DEPARTAMENTO_EJECUTORA_NOMBRE": "Departamento"})
mostrar_tabla(t_dep[["Departamento", "PIM", "Devengado", "Avance %"]],
              ["Departamento"])

if zona:
    st.subheader("Detalle por distrito (zona de influencia)")
    por_dist = (df_f.groupby(["DEPARTAMENTO_EJECUTORA_NOMBRE", "PROVINCIA_EJECUTORA_NOMBRE",
                              "DISTRITO_EJECUTORA_NOMBRE"])
                .agg(PIM=("MONTO_PIM", "sum"), Devengado=("MONTO_DEVENGADO", "sum")).reset_index())
    por_dist["Avance %"] = (por_dist["Devengado"] / por_dist["PIM"] * 100).round(1)
    por_dist = por_dist[por_dist["PIM"] > 0].sort_values("Avance %")
    por_dist["PIM"] = por_dist["PIM"].apply(soles)
    por_dist["Devengado"] = por_dist["Devengado"].apply(soles)
    por_dist = por_dist.rename(columns={"DEPARTAMENTO_EJECUTORA_NOMBRE": "Departamento",
                                        "PROVINCIA_EJECUTORA_NOMBRE": "Provincia",
                                        "DISTRITO_EJECUTORA_NOMBRE": "Distrito"})
    mostrar_tabla(por_dist)

    # Nota: distritos considerados como zona de influencia, agrupados por region
    def _cap(txt):
        return str(txt).strip().title()

    def _por_region(sub_e):
        """Devuelve 'Region1 (Distrito1, Distrito2), Region2 (Distrito3)' capitalizado."""
        grupos = []
        for reg in sorted(sub_e["REGION"].unique()):
            dists = sorted(sub_e[sub_e["REGION"] == reg]["DISTRITO"].unique())
            dists_txt = ", ".join(_cap(d) for d in dists)
            grupos.append(f"{_cap(reg)} ({dists_txt})")
        return " ".join(grupos)

    if seleccion == "Todas las empresas Breca":
        partes = []
        for emp in sorted(breca["EMPRESA"].unique()):
            sub_e = breca[breca["EMPRESA"] == emp]
            partes.append(f"{str(emp).strip().upper()} ({_por_region(sub_e)})")
        nota = "Se consideraron como zona de influencia los distritos: " + " ".join(partes)
    else:
        sub_e = breca[breca["EMPRESA"] == seleccion]
        nota = "Se consideraron como zona de influencia los siguientes distritos: " + _por_region(sub_e)

    st.caption(nota)

st.divider()

# ----------------------------------------------------------------------
# Sector (omitiendo el sector en blanco de la vista, pero ya contado en totales)
# ----------------------------------------------------------------------
st.subheader("Avance de ejecucion por funcion")
por_sec = (df_f.groupby("FUNCION_NOMBRE")
           .agg(PIM=("MONTO_PIM", "sum"), Devengado=("MONTO_DEVENGADO", "sum")).reset_index())
por_sec["Avance %"] = (por_sec["Devengado"] / por_sec["PIM"] * 100).round(1)
# Omitir filas con sector vacio o en blanco
por_sec = por_sec[por_sec["FUNCION_NOMBRE"].apply(lambda x: normalizar(x) != "")]
por_sec = por_sec[por_sec["PIM"] > 0].sort_values("Avance %")

def color_av(v):
    return "#3E7C4F" if v >= 70 else "#C9873A" if v >= 40 else "#E05C34"

fig_sec = px.bar(por_sec, x="Avance %", y="FUNCION_NOMBRE", orientation="h", text="Avance %")
fig_sec.update_traces(marker_color=[color_av(v) for v in por_sec["Avance %"]],
                      texttemplate="%{text}%", textposition="outside")
fig_sec.update_layout(yaxis_title="", xaxis_title="Avance de ejecucion (%)",
                      height=max(400, 28 * len(por_sec)), margin=dict(l=10, r=40, t=10, b=10))
st.plotly_chart(fig_sec, use_container_width=True)

st.subheader("Detalle por funcion")
t_sec = por_sec.copy()
t_sec["PIM"] = t_sec["PIM"].apply(soles)
t_sec["Devengado"] = t_sec["Devengado"].apply(soles)
t_sec = t_sec.rename(columns={"FUNCION_NOMBRE": "Funcion"})
mostrar_tabla(t_sec[["Funcion", "PIM", "Devengado", "Avance %"]],
              ["Funcion"])

st.divider()

# ----------------------------------------------------------------------
# Top 20 proyectos con columnas Region y Sector, excluyendo ciertos nombres
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# Avance por NIVEL DE GOBIERNO
# ----------------------------------------------------------------------
if "NIVEL_GOBIERNO_NOMBRE" in df_f.columns:
    st.subheader("Avance de ejecucion por nivel de gobierno")
    por_niv = (df_f.groupby("NIVEL_GOBIERNO_NOMBRE")
               .agg(PIM=("MONTO_PIM", "sum"), Devengado=("MONTO_DEVENGADO", "sum")).reset_index())
    por_niv["Avance %"] = (por_niv["Devengado"] / por_niv["PIM"] * 100).round(1)
    por_niv = por_niv[por_niv["PIM"] > 0].sort_values("Avance %")
    if len(por_niv):
        fig_niv = px.bar(por_niv, x="Avance %", y="NIVEL_GOBIERNO_NOMBRE",
                         orientation="h", text="Avance %")
        fig_niv.update_traces(marker_color=[color_av(v) for v in por_niv["Avance %"]],
                              texttemplate="%{text}%", textposition="outside")
        fig_niv.update_layout(yaxis_title="", xaxis_title="Avance de ejecucion (%)",
                              height=max(300, 60 * len(por_niv)), margin=dict(l=10, r=40, t=10, b=10))
        st.plotly_chart(fig_niv, use_container_width=True)
    st.divider()

# ----------------------------------------------------------------------
# Top entidades (PLIEGO) por PIM
# ----------------------------------------------------------------------
if "PLIEGO_NOMBRE" in df_f.columns:
    st.subheader("Principales entidades por presupuesto")
    st.caption("Top 15 pliegos por PIM")
    por_pli = (df_f.groupby("PLIEGO_NOMBRE")
               .agg(PIM=("MONTO_PIM", "sum"), Devengado=("MONTO_DEVENGADO", "sum")).reset_index())
    por_pli["Avance %"] = (por_pli["Devengado"] / por_pli["PIM"] * 100).round(1)
    por_pli = por_pli[por_pli["PIM"] > 0].sort_values("PIM", ascending=False).head(15)
    t_pli = por_pli.copy()
    t_pli["PIM"] = t_pli["PIM"].apply(soles)
    t_pli["Devengado"] = t_pli["Devengado"].apply(soles)
    t_pli = t_pli.rename(columns={"PLIEGO_NOMBRE": "Entidad (Pliego)"})
    mostrar_tabla(t_pli[["Entidad (Pliego)", "PIM", "Devengado", "Avance %"]],
                  ["Entidad (Pliego)"])
    st.divider()

# ----------------------------------------------------------------------
# Composicion del gasto: inversion (capital) vs gasto corriente
# ----------------------------------------------------------------------
if "PRODUCTO_PROYECTO" in df_f.columns:
    st.subheader("Composicion del gasto: inversion vs corriente")
    cod = df_f["PRODUCTO_PROYECTO"].astype(str).str.strip()
    es_inv = cod.str.startswith("2")
    pim_inv = df_f.loc[es_inv, "MONTO_PIM"].sum()
    dev_inv = df_f.loc[es_inv, "MONTO_DEVENGADO"].sum()
    pim_corr = df_f.loc[~es_inv, "MONTO_PIM"].sum()
    dev_corr = df_f.loc[~es_inv, "MONTO_DEVENGADO"].sum()

    # Elegir base: PIM (presupuesto). Se podria alternar, pero PIM refleja la asignacion.
    datos_pie = pd.DataFrame({
        "Tipo": ["Inversion (capital)", "Gasto corriente"],
        "PIM": [pim_inv, pim_corr],
        "Devengado": [dev_inv, dev_corr],
    })
    datos_pie = datos_pie[datos_pie["PIM"] > 0]

    if len(datos_pie):
        fig_pie = px.pie(
            datos_pie, names="Tipo", values="PIM", hole=0.45,
            color="Tipo",
            color_discrete_map={"Inversion (capital)": "#3E7C4F",
                                "Gasto corriente": "#E05C34"},
        )
        # Mostrar % en el grafico y el monto (PIM y devengado) al pasar el cursor
        fig_pie.update_traces(
            textinfo="percent+label",
            customdata=datos_pie[["Devengado"]].values,
            hovertemplate="<b>%{label}</b><br>PIM: S/ %{value:,.0f}<br>Devengado: S/ %{customdata[0]:,.0f}<br>Participacion: %{percent}<extra></extra>",
        )
        fig_pie.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_pie, use_container_width=True)
        st.caption("Porcentaje calculado sobre el PIM. Pasa el cursor para ver los montos.")
    st.divider()

st.subheader("Principales proyectos de inversion publica")
st.caption("Top 20 proyectos de inversion por PIM (excluye gasto corriente)")

total_regiones = df_f["DEPARTAMENTO_EJECUTORA_NOMBRE"].nunique()

def resumen_regiones(regiones):
    regs = sorted(set(r for r in regiones if str(r).strip()))
    if len(regs) >= total_regiones and total_regiones > 5:
        return "Todas las regiones"
    if len(regs) > 5:
        return "Varias regiones"
    return ", ".join(regs)

def funcion_principal(grupo):
    # la funcion con mayor PIM dentro del proyecto
    s = grupo.groupby("FUNCION_NOMBRE")["MONTO_PIM"].sum()
    s = s[s.index.map(lambda x: normalizar(x) != "")]
    return s.idxmax() if len(s) else ""

# Filtrar SOLO proyectos de inversion (codigo PRODUCTO_PROYECTO que empieza con "2").
# Los que empiezan con "3" son productos/actividades (gasto corriente) y se excluyen.
if "PRODUCTO_PROYECTO" in df_f.columns:
    es_inversion = df_f["PRODUCTO_PROYECTO"].astype(str).str.strip().str.startswith("2")
else:
    es_inversion = True  # respaldo si el archivo no tiene el codigo
df_proy = df_f[es_inversion & df_f["PRODUCTO_PROYECTO_NOMBRE"].apply(
    lambda x: normalizar(x) != "" and normalizar(x) not in PROY_EXCLUIR)].copy()

filas = []
for nombre, grupo in df_proy.groupby("PRODUCTO_PROYECTO_NOMBRE"):
    pim_p = grupo["MONTO_PIM"].sum()
    dev_p = grupo["MONTO_DEVENGADO"].sum()
    if pim_p <= 0:
        continue
    filas.append({
        "Proyecto": nombre,
        "Region": resumen_regiones(grupo["DEPARTAMENTO_EJECUTORA_NOMBRE"]),
        "Funcion": funcion_principal(grupo),
        "_pim": pim_p, "_dev": dev_p,
        "Avance %": round(dev_p / pim_p * 100, 1),
    })

top = pd.DataFrame(filas).sort_values("_pim", ascending=False).head(20)
top["PIM"] = top["_pim"].apply(soles)
top["Devengado"] = top["_dev"].apply(soles)
mostrar_tabla(top[["Proyecto", "Region", "Funcion", "PIM", "Devengado", "Avance %"]],
              anchos={"Proyecto": "large", "Region": "medium", "Funcion": "medium"})

st.caption("Fuente: MEF, Consulta Amigable / Datos Abiertos (Gasto Diario). Elaboracion propia.")
