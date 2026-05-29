# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class MetaAdsDataset(models.Model):
    _name = 'meta.ads.dataset'
    _description = 'Configuración BigQuery para Meta Ads'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Nombre', required=True, tracking=True)
    project_id = fields.Char(
        string='Project ID',
        required=True,
        help='ID del proyecto en Google Cloud Platform',
        tracking=True,
    )
    dataset_name = fields.Char(
        string='Dataset Name',
        required=True,
        help='Nombre del dataset en BigQuery',
        tracking=True,
    )
    credentials_json = fields.Text(
        string='Credentials JSON',
        required=True,
        password=True,
        help='Contenido del archivo JSON de la Service Account de GCP',
        tracking=True,
    )
    is_active = fields.Boolean(string='Activo', default=True, tracking=True)
    table_prefix = fields.Char(
        string='Prefijo de Tablas',
        default='daily_',
        help='Prefijo para nombrar las tablas en BigQuery',
        tracking=True,
    )
    account_ids = fields.One2many(
        'meta.ads.account',
        'dataset_id',
        string='Cuentas Asociadas',
        readonly=True,
    )

    @api.constrains('dataset_name')
    def _check_dataset_name(self):
        for rec in self:
            name = (rec.dataset_name or '').strip()
            if ' ' in name:
                raise UserError(_('El nombre del dataset no puede contener espacios.'))

    def action_test_connection_bigquery(self):
        self.ensure_one()
        try:
            from ..services.bigquery_service import BigQueryService
            service = BigQueryService(
                project_id=self.project_id,
                credentials_json=self.credentials_json,
            )
            service.test_connection()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Conexión con BigQuery exitosa.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as e:
            _logger.exception('Error testeando conexión BigQuery')
            raise UserError(_('Error de conexión con BigQuery: %s') % str(e))
