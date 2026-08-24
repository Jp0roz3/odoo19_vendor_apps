# -*- coding: utf-8 -*-
from odoo import models, fields, api

class HrSalaryRuleCategory(models.Model):
    _name = 'hr.salary.rule.category'
    _inherit = ['hr.salary.rule.category']
    _description = 'Categoría de Reglas Salariales'

    name = fields.Char(string="Nombre de Categoría", required=True)
    code = fields.Char(string="Código", required=True)


class HrPayrollStructure(models.Model):
    _name = 'hr.payroll.structure'
    _inherit = ['hr.payroll.structure']
    _description = 'Estructura Salarial de Nómina'

    name = fields.Char(string="Nombre de la Estructura", required=True)
    code = fields.Char(string="Código")
    rule_ids = fields.Many2many('hr.salary.rule', string="Reglas Salariales")


class HrSalaryRule(models.Model):
    _name = 'hr.salary.rule'
    _inherit = ['hr.salary.rule']
    _description = 'Regla Salarial de Nómina Venezuela'
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
