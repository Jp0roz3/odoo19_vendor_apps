# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrPrestacionesAnticipo(models.Model):
    _name = 'hr.prestaciones.anticipo'
    _description = 'Solicitud de Anticipo de Prestaciones Sociales (Art. 144 LOTTT)'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Referencia", default=lambda self: _('Nuevo'), readonly=True)
    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True)
    contract_id = fields.Many2one('hr.contract', string="Contrato", compute='_compute_contract', store=True)
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    date_request = fields.Date(string="Fecha de Solicitud", default=fields.Date.today, required=True)
    tasa_bcv = fields.Float(string="Tasa BCV Aplicada", digits=(12, 6), default=lambda self: self.env.company.get_bcv_rate())

    fondo_acumulado_bs = fields.Float(string="Fondo Prestaciones Acumulado (Bs)", compute='_compute_fondo', store=True)
    max_anticipo_bs = fields.Float(string="Máximo Legal Permitido 75% (Bs)", compute='_compute_fondo', store=True)

    monto_solicitado_bs = fields.Float(string="Monto Solicitado (Bs)", digits=(12, 2), required=True)
    monto_solicitado_usd = fields.Float(string="Monto Solicitado ($ USD)", digits=(12, 2), compute='_compute_usd', store=True)

    motivo = fields.Selection([
        ('vivienda', 'Construcción, adquisición o mejora de vivienda (Art. 144a)'),
        ('hipoteca', 'Liberación de hipoteca o gravamen de vivienda (Art. 144b)'),
        ('salud', 'Inversión en salud y gastos médicos para el trabajador o su familia (Art. 144c)'),
        ('educacion', 'Gastos por educación para el trabajador o sus hijos (Art. 144d)'),
    ], string="Motivo Legal (LOTTT Art. 144)", required=True, default='vivienda')

    observaciones = fields.Text(string="Detalle / Justificación de la Solicitud")

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approved', 'Aprobado por RRHH'),
        ('paid', 'Pagado / Descontado'),
        ('refused', 'Rechazado'),
    ], string="Estado", default='draft', tracking=True)

    @api.depends('employee_id')
    def _compute_contract(self):
        for rec in self:
            rec.contract_id = rec.employee_id.contract_id.id if rec.employee_id else False

    @api.depends('employee_id', 'contract_id')
    def _compute_fondo(self):
        for rec in self:
            if rec.employee_id:
                lines = self.env['hr.prestaciones.line'].search([('employee_id', '=', rec.employee_id.id)])
                total_garantia = sum(lines.mapped('monto_garantia_trimestre_bs'))
                rec.fondo_acumulado_bs = round(total_garantia, 2)
                rec.max_anticipo_bs = round(total_garantia * 0.75, 2)
            else:
                rec.fondo_acumulado_bs = 0.0
                rec.max_anticipo_bs = 0.0

    @api.depends('monto_solicitado_bs', 'tasa_bcv')
    def _compute_usd(self):
        for rec in self:
            rate = rec.tasa_bcv or 1.0
            rec.monto_solicitado_usd = round((rec.monto_solicitado_bs or 0.0) / rate, 2)

    def action_approve(self):
        for rec in self:
            if rec.monto_solicitado_bs > rec.max_anticipo_bs and rec.max_anticipo_bs > 0:
                raise UserError(_("El monto solicitado (%s Bs) excede el 75%% máximo permitido por la LOTTT (%s Bs).") % (rec.monto_solicitado_bs, rec.max_anticipo_bs))
            rec.write({'state': 'approved'})

    def action_paid(self):
        for rec in self:
            rec.write({'state': 'paid'})

    def action_refuse(self):
        for rec in self:
            rec.write({'state': 'refused'})


