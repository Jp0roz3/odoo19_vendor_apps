# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class PosSession(models.Model):
    _inherit = 'pos.session'

    fiscal_z_report_number = fields.Char(
        string="N° Cierre Z",
        copy=False,
        help="Número correlativo de cierre Z emitido por la impresora al finalizar el turno o jornada."
    )
    fiscal_z_report_date = fields.Datetime(
        string="Fecha Cierre Z",
        copy=False
    )
    fiscal_orders_count = fields.Integer(
        string="Órdenes Fiscales",
        compute="_compute_fiscal_stats"
    )
    fiscal_sales_total = fields.Monetary(
        string="Total Ventas Fiscales",
        compute="_compute_fiscal_stats",
        currency_field='currency_id'
    )

    @api.depends('order_ids', 'order_ids.is_fiscal_printed', 'order_ids.amount_total')
    def _compute_fiscal_stats(self):
        for session in self:
            fiscal_orders = session.order_ids.filtered(lambda o: o.is_fiscal_printed and o.state not in ['cancel'])
            session.fiscal_orders_count = len(fiscal_orders)
            session.fiscal_sales_total = sum(fiscal_orders.mapped('amount_total'))

    def action_register_z_report(self, z_number):
        """Registra el número de Reporte Z emitido para esta sesión."""
        self.ensure_one()
        self.write({
            'fiscal_z_report_number': z_number,
            'fiscal_z_report_date': fields.Datetime.now(),
        })
        # Asignar a las órdenes de la sesión que no tengan Z asignado
        self.order_ids.filtered(lambda o: o.is_fiscal_printed and not o.fiscal_z_number).write({
            'fiscal_z_number': z_number
        })
        return True
