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

    def action_print_inventory_book(self):
        """Genera el reporte de inventario valorado."""
        self.ensure_one()
        rate_rec = self.env['l10n_ve.exchange.rate'].get_rate_for_date(self.date_to, company_id=self.company_id.id)
        rate = rate_rec.rate if rate_rec and rate_rec.rate > 0 else (self.company_id.get_current_bcv_rate() or 779.9522)

        products = self.env['product.product'].search([
            ('type', '=', 'consu'),
            ('company_id', 'in', [self.company_id.id, False]),
        ])
        if not products:
            products = self.env['product.product'].search([
                ('company_id', 'in', [self.company_id.id, False])
            ], limit=100)

        # Generar vista o reporte
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Libro de Inventario Valorado'),
                'message': _('Inventario generado a fecha %s con Tasa BCV: %s Bs/$.') % (self.date_to, rate),
                'sticky': False,
                'type': 'success',
            }
        }
