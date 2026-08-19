# -*- coding: utf-8 -*-
from odoo import models, fields, api

class HrLeyPensionesLine(models.Model):
    _name = 'hr.ley.pensiones.line'
    _description = 'Registro Mensual Aporte Patronal Ley de Protección de Pensiones 9% (SENIAT Mayo 2024)'
    _order = 'year desc, month desc, id desc'

    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company, required=True)
    year = fields.Integer(string="Año", required=True, default=lambda self: fields.Date.today().year)
    month = fields.Selection([
        ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'),
        ('5', 'Mayo'), ('6', 'Junio'), ('7', 'Julio'), ('8', 'Agosto'),
        ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre')
    ], string="Mes", required=True)

    total_trabajadores = fields.Integer(string="Total Trabajadores Declarados", default=0)

    total_remuneraciones_bs = fields.Float(
        string="Total Remuneraciones Otorgadas (Bs)",
        digits=(12, 2),
        help="Suma de salarios + bonificaciones de carácter no salarial + cesta ticket pagados en el mes."
    )
    total_remuneraciones_usd = fields.Float(
        string="Total Remuneraciones Otorgadas ($ USD)",
        digits=(12, 2)
    )

    porcentaje_aporte = fields.Float(string="Porcentaje Aporte Patronal (%)", default=9.00, digits=(5, 2))

    monto_aporte_seniat_bs = fields.Float(
        string="Monto Aporte a Pagar SENIAT (Bs)",
        compute='_compute_monto_aporte',
        store=True,
        digits=(12, 2)
    )
    monto_aporte_seniat_usd = fields.Float(
        string="Monto Aporte a Pagar SENIAT ($ USD)",
        compute='_compute_monto_aporte',
        store=True,
        digits=(12, 2)
    )

    tasa_bcv = fields.Float(string="Tasa BCV del Mes", digits=(12, 6), default=lambda self: self.env.company.current_bcv_rate)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('declared', 'Declarado ante SENIAT'),
        ('paid', 'Pagado'),
    ], string="Estado", default='draft')

    @api.depends('total_remuneraciones_bs', 'porcentaje_aporte', 'tasa_bcv')
    def _compute_monto_aporte(self):
        for rec in self:
            rate = rec.tasa_bcv or rec.env.company.current_bcv_rate or 1.0
            aporte_bs = round(((rec.total_remuneraciones_bs or 0.0) * (rec.porcentaje_aporte / 100.0)), 2)
            rec.monto_aporte_seniat_bs = aporte_bs
            if rate > 0:
                rec.monto_aporte_seniat_usd = round(aporte_bs / rate, 2)
            else:
                rec.monto_aporte_seniat_usd = 0.0

    def action_declare(self):
        self.write({'state': 'declared'})

    def action_paid(self):
        self.write({'state': 'paid'})
