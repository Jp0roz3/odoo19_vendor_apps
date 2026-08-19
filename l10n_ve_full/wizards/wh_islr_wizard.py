# -*- coding: utf-8 -*-
"""Venezuela360: Wizard — Crear Retención ISLR desde Factura"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WhIslrWizard(models.TransientModel):
    _name = 'account.wh.islr.wizard'
    _description = 'Wizard Retención ISLR desde Factura'

    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura',
        required=True,
        domain="[('state', '=', 'posted')]",
    )
    partner_id = fields.Many2one(related='move_id.partner_id', readonly=True)
    concept_id = fields.Many2one(
        comodel_name='account.wh.islr.concept',
        string='Concepto ISLR',
        required=True,
    )
    date = fields.Date(string='Fecha de Retención', required=True,
                       default=fields.Date.context_today)

    @api.onchange('move_id')
    def _onchange_move_id(self):
        if self.move_id and self.move_id.partner_id.l10n_ve_islr_concept_id:
            self.concept_id = self.move_id.partner_id.l10n_ve_islr_concept_id

    def action_create_wh_islr(self):
        self.ensure_one()
        wh = self.env['account.wh.islr'].create({
            'move_id':    self.move_id.id,
            'concept_id': self.concept_id.id,
            'date':       self.date,
        })
        wh.action_confirm()
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'account.wh.islr',
            'res_id':    wh.id,
            'view_mode': 'form',
            'target':    'current',
        }
