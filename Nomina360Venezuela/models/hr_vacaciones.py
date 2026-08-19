# -*- coding: utf-8 -*-
from odoo import models, fields, api

class HrVacacionesHistorico(models.Model):
    _name = 'hr.vacaciones.historico'
    _description = 'Control Histórico de Vacaciones y Bono Vacacional (Art. 190, 192 LOTTT)'
    _order = 'year desc, id desc'

    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True, ondelete='cascade')
    contract_id = fields.Many2one('hr.contract', string="Contrato", required=True)
    year = fields.Integer(string="Año de Servicio", required=True, default=lambda self: fields.Date.today().year)

    dias_habiles_vacaciones = fields.Integer(string="Días Hábiles Disfrutados", default=15)
    dias_bono_vacacional = fields.Integer(string="Días Bono Vacacional Pagados", default=15)
    dias_adicionales_antiguedad = fields.Integer(string="Días Adicionales por Antigüedad", default=0)

    date_from = fields.Date(string="Fecha Inicio Vacaciones")
    date_to = fields.Date(string="Fecha Fin Vacaciones")
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approved', 'Aprobado'),
        ('enjoyed', 'Disfrutado'),
    ], string="Estado", default='draft')

    monto_bono_vacacional_bs = fields.Float(string="Monto Bono Vacacional (Bs)", digits=(12, 2))
    monto_bono_vacacional_usd = fields.Float(string="Monto Bono Vacacional ($ USD)", digits=(12, 2))
