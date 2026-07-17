# -*- coding: utf-8 -*-
"""Servicio de consultas a BigQuery para el dashboard de Meta Ads."""
import logging

_logger = logging.getLogger(__name__)

try:
    from google.cloud import bigquery
    from google.api_core.exceptions import BadRequest
except Exception as e:  # pragma: no cover
    _logger.warning("google-cloud-bigquery no está instalado: %s", e)
    bigquery = None
    BadRequest = Exception


class BigQueryQueryService:
    """Ejecuta queries agregados contra las tablas de Meta Ads en BigQuery."""

    def __init__(self, project_id, credentials_json):
        if bigquery is None:
            raise RuntimeError(
                "La librería 'google-cloud-bigquery' no está instalada. "
                "Ejecute: pip install google-cloud-bigquery"
            )
        self.project_id = project_id
        import json
        from google.oauth2 import service_account
        if isinstance(credentials_json, str):
            creds_dict = json.loads(credentials_json)
        else:
            creds_dict = credentials_json
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        self.client = bigquery.Client(project=project_id, credentials=credentials)

    @staticmethod
    def _table_ref(project_id, dataset_name, table_name):
        return f"{project_id}.{dataset_name}.{table_name}"

    def _run_query(self, query, params=None):
        """Ejecuta una query parametrizada y retorna lista de dicts."""
        job_config = None
        if params:
            query_params = []
            for key, bq_type, value in params:
                query_params.append(
                    bigquery.ScalarQueryParameter(key, bq_type, value)
                )
            job_config = bigquery.QueryJobConfig(query_parameters=query_params)

        try:
            query_job = self.client.query(query, job_config=job_config)
            rows = query_job.result()
            return [dict(row) for row in rows]
        except BadRequest as e:
            _logger.error("BigQuery query error: %s", e)
            raise

    # -----------------------------------------------------------------
    # Métodos públicos para el dashboard
    # -----------------------------------------------------------------

    def get_kpis(self, table_ref, date_from, date_to, campaign_name=None):
        """KPIs agregados para el rango de fechas."""
        query = f"""
            SELECT
                SUM(spend) AS spend,
                SUM(impressions) AS impressions,
                SUM(clicks) AS clicks,
                SAFE_DIVIDE(SUM(clicks), SUM(impressions)) * 100 AS ctr,
                SAFE_DIVIDE(SUM(spend), SUM(clicks)) AS cpc,
                SUM(reach) AS reach,
                AVG(frequency) AS frequency
            FROM `{table_ref}`
            WHERE date BETWEEN @date_from AND @date_to
        """
        params = [
            ('date_from', 'DATE', date_from),
            ('date_to', 'DATE', date_to),
        ]
        if campaign_name:
            query += " AND campaign_name = @campaign_name"
            params.append(('campaign_name', 'STRING', campaign_name))

        rows = self._run_query(query, params)
        return rows[0] if rows else {}

    def get_daily_series(self, table_ref, date_from, date_to, campaign_name=None):
        """Serie diaria de spend, impressions, clicks."""
        query = f"""
            SELECT
                date,
                SUM(spend) AS spend,
                SUM(impressions) AS impressions,
                SUM(clicks) AS clicks,
                SAFE_DIVIDE(SUM(clicks), SUM(impressions)) * 100 AS ctr
            FROM `{table_ref}`
            WHERE date BETWEEN @date_from AND @date_to
        """
        params = [
            ('date_from', 'DATE', date_from),
            ('date_to', 'DATE', date_to),
        ]
        if campaign_name:
            query += " AND campaign_name = @campaign_name"
            params.append(('campaign_name', 'STRING', campaign_name))
        query += " GROUP BY date ORDER BY date ASC"

        return self._run_query(query, params)

    def get_campaigns(self, table_ref, date_from, date_to):
        """Tabla agregada por campaña."""
        query = f"""
            SELECT
                campaign_name,
                SUM(spend) AS spend,
                SUM(impressions) AS impressions,
                SUM(clicks) AS clicks,
                SAFE_DIVIDE(SUM(clicks), SUM(impressions)) * 100 AS ctr
            FROM `{table_ref}`
            WHERE date BETWEEN @date_from AND @date_to
            GROUP BY campaign_name
            ORDER BY impressions DESC
            LIMIT 100
        """
        params = [
            ('date_from', 'DATE', date_from),
            ('date_to', 'DATE', date_to),
        ]
        return self._run_query(query, params)

    def get_ads(self, table_ref, date_from, date_to, campaign_name=None):
        """Tabla agregada por anuncio (solo si la tabla tiene ad_name)."""
        query = f"""
            SELECT
                campaign_name,
                ad_name,
                SUM(spend) AS spend,
                SUM(impressions) AS impressions,
                SUM(clicks) AS clicks,
                SAFE_DIVIDE(SUM(clicks), SUM(impressions)) * 100 AS ctr
            FROM `{table_ref}`
            WHERE date BETWEEN @date_from AND @date_to
        """
        params = [
            ('date_from', 'DATE', date_from),
            ('date_to', 'DATE', date_to),
        ]
        if campaign_name:
            query += " AND campaign_name = @campaign_name"
            params.append(('campaign_name', 'STRING', campaign_name))
        query += """
            AND ad_name IS NOT NULL
            GROUP BY campaign_name, ad_name
            ORDER BY impressions DESC
            LIMIT 100
        """
        try:
            return self._run_query(query, params)
        except BadRequest:
            # La tabla puede no tener campo ad_name (nivel campaign)
            _logger.info('BigQuery: tabla %s no tiene ad_name, omitiendo ads', table_ref)
            return []

    def get_placements(self, table_ref, date_from, date_to, campaign_name=None):
        """Distribución por publisher_platform."""
        query = f"""
            SELECT
                COALESCE(publisher_platform, 'Desconocido') AS publisher_platform,
                SUM(spend) AS spend,
                SUM(impressions) AS impressions,
                SUM(clicks) AS clicks
            FROM `{table_ref}`
            WHERE date BETWEEN @date_from AND @date_to
        """
        params = [
            ('date_from', 'DATE', date_from),
            ('date_to', 'DATE', date_to),
        ]
        if campaign_name:
            query += " AND campaign_name = @campaign_name"
            params.append(('campaign_name', 'STRING', campaign_name))
        query += """
            GROUP BY publisher_platform
            ORDER BY impressions DESC
            LIMIT 50
        """
        return self._run_query(query, params)
