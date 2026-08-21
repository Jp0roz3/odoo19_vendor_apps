# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de account.report para Reportes Financieros Bimoneda
=============================================================================
Añade el filtro bimoneda (Moneda: Bs.F / Moneda: $) a los reportes contables
(Balance General, Estado de Resultados, etc.).

Funcionalidades:
 1. Opción bimoneda `l10n_ve_currency` ('bs' o 'usd').
 2. Recálculo dinámico de cifras a Dólares ($) usando la Tasa Oficial BCV.
 3. Badge indicador `En .Bs.F` / `En .$` y menú desplegable interactivo.

Autor: JeanPerozo / Nubelco
"""
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AccountReport(models.Model):
    _inherit = 'account.report'

    filter_l10n_ve_currency = fields.Boolean(
        string="Filtro Bimoneda Dual (Bs.F / $)",
        default=True,
        compute='_compute_filter_l10n_ve_currency',
        store=True,
        readonly=False,
    )

    @api.depends('root_report_id')
    def _compute_filter_l10n_ve_currency(self):
        for report in self:
            report.filter_l10n_ve_currency = True

    def _get_options(self, previous_options=None):
        options = super()._get_options(previous_options)
        
        # Activar el filtro bimoneda para el usuario
        selected_currency = 'bs'
        if previous_options and 'l10n_ve_currency' in previous_options:
            selected_currency = previous_options['l10n_ve_currency']

        options['filter_l10n_ve_currency'] = True
        options['l10n_ve_currency'] = selected_currency
        options['l10n_ve_currency_label'] = '$' if selected_currency == 'usd' else 'Bs.F'
        options['l10n_ve_badge_label'] = 'En .$' if selected_currency == 'usd' else 'En .Bs.F'

        return options

    def _format_value(self, options, value, figure_type, blank_if_zero=False, currency=None):
        if options and options.get('filter_l10n_ve_currency') and options.get('l10n_ve_currency') == 'usd':
            if figure_type == 'monetary' and isinstance(value, (int, float)):
                date_to = (options.get('date', {}) or {}).get('date_to') or fields.Date.context_today(self)
                rate_bcv = 777.4161
                company = self.env.company
                bs_curr = getattr(company, 'l10n_ve_currency_bs_id', None)
                if bs_curr:
                    rate_rec = self.env['res.currency.rate'].search([
                        ('currency_id', '=', bs_curr.id),
                        ('name', '<=', date_to),
                    ], order='name desc', limit=1)
                    if rate_rec and rate_rec.rate > 0:
                        rate_bcv = rate_rec.rate if rate_rec.rate > 1.0 else (1.0 / rate_rec.rate)

                val_usd = value / rate_bcv if rate_bcv else value
                formatted = f"{val_usd:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                return f"$ {formatted}"

        elif options and options.get('filter_l10n_ve_currency') and options.get('l10n_ve_currency') == 'bs':
            if figure_type == 'monetary' and isinstance(value, (int, float)):
                formatted = f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                return f"{formatted} Bs.F"

        return super()._format_value(options, value, figure_type, blank_if_zero=blank_if_zero, currency=currency)