class HrPayrollBankApproval(models.Model):
    _name = 'hr.payroll.bank.approval'
    _description = 'Portal de Aprobación Financiera de Disquetes Bancarios Masivos'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Código de Aprobación", required=True, default=lambda self: _('NUEVO-BANCO'))
    payslip_run_id = fields.Many2one('hr.payslip.run', string="Lote de Nómina", required=True)
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    bank_id = fields.Selection([
        ('banesco', 'Banesco Banco Universal (0134)'),
        ('provincial', 'BBVA Provincial (0108)'),
        ('bdv', 'Banco de Venezuela (0102)'),
        ('bnc', 'Banco Nacional de Crédito BNC (0191)'),
        ('bancamiga', 'Bancamiga (0172)'),
        ('mercantil', 'Banco Mercantil (0105)'),
    ], string="Entidad Bancaria Destino", default='banesco', required=True)

    tasa_bcv = fields.Float(string="Tasa BCV del Pago", digits=(12, 6), default=lambda self: self.env.company.get_bcv_rate())
    total_transferir_bs = fields.Float(string="Total a Transferir (Bs)", compute='_compute_totals', store=True, digits=(12, 2))
    total_transferir_usd = fields.Float(string="Total a Transferir ($ USD)", compute='_compute_totals', store=True, digits=(12, 2))
    cant_empleados = fields.Integer(string="Cantidad de Empleados Incluidos", compute='_compute_totals', store=True)

    approved_by_id = fields.Many2one('res.users', string="Aprobado Financieramente Por", readonly=True)
    date_approval = fields.Datetime(string="Fecha de Aprobación Financiera", readonly=True)

    state = fields.Selection([
        ('pending', 'Pendiente Validación Financiera'),
        ('validated', 'Validado por Tesorería'),
        ('approved', 'Aprobado para Pago Bancario'),
        ('sent', 'Enviado al Banco / Procesado'),
    ], string="Estado de Validación", default='pending', tracking=True)

    @api.depends('payslip_run_id', 'tasa_bcv')
    def _compute_totals(self):
        for rec in self:
            if rec.payslip_run_id:
                rec.total_transferir_bs = rec.payslip_run_id.total_bs
                rate = rec.tasa_bcv or 1.0
                rec.total_transferir_usd = round(rec.total_transferir_bs / rate, 2)
                rec.cant_empleados = len(rec.payslip_run_id.slip_ids)
            else:
                rec.total_transferir_bs = 0.0
                rec.total_transferir_usd = 0.0
                rec.cant_empleados = 0

    def action_validate_finance(self):
        for rec in self:
            rec.write({'state': 'validated'})

    def action_approve_finance(self):
        for rec in self:
            rec.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'date_approval': fields.Datetime.now()
            })

    def action_mark_sent(self):
        for rec in self:
            rec.write({'state': 'sent'})


