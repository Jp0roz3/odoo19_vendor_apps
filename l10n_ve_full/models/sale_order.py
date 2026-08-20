# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de sale.order
======================================
Asegura que el módulo de Ventas utilice la Tarifa Principal en USD por defecto
y calcule la equivalencia en Bolívares (Bs.) usando la tasa BCV del día.
"""
from odoo import models, fields, api, _
import sys

if 'odoo.addons.sale' in sys.modules:
    class SaleOrder(models.Model):
        _inherit = 'sale.order'

        l10n_ve_rate = fields.Float(
            string='Tasa BCV (Bs/USD)',
            compute='_compute_ve_sale_dual',
        )
        l10n_ve_untaxed_bs = fields.Float(
            string='Base imponible Bs.',
            compute='_compute_ve_sale_dual',
            digits=(18, 2),
        )
        l10n_ve_tax_bs = fields.Float(
            string='Impuestos Bs.',
            compute='_compute_ve_sale_dual',
            digits=(18, 2),
        )
        l10n_ve_total_bs = fields.Float(
            string='Total Order Bs.',
            compute='_compute_ve_sale_dual',
            digits=(18, 2),
        )

        @api.depends('amount_untaxed', 'amount_tax', 'amount_total', 'currency_id', 'date_order', 'company_id')
        def _compute_ve_sale_dual(self):
            for order in self:
                date = order.date_order or fields.Date.context_today(order)
                rate_rec = self.env['l10n_ve.exchange.rate'].get_rate_for_date(date, company_id=order.company_id.id)
                if not rate_rec or not rate_rec.rate:
                    rate_rec = self.env['l10n_ve.exchange.rate'].get_latest_rate(company_id=order.company_id.id)
                rate_val = rate_rec.rate if rate_rec and rate_rec.rate > 0 else (order.company_id.get_current_bcv_rate() or 1.0)

                order.l10n_ve_rate = rate_val
                bs_currency = order.company_id.l10n_ve_currency_bs_id
                is_bs = (order.currency_id == bs_currency) or (order.currency_id.name in ['VES', 'VEF', 'VEB'])

                if is_bs:
                    order.l10n_ve_untaxed_bs = order.amount_untaxed
                    order.l10n_ve_tax_bs = order.amount_tax
                    order.l10n_ve_total_bs = order.amount_total
                else:
                    order.l10n_ve_untaxed_bs = order.amount_untaxed * rate_val
                    order.l10n_ve_tax_bs = order.amount_tax * rate_val
                    order.l10n_ve_total_bs = order.amount_total * rate_val
