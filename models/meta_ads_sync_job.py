# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import time
from datetime import datetime, timedelta, date as dt_date

_logger = logging.getLogger(__name__)


class MetaAdsSyncJob(models.TransientModel):
    _name = 'meta.ads.sync.job'
    _description = 'Orquestador de Sincronización Meta Ads'

    # Campos transitorios para tracking de ejecución
    name = fields.Char(string='Descripción')
    state = fields.Selection(
        [
            ('draft', 'Pendiente'),
            ('running', 'Ejecutando'),
            ('done', 'Completado'),
            ('error', 'Error'),
        ],
        string='Estado',
        default='draft',
    )

    # -----------------------------------------------------------------
    # Métodos públicos orquestadores
    # -----------------------------------------------------------------

    @api.model
    def sync_meta_ads_data(self):
        """Método invocado por el cron diario. Sincroniza 'ayer' para todas las cuentas activas."""
        today_str = fields.Date.context_today(self)
        today_date = datetime.strptime(today_str, '%Y-%m-%d').date()
        yesterday = today_date - timedelta(days=1)
        accounts = self.env['meta.ads.account'].sudo().search([
            ('is_active', '=', True),
            ('dataset_id', '!=', False),
        ])
        if not accounts:
            _logger.info('Meta Ads Sync: no hay cuentas activas para sincronizar.')
            return True

        for account in accounts:
            ok, error_msg = self._run_sync(
                account=account,
                date_from=yesterday,
                date_to=yesterday,
                sync_type='automatic',
            )
            if not ok:
                _logger.warning('Meta Ads Sync automático falló para cuenta %s: %s', account.name, error_msg)
        return True

    @api.model
    def sync_account_manual(self, account_id, date_from, date_to):
        """Sync manual para una cuenta y rango de fechas."""
        account = self.env['meta.ads.account'].sudo().browse(account_id)
        if not account.exists():
            raise UserError(_('La cuenta seleccionada no existe.'))
        ok, error_msg = self._run_sync(
            account=account,
            date_from=self._to_date(date_from),
            date_to=self._to_date(date_to),
            sync_type='manual',
        )
        if not ok:
            raise UserError(_('Error durante la sincronización:\n%s') % (error_msg or 'Revise los logs para más detalles.'))
        return True

    @api.model
    def resync_account_period(self, account_id, date_from, date_to):
        """Reprocesa un período completo (DELETE + INSERT por cada fecha)."""
        account = self.env['meta.ads.account'].sudo().browse(account_id)
        if not account.exists():
            raise UserError(_('La cuenta seleccionada no existe.'))
        d_from = self._to_date(date_from)
        d_to = self._to_date(date_to)
        current = d_from
        errors = []
        while current <= d_to:
            ok, error_msg = self._run_sync(
                account=account,
                date_from=current,
                date_to=current,
                sync_type='resync',
            )
            if not ok:
                errors.append(f"{current}: {error_msg or 'Error desconocido'}")
            current += timedelta(days=1)
        if errors:
            raise UserError(
                _('La sincronización falló para las siguientes fechas:\n%s') % '\n'.join(errors)
            )
        return True

    # -----------------------------------------------------------------
    # Núcleo del ETL
    # -----------------------------------------------------------------

    def _run_sync(self, account, date_from, date_to, sync_type='automatic'):
        """Ejecuta el flujo ETL completo para una cuenta y rango de fechas.
        Retorna (True, None) si tuvo éxito, (False, error_message) en caso de error."""
        start_time = time.time()
        account.sudo().write({'sync_status': 'running'})

        log_vals = {
            'account_id': account.id,
            'sync_date': fields.Datetime.now(),
            'status': 'success',
            'records_processed': 0,
            'date_from': date_from,
            'date_to': date_to,
            'level': account.sync_level,
            'sync_type': sync_type,
        }
        error_msg = None

        try:
            # 1) Extraer de Meta
            _logger.info(
                'Meta Ads Sync [%s]: extrayendo %s - %s (nivel=%s)',
                account.name, date_from, date_to, account.sync_level,
            )
            records = self._fetch_from_meta(account, date_from, date_to)

            if not records:
                _logger.info('Meta Ads Sync [%s]: sin datos para el período.', account.name)
                log_vals['status'] = 'success'
                log_vals['records_processed'] = 0
            else:
                # 2) Cargar en BigQuery
                _logger.info(
                    'Meta Ads Sync [%s]: insertando %s registros en BigQuery',
                    account.name, len(records),
                )
                self._upsert_to_bigquery(account, records, date_from, date_to)
                log_vals['records_processed'] = len(records)

            account.sudo().write({
                'last_sync': fields.Datetime.now(),
                'sync_status': 'success',
            })

        except Exception as e:
            _logger.exception('Meta Ads Sync [%s]: error', account.name)
            account.sudo().write({'sync_status': 'error'})
            log_vals['status'] = 'error'
            error_msg = str(e)
            log_vals['error_message'] = error_msg

        finally:
            log_vals['execution_time'] = round(time.time() - start_time, 2)
            self.env['meta.ads.sync.log'].sudo().create(log_vals)

        if error_msg:
            return False, error_msg
        return True, None

    def _fetch_from_meta(self, account, date_from, date_to):
        """Llama al servicio de Meta y retorna registros normalizados."""
        from ..services.meta_api_service import MetaApiService
        service = MetaApiService(
            app_id=account.app_id,
            app_secret=account.app_secret,
            access_token=account.access_token,
        )
        return service.fetch_insights(
            account_id=account._get_clean_account_id(),
            date_from=date_from,
            date_to=date_to,
            level=account.sync_level,
        )

    def _upsert_to_bigquery(self, account, records, date_from, date_to):
        """Estrategia DELETE + INSERT en BigQuery."""
        from ..services.bigquery_service import BigQueryService
        dataset = account.dataset_id
        service = BigQueryService(
            project_id=dataset.project_id,
            credentials_json=dataset.credentials_json,
        )
        table_name = self._get_table_name(dataset, account.sync_level)

        # Asegurar que exista la tabla
        service.ensure_table(
            dataset_name=dataset.dataset_name,
            table_name=table_name,
            level=account.sync_level,
        )

        # Upsert por cada fecha dentro del rango
        dates = self._date_range(date_from, date_to)
        for d in dates:
            day_records = [r for r in records if r.get('date') == str(d)]
            if day_records:
                service.upsert_daily_data(
                    dataset_name=dataset.dataset_name,
                    table_name=table_name,
                    date_str=str(d),
                    records=day_records,
                )
        return True

    @staticmethod
    def _get_table_name(dataset, level):
        prefix = (dataset.table_prefix or 'daily_').strip()
        mapping = {
            'campaign': 'campaign_stats',
            'adset': 'adset_stats',
            'ad': 'ad_stats',
        }
        return f"{prefix}{mapping.get(level, 'campaign_stats')}"

    def _date_range(self, date_from, date_to):
        """Genera lista de fechas entre date_from y date_to inclusive."""
        d_from = self._to_date(date_from)
        d_to = self._to_date(date_to)
        dates = []
        current = d_from
        while current <= d_to:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    @staticmethod
    def _to_date(value):
        """Convierte string o datetime.date a datetime.date."""
        if isinstance(value, dt_date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value, '%Y-%m-%d').date()
        raise ValueError(_('Tipo de fecha no soportado: %s') % type(value))