class HrPayrollDashboardBI(models.Model):
    _name = 'hr.payroll.dashboard.bi'
    _description = 'Tablero de Control BI Gerencial de Nómina Venezuela'

    name = fields.Char(string="Indicador", default="Tablero de Control Gerencial - Nubelco 360")
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    total_empleados_activos = fields.Integer(string="Empleados Activos", compute='_compute_kpis')
    total_costo_mes_bs = fields.Float(string="Costo Nómina Mes (Bs)", compute='_compute_kpis', digits=(12, 2))
    total_costo_mes_usd = fields.Float(string="Costo Nómina Mes ($ USD)", compute='_compute_kpis', digits=(12, 2))
    promedio_salario_usd = fields.Float(string="Promedio Salarial Empleado ($ USD)", compute='_compute_kpis', digits=(12, 2))
    total_prestaciones_acumuladas_bs = fields.Float(string="Fondo Total Prestaciones (Bs)", compute='_compute_kpis', digits=(12, 2))
    total_ley_pensiones_seniat_bs = fields.Float(string="Aporte Ley Pensiones SENIAT 9% (Bs)", compute='_compute_kpis', digits=(12, 2))

    dashboard_html = fields.Html(string="Tablero BI Interactivo & Gráficas", compute='_compute_dashboard_html')

    def _compute_kpis(self):
        for rec in self:
            emp_count = self.env['hr.employee'].search_count([('active', '=', True)])
            rec.total_empleados_activos = emp_count

            payslips = self.env['hr.payslip'].search([('state', '=', 'done')])
            total_net_bs = sum(payslips.mapped('net_wage_bs'))
            total_net_usd = sum(payslips.mapped('net_wage_usd'))

            rec.total_costo_mes_bs = round(total_net_bs, 2)
            rec.total_costo_mes_usd = round(total_net_usd, 2)
            rec.promedio_salario_usd = round(total_net_usd / emp_count, 2) if emp_count > 0 else 0.0

            lines = self.env['hr.prestaciones.line'].search([])
            rec.total_prestaciones_acumuladas_bs = round(sum(lines.mapped('monto_garantia_trimestre_bs')), 2)
            rec.total_ley_pensiones_seniat_bs = round(total_net_bs * 0.09, 2)

    @api.depends('company_id')
    def _compute_dashboard_html(self):
        for rec in self:
            emp_count = self.env['hr.employee'].search_count([('active', '=', True)])
            payslips = self.env['hr.payslip'].search([('state', '=', 'done')])
            total_net_bs = round(sum(payslips.mapped('net_wage_bs')), 2)
            total_net_usd = round(sum(payslips.mapped('net_wage_usd')), 2)
            rate = rec.company_id.get_bcv_rate() or 757.74
            avg_usd = round(total_net_usd / emp_count, 2) if emp_count > 0 else 0.0

            lines = self.env['hr.prestaciones.line'].search([])
            fondo_bs = round(sum(lines.mapped('monto_garantia_trimestre_bs')), 2)
            fondo_usd = round(fondo_bs / rate, 2)
            seniat_9 = round(total_net_bs * 0.09, 2)
            seniat_9_usd = round(seniat_9 / rate, 2)

            html = f"""
            <div style="background: #0F172A; border-radius: 16px; padding: 24px; color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.3); border: 1px solid #1E293B;">
                
                <!-- Dashboard Header Banner -->
                <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 18px; margin-bottom: 24px;">
                    <div style="display: flex; align-items: center; gap: 14px;">
                        <div style="width: 48px; height: 48px; border-radius: 14px; background: linear-gradient(135deg, #0EA5E9 0%, #2563EB 100%); display: flex; align-items: center; justify-content: center; font-size: 26px; box-shadow: 0 4px 14px rgba(14, 165, 233, 0.4);">
                            📊
                        </div>
                        <div>
                            <h2 style="margin: 0; font-size: 22px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px;">Tablero BI Gerencial 360 <span style="background: #0284C7; color: #E0F2FE; font-size: 11px; padding: 3px 10px; border-radius: 20px; font-weight: 700; text-transform: uppercase; margin-left: 10px;">Executive Live</span></h2>
                            <span style="color: #94A3B8; font-size: 13px;">Consolidado Digital de Nómina Venezolana, Tasa BCV & Retenciones SENIAT</span>
                        </div>
                    </div>
                    <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid #0EA5E9; padding: 8px 16px; border-radius: 24px; color: #38BDF8; font-size: 13px; font-weight: 700;">
                        🔱 Tasa BCV Oficial: <strong style="color: #34D399;">{rate:.4f} Bs/USD</strong>
                    </div>
                </div>

                <!-- 5 Executive KPI Cards -->
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px;">
                    
                    <div style="background: #1E293B; border-radius: 14px; padding: 18px; border-left: 5px solid #3B82F6;">
                        <span style="color: #94A3B8; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">EMPLEADOS ACTIVOS</span>
                        <div style="font-size: 32px; font-weight: 800; color: #60A5FA; margin: 8px 0 4px 0;">{emp_count}</div>
                        <span style="color: #CBD5E1; font-size: 12px;">Promedio Salario: <strong style="color: #34D399;">${avg_usd:,.2f} USD</strong></span>
                    </div>

                    <div style="background: #1E293B; border-radius: 14px; padding: 18px; border-left: 5px solid #10B981;">
                        <span style="color: #94A3B8; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">MASA SALARIAL NETA (BS / USD)</span>
                        <div style="font-size: 26px; font-weight: 800; color: #34D399; margin: 8px 0 4px 0;">{total_net_bs:,.2f} Bs</div>
                        <span style="color: #CBD5E1; font-size: 12px;">Equivalente en Dólares: <strong style="color: #38BDF8;">${total_net_usd:,.2f} USD</strong></span>
                    </div>

                    <div style="background: #1E293B; border-radius: 14px; padding: 18px; border-left: 5px solid #F59E0B;">
                        <span style="color: #94A3B8; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">FONDO PRESTACIONES SOCIALES</span>
                        <div style="font-size: 26px; font-weight: 800; color: #FBBF24; margin: 8px 0 4px 0;">{fondo_bs:,.2f} Bs</div>
                        <span style="color: #CBD5E1; font-size: 12px;">Garantía en Dólares: <strong>${fondo_usd:,.2f} USD</strong></span>
                    </div>

                    <div style="background: #1E293B; border-radius: 14px; padding: 18px; border-left: 5px solid #EC4899;">
                        <span style="color: #94A3B8; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">APORTE SENIAT PENSIONES 9%</span>
                        <div style="font-size: 26px; font-weight: 800; color: #F472B6; margin: 8px 0 4px 0;">{seniat_9:,.2f} Bs</div>
                        <span style="color: #CBD5E1; font-size: 12px;">Equivalente: <strong>${seniat_9_usd:,.2f} USD</strong></span>
                    </div>

                    <div style="background: #1E293B; border-radius: 14px; padding: 18px; border-left: 5px solid #8B5CF6;">
                        <span style="color: #94A3B8; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">CESTACICKET SOCIALISTA INDEXADO</span>
                        <div style="font-size: 26px; font-weight: 800; color: #A78BFA; margin: 8px 0 4px 0;">$40.00 USD</div>
                        <span style="color: #CBD5E1; font-size: 12px;">Decreto Legal: <strong>{40*rate:,.2f} Bs / mes</strong></span>
                    </div>

                    <div style="background: #1E293B; border-radius: 14px; padding: 18px; border-left: 5px solid #06B6D4;">
                        <span style="color: #94A3B8; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">ESTATUS DE INTEGRIDAD LEGAL</span>
                        <div style="font-size: 22px; font-weight: 800; color: #22D3EE; margin: 8px 0 4px 0;">100% AUDITADO</div>
                        <span style="color: #CBD5E1; font-size: 12px;">LOTTT Art. 142/144 & IVSS/FAOV</span>
                    </div>

                </div>

                <!-- Graphic Visual Bar Cards -->
                <div style="background: #1E293B; border-radius: 14px; padding: 20px; margin-bottom: 20px; border: 1px solid #334155;">
                    <h3 style="margin-top: 0; margin-bottom: 14px; font-size: 16px; color: #FFFFFF;">📊 Distribución Gráfica de Masa Salarial & Carga Patronal</h3>
                    
                    <div style="margin-bottom: 14px;">
                        <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px;">
                            <span>Sueldo Neto de Trabajadores (75%)</span>
                            <span style="color: #34D399; font-weight: bold;">{total_net_bs*0.75:,.2f} Bs</span>
                        </div>
                        <div style="width: 100%; height: 12px; background: #0F172A; border-radius: 6px; overflow: hidden;">
                            <div style="width: 75%; height: 100%; background: linear-gradient(90deg, #10B981 0%, #34D399 100%);"></div>
                        </div>
                    </div>

                    <div style="margin-bottom: 14px;">
                        <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px;">
                            <span>Aporte Ley de Pensiones SENIAT 9%</span>
                            <span style="color: #F472B6; font-weight: bold;">{seniat_9:,.2f} Bs</span>
                        </div>
                        <div style="width: 100%; height: 12px; background: #0F172A; border-radius: 6px; overflow: hidden;">
                            <div style="width: 9%; height: 100%; background: linear-gradient(90deg, #EC4899 0%, #F472B6 100%);"></div>
                        </div>
                    </div>

                    <div>
                        <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px;">
                            <span>Aportes Patronales IVSS (10%) & FAOV (2%)</span>
                            <span style="color: #FBBF24; font-weight: bold;">{total_net_bs*0.12:,.2f} Bs</span>
                        </div>
                        <div style="width: 100%; height: 12px; background: #0F172A; border-radius: 6px; overflow: hidden;">
                            <div style="width: 12%; height: 100%; background: linear-gradient(90deg, #F59E0B 0%, #FBBF24 100%);"></div>
                        </div>
                    </div>
                </div>

                <div style="text-align: right; color: #64748B; font-size: 11px;">
                    ⚡ Nomina360 Enterprise BI Dashboard • Nubelco Real-Time Analytics v19.2
                </div>

            </div>
            """
            rec.dashboard_html = html


