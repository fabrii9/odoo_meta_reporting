# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class MetaAdsResyncWizard(models.TransientModel):
    _name = 'meta.ads.resync.wizard'
    _description = 'Wizard - Reprocesar Período Meta Ads'

    account_id = fields.Many2one(
        'meta.ads.account',
        string='Cuenta Meta',
        required=True,
        domain=[('is_active', '=', True)],
    )
    date_from = fields.Date(string='Fecha Desde', required=True)
    date_to = fields.Date(string='Fecha Hasta', required=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_('La fecha desde debe ser menor o igual a la fecha hasta.'))

    def action_resync_period(self):
        self.ensure_one()
        if not self.account_id:
            raise UserError(_('Debe seleccionar una cuenta.'))
        try:
            self.env['meta.ads.sync.job'].sudo().resync_account_period(
                account_id=self.account_id.id,
                date_from=self.date_from,
                date_to=self.date_to,
            )
            days = (self.date_to - self.date_from).days + 1
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _(
                        'Re-sync completado: %(days)s día(s) reprocesados para %(account)s.'
                    ) % {
                        'days': days,
                        'account': self.account_id.name,
                    },
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as e:
            _logger.exception('Error en re-sync')
            raise UserError(_('Error durante el reprocesamiento: %s') % str(e))
