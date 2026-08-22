# -*- coding: utf-8 -*-
"""
Venezuela360: Reporte de Libro de Inventario y Balances (SENIAT)
================================================================
Genera el libro obligatorio de inventario y existencias valoradas
en moneda base (USD) y Bolívares (Bs.F) a la tasa oficial de corte.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class InventoryBookWizard(models.TransientModel):
    _name = 'l10n_ve.inventory.book.wizard'
    _description = 'Reporte de Libro de Inventario Valorado'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    date_to = fields.Date(
        string='Fecha de Corte',
        required=True,
        default=fields.Date.context_today,
    )
    category_ids = fields.Many2many(
        comodel_name='product.category',
        string='Categorías de Producto',
    )

    def _get_inventory_lines(self):
        """Calcula las existencias y valoraciones en USD y Bolívares a la fecha de corte."""
        self.ensure_one()
        rate_rec = self.env['l10n_ve.exchange.rate'].get_rate_for_date(self.date_to, company_id=self.company_id.id)
        rate = rate_rec.rate if rate_rec and rate_rec.rate > 0 else (self.company_id.get_current_bcv_rate() or 779.9522)

        domain = [('company_id', 'in', [self.company_id.id, False])]
        if self.category_ids:
            domain.append(('categ_id', 'in', self.category_ids.ids))

        products = self.env['product.product'].search(domain)
        lines = []
        total_usd = 0.0
        total_bs = 0.0
        total_qty = 0.0

        for p in products:
            qty = getattr(p, 'qty_available', 0.0) or 0.0
            cost_usd = p.standard_price or getattr(p, 'l10n_ve_standard_price_usd', 0.0) or 0.0
            cost_bs = round(cost_usd * rate, 2)
            subtotal_usd = round(qty * cost_usd, 2)
            subtotal_bs = round(qty * cost_bs, 2)

            total_qty += qty
            total_usd += subtotal_usd
            total_bs += subtotal_bs

            lines.append({
                'code': p.default_code or '',
                'name': p.display_name or p.name,
                'category': p.categ_id.name or '',
                'uom': p.uom_id.name or 'Unidades',
                'qty': qty,
                'cost_usd': cost_usd,
                'cost_bs': cost_bs,
                'total_usd': subtotal_usd,
                'total_bs': subtotal_bs,
            })

        return {
            'lines': lines,
            'rate': rate,
            'total_qty': total_qty,
            'total_usd': total_usd,
            'total_bs': total_bs,
        }

    def action_print_inventory_book(self):
        """Genera y descarga directamente el PDF del Libro de Inventario Valorado."""
        self.ensure_one()
        return self.env.ref('l10n_ve_full.action_report_inventory_book').report_action(self)