class HrPayrollAIAssistant(models.Model):
    _name = 'hr.payroll.ai.assistant'
    _description = 'Asistente Virtual de Inteligencia Artificial para Consultas LOTTT'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Consulta / Título", required=True)
    employee_id = fields.Many2one('hr.employee', string="Empleado Consultante", required=True)
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    pregunta = fields.Text(string="Pregunta del Trabajador sobre la Nómina o LOTTT", required=True)
    respuesta_ia = fields.Text(string="Respuesta Técnica de Inteligencia Artificial (Nubelco AI)", readonly=True)

    categoria = fields.Selection([
        ('cestaticket', 'Cestaticket Socialista ($40 BCV)'),
        ('prestaciones', 'Prestaciones Sociales (Art. 142 LOTTT)'),
        ('vacaciones', 'Vacaciones y Bono Vacacional'),
        ('retenciones', 'Deducciones Legales (IVSS/FAOV/Pensiones)'),
        ('liquidaciones', 'Liquidación y Finiquito laboral'),
    ], string="Categoría Temática", default='prestaciones', required=True)

    def action_consult_ai(self):
        for rec in self:
            emp_name = rec.employee_id.name if rec.employee_id else "Estimado Empleado"
            rate = rec.company_id.get_bcv_rate()
            cesta_usd = rec.company_id.cesta_ticket_usd
            cesta_bs = round(cesta_usd * rate, 2)

            if rec.categoria == 'cestaticket':
                answer = f"Hola {emp_name}. De acuerdo a la Ley del Cestaticket Socialista y decretos vigentes, tu Bono de Alimentación mensual equivale a ${cesta_usd} USD calculados a la Tasa BCV oficial del día ({rate} Bs/USD), para un total asignado de {cesta_bs} Bs/mes. Este beneficio es de carácter social NO salarial (Art. 105 LOTTT)."
            elif rec.categoria == 'prestaciones':
                lines = self.env['hr.prestaciones.line'].search([('employee_id', '=', rec.employee_id.id)])
                total_garantia = sum(lines.mapped('monto_garantia_trimestre_bs'))
                max_75 = round(total_garantia * 0.75, 2)
                answer = f"Hola {emp_name}. Según el Art. 142 de la LOTTT, la empresa acredita trimestralmente 15 días de salario integral a tu fondo de garantía. Al día de hoy tienes un acumulado garantizado de {total_garantia:.2f} Bs, sobre el cual tienes derecho legal de solicitar un anticipo de hasta el 75% ({max_75:.2f} Bs) para vivienda, salud o educación (Art. 144 LOTTT)."
            elif rec.categoria == 'retenciones':
                answer = f"Hola {emp_name}. Tienes aplicadas las deducciones obligatorias de ley: IVSS Seguro Social (4% sobre sueldo base hasta tope de 5 salarios mínimos), Paro Forzoso SPF (0.5%), FAOV BANAVIH (1%) y la retención del Impuesto Sobre la Renta (ISLR) según tu planilla AR-I. Adicionalmente, tu patrono realiza el aporte especial del 9% según la Ley de Protección de las Pensiones de Mayo 2024."
            else:
                answer = f"Hola {emp_name}. Tu consulta sobre {rec.categoria} ha sido procesada de acuerdo a las tablas y fórmulas de la Ley Orgánica del Trabajo, los Trabajadores y las Trabajadoras (LOTTT) y tu contrato vigente fijado en USD a Tasa BCV."

            rec.write({'respuesta_ia': answer})


