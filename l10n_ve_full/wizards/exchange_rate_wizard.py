# -*- coding: utf-8 -*-
"""
Venezuela360: Wizard — Carga masiva de Tasas BCV
==================================================
Permite cargar múltiples tasas BCV de una sola vez
(ej: pegar desde una tabla de la web del BCV).
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ExchangeRateWizardLine(models.TransientModel):
    _name = 'l10n_ve.exchange.rate.wizard.line'
    _description = 'Línea de carga masiva de tasa BCV'

    wizard_id = fields.Many2one('l10n_ve.exchange.rate.wizard', ondelete='cascade')
    date = fields.Date(string='Fecha', required=True)
    rate = fields.Float(string='Tasa (Bs/USD)', required=True, digits=(18, 6))
    source = fields.Selection([
        ('bcv', 'BCV'),
        ('seniat', 'SENIAT'),
        ('manual', 'Manual'),
    ], default='bcv', required=True)


class ExchangeRateWizard(models.TransientModel):
    """Wizard para registrar o importar múltiples tasas BCV de forma eficiente."""
    _name = 'l10n_ve.exchange.rate.wizard'
    _description = 'Wizard Carga Tasas BCV'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_from_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Origen',
        required=True,
        default=lambda self: self.env.ref('base.USD', raise_if_not_found=False),
    )
    currency_to_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda Destino (Bs)',
        required=True,
        default=lambda self: self.env['res.currency'].search(
            [('name', 'in', ['VES', 'VEF', 'VEB'])], limit=1
        ),
    )
    line_ids = fields.One2many(
        comodel_name='l10n_ve.exchange.rate.wizard.line',
        inverse_name='wizard_id',
        string='Tasas a Registrar',
    )
    overwrite_existing = fields.Boolean(
        string='Sobreescribir tasas existentes para la misma fecha',
        default=False,
    )

    def action_create_rates(self):
        """Crea las tasas BCV desde las líneas del wizard."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Ingresa al menos una línea con fecha y tasa.'))

        created, skipped, updated = 0, 0, 0
        ExchangeRate = self.env['l10n_ve.exchange.rate']

        for line in self.line_ids:
            existing = ExchangeRate.search([
                ('date', '=', line.date),
                ('company_id', '=', self.company_id.id),
                ('currency_from_id', '=', self.currency_from_id.id),
                ('currency_to_id', '=', self.currency_to_id.id),
            ], limit=1)

            if existing:
                if self.overwrite_existing:
                    existing.write({'rate': line.rate, 'source': line.source})
                    updated += 1
                else:
                    skipped += 1
            else:
                ExchangeRate.create({
                    'date': line.date,
                    'rate': line.rate,
                    'source': line.source,
                    'company_id': self.company_id.id,
                    'currency_from_id': self.currency_from_id.id,
                    'currency_to_id': self.currency_to_id.id,
                })
                created += 1

        msg = _(
            'Proceso completado:\n'
            '  ✅ Creadas: %(c)d\n'
            '  🔄 Actualizadas: %(u)d\n'
            '  ⏭️  Omitidas (ya existían): %(s)d'
        ) % {'c': created, 'u': updated, 's': skipped}

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tasas BCV registradas'),
                'message': msg,
                'type': 'success',
                'sticky': False,
            },
        }
