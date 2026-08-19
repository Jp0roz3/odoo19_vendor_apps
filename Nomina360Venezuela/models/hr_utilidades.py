# -*- coding: utf-8 -*-
from odoo import models, fields, api

class HrUtilidades(models.Model):
    _name = 'hr.utilidades'
    _description = 'Cálculo de Utilidades y Aguinaldos de Fin de Año (Art. 131, 132 LOTTT)'
    _order = 'year desc, id desc'

    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True, ondelete='cascade')
    contract_id = fields.Many2one('hr.contract', string="Contrato", required=True)
    year = fields.Integer(string="Año Fiscal", required=True, default=lambda self: fields.Date.today().year)

    days_utilidades = fields.Integer(string="Días de Utilidades", default=30, help="De 30 a 120 días según Art. 131 LOTTT.")
    salario_promedio_diario_bs = fields.Float(string="Salario Promedio Diario (Bs)", digits=(12, 2))
    salario_promedio_diario_usd = fields.Float(string="Salario Promedio Diario ($ USD)", digits=(12, 2))

    total_utilidades_bs = fields.Float(string="Total Utilidades (Bs)", compute='_compute_totals', store=True, digits=(12, 2))
    total_utilidades_usd = fields.Float(string="Total Utilidades ($ USD)", compute='_compute_totals', store=True, digits=(12, 2))

    inces_deduction_bs = fields.Float(string="Deducción INCES Empleado 0.5% (Bs)", compute='_compute_totals', store=True, digits=(12, 2))
    net_utilidades_bs = fields.Float(string="Neto a Pagar Utilidades (Bs)", compute='_compute_totals', store=True, digits=(12, 2))

    tasa_bcv = fields.Float(string="Tasa BCV", digits=(12, 6), default=lambda self: self.env.company.current_bcv_rate)

    @api.depends('days_utilidades', 'salario_promedio_diario_bs', 'salario_promedio_diario_usd', 'tasa_bcv')
    def _compute_totals(self):
        for rec in self:
            rate = rec.tasa_bcv or rec.env.company.current_bcv_rate or 1.0
            tot_bs = (rec.salario_promedio_diario_bs or 0.0) * rec.days_utilidades
            rec.total_utilidades_bs = round(tot_bs, 2)
            rec.inces_deduction_bs = round(tot_bs * 0.005, 2)  # INCES employee 0.5%
            rec.net_utilidades_bs = round(tot_bs - rec.inces_deduction_bs, 2)

            if rate > 0:
                rec.total_utilidades_usd = round(rec.total_utilidades_bs / rate, 2)
            else:
                rec.total_utilidades_usd = 0.0
