# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    bcv_rate_api_enabled = fields.Boolean(
        string="Sincronización Automática Tasa BCV",
        default=True,
        help="Permite actualizar automáticamente la tasa de cambio oficial del Banco Central de Venezuela."
    )
    current_bcv_rate = fields.Float(
        string="Tasa BCV Manual / Referencial (USD/Bs)",
        digits=(12, 6),
        default=757.74,
        help="Tasa oficial de cambio del Banco Central de Venezuela o tasa manual asignada."
    )
    ivss_risk_level = fields.Selection([
        ('minimo', 'Riesgo Mínimo (Patrono 9%)'),
        ('medio', 'Riesgo Medio (Patrono 10%)'),
        ('maximo', 'Riesgo Máximo (Patrono 11%)'),
    ], string="Nivel de Riesgo IVSS Patronal", default='medio', required=True)

    cesta_ticket_usd = fields.Float(
        string="Monto Cesta Ticket Socialista (USD)",
        digits=(12, 2),
        default=40.00,
        help="Monto legal mensual indexado en dólares para Bono de Alimentación según Ley."
    )
    salario_minimo_nacional = fields.Float(
        string="Salario Mínimo Nacional (Bs)",
        digits=(12, 2),
        default=130.00,
        help="Salario Mínimo Nacional decretado por el Ejecutivo para cálculo de topes IVSS/SPF."
    )
    ley_pensiones_rate = fields.Float(
        string="Aporte Ley de Protección de Pensiones (%)",
        digits=(5, 2),
        default=9.00,
        help="Porcentaje de contribución patronal especial mensual según Ley de Mayo de 2024."
    )

    bank_code_default = fields.Selection([
        ('0102', 'Banco de Venezuela (BDV)'),
        ('0134', 'Banesco Banco Universal'),
        ('0105', 'Banco Mercantil'),
        ('0108', 'BBVA Provincial'),
        ('0191', 'Banco Nacional de Crédito (BNC)'),
        ('0172', 'Bancamiga'),
    ], string="Banco Predeterminado para Nómina", default='0134')

    cesta_ticket_special_rate = fields.Float(
        string="Tasa Cestaticket Especial (Bs/USD)",
        digits=(12, 6),
        default=0.00,
        help="Tasa especial fijada por la administración para el Beneficio Complementario de Alimentación."
    )
    bcv_cut_day = fields.Selection([
        ('wednesday', 'Miércoles (Corte Oficial)'),
        ('daily', 'Diario (Tasa del Día)'),
    ], string="Día de Corte Tasa BCV", default='wednesday', required=True)

    utilidades_provision_days = fields.Selection([
        ('60', '60 Días de Utilidades'),
        ('100', '100 Días de Utilidades'),
        ('110', '110 Días de Utilidades'),
        ('120', '120 Días de Utilidades (Máximo Legal)'),
    ], string="Convención de Provisión de Utilidades", default='60', required=True)

    def get_bcv_rate(self, is_cesta_ticket=False):
        self.ensure_one()
        if is_cesta_ticket and self.cesta_ticket_special_rate > 1.0:
            return round(self.cesta_ticket_special_rate, 4)

        # 1. Check active currency rate in Odoo res.currency
        try:
            usd = self.env.ref('base.USD', raise_if_not_found=False)
            if usd and usd.rate > 0:
                r = usd.rate
                if r > 1.0:
                    return round(r, 4)
                elif 0 < r < 1.0:
                    inv = round(1.0 / r, 4)
                    if inv > 1.0:
                        return inv
        except Exception:
            pass

        try:
            vef = self.env.ref('base.VEF', raise_if_not_found=False) or self.env.ref('base.VES', raise_if_not_found=False)
            if vef and vef.rate > 0:
                r = vef.rate
                if r > 1.0:
                    return round(r, 4)
                elif 0 < r < 1.0:
                    inv = round(1.0 / r, 4)
                    if inv > 1.0:
                        return inv
        except Exception:
            pass

        # 2. Company setting rate
        if self.current_bcv_rate > 1.0:
            return round(self.current_bcv_rate, 4)

        # 3. Default fallback BCV rate
        return 757.74


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bcv_rate_api_enabled = fields.Boolean(related='company_id.bcv_rate_api_enabled', readonly=False)
    current_bcv_rate = fields.Float(related='company_id.current_bcv_rate', readonly=False)
    cesta_ticket_special_rate = fields.Float(related='company_id.cesta_ticket_special_rate', readonly=False)
    bcv_cut_day = fields.Selection(related='company_id.bcv_cut_day', readonly=False)
    utilidades_provision_days = fields.Selection(related='company_id.utilidades_provision_days', readonly=False)
    ivss_risk_level = fields.Selection(related='company_id.ivss_risk_level', readonly=False)
    cesta_ticket_usd = fields.Float(related='company_id.cesta_ticket_usd', readonly=False)
    salario_minimo_nacional = fields.Float(related='company_id.salario_minimo_nacional', readonly=False)
    ley_pensiones_rate = fields.Float(related='company_id.ley_pensiones_rate', readonly=False)
    bank_code_default = fields.Selection(related='company_id.bank_code_default', readonly=False)
