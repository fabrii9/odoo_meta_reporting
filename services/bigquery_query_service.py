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
                SAFE_DIVIDE(SUM(spend), SUM(impressions)) * 1000 AS cpm,
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
        """Serie diaria de spend, impressions, clicks y ratios."""
        query = f"""
            SELECT
                date,
                SUM(spend) AS spend,
                SUM(impressions) AS impressions,
                SUM(clicks) AS clicks,
                SAFE_DIVIDE(SUM(clicks), SUM(impressions)) * 100 AS ctr,
                SAFE_DIVIDE(SUM(spend), SUM(clicks)) AS cpc,
                SAFE_DIVIDE(SUM(spend), SUM(impressions)) * 1000 AS cpm
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
        """Tabla agregada por campaña, incluye ROAS ponderado por gasto."""
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
        campaigns = self._run_query(query, params)

        # ROAS por campaña (ponderado por gasto diario)
        try:
            roas_map = self._get_roas_map(table_ref, date_from, date_to, 'campaign_name')
            for row in campaigns:
                row['roas'] = roas_map.get(row.get('campaign_name'))
        except (BadRequest, NotFound):
            _logger.info('BigQuery: no se pudo calcular ROAS por campaña en %s', table_ref)

        return campaigns

    def _get_roas_map(self, table_ref, date_from, date_to, group_field):
        """ROAS ponderado por gasto agrupado por un campo. Retorna {grupo: roas}."""
        query = f"""
            SELECT
                {group_field} AS grp,
                SAFE_DIVIDE(
                    SUM(SAFE_CAST(JSON_VALUE(r, '$.value') AS FLOAT64) * spend),
                    SUM(spend)
                ) AS roas
            FROM `{table_ref}`,
            UNNEST(JSON_EXTRACT_ARRAY(purchase_roas)) AS r
            WHERE date BETWEEN @date_from AND @date_to
            AND JSON_VALUE(r, '$.action_type') IN ('purchase', 'omni_purchase')
            GROUP BY {group_field}
        """
        params = [
            ('date_from', 'DATE', date_from),
            ('date_to', 'DATE', date_to),
        ]
        rows = self._run_query(query, params)
        return {row['grp']: row['roas'] for row in rows}

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
        """Tabla agregada por anuncio con creatividades, compras y ROAS."""
        query = f"""
            SELECT
                campaign_name,
                ad_name,
                ANY_VALUE(thumbnail_url) AS thumbnail_url,
                ANY_VALUE(image_url) AS image_url,
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
            ads = self._run_query(query, params)
        except (BadRequest, NotFound):
            # La tabla puede no existir o no tener las columnas de creatividades:
            # fallback a la query original sin imágenes
            _logger.info('BigQuery: %s sin columnas de creatividades, usando fallback', table_ref)
            return self._get_ads_basic(table_ref, date_from, date_to, campaign_name)

        # Compras y ROAS por anuncio (desde JSON histórico de actions/purchase_roas)
        try:
            purchases_map = self._get_purchases_map(table_ref, date_from, date_to, campaign_name)
            roas_map = self._get_roas_map(table_ref, date_from, date_to, 'ad_name')
            for row in ads:
                row['purchases'] = purchases_map.get(row.get('ad_name'))
                row['roas'] = roas_map.get(row.get('ad_name'))
        except (BadRequest, NotFound):
            _logger.info('BigQuery: no se pudieron calcular compras/ROAS por anuncio')

        return ads

    def _get_ads_basic(self, table_ref, date_from, date_to, campaign_name=None):
        """Query original de anuncios sin columnas de creatividades."""
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
            _logger.info('BigQuery: tabla %s no existe o no tiene ad_name, omitiendo ads', table_ref)
            return []

    def _get_purchases_map(self, table_ref, date_from, date_to, campaign_name=None):
        """Compras por anuncio desde el JSON de actions. Retorna {ad_name: purchases}."""
        query = f"""
            SELECT
                ad_name,
                SUM(SAFE_CAST(JSON_VALUE(a, '$.value') AS FLOAT64)) AS purchases
            FROM `{table_ref}`,
            UNNEST(JSON_EXTRACT_ARRAY(actions)) AS a
            WHERE date BETWEEN @date_from AND @date_to
            AND JSON_VALUE(a, '$.action_type') IN ('purchase', 'omni_purchase')
        """
        params = [
            ('date_from', 'DATE', date_from),
            ('date_to', 'DATE', date_to),
        ]
        if campaign_name:
            query += " AND campaign_name = @campaign_name"
            params.append(('campaign_name', 'STRING', campaign_name))
        query += " GROUP BY ad_name"
        rows = self._run_query(query, params)
        return {row['ad_name']: row['purchases'] for row in rows}

    def get_funnel(self, table_ref, date_from, date_to, campaign_name=None):
        """
        Embudo completo: impresiones → clics en enlace → vistas de página →
        agregados al carrito → checkout iniciado → compras.
        Incluye costo por paso (gasto / cantidad).
        """
        params = [
            ('date_from', 'DATE', date_from),
            ('date_to', 'DATE', date_to),
        ]

        # Totales base (con fallback si inline_link_clicks aún no existe)
        totals_query = f"""
            SELECT
                SUM(spend) AS spend,
                SUM(impressions) AS impressions,
                SUM(inline_link_clicks) AS link_clicks,
                SUM(clicks) AS clicks
            FROM `{table_ref}`
            WHERE date BETWEEN @date_from AND @date_to
        """
        if campaign_name:
            totals_query += " AND campaign_name = @campaign_name"
            totals_params = params + [('campaign_name', 'STRING', campaign_name)]
        else:
            totals_params = params
        try:
            rows = self._run_query(totals_query, totals_params)
            totals = rows[0] if rows else {}
        except BadRequest as e:
            if 'inline_link_clicks' not in str(e):
                raise
            fallback_query = totals_query.replace(
                'SUM(inline_link_clicks) AS link_clicks,', ''
            )
            rows = self._run_query(fallback_query, totals_params)
            totals = rows[0] if rows else {}

        # Totales por tipo de acción
        actions_query = f"""
            SELECT
                JSON_VALUE(a, '$.action_type') AS action_type,
                SUM(SAFE_CAST(JSON_VALUE(a, '$.value') AS FLOAT64)) AS total
            FROM `{table_ref}`,
            UNNEST(JSON_EXTRACT_ARRAY(actions)) AS a
            WHERE date BETWEEN @date_from AND @date_to
        """
        if campaign_name:
            actions_query += " AND campaign_name = @campaign_name"
        actions_query += " GROUP BY action_type"
        action_totals = {}
        try:
            for row in self._run_query(actions_query, totals_params):
                action_totals[row['action_type']] = row['total'] or 0
        except BadRequest:
            _logger.info('BigQuery: no se pudieron extraer acciones para el embudo')

        def action_count(*types):
            return sum(action_totals.get(t, 0) for t in types)

        spend = totals.get('spend') or 0
        link_clicks = totals.get('link_clicks') or totals.get('clicks') or 0

        steps = [
            {'key': 'impressions', 'label': 'Impresiones', 'count': totals.get('impressions') or 0},
            {'key': 'link_clicks', 'label': 'Clics en enlace', 'count': link_clicks},
            {'key': 'landing_page_view', 'label': 'Visitas a la página', 'count': action_count('landing_page_view')},
            {'key': 'add_to_cart', 'label': 'Agregados al carrito', 'count': action_count('add_to_cart', 'omni_add_to_cart')},
            {'key': 'initiate_checkout', 'label': 'Checkout iniciado', 'count': action_count('initiate_checkout', 'omni_initiated_checkout')},
            {'key': 'purchase', 'label': 'Compras', 'count': action_count('purchase', 'omni_purchase')},
        ]

        # Costo por paso y tasa de conversión entre pasos
        prev_count = None
        for step in steps:
            count = step['count'] or 0
            step['cost'] = (spend / count) if count else None
            step['rate'] = (count / prev_count * 100) if prev_count else None
            prev_count = count if count else prev_count

        return steps

    def get_ratio_series(self, table_ref, date_from, date_to, campaign_name=None):
        """Serie diaria extendida: ctr, cpc, cpm y roas ponderado."""
        daily = self.get_daily_series(table_ref, date_from, date_to, campaign_name)

        # ROAS diario ponderado por gasto
        query = f"""
            SELECT
                date,
                SAFE_DIVIDE(
                    SUM(SAFE_CAST(JSON_VALUE(r, '$.value') AS FLOAT64) * spend),
                    SUM(spend)
                ) AS roas
            FROM `{table_ref}`,
            UNNEST(JSON_EXTRACT_ARRAY(purchase_roas)) AS r
            WHERE date BETWEEN @date_from AND @date_to
            AND JSON_VALUE(r, '$.action_type') IN ('purchase', 'omni_purchase')
        """
        params = [
            ('date_from', 'DATE', date_from),
            ('date_to', 'DATE', date_to),
        ]
        if campaign_name:
            query += " AND campaign_name = @campaign_name"
            params.append(('campaign_name', 'STRING', campaign_name))
        query += " GROUP BY date ORDER BY date ASC"

        try:
            roas_rows = self._run_query(query, params)
            roas_map = {str(row['date']): row['roas'] for row in roas_rows}
            for row in daily:
                row['roas'] = roas_map.get(str(row.get('date')))
        except BadRequest:
            _logger.info('BigQuery: no se pudo calcular ROAS diario')

        return daily

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
