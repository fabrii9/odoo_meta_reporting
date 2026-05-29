# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class MetaAdsSyncManualWizard(models.TransientModel):
    _name = 'meta.ads.sync.manual.wizard'
    _description = 'Wizard - Sincronizar Meta Ads Ahora'

    account_id = fields.Many2one(
        'meta.ads.account',
        string='Cuenta Meta',
        required=True,
        domain=[('is_active', '=', True)],
    )
    sync_date = fields.Date(
        string='Fecha a Sincronizar',
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )

    def action_sync_now(self):
        self.ensure_one()
        if not self.account_id:
            raise UserError(_('Debe seleccionar una cuenta.'))
        try:
            self.env['meta.ads.sync.job'].sudo().sync_account_manual(
                account_id=self.account_id.id,
                date_from=self.sync_date,
                date_to=self.sync_date,
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _(
                        'Sincronización completada para %(account)s el %(date)s.'
                    ) % {
                        'account': self.account_id.name,
                        'date': self.sync_date,
                    },
                    'type': 'success',
                    'sticky': False,
                },
            }
        except Exception as e:
            _logger.exception('Error en sync manual')
            raise UserError(_('Error durante la sincronización: %s') % str(e))
