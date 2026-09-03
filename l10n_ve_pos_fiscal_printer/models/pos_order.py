# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class PosOrder(models.Model):
    _inherit = 'pos.order'

    fiscal_invoice_number = fields.Char(
        string="Factura Fiscal N°",
        copy=False,
        index=True,
        help="Número consecutivo asignado por la memoria fiscal de la impresora."
    )
    fiscal_control_number = fields.Char(
        string="N° Control Fiscal",
        copy=False,
        help="Número de control SENIAT asignado a la transacción fiscal."
    )
    fiscal_printer_serial = fields.Char(
        string="Serial Fiscal Impresora",
        copy=False,
        help="Serial de la máquina fiscal que emitió el documento (ej: Z1A8120000)."
    )
    is_fiscal_printed = fields.Boolean(
        string="Impreso Fiscalmente",
        default=False,
        copy=False,
        help="Indica si la orden fue impresa legalmente por una máquina fiscal."
    )
    fiscal_print_date = fields.Datetime(
        string="Fecha Emisión Fiscal",
        copy=False,
        help="Fecha y hora de la emisión física en la impresora."
    )
    fiscal_z_number = fields.Char(
        string="N° Cierre Z",
        copy=False,
        help="Número del reporte Z del día en que se procesó la venta."
    )

    @api.model
    def _order_fields(self, ui_order):
        fields_dict = super()._order_fields(ui_order)
        fields_dict['fiscal_invoice_number'] = ui_order.get('fiscal_invoice_number') or False
        fields_dict['fiscal_control_number'] = ui_order.get('fiscal_control_number') or False
        fields_dict['fiscal_printer_serial'] = ui_order.get('fiscal_printer_serial') or False
        fields_dict['is_fiscal_printed']     = ui_order.get('is_fiscal_printed') or False
        fields_dict['fiscal_z_number']        = ui_order.get('fiscal_z_number') or False
        if ui_order.get('fiscal_print_date'):
            fields_dict['fiscal_print_date'] = ui_order.get('fiscal_print_date')
        elif ui_order.get('is_fiscal_printed'):
            fields_dict['fiscal_print_date'] = fields.Datetime.now()
        return fields_dict

    def _export_for_ui(self, order):
        result = super()._export_for_ui(order)
        result['fiscal_invoice_number'] = order.fiscal_invoice_number or False
        result['fiscal_control_number'] = order.fiscal_control_number or False
        result['fiscal_printer_serial'] = order.fiscal_printer_serial or False
        result['is_fiscal_printed']     = order.is_fiscal_printed or False
        result['fiscal_print_date']     = order.fiscal_print_date or False
        result['fiscal_z_number']        = order.fiscal_z_number or False
        return result

    def action_register_fiscal_print(self, invoice_number, printer_serial=None, control_number=None, z_number=None):
        """Registra la emisión fiscal de una orden confirmada."""
        self.ensure_one()
        vals = {
            'fiscal_invoice_number': invoice_number,
            'is_fiscal_printed': True,
            'fiscal_print_date': fields.Datetime.now(),
        }
        if printer_serial:
            vals['fiscal_printer_serial'] = printer_serial
        if control_number:
            vals['fiscal_control_number'] = control_number
        if z_number:
            vals['fiscal_z_number'] = z_number

        self.write(vals)

        # Si existe factura contable generada, sincronizar datos con account.move
        if self.account_move:
            move_vals = {}
            if hasattr(self.account_move, 'fiscal_invoice_number'):
                move_vals['fiscal_invoice_number'] = invoice_number
            if hasattr(self.account_move, 'fiscal_machine_serial'):
                move_vals['fiscal_machine_serial'] = printer_serial or False
            if hasattr(self.account_move, 'l10n_ve_fiscal_printer_serial'):
                move_vals['l10n_ve_fiscal_printer_serial'] = printer_serial or False
            if hasattr(self.account_move, 'l10n_ve_control_number') and control_number:
                move_vals['l10n_ve_control_number'] = control_number
            if move_vals:
                self.account_move.write(move_vals)

        return True


class AccountMove(models.Model):
    _inherit = 'account.move'

    fiscal_invoice_number = fields.Char(
        string="Factura Fiscal N°",
        copy=False,
        readonly=True,
        help="Número de factura emitido por la máquina fiscal."
    )
    fiscal_machine_serial = fields.Char(
        string="Serial Impresora Fiscal",
        copy=False,
        readonly=True,
        help="Serial del hardware fiscal SENIAT."
    )
    credit_note_number = fields.Char(
        string="Nota de Crédito Fiscal N°",
        copy=False,
        readonly=True,
        help="Número de nota de crédito emitido por la máquina fiscal."
    )
