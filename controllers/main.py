# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request, Response
import json
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class MetaAdsDashboardController(http.Controller):
    """Controlador para el dashboard de Meta Ads."""

    @http.route('/meta_reporting/dashboard', type='http', auth='user', website=False)
    def dashboard(self, **kwargs):
        """Renderiza la página del dashboard."""
        if not self._check_access():
            return request.redirect('/web/login')

        # Fechas por defecto: último mes completo
        date_to = fields.Date.context_today(request.env.user)
        date_from = date_to.replace(day=1) - timedelta(days=1)
        date_from = date_from.replace(day=1)

        accounts = request.env['meta.ads.account'].sudo().search([
            ('is_active', '=', True),
            ('dataset_id', '!=', False),
        ])

        values = {
            'default_date_from': date_from.strftime('%Y-%m-%d'),
            'default_date_to': date_to.strftime('%Y-%m-%d'),
            'accounts': accounts,
        }
        return request.render('odoo_meta_reporting.meta_ads_dashboard_template', values)

    @http.route('/meta_reporting/dashboard/data', type='http', auth='user', methods=['POST'], csrf=False)
    def dashboard_data(self, **kwargs):
        """Devuelve datos JSON para el dashboard."""
        if not self._check_access():
            return Response(
                json.dumps({'error': 'Acceso denegado'}),
                content_type='application/json',
                status=403,
            )

        try:
            params = json.loads(request.httprequest.data) or {}
        except Exception:
            params = {}

        account_id = params.get('account_id')
        date_from = params.get('date_from')
        date_to = params.get('date_to')
        campaign_name = params.get('campaign_name')

        if not account_id:
            return Response(
                json.dumps({'error': 'Debe seleccionar una cuenta'}),
                content_type='application/json',
                status=400,
            )

        account = request.env['meta.ads.account'].sudo().browse(int(account_id))
        if not account.exists():
            return Response(
                json.dumps({'error': 'Cuenta no encontrada'}),
                content_type='application/json',
                status=404,
            )

        # Fechas por defecto si no vienen
        if not date_from or not date_to:
            d_to = fields.Date.context_today(request.env.user)
            d_from = d_to - timedelta(days=6)
            date_from = d_from.strftime('%Y-%m-%d')
            date_to = d_to.strftime('%Y-%m-%d')

        try:
            from ..services.bigquery_query_service import BigQueryQueryService

            dataset = account.dataset_id
            job_model = request.env['meta.ads.sync.job'].sudo()

            def table_ref(level):
                table_name = job_model._get_table_name(dataset, level)
                return f"{dataset.project_id}.{dataset.dataset_name}.{table_name}"

            service = BigQueryQueryService(
                project_id=dataset.project_id,
                credentials_json=dataset.credentials_json,
            )

            # Consultar los 3 niveles (si existen las tablas)
            campaign_ref = table_ref('campaign')
            adset_ref = table_ref('adset')
            ad_ref = table_ref('ad')

            kpis = service.get_kpis(campaign_ref, date_from, date_to, campaign_name)
            conversion_kpis = service.get_conversion_kpis(campaign_ref, date_from, date_to, campaign_name)
            daily = service.get_daily_series(campaign_ref, date_from, date_to, campaign_name)
            campaigns = service.get_campaigns(campaign_ref, date_from, date_to)
            adsets = service.get_adsets(adset_ref, date_from, date_to, campaign_name)
            ads = service.get_ads(ad_ref, date_from, date_to, campaign_name)
            placements = service.get_placements(campaign_ref, date_from, date_to, campaign_name)

            def clean_value(v):
                if v is None:
                    return 0
                if isinstance(v, float):
                    if v != v:  # NaN
                        return 0
                    return round(v, 4)
                if hasattr(v, 'isoformat'):
                    # datetime.date o datetime.datetime
                    return v.isoformat()
                return v

            def clean_row(row):
                return {k: clean_value(v) for k, v in row.items()}

            result = {
                'success': True,
                'kpis': clean_row(kpis),
                'conversion_kpis': clean_row(conversion_kpis),
                'daily': [clean_row(r) for r in daily],
                'campaigns': [clean_row(r) for r in campaigns],
                'adsets': [clean_row(r) for r in adsets],
                'ads': [clean_row(r) for r in ads],
                'placements': [clean_row(r) for r in placements],
                'filters': {
                    'account_id': account_id,
                    'date_from': date_from,
                    'date_to': date_to,
                    'campaign_name': campaign_name,
                },
            }
            return Response(json.dumps(result), content_type='application/json')

        except Exception as e:
            _logger.exception('Error consultando dashboard de Meta Ads')
            return Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500,
            )

    def _check_access(self):
        """Verifica que el usuario pertenezca a los grupos del módulo."""
        user = request.env.user
        return (
            user.has_group('odoo_meta_reporting.group_meta_ads_user')
            or user.has_group('odoo_meta_reporting.group_meta_ads_manager')
        )
