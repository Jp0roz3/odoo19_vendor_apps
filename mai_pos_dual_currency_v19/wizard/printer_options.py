# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PosPrinterOptions(models.TransientModel):
    _name = 'pos.printer.options'
    _description = 'Opciones de Impresora Fiscal'

    pos_config_id = fields.Many2one('pos.config', string='Punto de Venta', required=True, default=lambda self: self.env.context.get('active_id'))
    
    # Reporte Z
    z_start = fields.Integer(string='Número Inicial', default=0)
    z_end = fields.Integer(string='Número Final', default=0)

    # Memoria de Auditoría
    audit_start = fields.Integer(string='Número Inicial', default=0)
    audit_end = fields.Integer(string='Número Final', default=0)

    def action_print_z_report(self):
        self.ensure_one()
        # Return a client action to be handled by JS in the frontend
        return {
            'type': 'ir.actions.client',
            'tag': 'pos_fiscal_printer_action',
            'params': {
                'action': 'print_z_report',
                'z_start': self.z_start,
                'z_end': self.z_end,
                'pos_config_id': self.pos_config_id.id,
            }
        }

    def action_print_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'pos_fiscal_printer_action',
            'params': {
                'action': 'print_invoices',
                'audit_start': self.audit_start,
                'audit_end': self.audit_end,
                'pos_config_id': self.pos_config_id.id,
            }
        }

    def action_print_credit_notes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'pos_fiscal_printer_action',
            'params': {
                'action': 'print_credit_notes',
                'audit_start': self.audit_start,
                'audit_end': self.audit_end,
                'pos_config_id': self.pos_config_id.id,
            }
        }
