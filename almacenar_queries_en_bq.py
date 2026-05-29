"""
Script para almacenar todas las scheduled queries en BigQuery
Permite relanzarlas bajo demanda
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
from google.cloud import bigquery
from datetime import datetime
import glob

# Configuración
PROJECT_ID = 'mo-customer-ops-reporting'
DATASET_ID = 'ZZ_WORK'
TABLE_ID = 'SCHEDULED_QUERIES_BACKUP'

# Buscar el Excel más reciente (primero intentar con REAL, luego ALL)
excel_files = glob.glob('C:\\Users\\luis.figueredo\\Scheduled_Queries_REAL_*.xlsx')
if not excel_files:
    excel_files = glob.glob('C:\\Users\\luis.figueredo\\ALL_Scheduled_Queries_*.xlsx')

if excel_files:
    EXCEL_FILE = max(excel_files, key=lambda x: x.split('_')[-1])
else:
    EXCEL_FILE = 'C:\\Users\\luis.figueredo\\Scheduled_Queries_REAL_20260529_085517.xlsx'


def crear_tabla_backup(client):
    """
    Crea la tabla para almacenar las scheduled queries
    """
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    schema = [
        bigquery.SchemaField("query_id", "STRING", mode="REQUIRED", description="ID único de la query"),
        bigquery.SchemaField("query_name", "STRING", mode="REQUIRED", description="Nombre de la scheduled query"),
        bigquery.SchemaField("display_name", "STRING", description="Display name de la query"),
        bigquery.SchemaField("user_id", "STRING", description="User ID del propietario"),
        bigquery.SchemaField("user_email", "STRING", description="Email del propietario"),
        bigquery.SchemaField("estado_original", "STRING", description="Estado original (SUCCEEDED, FAILED, etc)"),
        bigquery.SchemaField("schedule", "STRING", description="Programación original"),
        bigquery.SchemaField("dataset_destino", "STRING", description="Dataset de destino"),
        bigquery.SchemaField("tipo", "STRING", description="CALL o SQL_DIRECTO"),
        bigquery.SchemaField("tiene_multiples_calls", "BOOLEAN", description="Si tiene múltiples CALLs"),
        bigquery.SchemaField("num_calls", "INTEGER", description="Número de CALLs (si aplica)"),
        bigquery.SchemaField("procedimientos", "STRING", description="Lista de procedimientos separados por |"),
        bigquery.SchemaField("sql_query", "STRING", mode="REQUIRED", description="Query SQL completa"),
        bigquery.SchemaField("tablas_usadas", "STRING", description="Tablas que usa (para SQL directo)"),
        bigquery.SchemaField("ultima_ejecucion_original", "STRING", description="Última ejecución en scheduled query"),
        bigquery.SchemaField("fecha_backup", "TIMESTAMP", mode="REQUIRED", description="Fecha de este backup"),
        bigquery.SchemaField("activa", "BOOLEAN", description="Si estaba activa al momento del backup"),
        bigquery.SchemaField("notas", "STRING", description="Notas adicionales"),
    ]

    table = bigquery.Table(table_ref, schema=schema)
    table.description = "Backup de todas las scheduled queries del proyecto con posibilidad de relanzarlas"

    try:
        table = client.create_table(table)
        print(f"   [OK] Tabla creada: {table_ref}")
        return True
    except Exception as e:
        if "Already Exists" in str(e):
            print(f"   [INFO] La tabla ya existe: {table_ref}")
            return True
        else:
            print(f"   [ERROR] Error al crear tabla: {str(e)}")
            return False


def cargar_datos_en_tabla(client, df):
    """
    Carga los datos del Excel en la tabla de BigQuery
    """
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    print(f"\n3. Preparando datos para carga...")

    # Preparar datos
    datos_para_bq = []

    for idx, row in df.iterrows():
        tiene_call = 'CALL' in str(row.get('Query SQL', '')).upper()

        # Extraer procedimientos si tiene CALL
        procedimientos = ""
        num_calls = 0
        if tiene_call:
            import re
            patron = r'CALL\s+`([^`]+)`'
            matches = re.findall(patron, str(row.get('Query SQL', '')), re.IGNORECASE)
            procedimientos = ' | '.join(matches)
            num_calls = len(matches)

        # Determinar estado original
        estado_run = row.get('Ultimo Estado Run')
        if pd.notna(estado_run):
            estado_run_int = int(estado_run)
            # Mapear estados de Transfer RUN (no confundir con Transfer CONFIG state)
            # Basado en observaciones reales:
            # - 4 aparece para queries exitosas (SUCCEEDED)
            # - 5 aparece para queries falladas (FAILED)
            # - 3 aparece cuando está corriendo actualmente
            # - 2 probablemente RUNNING inicial
            # - 1 probablemente PENDING
            if estado_run_int == 4:
                estado_str = 'SUCCEEDED'
            elif estado_run_int == 5:
                estado_str = 'FAILED'
            elif estado_run_int == 3:
                estado_str = 'RUNNING'  # O podría ser SUCCEEDED en progreso
            elif estado_run_int == 2:
                estado_str = 'RUNNING'
            elif estado_run_int == 1:
                estado_str = 'PENDING'
            elif estado_run_int == 6:
                estado_str = 'CANCELLED'
            elif estado_run_int == 0:
                estado_str = 'UNSPECIFIED'
            else:
                estado_str = f'STATE_{estado_run_int}'
        else:
            estado_str = row.get('Estado', '')  # Fallback para Excel viejo

        registro = {
            'query_id': row.get('Config ID', f"query_{idx}"),
            'query_name': row.get('Nombre', 'Sin nombre'),
            'display_name': row.get('Display Name', row.get('Nombre', 'Sin nombre')),
            'user_id': str(row.get('User ID', '')),
            'user_email': row.get('User Email', None),
            'estado_original': estado_str,  # CORREGIDO: mapear desde "Ultimo Estado Run"
            'schedule': row.get('Schedule', ''),
            'dataset_destino': row.get('Dataset Destino', ''),
            'tipo': 'CALL' if tiene_call else 'SQL_DIRECTO',
            'tiene_multiples_calls': num_calls > 1,
            'num_calls': num_calls if tiene_call else None,
            'procedimientos': procedimientos if procedimientos else None,
            'sql_query': str(row.get('Query SQL', ''))[:1000000],  # Limitar tamaño
            'tablas_usadas': str(row.get('Tablas Usadas', '')) if not tiene_call else None,
            'ultima_ejecucion_original': str(row.get('Ultima Ejecucion Real', row.get('Ultima Ejecucion', ''))),  # CORREGIDO: usar "Ultima Ejecucion Real"
            'fecha_backup': datetime.now(),
            'activa': not row.get('Disabled', False),  # CORREGIDO: usar campo 'Disabled'
            'notas': None
        }

        datos_para_bq.append(registro)

    # Convertir a DataFrame
    df_bq = pd.DataFrame(datos_para_bq)

    print(f"   [OK] {len(df_bq)} queries preparadas")

    # Cargar a BigQuery
    print(f"\n4. Cargando datos a BigQuery...")

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE  # Reemplazar datos
    )

    job = client.load_table_from_dataframe(
        df_bq,
        table_ref,
        job_config=job_config
    )

    job.result()  # Esperar a que termine

    print(f"   [OK] Datos cargados exitosamente")

    # Verificar
    query = f"SELECT COUNT(*) as total FROM `{table_ref}`"
    result = client.query(query).result()
    for row in result:
        print(f"   [INFO] Total de queries en la tabla: {row.total}")


def crear_procedimiento_ejecutor(client):
    """
    Crea un procedimiento almacenado para ejecutar queries bajo demanda
    """
    procedure_sql = f"""
