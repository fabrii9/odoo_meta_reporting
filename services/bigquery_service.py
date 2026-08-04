# -*- coding: utf-8 -*-
import logging
import json

_logger = logging.getLogger(__name__)

try:
    from google.cloud import bigquery
    from google.cloud.bigquery import SchemaField
    from google.api_core.exceptions import NotFound, Conflict, BadRequest
except Exception as e:  # pragma: no cover
    _logger.warning("google-cloud-bigquery no está instalado: %s", e)
    bigquery = None
    SchemaField = None
    NotFound = Exception
    Conflict = Exception
    BadRequest = Exception


class BigQueryService:
    def __init__(self, project_id, credentials_json):
        if bigquery is None:
            raise RuntimeError(
                "La librería 'google-cloud-bigquery' no está instalada. "
                "Ejecute: pip install google-cloud-bigquery"
            )
        self.project_id = project_id
        # credentials_json puede ser string o dict
        if isinstance(credentials_json, str):
            creds_dict = json.loads(credentials_json)
        else:
            creds_dict = credentials_json
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        self.client = bigquery.Client(project=project_id, credentials=credentials)

    def test_connection(self):
        """Verifica acceso al proyecto listando datasets."""
        datasets = list(self.client.list_datasets())
        _logger.info('BigQuery connection OK. Datasets encontrados: %s', len(datasets))
        return True

    def ensure_table(self, dataset_name, table_name, level='campaign'):
        """Crea el dataset y tabla si no existen."""
        dataset_ref = f"{self.project_id}.{dataset_name}"
        table_ref = f"{dataset_ref}.{table_name}"

        # Crear dataset si no existe
        try:
            self.client.get_dataset(dataset_ref)
        except NotFound:
            _logger.info('BigQuery: creando dataset %s', dataset_name)
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            self.client.create_dataset(dataset, exists_ok=True)

        # Crear tabla si no existe
        try:
            self.client.get_table(table_ref)
        except NotFound:
            _logger.info('BigQuery: creando tabla %s', table_ref)
            schema = self._build_schema(level)
            table = bigquery.Table(table_ref, schema=schema)
            # Sin partición para compatibilidad con DML queries simples
            self.client.create_table(table, exists_ok=True)

        return True

    def upsert_daily_data(self, dataset_name, table_name, date_str, records):
        """DELETE + INSERT para una fecha específica."""
        table_ref = f"{self.project_id}.{dataset_name}.{table_name}"

        # 1) DELETE
        delete_query = f"""
            DELETE FROM `{table_ref}`
            WHERE date = @sync_date
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("sync_date", "DATE", date_str),
            ]
        )
        _logger.info('BigQuery: DELETE %s WHERE date=%s', table_ref, date_str)
        delete_job = self.client.query(delete_query, job_config=job_config)
        delete_job.result()

        # 2) INSERT
        if not records:
            return True

        errors = self.client.insert_rows_json(table_ref, records)
        if errors:
            _logger.error('BigQuery insert errors: %s', errors)
            raise RuntimeError(f"Error insertando en BigQuery: {errors}")

        _logger.info(
            'BigQuery: INSERT %s registros en %s para date=%s',
            len(records), table_ref, date_str,
        )
        return True

    def _build_schema(self, level='campaign'):
        """Define schema de tablas según nivel."""
        base = [
            SchemaField("date", "DATE", mode="REQUIRED"),
            SchemaField("campaign_id", "STRING"),
            SchemaField("campaign_name", "STRING"),
            SchemaField("spend", "FLOAT64"),
            SchemaField("impressions", "INT64"),
            SchemaField("clicks", "INT64"),
            SchemaField("ctr", "FLOAT64"),
            SchemaField("cpc", "FLOAT64"),
            SchemaField("cpm", "FLOAT64"),
            SchemaField("reach", "INT64"),
            SchemaField("frequency", "FLOAT64"),
            SchemaField("purchase_roas", "STRING"),
            SchemaField("actions", "STRING"),
            SchemaField("cost_per_action_type", "STRING"),
        ]

        if level in ('adset', 'ad'):
            base.insert(3, SchemaField("adset_id", "STRING"))
            base.insert(4, SchemaField("adset_name", "STRING"))

        if level == 'ad':
            base.insert(5, SchemaField("ad_id", "STRING"))
            base.insert(6, SchemaField("ad_name", "STRING"))
            # Creative data para mostrar imágenes en Looker Studio
            base.append(SchemaField("thumbnail_url", "STRING"))
            base.append(SchemaField("image_url", "STRING"))
            base.append(SchemaField("creative_type", "STRING"))
            base.append(SchemaField("creative_name", "STRING"))

        return base
