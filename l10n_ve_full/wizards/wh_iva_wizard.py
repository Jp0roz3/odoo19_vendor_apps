# -*- coding: utf-8 -*-
"""Venezuela360: Wizard — Crear Retención IVA desde Factura"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WhIvaWizard(models.TransientModel):
    _name = 'account.wh.iva.wizard'
    _description = 'Wizard Retención IVA desde Factura'

    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura',
        required=True,
        domain="[('move_type', 'in', ['in_invoice','in_refund','out_invoice','out_refund']),"
               "('state', '=', 'posted')]",
    )
    partner_id  = fields.Many2one(related='move_id.partner_id', readonly=True)
    wh_type     = fields.Selection([
        ('supplier', 'Retención a Proveedor'),
        ('customer', 'Retención a Cliente'),
    ], required=True, default='supplier')
    wh_rate     = fields.Float(string='% Retención sobre IVA', required=True, default=75.0)
    date        = fields.Date(string='Fecha de Retención', required=True,
                               default=fields.Date.context_today)

    @api.onchange('move_id')
    def _onchange_move_id(self):
        if self.move_id and self.move_id.partner_id:
            self.wh_rate = self.move_id.partner_id.get_wh_iva_rate(
                company=self.move_id.company_id
            )
            if self.move_id.move_type in ('in_invoice', 'in_refund'):
                self.wh_type = 'supplier'
            else:
                self.wh_type = 'customer'

    def action_create_wh_iva(self):
        self.ensure_one()
        if not self.move_id.l10n_ve_amount_tax_bs:
            raise UserError(_('La factura no tiene IVA registrado en Bs. '
                              'Verifica que la tasa BCV esté asignada.'))
        wh = self.env['account.wh.iva'].create({
            'wh_type': self.wh_type,
            'move_id': self.move_id.id,
            'date':    self.date,
            'wh_rate': self.wh_rate,
        })
        wh.action_confirm()
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'account.wh.iva',
            'res_id':    wh.id,
            'view_mode': 'form',
            'target':    'current',
        }
