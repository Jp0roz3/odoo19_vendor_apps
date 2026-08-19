# -*- coding: utf-8 -*-
"""Venezuela360: Wizard — Crear Retención Municipal desde Factura"""
from odoo import models, fields, api, _


class WhMunicipalWizard(models.TransientModel):
    _name = 'account.wh.municipal.wizard'
    _description = 'Wizard Retención Municipal desde Factura'

    move_id = fields.Many2one(
        comodel_name='account.move', string='Factura', required=True,
        domain="[('state', '=', 'posted')]",
    )
    partner_id = fields.Many2one(related='move_id.partner_id', readonly=True)
    municipality_id = fields.Many2one(
        comodel_name='l10n_ve.municipality',
        string='Municipio', required=True,
    )
    rate_pct = fields.Float(string='Alícuota IAE (%)', required=True, default=0.0)
    economic_activity = fields.Char(string='Actividad Económica')
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)

    @api.onchange('municipality_id', 'move_id')
    def _onchange_municipality(self):
        if self.municipality_id:
            self.rate_pct = self.municipality_id.wh_municipal_rate
            if self.move_id and self.move_id.partner_id.l10n_ve_municipal_rate:
                self.rate_pct = self.move_id.partner_id.l10n_ve_municipal_rate
            if self.move_id and self.move_id.partner_id.l10n_ve_municipal_activity:
                self.economic_activity = self.move_id.partner_id.l10n_ve_municipal_activity

    def action_create_wh_municipal(self):
        self.ensure_one()
        wh = self.env['account.wh.municipal'].create({
            'move_id':           self.move_id.id,
            'municipality_id':   self.municipality_id.id,
            'rate_pct':          self.rate_pct,
            'economic_activity': self.economic_activity or '',
            'date':              self.date,
        })
        wh.action_confirm()
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'account.wh.municipal',
            'res_id':    wh.id,
            'view_mode': 'form',
            'target':    'current',
        }