CREATE OR REPLACE PROCEDURE `{PROJECT_ID}.{DATASET_ID}.EJECUTAR_QUERY_BACKUP`(
    IN query_name_param STRING
)
BEGIN
    DECLARE sql_to_execute STRING;
    DECLARE query_type STRING;
    DECLARE query_exists INT64;

    -- Verificar si la query existe
    SET query_exists = (
        SELECT COUNT(*)
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
        WHERE query_name = query_name_param
    );

    IF query_exists = 0 THEN
        SELECT ERROR(FORMAT('Query no encontrada: %s', query_name_param));
    END IF;

    -- Obtener el SQL y el tipo
    SET (sql_to_execute, query_type) = (
        SELECT AS STRUCT sql_query, tipo
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
        WHERE query_name = query_name_param
        LIMIT 1
    );

    -- Log de ejecución
    SELECT
        query_name_param as query_ejecutada,
        query_type as tipo,
        CURRENT_TIMESTAMP() as fecha_ejecucion,
        'Iniciando ejecución...' as estado;

    -- Ejecutar el SQL
    EXECUTE IMMEDIATE sql_to_execute;

    -- Confirmar ejecución
    SELECT
        query_name_param as query_ejecutada,
        'Ejecución completada exitosamente' as resultado,
        CURRENT_TIMESTAMP() as fecha_fin;

