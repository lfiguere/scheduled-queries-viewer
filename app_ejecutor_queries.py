"""
Aplicación Web para ejecutar Scheduled Queries bajo demanda
Interfaz visual con botones de ejecución
Versión: 1.0
"""

import streamlit as st
import pandas as pd
from google.cloud import bigquery
from datetime import datetime
import time
from dateutil import parser
import pytz
import subprocess
import sys
import json
from google.oauth2 import credentials as oauth2_credentials

# Configuración
PROJECT_ID = 'mo-customer-ops-reporting'
DATASET_ID = 'ZZ_WORK'
TABLE_ID = 'SCHEDULED_QUERIES_BACKUP'

# Configurar credenciales desde Streamlit secrets
def get_bigquery_client_cached():
    """Obtiene cliente de BigQuery con credenciales de Streamlit secrets"""
    try:
        # Intentar usar secrets de Streamlit (en cloud)
        creds_dict = dict(st.secrets["gcp_credentials"])
        creds = oauth2_credentials.Credentials(
            token=None,
            refresh_token=creds_dict.get("refresh_token"),
            token_uri=creds_dict.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=creds_dict.get("client_id"),
            client_secret=creds_dict.get("client_secret")
        )
        return bigquery.Client(project=PROJECT_ID, credentials=creds)
    except:
        # Fallback a credenciales locales (desarrollo local)
        return bigquery.Client(project=PROJECT_ID)

