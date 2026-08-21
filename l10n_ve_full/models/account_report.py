# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de account.report para Reportes Financieros Bimoneda
=============================================================================
Soporta Odoo Enterprise `account_reports` (`get_options`).
Añade el botón [💵 Moneda: Bs.F / $] en la barra de acciones superior
y recalcula dinámicamente el Balance General entre Bolívares (Bs.F) y Dólares ($).

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
        store=False,
    )

    def _compute_filter_l10n_ve_currency(self):
        for report in self:
            report.filter_l10n_ve_currency = True

    def get_options(self, previous_options=None):
        options = super().get_options(previous_options)
        
        selected_currency = 'bs'
        if previous_options and isinstance(previous_options, dict) and 'l10n_ve_currency' in previous_options:
            selected_currency = previous_options['l10n_ve_currency']

        options['filter_l10n_ve_currency'] = True
        options['l10n_ve_currency'] = selected_currency
        options['l10n_ve_currency_label'] = '$' if selected_currency == 'usd' else 'Bs.F'
        options['l10n_ve_badge_label'] = 'En .$' if selected_currency == 'usd' else 'En .Bs.F'

        # Agregar botón de Moneda en la barra de acciones superior (junto a PDF / XLSX)
        if 'buttons' in options and isinstance(options['buttons'], list):
            btn_label = f"💵 Moneda: {options['l10n_ve_currency_label']}"
            # Evitar duplicados
            options['buttons'] = [b for b in options['buttons'] if not (isinstance(b, dict) and b.get('action') == 'action_switch_l10n_ve_currency')]
            options['buttons'].append({
                'name': btn_label,
                'action': 'action_switch_l10n_ve_currency',
                'sequence': 1,
            })

        return options

    def _get_options(self, previous_options=None):
        if hasattr(super(), '_get_options'):
            options = super()._get_options(previous_options)
        else:
            options = {}
        return self.get_options(previous_options or options)

    def action_switch_l10n_ve_currency(self, options):
        """Acción ejecutada al hacer clic en el botón de Moneda en el reporte."""
        current = options.get('l10n_ve_currency', 'bs')
        new_currency = 'usd' if current == 'bs' else 'bs'
        options['l10n_ve_currency'] = new_currency
        options['l10n_ve_currency_label'] = '$' if new_currency == 'usd' else 'Bs.F'
        options['l10n_ve_badge_label'] = 'En .$' if new_currency == 'usd' else 'En .Bs.F'

        # Retornar recarga reactiva de la vista del reporte
        return {
            'type': 'ir.actions.client',
            'tag': 'account_report',
            'options': options,
            'ignore_session': 'both',
        }

    def _format_value(self, options, value, figure_type, blank_if_zero=False, currency=None):
        if options and isinstance(options, dict) and options.get('l10n_ve_currency') == 'usd':
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

        elif options and isinstance(options, dict) and options.get('l10n_ve_currency') == 'bs':
            if figure_type == 'monetary' and isinstance(value, (int, float)):
                formatted = f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                return f"{formatted} Bs.F"

        return super()._format_value(options, value, figure_type, blank_if_zero=blank_if_zero, currency=currency)