END;
"""

    print(f"\n5. Creando procedimiento para ejecutar queries...")

    try:
        client.query(procedure_sql).result()
        print(f"   [OK] Procedimiento creado: {DATASET_ID}.EJECUTAR_QUERY_BACKUP")
        print(f"\n   Para ejecutar una query, usa:")
        print(f"   CALL `{PROJECT_ID}.{DATASET_ID}.EJECUTAR_QUERY_BACKUP`('NOMBRE_DE_LA_QUERY');")
    except Exception as e:
        print(f"   [ERROR] Error al crear procedimiento: {str(e)}")


def crear_vista_consulta(client):
    """
    Crea una vista para consultar fácilmente las queries disponibles
    """
    view_sql = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET_ID}.V_QUERIES_DISPONIBLES` AS
SELECT
    query_name,
    tipo,
    schedule,
    dataset_destino,
    activa,
    num_calls,
    procedimientos,
    fecha_backup,
    CASE
        WHEN activa THEN '🟢 ACTIVA'
        ELSE '🔴 INACTIVA'
    END as estado_visual,
    CONCAT(
        'CALL `{PROJECT_ID}.{DATASET_ID}.EJECUTAR_QUERY_BACKUP`(\\'',
        query_name,
        '\\');'
    ) as comando_ejecutar
FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
ORDER BY query_name
"""

    print(f"\n6. Creando vista de consulta...")

    try:
        client.query(view_sql).result()
        print(f"   [OK] Vista creada: {DATASET_ID}.V_QUERIES_DISPONIBLES")
        print(f"\n   Para ver todas las queries disponibles:")
        print(f"   SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.V_QUERIES_DISPONIBLES`;")
    except Exception as e:
        print(f"   [ERROR] Error al crear vista: {str(e)}")


def main():
    print("=" * 80)
    print("ALMACENAR SCHEDULED QUERIES EN BIGQUERY")
    print("Con capacidad de relanzamiento bajo demanda")
    print("=" * 80)

    try:
        # Conectar a BigQuery
        print(f"\n1. Conectando a BigQuery...")
        client = bigquery.Client(project=PROJECT_ID)
        print(f"   [OK] Conectado a proyecto: {PROJECT_ID}")

        # Crear tabla
        print(f"\n2. Creando tabla de backup: {DATASET_ID}.{TABLE_ID}")
        if not crear_tabla_backup(client):
            print("   [ERROR] No se pudo crear la tabla")
            return

        # Leer Excel
        print(f"\n3. Leyendo datos del Excel...")
        df = pd.read_excel(EXCEL_FILE, sheet_name='Scheduled Queries')
        print(f"   [OK] {len(df)} queries leídas")

        # Cargar datos
        cargar_datos_en_tabla(client, df)

        # Crear procedimiento ejecutor
        crear_procedimiento_ejecutor(client)

        # Crear vista
        crear_vista_consulta(client)

        # Resumen final
        print("\n" + "=" * 80)
        print("RESUMEN")
        print("=" * 80)
        print(f"✅ Tabla creada: {PROJECT_ID}.{DATASET_ID}.{TABLE_ID}")
        print(f"✅ Vista creada: {PROJECT_ID}.{DATASET_ID}.V_QUERIES_DISPONIBLES")
        print(f"✅ Procedimiento creado: {PROJECT_ID}.{DATASET_ID}.EJECUTAR_QUERY_BACKUP")

        print("\n" + "=" * 80)
        print("CÓMO USAR:")
        print("=" * 80)
        print("\n1. Ver todas las queries disponibles:")
        print(f"   SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.V_QUERIES_DISPONIBLES`;")

        print("\n2. Ejecutar una query específica:")
        print(f"   CALL `{PROJECT_ID}.{DATASET_ID}.EJECUTAR_QUERY_BACKUP`('NOMBRE_DE_LA_QUERY');")

        print("\n3. Buscar queries por tipo:")
        print(f"   SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.V_QUERIES_DISPONIBLES`")
        print(f"   WHERE tipo = 'CALL';  -- o 'SQL_DIRECTO'")

        print("\n4. Ver solo queries activas:")
        print(f"   SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.V_QUERIES_DISPONIBLES`")
        print(f"   WHERE activa = TRUE;")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n[ERROR] Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
