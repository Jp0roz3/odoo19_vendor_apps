# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    is_payroll_entry = fields.Boolean(string="Es Asiento de Nómina", default=False)
    tasa_bcv_payroll = fields.Float(string="Tasa BCV del Asiento de Nómina", digits=(12, 6))
    total_payroll_usd = fields.Float(string="Total Nómina ($ USD)", digits=(12, 2))
