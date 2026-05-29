"""
Exportar scheduled queries con la ÚLTIMA EJECUCIÓN REAL (no la próxima)
usando BigQuery Data Transfer API v1
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from google.cloud import bigquery_datatransfer_v1
import pandas as pd
from datetime import datetime
import re

PROJECT_ID = 'mo-customer-ops-reporting'
LOCATION = 'EU'

def extraer_tablas_de_sql(sql_query):
    """Extrae nombres de tablas de una query SQL"""
    if not sql_query:
        return []

    patron = r'`([a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_*]+)`'
    tablas = re.findall(patron, sql_query)

    patron_sin_backticks = r'(?:FROM|JOIN)\s+([a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_*]+)'
    tablas_sin_backticks = re.findall(patron_sin_backticks, sql_query, re.IGNORECASE)

    todas_tablas = set(tablas)
    todas_tablas.update(tablas_sin_backticks)

    return sorted(list(todas_tablas))


def main():
    print("=" * 80)
    print("EXPORTADOR DE SCHEDULED QUERIES CON ÚLTIMA EJECUCIÓN REAL")
    print("=" * 80)
    print(f"Proyecto: {PROJECT_ID}")
    print(f"NOTA: Esto puede tardar varios minutos (consulta 169 transfers)")
    print("=" * 80)

    client = bigquery_datatransfer_v1.DataTransferServiceClient()
    parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"

    print(f"\n1. Listando transfer configs...")
    transfer_configs = list(client.list_transfer_configs(parent=parent))
    print(f"   [OK] {len(transfer_configs)} transfer configs encontrados")

    print(f"\n2. Procesando cada transfer y obteniendo última ejecución...")
    resultados = []

    for i, config in enumerate(transfer_configs, 1):
        if i % 10 == 0:
            print(f"   Procesadas: {i}/{len(transfer_configs)}")

        display_name = config.display_name
        params = dict(config.params)
        query_sql = params.get('query', '')
        tablas = extraer_tablas_de_sql(query_sql)

        # Obtener ÚLTIMA EJECUCIÓN REAL
        ultima_ejecucion_real = None
        ultimo_estado = None

        try:
            runs = list(client.list_transfer_runs(parent=config.name))
            if runs:
                # Ordenar por run_time (más reciente primero)
                runs_sorted = sorted(runs, key=lambda x: x.run_time, reverse=True)
                ultimo_run = runs_sorted[0]
                ultima_ejecucion_real = ultimo_run.run_time.isoformat() if ultimo_run.run_time else None
                ultimo_estado = int(ultimo_run.state)
        except Exception as e:
            # Si no hay permisos o no hay runs, dejar None
            pass

        registro = {
            'Nombre': display_name,
            'Display Name': config.display_name,
            'User ID': config.user_id,
            'User Email': config.owner_info.email if config.owner_info and config.owner_info.email else None,
            'Estado Config': int(config.state),  # State del config
            'Ultimo Estado Run': ultimo_estado,  # State del último run
            'Disabled': config.disabled,
            'Schedule': config.schedule,
            'Dataset Destino': config.destination_dataset_id,
            'Num Tablas': len(tablas),
            'Tablas Usadas': ' | '.join(tablas),
            'Ultima Ejecucion Real': ultima_ejecucion_real,  # REAL, no next_run_time
            'Proxima Ejecucion': config.next_run_time.isoformat() if config.next_run_time else None,
            'Actualizacion': config.update_time.isoformat() if config.update_time else None,
            'Config ID': config.name.split('/')[-1],
            'Query SQL': query_sql
        }

        resultados.append(registro)

    print(f"   [OK] Procesadas todas las queries\n")

    # Exportar a Excel
    print("3. Exportando a Excel...")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archivo_salida = f'C:\\Users\\luis.figueredo\\Scheduled_Queries_REAL_{timestamp}.xlsx'

    df = pd.DataFrame(resultados)

    # Crear ranking de tablas
    todas_las_tablas = []
    for idx, row in df.iterrows():
        tablas_str = row['Tablas Usadas']
        if pd.notna(tablas_str) and tablas_str:
            tablas_list = tablas_str.split(' | ')
            todas_las_tablas.extend(tablas_list)

    from collections import Counter
    tabla_counter = Counter(todas_las_tablas)
    df_ranking = pd.DataFrame([
        {'Tabla': tabla, 'Num Queries': count}
        for tabla, count in tabla_counter.most_common(50)
    ])

    # Dependencias
    datos_dependencias = []
    for idx, row in df.iterrows():
        query_name = row['Nombre']
        tablas_str = row['Tablas Usadas']
        if pd.notna(tablas_str) and tablas_str:
            tablas_list = tablas_str.split(' | ')
            for tabla in tablas_list:
                datos_dependencias.append({
                    'Tabla': tabla,
                    'Query': query_name
                })

    df_dependencias = pd.DataFrame(datos_dependencias)

    # Exportar
    with pd.ExcelWriter(archivo_salida, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Scheduled Queries', index=False)
        df_dependencias.to_excel(writer, sheet_name='Dependencias', index=False)
        df_ranking.to_excel(writer, sheet_name='Ranking Tablas', index=False)

    print(f"   [OK] Archivo exportado: {archivo_salida}")

    # Estadísticas
    print("\n" + "=" * 80)
    print("ESTADÍSTICAS")
    print("=" * 80)
    print(f"Total: {len(df)}")
    print(f"Activas (disabled=False): {len(df[df['Disabled'] == False])}")
    print(f"Inactivas (disabled=True): {len(df[df['Disabled'] == True])}")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
