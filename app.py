
import streamlit as st
import pandas as pd
import folium
from math import radians, sin, cos, sqrt, atan2
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from streamlit_folium import st_folium

st.set_page_config(layout="wide", page_title="Optimizador de Rutas Escolares")

@st.cache_resource
def init_geocode():
    geolocator = Nominatim(user_agent="optimizador_escuelas_streamlit_v2")
    return RateLimiter(geolocator.geocode, min_delay_seconds=1, error_wait_seconds=2)

@st.cache_data(show_spinner=False)
def obtener_coordenadas(direccion):
    geocode = init_geocode()
    try:
        location = geocode(f"{direccion}, Ciudad Autonoma de Buenos Aires, Argentina", timeout=10)
        if location:
            return location.latitude, location.longitude
        return None, None
    except Exception:
        return None, None

def haversine_km(coord1, coord2):
    R = 6371
    lat1, lon1 = radians(coord1[0]), radians(coord1[1])
    lat2, lon2 = radians(coord2[0]), radians(coord2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

def optimizar_ruta(puntos):
    if not puntos:
        return []
    restantes = list(puntos)
    actual = restantes.pop(0)
    ruta = [actual]
    while restantes:
        siguiente = min(restantes, key=lambda x: haversine_km(
            (actual['lat'], actual['lon']), (x['lat'], x['lon'])
        ))
        ruta.append(siguiente)
        restantes.remove(siguiente)
        actual = siguiente
    return ruta

@st.cache_data(show_spinner=False)
def load_data():
    try:
        df_loaded = pd.read_excel('NOMENCLADOR_ESCOLAR.xlsx', engine='openpyxl')
    except FileNotFoundError:
        try:
            df_loaded = pd.read_csv('NOMENCLADOR_ESCOLAR.csv')
        except Exception as e:
            st.error(f"⚠️ No se encontró el archivo de datos. Error: {e}")
            st.stop()
    df_loaded.columns = df_loaded.columns.str.strip()
    return df_loaded

df = load_data()

# --- Session state ---
if 'escuelas_a_visitar' not in st.session_state:
    st.session_state.escuelas_a_visitar = []
if 'ruta_calculada' not in st.session_state:
    st.session_state.ruta_calculada = None
if 'punto_inicio_validado' not in st.session_state:
    st.session_state.punto_inicio_validado = None  # {'direccion', 'lat', 'lon', 'display'}

# --- Sidebar ---
area_options = ["TODOS"] + sorted(df['ÁREA'].unique().astype(str).tolist())
de_options = ["TODOS"] + sorted(df['DE'].unique().tolist())

with st.sidebar:
    st.header("Filtros de Búsqueda")
    area_selector = st.selectbox('Filtrar por Área:', options=area_options)
    de_selector = st.selectbox('Filtrar por DE:', options=de_options)
    buscador = st.text_input('Buscar (Nombre, Código, Número):', placeholder='Ej: Remedios de Escalada')

    st.markdown("---")
    st.subheader("📍 Mi Ubicación de Inicio")
    ubicacion_inicio = st.text_input('Dirección:', placeholder='Ej: Av. Rivadavia 1234', key='input_ubicacion')

    if st.button('Validar Dirección', key='btn_validar_inicio'):
        if not ubicacion_inicio.strip():
            st.warning("Ingresá una dirección primero.")
        else:
            with st.spinner('Buscando...'):
                lat, lon = obtener_coordenadas(ubicacion_inicio.strip())
            if lat and lon:
                # Hacer geocodificación inversa para mostrar la dirección normalizada
                try:
                    geolocator = Nominatim(user_agent="optimizador_escuelas_streamlit_v2")
                    loc = geolocator.reverse((lat, lon), language='es', timeout=10)
                    display = loc.address if loc else ubicacion_inicio.strip()
                except Exception:
                    display = ubicacion_inicio.strip()
                st.session_state.punto_inicio_validado = {
                    'direccion': ubicacion_inicio.strip(),
                    'lat': lat,
                    'lon': lon,
                    'display': display
                }
                st.session_state.ruta_calculada = None
            else:
                st.session_state.punto_inicio_validado = None
                st.error("❌ No se encontró la dirección. Intentá ser más específico.")

    # Mostrar resultado de validación
    p = st.session_state.punto_inicio_validado
    if p:
        st.success("✅ Dirección encontrada")
        st.caption(p['display'])
        st.caption(f"🌐 {p['lat']:.5f}, {p['lon']:.5f}")
        # Mini mapa de previsualización
        mini_map = folium.Map(location=[p['lat'], p['lon']], zoom_start=15)
        folium.Marker(
            location=[p['lat'], p['lon']],
            popup="Mi Ubicación",
            icon=folium.Icon(color='green', icon='home', prefix='fa')
        ).add_to(mini_map)
        st_folium(mini_map, width=260, height=200, returned_objects=[], key="mini_map_inicio")
    elif st.session_state.get('btn_validar_inicio'):
        pass  # ya se mostró el error arriba

# --- Filtrado ---
filtered_df = df.copy()
if area_selector != "TODOS":
    filtered_df = filtered_df[filtered_df['ÁREA'].astype(str) == area_selector]
if de_selector != "TODOS":
    try:
        filtered_df = filtered_df[filtered_df['DE'] == int(de_selector)]
    except ValueError:
        filtered_df = filtered_df[filtered_df['DE'].astype(str) == de_selector]
if len(buscador) >= 2:
    q = buscador.lower()
    mask = (
        filtered_df['NOMBRE'].astype(str).str.lower().str.contains(q) |
        filtered_df['CÓDIGO'].astype(str).str.lower().str.contains(q) |
        filtered_df['NUM_ESC'].astype(str).str.lower().str.contains(q)
    )
    filtered_df = filtered_df[mask]

resultados = filtered_df.head(15)

# --- Header ---
st.title("🏫 Optimizador de Rutas Escolares")
st.markdown("### Planifica la mejor ruta para visitar escuelas")

# --- Selección de escuelas ---
st.subheader("Escuelas Encontradas (Máximo 15 resultados)")
col1, col2 = st.columns([0.7, 0.3])

with col1:
    options_list = [
        (f"[{row['CÓDIGO']}] DE {row['DE']} - {row['NOMBRE']} ({row['DIRECCION']})", row.to_dict())
        for _, row in resultados.iterrows()
    ]
    display_labels = [x[0] for x in options_list]
    label_to_data = {x[0]: x[1] for x in options_list}

    selected_labels = st.multiselect('Escuelas', options=display_labels, label_visibility="hidden")

    if st.button('Añadir Escuelas Seleccionadas a la Ruta'):
        added = 0
        for label in selected_labels:
            school = label_to_data[label]
            uid = (school.get('CÓDIGO'), school.get('NOMBRE'), school.get('DIRECCION'))
            if not any((e.get('CÓDIGO'), e.get('NOMBRE'), e.get('DIRECCION')) == uid for e in st.session_state.escuelas_a_visitar):
                st.session_state.escuelas_a_visitar.append(school)
                added += 1
        if added:
            st.session_state.ruta_calculada = None  # invalidar ruta anterior
            st.success(f"{added} escuela(s) añadida(s).")
        else:
            st.info("Todas ya estaban en la lista.")

with col2:
    st.subheader("Escuelas para visitar")
    if st.session_state.escuelas_a_visitar:
        for i, esc in enumerate(st.session_state.escuelas_a_visitar):
            st.write(f"{i+1}. {esc['NOMBRE']} ({esc['DIRECCION']})")
        if st.button('Limpiar Lista'):
            st.session_state.escuelas_a_visitar = []
            st.session_state.ruta_calculada = None
            st.rerun()
    else:
        st.info("No hay escuelas seleccionadas.")

st.markdown("---")

# --- Botón calcular ---
if st.button('Calcular Ruta Óptima', type='primary'):
    p_inicio = st.session_state.punto_inicio_validado
    if not st.session_state.escuelas_a_visitar and not p_inicio:
        st.warning("❌ Seleccioná al menos una escuela o validá una ubicación de inicio.")
    else:
        puntos = []

        if p_inicio:
            puntos.append({
                'nombre': 'Mi Ubicación',
                'direccion': p_inicio['direccion'],
                'lat': p_inicio['lat'],
                'lon': p_inicio['lon']
            })
            st.success("✅ Usando ubicación de inicio validada.")

        total = len(st.session_state.escuelas_a_visitar)
        if total > 0:
            st.write(f"🌍 Geocodificando {total} escuela(s)...")
            progress_bar = st.progress(0)
            for idx, esc in enumerate(st.session_state.escuelas_a_visitar):
                lat, lon = obtener_coordenadas(esc['DIRECCION'])
                if lat and lon:
                    puntos.append({'nombre': esc['NOMBRE'], 'direccion': esc['DIRECCION'], 'lat': lat, 'lon': lon})
                else:
                    st.warning(f"⚠️ No se encontró: {esc['DIRECCION']} (omitida)")
                progress_bar.progress((idx + 1) / total)

        if len(puntos) < 2:
            st.error("❌ Se necesitan al menos 2 puntos para calcular una ruta.")
        else:
            ruta = optimizar_ruta(puntos)
            st.session_state.ruta_calculada = ruta  # guardar en session_state
            st.success(f"✅ Ruta optimizada con {len(ruta)} paradas.")

# --- Mostrar resultado FUERA del bloque del botón ---
if st.session_state.ruta_calculada:
    ruta_final = st.session_state.ruta_calculada

    st.markdown("## 🏁 Hoja de Ruta Recomendada")

    avg_lat = sum(e['lat'] for e in ruta_final) / len(ruta_final)
    avg_lon = sum(e['lon'] for e in ruta_final) / len(ruta_final)
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)

    route_coords = []
    school_counter = 0

    for esc in ruta_final:
        route_coords.append([esc['lat'], esc['lon']])
        if esc['nombre'] == 'Mi Ubicación':
            folium.Marker(
                location=[esc['lat'], esc['lon']],
                popup=folium.Popup(f"<b>Inicio:</b> {esc['direccion']}", max_width=250),
                icon=folium.Icon(color='green', icon='home', prefix='fa')
            ).add_to(m)
            st.markdown(f"**🏠 Inicio:** {esc['direccion']}")
        else:
            school_counter += 1
            folium.Marker(
                location=[esc['lat'], esc['lon']],
                popup=folium.Popup(f"<b>{school_counter}. {esc['nombre']}</b><br>{esc['direccion']}", max_width=250),
                icon=folium.Icon(color='blue', icon='graduation-cap', prefix='fa')
            ).add_to(m)
            st.markdown(f"**{school_counter}ª Parada:** {esc['nombre']} — {esc['direccion']}")

    if len(route_coords) > 1:
        folium.PolyLine(route_coords, color='red', weight=3, opacity=0.8).add_to(m)

    st.markdown("### Mapa")
    # returned_objects=[] evita que el mapa dispare reruns al interactuar
    st_folium(m, width=700, height=500, returned_objects=[], key="route_map")
