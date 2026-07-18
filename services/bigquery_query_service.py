# -*- coding: utf-8 -*-
"""Servicio de consultas a BigQuery para el dashboard de Meta Ads."""
import logging

_logger = logging.getLogger(__name__)

try:
    from google.cloud import bigquery
    from google.api_core.exceptions import BadRequest, NotFound
except Exception as e:  # pragma: no cover
    _logger.warning("google-cloud-bigquery no está instalado: %s", e)
    bigquery = None
    BadRequest = Exception
    NotFound = Exception


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

    def get_adsets(self, table_ref, date_from, date_to, campaign_name=None):
        """Tabla agregada por adset (solo si la tabla tiene adset_name)."""
        query = f"""
            SELECT
                campaign_name,
                adset_name,
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
            AND adset_name IS NOT NULL
            GROUP BY campaign_name, adset_name
            ORDER BY impressions DESC
            LIMIT 100
        """
        try:
            return self._run_query(query, params)
        except (BadRequest, NotFound):
            _logger.info('BigQuery: tabla %s no existe o no tiene adset_name, omitiendo adsets', table_ref)
            return []

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
        except (BadRequest, NotFound):
            # La tabla puede no existir o no tener campo ad_name
            _logger.info('BigQuery: tabla %s no existe o no tiene ad_name, omitiendo ads', table_ref)
            return []

    def get_conversion_kpis(self, table_ref, date_from, date_to, campaign_name=None):
        """KPIs de conversión: purchases, purchase_value, roas, cost_per_purchase."""
        query = f"""
            WITH purchases AS (
                SELECT
                    SUM(CAST(JSON_VALUE(action, '$.value') AS INT64)) AS purchases,
                    SUM(CAST(JSON_VALUE(action, '$.value') AS FLOAT64)) AS purchase_value
                FROM `{table_ref}`,
                UNNEST(JSON_EXTRACT_ARRAY(actions)) AS action
                WHERE date BETWEEN @date_from AND @date_to
                AND JSON_VALUE(action, '$.action_type') = 'purchase'
            ),
            roas AS (
                SELECT
                    AVG(CAST(JSON_VALUE(roas, '$.value') AS FLOAT64)) AS roas
                FROM `{table_ref}`,
                UNNEST(JSON_EXTRACT_ARRAY(purchase_roas)) AS roas
                WHERE date BETWEEN @date_from AND @date_to
                AND JSON_VALUE(roas, '$.action_type') = 'purchase'
            ),
            spend AS (
                SELECT SUM(spend) AS total_spend
                FROM `{table_ref}`
                WHERE date BETWEEN @date_from AND @date_to
            )
            SELECT
                purchases.purchases,
                purchases.purchase_value,
                roas.roas,
                SAFE_DIVIDE(spend.total_spend, purchases.purchases) AS cost_per_purchase
            FROM purchases, roas, spend
        """
        params = [
            ('date_from', 'DATE', date_from),
            ('date_to', 'DATE', date_to),
        ]
        try:
            rows = self._run_query(query, params)
            return rows[0] if rows else {}
        except BadRequest:
            _logger.info('BigQuery: no se pudieron extraer conversiones de %s', table_ref)
            return {}

    def get_placements(self, table_ref, date_from, date_to, campaign_name=None):
        """Distribución por publisher_platform. Fallback si la columna aun no existe."""
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
        try:
            return self._run_query(query, params)
        except (BadRequest, NotFound) as e:
            if 'publisher_platform' not in str(e):
                raise
            # Fallback: tabla aun no tiene la columna o no existe, devolvemos un solo bucket agregado
            _logger.warning('BigQuery: columna publisher_platform no existe en %s, usando fallback', table_ref)
            fallback_query = f"""
                SELECT
                    'Desconocido' AS publisher_platform,
                    SUM(spend) AS spend,
                    SUM(impressions) AS impressions,
                    SUM(clicks) AS clicks
                FROM `{table_ref}`
                WHERE date BETWEEN @date_from AND @date_to
            """
            if campaign_name:
                fallback_query += " AND campaign_name = @campaign_name"
            return self._run_query(fallback_query, params)
