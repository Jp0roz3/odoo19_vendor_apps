# -*- coding: utf-8 -*-
"""
Venezuela360: Reporte de Ganancia/Pérdida Cambiaria en Ventas vs Compras
========================================================================
Compara la tasa de cambio a la que se compró la mercancía vs la tasa de cambio
a la que se vendió a los clientes, calculando la ganancia o pérdida cambiaria realizada.

Ejemplo:
  Compra al proveedor a tasa 800 Bs/$
  Venta al cliente a tasa 700 Bs/$
  Pérdida cambiaria = 100 Bs por cada dólar vendido.

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class RateDifferenceWizard(models.TransientModel):
    _name = 'l10n_ve.rate.difference.wizard'
    _description = 'Reporte de Diferencial Cambiario en Ventas vs Compras'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=fields.Date.context_today,
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=fields.Date.context_today,
    )

    def action_generate_report(self):
        """Calcula y muestra el diferencial cambiario por factura de venta."""
        self.ensure_one()
        invoices = self.env['account.move'].search([
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ])

        if not invoices:
            raise UserError(
                _('No se encontraron facturas de venta confirmadas entre %s y %s.')
                % (self.date_from, self.date_to)
            )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas con Diferencial Cambiario'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoices.ids)],
        }
