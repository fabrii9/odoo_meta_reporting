# -*- coding: utf-8 -*-
from odoo import models, fields


class MetaAdsSyncLog(models.Model):
    _name = 'meta.ads.sync.log'
    _description = 'Log de Sincronización Meta Ads'
    _order = 'sync_date desc, id desc'
    _inherit = ['mail.thread']

    account_id = fields.Many2one(
        'meta.ads.account',
        string='Cuenta Meta',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sync_date = fields.Datetime(string='Fecha de Sync', default=lambda self: fields.Datetime.now())
    status = fields.Selection(
        [
            ('success', 'Éxito'),
            ('partial', 'Parcial'),
            ('error', 'Error'),
        ],
        string='Estado',
        required=True,
        index=True,
    )
    records_processed = fields.Integer(string='Registros Procesados', default=0)
    error_message = fields.Text(string='Mensaje de Error')
    execution_time = fields.Float(string='Tiempo de Ejecución (segundos)', digits=(12, 2))
    date_from = fields.Date(string='Fecha Desde')
    date_to = fields.Date(string='Fecha Hasta')
    level = fields.Selection(
        [
            ('campaign', 'Campaña'),
            ('adset', 'Adset'),
            ('ad', 'Anuncio'),
        ],
        string='Nivel',
    )
    sync_type = fields.Selection(
        [
            ('automatic', 'Automático'),
            ('manual', 'Manual'),
            ('resync', 'Re-sync'),
        ],
        string='Tipo de Sync',
        default='automatic',
    )
