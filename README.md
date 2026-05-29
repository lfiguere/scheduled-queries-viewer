# Scheduled Queries Viewer

Aplicación web para visualizar y monitorear las scheduled queries de BigQuery.

## Características

- Visualización de 169 scheduled queries
- Estado en tiempo real (SUCCEEDED, FAILED, RUNNING)
- Filtros por estado y búsqueda por nombre
- Actualización bajo demanda desde BigQuery Data Transfer API
- Conversión automática de zonas horarias (UTC → Madrid)

## Tecnologías

- Streamlit
- Google Cloud BigQuery
- Google Cloud BigQuery Data Transfer API
- Python 3.12

## Configuración

Requiere credenciales de Google Cloud con permisos para:
- BigQuery Data Transfer (lectura)
- BigQuery (lectura/escritura en dataset ZZ_WORK)

## Autor

Luis Figueredo - MasOrange