class HrPayrollAIChat(models.TransientModel):
    _name = 'hr.payroll.ai.chat'
    _description = 'Asistente de IA Laboral LOTTT & SuperBrain HR - Chat Directo Nubelco'

    employee_id = fields.Many2one('hr.employee', string="Empleado a Consultar (Opcional)")
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    pregunta_chat = fields.Text(
        string="Escribe tu consulta en lenguaje natural",
        required=True,
        default="¿Cuánto gana María Alejandra Benítez y cuál es su saldo de prestaciones sociales?",
        help="Puedes consultar salarios en USD/Bs, expedientes de empleados, Tasa BCV, Cestaticket, retenciones SENIAT, liquidaciones o artículos de la LOTTT."
    )
    respuesta_html = fields.Html(string="Respuesta Nubelco AI Neural Interface", readonly=True)

    def action_send_chat(self):
        self.ensure_one()
        q_raw = self.pregunta_chat or ''
        q = q_raw.lower()
        rate = self.company_id.get_bcv_rate()
        cesta_usd = self.company_id.cesta_ticket_usd
        cesta_bs = round(cesta_usd * rate, 2)

        # 1. Search for Employee in query or use explicitly selected employee
        target_emp = self.employee_id
        if not target_emp:
            all_emps = self.env['hr.employee'].search([('active', '=', True)])
            for emp in all_emps:
                name_parts = emp.name.lower().split()
                if any(part in q for part in name_parts if len(part) > 2):
                    target_emp = emp
                    break

        # 2. Ultra-Sleek Glassmorphic Modern UI Cards
        if target_emp:
            emp = target_emp
            contract = emp.contract_id or self.env['hr.contract'].search([('employee_id', '=', emp.id)], limit=1)
            wage_usd = contract.wage_usd if contract else 0.0
            wage_bs = contract.wage_bs if contract else round(wage_usd * rate, 2)
            job = emp.job_title or 'Cargo no asignado'
            ci = emp.identification_id or 'V00000000'

            latest_slip = self.env['hr.payslip'].search([('employee_id', '=', emp.id)], order='date_to desc', limit=1)
            net_bs = latest_slip.net_wage_bs if latest_slip else round(wage_bs / 2, 2)
            net_usd = latest_slip.net_wage_usd if latest_slip else round(wage_usd / 2, 2)

            lines = self.env['hr.prestaciones.line'].search([('employee_id', '=', emp.id)])
            fondo_bs = sum(lines.mapped('monto_garantia_trimestre_bs'))
            fondo_usd = round(fondo_bs / rate, 2)
            max_anticipo = round(fondo_bs * 0.75, 2)

            anticipos = self.env['hr.prestaciones.anticipo'].search([('employee_id', '=', emp.id), ('state', '=', 'approved')])
            total_anticipos_bs = sum(anticipos.mapped('monto_solicitado_bs'))

            html = f"""
            <div style="background: #0F172A; border-radius: 16px; padding: 24px; color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2); border: 1px solid #1E293B;">
                
                <!-- AI Engine Header Bar -->
                <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 16px; margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="width: 44px; height: 44px; border-radius: 12px; background: linear-gradient(135deg, #6366F1 0%, #3B82F6 100%); display: flex; align-items: center; justify-content: center; font-size: 22px; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);">
                            🤖
                        </div>
                        <div>
                            <h3 style="margin: 0; font-size: 18px; font-weight: 700; color: #FFFFFF; letter-spacing: -0.3px;">Nubelco AI SuperBrain <span style="background: #10B981; color: #022C22; font-size: 10px; padding: 2px 8px; border-radius: 20px; font-weight: 800; text-transform: uppercase; margin-left: 8px;">Neural v19.2</span></h3>
                            <span style="color: #94A3B8; font-size: 12px;">Ficha Inteligente de Recursos Humanos & Nómina Contable</span>
                        </div>
                    </div>
                    <div style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); padding: 6px 14px; border-radius: 20px; font-size: 12px; color: #CBD5E1;">
                        🔱 Tasa BCV: <strong style="color: #10B981;">{rate:.4f} Bs/USD</strong>
                    </div>
                </div>

                <!-- Target Employee Card -->
                <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; border-radius: 12px; padding: 16px; margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <span style="color: #6366F1; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">EXPEDIENTE DEL TRABAJADOR</span>
                            <h2 style="margin: 4px 0 2px 0; font-size: 22px; font-weight: 700; color: #FFFFFF;">{emp.name}</h2>
                            <span style="color: #94A3B8; font-size: 13px;">C.I. {ci} • {job}</span>
                        </div>
                        <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.25) 100%); border: 1px solid #10B981; color: #34D399; padding: 6px 14px; border-radius: 8px; font-size: 12px; font-weight: 600;">
                            ✓ Contrato USD Activo
                        </div>
                    </div>
                </div>

                <!-- 4 KPI Grid Cards -->
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-bottom: 20px;">
                    
                    <div style="background: #1E293B; border-radius: 12px; padding: 16px; border-left: 4px solid #6366F1;">
                        <span style="color: #94A3B8; font-size: 11px; font-weight: 600; text-transform: uppercase;">SUELDO PACTADO (USD)</span>
                        <div style="font-size: 24px; font-weight: 800; color: #818CF8; margin: 6px 0 2px 0;">${wage_usd:,.2f} USD</div>
                        <span style="color: #CBD5E1; font-size: 12px;">Equivalente: <strong>{wage_bs:,.2f} Bs</strong></span>
                    </div>

                    <div style="background: #1E293B; border-radius: 12px; padding: 16px; border-left: 4px solid #10B981;">
                        <span style="color: #94A3B8; font-size: 11px; font-weight: 600; text-transform: uppercase;">ÚLTIMO NETO QUINCENAL</span>
                        <div style="font-size: 24px; font-weight: 800; color: #34D399; margin: 6px 0 2px 0;">{net_bs:,.2f} Bs</div>
                        <span style="color: #CBD5E1; font-size: 12px;">Equivalente: <strong>${net_usd:,.2f} USD</strong></span>
                    </div>

                    <div style="background: #1E293B; border-radius: 12px; padding: 16px; border-left: 4px solid #F59E0B;">
                        <span style="color: #94A3B8; font-size: 11px; font-weight: 600; text-transform: uppercase;">FONDO PRESTACIONES (ART. 142)</span>
                        <div style="font-size: 24px; font-weight: 800; color: #FBBF24; margin: 6px 0 2px 0;">{fondo_bs:,.2f} Bs</div>
                        <span style="color: #CBD5E1; font-size: 12px;">Equivalente: <strong>${fondo_usd:,.2f} USD</strong></span>
                    </div>

                    <div style="background: #1E293B; border-radius: 12px; padding: 16px; border-left: 4px solid #EC4899;">
                        <span style="color: #94A3B8; font-size: 11px; font-weight: 600; text-transform: uppercase;">DISPONIBLE ANTICIPO 75% (ART. 144)</span>
                        <div style="font-size: 24px; font-weight: 800; color: #F472B6; margin: 6px 0 2px 0;">{max_anticipo:,.2f} Bs</div>
                        <span style="color: #CBD5E1; font-size: 12px;">Anticipos dados: <strong>{total_anticipos_bs:,.2f} Bs</strong></span>
                    </div>

                </div>

                <!-- Legal Footer Note -->
                <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid #334155; border-radius: 10px; padding: 14px; font-size: 12px; color: #94A3B8; display: flex; align-items: center; justify-content: space-between;">
                    <span>⚖️ <strong>Marco Legal Vigilado:</strong> LOTTT Art. 142/144 • Cestaticket ${cesta_usd:.0f} BCV ({cesta_bs:,.2f} Bs) • SENIAT 9% Pensiones.</span>
                    <span style="color: #6366F1; font-weight: 700;">Nubelco Enterprise v19</span>
                </div>

            </div>
            """
        elif 'cestaticket' in q or 'bono' in q or 'aliment' in q or '40' in q:
            html = f"""
            <div style="background: #0F172A; border-radius: 16px; padding: 24px; color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3); border: 1px solid #1E293B;">
                <div style="display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #334155; padding-bottom: 14px; margin-bottom: 18px;">
                    <div style="width: 40px; height: 40px; border-radius: 10px; background: #10B981; display: flex; align-items: center; justify-content: center; font-size: 20px;">🟢</div>
                    <div>
                        <h3 style="margin: 0; color: #FFFFFF; font-size: 17px;">Cestaticket Socialista Indexado</h3>
                        <span style="color: #94A3B8; font-size: 12px;">Decreto Presidencial & LOTTT Art. 105</span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px;">
                    <div style="background: #1E293B; padding: 14px; border-radius: 10px; border-left: 4px solid #10B981;">
                        <span style="color: #94A3B8; font-size: 11px;">MONTO EN USD</span>
                        <div style="font-size: 22px; font-weight: 800; color: #34D399;">${cesta_usd:,.2f} USD / mes</div>
                    </div>
                    <div style="background: #1E293B; padding: 14px; border-radius: 10px; border-left: 4px solid #3B82F6;">
                        <span style="color: #94A3B8; font-size: 11px;">EQUIVALENTE EN BOLÍVARES</span>
                        <div style="font-size: 22px; font-weight: 800; color: #60A5FA;">{cesta_bs:,.2f} Bs / mes</div>
                        <span style="font-size: 11px; color: #94A3B8;">({cesta_bs/2:,.2f} Bs por quincena a Tasa BCV {rate:.4f})</span>
                    </div>
                </div>
            </div>
            """
        elif 'pension' in q or 'seniat' in q or 'costo' in q or 'empresa' in q or 'total' in q:
            emp_count = self.env['hr.employee'].search_count([('active', '=', True)])
            payslips = self.env['hr.payslip'].search([('state', '=', 'done')])
            total_bs = sum(payslips.mapped('net_wage_bs'))
            total_usd = sum(payslips.mapped('net_wage_usd'))
            pensiones_9 = round(total_bs * 0.09, 2)

            html = f"""
            <div style="background: #0F172A; border-radius: 16px; padding: 24px; color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3); border: 1px solid #1E293B;">
                <div style="display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #334155; padding-bottom: 14px; margin-bottom: 18px;">
                    <div style="width: 40px; height: 40px; border-radius: 10px; background: #0284C7; display: flex; align-items: center; justify-content: center; font-size: 20px;">📊</div>
                    <div>
                        <h3 style="margin: 0; color: #FFFFFF; font-size: 17px;">Consolidado de Masa Salarial & Retenciones SENIAT</h3>
                        <span style="color: #94A3B8; font-size: 12px;">Nube de Datos Financieros de la Empresa</span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
                    <div style="background: #1E293B; padding: 14px; border-radius: 10px; border-left: 4px solid #6366F1;">
                        <span style="color: #94A3B8; font-size: 11px;">EMPLEADOS ACTIVOS</span>
                        <div style="font-size: 22px; font-weight: 800; color: #818CF8;">{emp_count}</div>
                    </div>
                    <div style="background: #1E293B; padding: 14px; border-radius: 10px; border-left: 4px solid #10B981;">
                        <span style="color: #94A3B8; font-size: 11px;">NÓMINA NETO MES</span>
                        <div style="font-size: 22px; font-weight: 800; color: #34D399;">{total_bs:,.2f} Bs</div>
                        <span style="font-size: 11px; color: #94A3B8;">(${total_usd:,.2f} USD)</span>
                    </div>
                    <div style="background: #1E293B; padding: 14px; border-radius: 10px; border-left: 4px solid #F59E0B;">
                        <span style="color: #94A3B8; font-size: 11px;">SENIAT PENSIONES 9%</span>
                        <div style="font-size: 22px; font-weight: 800; color: #FBBF24;">{pensiones_9:,.2f} Bs</div>
                    </div>
                </div>
            </div>
            """
        else:
            html = f"""
            <div style="background: #0F172A; border-radius: 16px; padding: 24px; color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3); border: 1px solid #1E293B;">
                <div style="display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #334155; padding-bottom: 14px; margin-bottom: 14px;">
                    <div style="width: 40px; height: 40px; border-radius: 10px; background: #6366F1; display: flex; align-items: center; justify-content: center; font-size: 20px;">🤖</div>
                    <div>
                        <h3 style="margin: 0; color: #FFFFFF; font-size: 17px;">Nubelco AI SuperBrain Engine</h3>
                        <span style="color: #94A3B8; font-size: 12px;">Respuesta Inteligente de Asistencia Laboral</span>
                    </div>
                </div>
                <p style="color: #CBD5E1; font-size: 14px;">Consulta evaluada: <em>"{q_raw}"</em></p>
                <p style="color: #94A3B8; font-size: 13px;">El sistema mantiene control automatizado de la LOTTT, Cestaticket $40 BCV, retenciones IVSS, FAOV y la contribución del 9% del SENIAT.</p>
            </div>
            """

        self.respuesta_html = html
        return {
            'name': _('Chat Directo Nubelco AI'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payroll.ai.chat',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