# Configurar la página
st.set_page_config(
    page_title="Ejecutor de Scheduled Queries",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
    /* Título principal más pequeño y MÁS ABAJO */
    h1 {
        font-size: 1.5rem !important;
        margin-top: 0 !important;
        margin-bottom: 1rem !important;
        padding-top: 0 !important;
    }

    h2 {
        font-size: 1.3rem !important;
        margin-top: 1.5rem !important;  /* MÁS ESPACIO ARRIBA para bajar el título */
        margin-bottom: 1rem !important;
        padding-top: 1rem !important;   /* PADDING ARRIBA para bajarlo más */
    }

    h3 {
        margin-top: 0.1rem !important;  /* MENOS espacio arriba para subir "Queries disponibles" */
        margin-bottom: 0.2rem !important;
    }

    /* MÁS espacio superior para bajar todo */
    .block-container {
        padding-top: 1.5rem !important;  /* AUMENTADO para bajar el título */
        padding-bottom: 1rem !important;
    }

    /* Separador con MENOS espacio para acercar queries */
    hr {
        margin-top: 0.5rem !important;
        margin-bottom: 0.3rem !important;  /* MENOS espacio abajo del separador */
    }

    /* Botones más pequeños */
    .stButton>button {
        width: 100%;
        background-color: #4CAF50;
        color: white;
        border-radius: 3px;
        padding: 0.2rem 0.4rem;
        font-size: 0.75rem;
        height: auto;
        min-height: 0;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }

    /* Estados más pequeños */
    .status-activa {
        color: green;
        font-weight: bold;
        font-size: 0.7rem;
    }
    .status-inactiva {
        color: red;
        font-weight: bold;
        font-size: 0.7rem;
    }

    /* Tarjetas más compactas */
    .query-card {
        padding: 0.3rem;
        border: 1px solid #ddd;
        border-radius: 3px;
        margin-bottom: 0.3rem;
        background-color: #f9f9f9;
    }
    .query-card h3 {
        font-size: 0.85rem;
        margin-bottom: 0.2rem;
        margin-top: 0;
    }

    /* Captions más pequeños */
    .stCaption {
        font-size: 0.65rem !important;
    }

    /* Filtros sidebar más pequeños */
    .sidebar .stRadio label, .sidebar .stMultiselect label, .sidebar .stTextInput label {
        font-size: 0.8rem !important;
    }

    /* Métricas más compactas */
    [data-testid="stMetric"] {
        padding: 0.2rem 0;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.7rem !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1rem !important;
    }

    .execution-success {
        padding: 10px;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        color: #155724;
    }
    .execution-error {
        padding: 10px;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        color: #721c24;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_bigquery_client_cached():
    """Obtener cliente de BigQuery (cacheado)"""
    return get_bigquery_client_cached()


def convertir_utc_a_madrid(fecha_str):
    """Convierte fecha UTC string a hora de Madrid"""
    if not fecha_str or fecha_str == 'nan' or pd.isna(fecha_str):
        return None

    try:
        # Parsear la fecha (formato: 2026-05-28T16:05:00)
        fecha_utc = parser.parse(str(fecha_str))

        # Si no tiene timezone, asumimos UTC
        if fecha_utc.tzinfo is None:
            fecha_utc = pytz.utc.localize(fecha_utc)

        # Convertir a Madrid
        madrid_tz = pytz.timezone('Europe/Madrid')
        fecha_madrid = fecha_utc.astimezone(madrid_tz)

        return fecha_madrid.strftime('%Y-%m-%d %H:%M')
    except:
        return str(fecha_str)[:19]


@st.cache_data(ttl=300)  # Cache por 5 minutos
def cargar_queries():
    """Cargar todas las queries desde BigQuery"""
    client = get_bigquery_client_cached()

    query = f"""
    SELECT
        query_name,
        user_id,
        tipo,
        schedule,
        dataset_destino,
        activa,
        num_calls,
        procedimientos,
        sql_query,
        fecha_backup,
        estado_original,
        ultima_ejecucion_original
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
    ORDER BY query_name
    """

    df = client.query(query).to_dataframe()
    return df


def ejecutar_query(query_name):
    """Ejecutar una query específica"""
    client = get_bigquery_client_cached()

    try:
        # Llamar al procedimiento almacenado
        call_sql = f"""
        CALL `{PROJECT_ID}.{DATASET_ID}.EJECUTAR_QUERY_BACKUP`('{query_name}')
        """

        with st.spinner(f'Ejecutando {query_name}...'):
            job = client.query(call_sql)
            job.result()  # Esperar a que termine

        return True, "Ejecución completada exitosamente"

    except Exception as e:
        error_msg = str(e)
        # Extraer mensaje de error más legible
        if "error" in error_msg.lower():
            error_msg = error_msg.split("error")[-1].strip()
        return False, f"Error: {error_msg[:500]}"


def main():
    # Header más compacto
    st.markdown("## 🚀 Ejecutor de Scheduled Queries")
    st.markdown("---")

    # Sidebar para filtros (más pequeño)
    st.sidebar.markdown("### ⚙️ Filtros")

    # Cargar datos
    try:
        df = cargar_queries()

        # Filtros
        filtro_estado = st.sidebar.radio(
            "Estado",
            ["Todas", "Solo Activas", "Solo Inactivas"],
            index=0
        )

        filtro_tipo = st.sidebar.multiselect(
            "Tipo",
            options=df['tipo'].unique().tolist(),
            default=df['tipo'].unique().tolist()
        )

        # Filtro por estado de ejecución - un estado por fila
        st.sidebar.markdown("**Estado de Ejecución:**")
        estados_disponibles = sorted(df['estado_original'].dropna().unique().tolist())

        # Contar queries sin estado
        queries_sin_estado = len(df[df['estado_original'].isna()])

        # Botones de control rápido
        col_btn1, col_btn2, col_btn3 = st.sidebar.columns(3)
        with col_btn1:
            if st.button("✅ Todos", key="btn_marcar_todos", help="Marcar todos los estados"):
                for estado in estados_disponibles:
                    st.session_state[f"chk_estado_{estado}"] = True
                st.session_state["chk_sin_estado"] = True
                st.rerun()
        with col_btn2:
            if st.button("❌ Ninguno", key="btn_desmarcar_todos", help="Desmarcar todos"):
                for estado in estados_disponibles:
                    st.session_state[f"chk_estado_{estado}"] = False
                st.session_state["chk_sin_estado"] = False
                st.rerun()
        with col_btn3:
            if st.button("💥 Failed", key="btn_solo_failed", help="Solo queries falladas"):
                for estado in estados_disponibles:
                    st.session_state[f"chk_estado_{estado}"] = (estado == 'FAILED')
                st.session_state["chk_sin_estado"] = False
                st.rerun()

        # Inicializar session state si no existe
        for estado in estados_disponibles:
            if f"chk_estado_{estado}" not in st.session_state:
                st.session_state[f"chk_estado_{estado}"] = True

        if "chk_sin_estado" not in st.session_state:
            st.session_state["chk_sin_estado"] = True

        # Checkboxes para cada estado
        filtro_estado_ejecucion = []
        for estado in estados_disponibles:
            estado_icon = '✅' if estado == 'SUCCEEDED' else ('❌' if estado == 'FAILED' else ('🔄' if estado == 'RUNNING' else '⚪'))
            if st.sidebar.checkbox(
                f"{estado_icon} {estado}",
                value=st.session_state[f"chk_estado_{estado}"],
                key=f"chk_estado_{estado}"
            ):
                filtro_estado_ejecucion.append(estado)

        # Checkbox para incluir queries sin estado
        incluir_sin_estado = st.sidebar.checkbox(
            f"⚫ Sin estado ({queries_sin_estado})",
            value=st.session_state["chk_sin_estado"],
            key="chk_sin_estado"
        )

        filtro_busqueda = st.sidebar.text_input(
            "🔍 Buscar por nombre",
            ""
        )

        # Botón para refrescar caché (en cloud solo limpia caché, en local ejecuta scripts)
        if st.sidebar.button("🔄 Refrescar datos", key="btn_refresh"):
            st.cache_data.clear()
            st.success("✅ Caché limpiada. Los datos se actualizarán en la próxima carga.")
            time.sleep(1)
            st.rerun()

        # Aplicar filtros
        df_filtrado = df.copy()

        if filtro_estado == "Solo Activas":
            df_filtrado = df_filtrado[df_filtrado['activa'] == True]
        elif filtro_estado == "Solo Inactivas":
            df_filtrado = df_filtrado[df_filtrado['activa'] == False]

        df_filtrado = df_filtrado[df_filtrado['tipo'].isin(filtro_tipo)]

        # Aplicar filtro de estado de ejecución
        # Si NO hay ningún estado seleccionado, no mostrar nada
        if not filtro_estado_ejecucion and not incluir_sin_estado:
            df_filtrado = df_filtrado.iloc[0:0]  # DataFrame vacío
        else:
            # Aplicar filtros con OR
            mask_estados = False

            if filtro_estado_ejecucion:
                mask_estados = df_filtrado['estado_original'].isin(filtro_estado_ejecucion)

            if incluir_sin_estado:
                mask_sin_estado = df_filtrado['estado_original'].isna()
                if isinstance(mask_estados, bool) and not mask_estados:
                    mask_estados = mask_sin_estado
                else:
                    mask_estados = mask_estados | mask_sin_estado

            if not isinstance(mask_estados, bool):
                df_filtrado = df_filtrado[mask_estados]

        if filtro_busqueda:
            df_filtrado = df_filtrado[
                df_filtrado['query_name'].str.contains(filtro_busqueda, case=False, na=False)
            ]

        # RESUMEN DINÁMICO - Se actualiza con filtros
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Resumen (filtrado):**")

        total_filtrado = len(df_filtrado)
        activas_filtrado = len(df_filtrado[df_filtrado['activa'] == True])
        succeeded_filtrado = len(df_filtrado[df_filtrado['estado_original'] == 'SUCCEEDED'])
        failed_filtrado = len(df_filtrado[df_filtrado['estado_original'] == 'FAILED'])

        st.sidebar.markdown(f"Total: **{total_filtrado}** / {len(df)}")
        st.sidebar.markdown(f"🟢 Activas: **{activas_filtrado}**")
        st.sidebar.markdown(f"✅ SUCCEEDED: **{succeeded_filtrado}**")
        st.sidebar.markdown(f"❌ FAILED: **{failed_filtrado}**")

        # Mostrar resultados (más pequeño)
        st.markdown(f"### 📋 Queries disponibles ({len(df_filtrado)})")

        if len(df_filtrado) == 0:
            st.warning("No se encontraron queries con los filtros aplicados")
        else:
            # Crear tabs para diferentes vistas
            tab1, tab2 = st.tabs(["Vista de Tarjetas", "Vista de Tabla"])

            with tab1:
                # Vista de tarjetas con botones (3 por fila)
                cols_per_row = 3

                for i in range(0, len(df_filtrado), cols_per_row):
                    cols = st.columns(cols_per_row)

                    for j in range(cols_per_row):
                        idx = i + j
                        if idx < len(df_filtrado):
                            row = df_filtrado.iloc[idx]
                            unique_id = f"{idx}_{row['query_name']}"  # Key único

                            with cols[j]:
                                # Tarjeta de query
                                estado_color = "status-activa" if row['activa'] else "status-inactiva"
                                estado_text = "🟢 ACTIVA" if row['activa'] else "🔴 INACTIVA"

                                # Color para el estado original
                                estado_orig = row.get('estado_original', 'N/A')
                                if estado_orig == 'SUCCEEDED':
                                    estado_orig_icon = '✅'
                                elif estado_orig == 'FAILED':
                                    estado_orig_icon = '❌'
                                elif estado_orig == 'RUNNING':
                                    estado_orig_icon = '🔄'
                                else:
                                    estado_orig_icon = '⚪'

                                with st.container():
                                    st.markdown(f"<div class='query-card'><h3>{row['query_name']}</h3></div>", unsafe_allow_html=True)
                                    st.markdown(f"<p class='{estado_color}'>{estado_text} | {estado_orig_icon} {estado_orig}</p>", unsafe_allow_html=True)

                                    st.caption(f"**Tipo:** {row['tipo']}")
                                    st.caption(f"**Schedule:** {row['schedule']}")

                                    if pd.notna(row['num_calls']) and row['num_calls'] > 0:
                                        st.caption(f"**CALLs:** {int(row['num_calls'])}")

                                    # Mostrar última ejecución (convertida a hora de Madrid)
                                    if pd.notna(row.get('ultima_ejecucion_original')):
                                        ultima_madrid = convertir_utc_a_madrid(row['ultima_ejecucion_original'])
                                        if ultima_madrid:
                                            st.caption(f"**Última:** {ultima_madrid} 🇪🇸")

                                    # Botones de acción MÁS JUNTOS
                                    col_btn1, col_btn2 = st.columns([1, 1])

                                    with col_btn1:
                                        # Botón ejecutar
                                        if st.button(
                                            "▶️ Ejecutar",
                                            key=f"exec_{unique_id}",
                                            type="primary"
                                        ):
                                            success, message = ejecutar_query(row['query_name'])

                                            if success:
                                                st.success(message)
                                                st.balloons()
                                            else:
                                                st.error(message)

                                    with col_btn2:
                                        # Botón ver SQL
                                        if st.button(
                                            "📄 SQL",
                                            key=f"sql_{unique_id}"
                                        ):
                                            st.session_state[f'show_sql_{unique_id}'] = True

                                    # Mostrar SQL si se solicitó
                                    if st.session_state.get(f'show_sql_{unique_id}', False):
                                        with st.expander("SQL Query", expanded=True):
                                            sql_preview = str(row['sql_query'])[:2000]
                                            if len(str(row['sql_query'])) > 2000:
                                                sql_preview += "\n\n... (truncado)"
                                            st.code(sql_preview, language='sql')

                                            if st.button("❌ Cerrar", key=f"close_{unique_id}"):
                                                st.session_state[f'show_sql_{unique_id}'] = False
                                                st.rerun()

                                    st.markdown("---")

            with tab2:
                # Vista de tabla - cambiar dataset_destino por ultima_ejecucion
                df_tabla = df_filtrado[[
                    'query_name',
                    'tipo',
                    'activa',
                    'estado_original',
                    'schedule',
                    'ultima_ejecucion_original',
                    'num_calls'
                ]].copy()

                df_tabla['activa'] = df_tabla['activa'].apply(
                    lambda x: '🟢 ACTIVA' if x else '🔴 INACTIVA'
                )

                df_tabla['estado_original'] = df_tabla['estado_original'].apply(
                    lambda x: f"✅ {x}" if x == 'SUCCEEDED' else (f"❌ {x}" if x == 'FAILED' else (f"🔄 {x}" if x == 'RUNNING' else f"⚪ {x}"))
                )

                st.dataframe(
                    df_tabla,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "query_name": "Nombre",
                        "tipo": "Tipo",
                        "activa": "Estado",
                        "estado_original": "Estado Ejecución",
                        "schedule": "Schedule",
                        "ultima_ejecucion_original": "Última Ejecución",
                        "num_calls": "# CALLs"
                    }
                )

                # Opción para ejecutar múltiples
                st.markdown("---")
                st.markdown("#### Ejecución múltiple")

                queries_seleccionadas = st.multiselect(
                    "Selecciona queries para ejecutar",
                    options=df_filtrado['query_name'].tolist(),
                    key="multiselect_queries_tab2"
                )

                if st.button("▶️ Ejecutar seleccionadas", disabled=len(queries_seleccionadas) == 0, key="btn_ejecutar_multiples"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for i, query_name in enumerate(queries_seleccionadas):
                        status_text.text(f"Ejecutando {query_name}... ({i+1}/{len(queries_seleccionadas)})")

                        success, message = ejecutar_query(query_name)

                        if success:
                            st.success(f"✅ {query_name}: {message}")
                        else:
                            st.error(f"❌ {query_name}: {message}")

                        progress_bar.progress((i + 1) / len(queries_seleccionadas))

                    status_text.text("¡Ejecución completada!")
                    st.balloons()

    except Exception as e:
        st.error(f"Error al cargar datos: {str(e)}")
        st.exception(e)

    # Footer (opcional, comentado para aspecto más profesional)
    # st.markdown("---")
    # st.caption(f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
