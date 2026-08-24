# -*- coding: utf-8 -*-
from odoo import models, fields, api

class HrSalaryRuleCategory(models.Model):
    _inherit = 'hr.salary.rule.category'

    code = fields.Char(string="Código")


class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'
    _order = 'sequence, id'

    name = fields.Char(string="Nombre de la Regla", required=True)
    code = fields.Char(string="Código", required=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    category_id = fields.Many2one('hr.salary.rule.category', string="Categoría", required=True)
    structure_id = fields.Many2one('hr.payroll.structure', string="Estructura Salarial")

    condition_select = fields.Selection([
        ('none', 'Siempre Verdadero'),
        ('python', 'Expresión Python'),
    ], string="Condición", default='none', required=True)
    condition_python = fields.Text(string="Código Python de Condición", default="result = True")

    amount_select = fields.Selection([
        ('code', 'Código Python'),
        ('fix', 'Monto Fijo'),
    ], string="Tipo de Cálculo", default='code', required=True)
    amount_python_compute = fields.Text(string="Código Python de Cálculo", default="result = 0.0")
    amount_fix = fields.Float(string="Monto Fijo", digits=(12, 2))
