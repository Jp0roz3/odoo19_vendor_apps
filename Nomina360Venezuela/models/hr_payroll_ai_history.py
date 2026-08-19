# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class HrPayrollAISession(models.Model):
    _name = 'hr.payroll.ai.session'
    _description = 'Sesión Persistente de Chat de IA Laboral (Nubelco AI SuperBrain)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'write_date desc, id desc'

    name = fields.Char(string="Título de la Conversación", required=True, default=lambda self: _('Nueva Consulta de IA'))
    user_id = fields.Many2one('res.users', string="Usuario", default=lambda self: self.env.user, required=True)
    employee_id = fields.Many2one('hr.employee', string="Empleado en Contexto (Opcional)")
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company, required=True)

    ai_provider = fields.Selection([
        ('heuristic_fallback', 'Motor Determinista Local (Palabras Clave / Sin API Key)'),
        ('deepseek', 'DeepSeek API (DeepSeek-R1 / V3)'),
        ('openai', 'OpenAI API (GPT-4o / GPT-4o-mini)'),
        ('anthropic', 'Anthropic API (Claude 3.5 Sonnet)'),
        ('ollama', 'Ollama Servidor Local (Privado On-Premise)'),
    ], string="Proveedor de IA", default=lambda self: self.env.company.ai_provider or 'heuristic_fallback', required=True)

    is_simulation_mode = fields.Boolean(string="Modo Simulación / Borrador", default=lambda self: self.env.company.ai_simulation_mode)

    message_ids = fields.One2many('hr.payroll.ai.message', 'session_id', string="Historial de Mensajes")
    input_text = fields.Text(string="Escribe tu consulta...", help="Consulta en lenguaje natural sobre salarios, prestaciones, anticipos o la LOTTT.")

    history_html = fields.Html(string="Consolidado de Conversación", compute='_compute_history_html', sanitize=False)
    message_count = fields.Integer(string="Cantidad de Mensajes", compute='_compute_history_html')

    @api.depends('message_ids', 'message_ids.content_html')
    def _compute_history_html(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)
            if not rec.message_ids:
                rec.history_html = """
                <div style="background: #0F172A; border-radius: 16px; padding: 24px; color: #94A3B8; text-align: center; font-family: -apple-system, sans-serif; border: 1px dashed #334155;">
                    <div style="font-size: 32px; margin-bottom: 8px;">🤖</div>
                    <h3 style="color: #FFFFFF; margin: 0 0 4px 0; font-size: 16px;">Sesión de IA Iniciada</h3>
                    <p style="margin: 0; font-size: 13px;">Escribe una pregunta o selecciona uno de los accesos rápidos a continuación para comenzar.</p>
                </div>
                """
            else:
                html_parts = []
                for msg in rec.message_ids.sorted('date'):
                    html_parts.append(msg.content_html or '')
                rec.history_html = "".join(html_parts)

    def action_send_message(self):
        self.ensure_one()
        query = (self.input_text or '').strip()
        if not query:
            return

        # Auto-generar título si es la primera pregunta
        if self.name in [_('Nueva Consulta de IA'), 'Nueva Consulta de IA']:
            clean_title = query[:40] + ("..." if len(query) > 40 else "")
            self.name = clean_title

        # 1. Registrar mensaje del usuario
        user_msg = self.env['hr.payroll.ai.message'].create({
            'session_id': self.id,
            'role': 'user',
            'content': query,
            'is_simulation': self.is_simulation_mode,
        })

        # Limpiar input
        self.input_text = ""

        # 2. Invocar servicio de IA pasando la sesión para contexto multi-turno
        service = self.env['hr.payroll.ai.service']
        llm_response = service.process_chat_query(
            query,
            employee_id=self.employee_id.id if self.employee_id else False,
            company_id=self.company_id,
            session_id=self.id
        )

        # 3. Registrar respuesta de la IA
        if llm_response:
            ai_content = llm_response
        else:
            # Fallback determinista local
            ai_content = self._generate_heuristic_fallback_response(query)

        self.env['hr.payroll.ai.message'].create({
            'session_id': self.id,
            'role': 'assistant',
            'content': ai_content,
            'is_simulation': self.is_simulation_mode,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payroll.ai.session',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'main',
        }

    def _generate_heuristic_fallback_response(self, query):
        q = query.lower()
        rate = self.company_id.get_bcv_rate() or 757.74
        cesta_usd = self.company_id.cesta_ticket_usd or 40.0
        cesta_bs = round(cesta_usd * rate, 2)

        emp = self.employee_id
        if not emp:
            all_emps = self.env['hr.employee'].search([('active', '=', True)])
            for e in all_emps:
                name_parts = e.name.lower().split()
                if any(part in q for part in name_parts if len(part) > 2):
                    emp = e
                    break

        if emp:
            contract = emp.contract_id or self.env['hr.contract'].search([('employee_id', '=', emp.id)], limit=1)
            wage_usd = contract.wage_usd if contract else 0.0
            wage_bs = contract.wage_bs if contract else round(wage_usd * rate, 2)
            lines = self.env['hr.prestaciones.line'].search([('employee_id', '=', emp.id)])
            fondo_bs = sum(lines.mapped('monto_garantia_trimestre_bs'))
            fondo_usd = round(fondo_bs / rate, 2)
            max_75 = round(fondo_bs * 0.75, 2)

            return f"""
            <strong>Expediente de {emp.name} (CI {emp.identification_id or 'N/A'}):</strong><br/>
            • <strong>Cargo:</strong> {emp.job_title or 'No asignado'}<br/>
            • <strong>Sueldo Pactado:</strong> ${wage_usd:,.2f} USD ({wage_bs:,.2f} Bs a Tasa BCV {rate:.4f})<br/>
            • <strong>Fondo Prestaciones (Art. 142 LOTTT):</strong> {fondo_bs:,.2f} Bs (${fondo_usd:,.2f} USD)<br/>
            • <strong>Disponible Anticipo 75% (Art. 144 LOTTT):</strong> {max_75:,.2f} Bs<br/>
            • <strong>Cestaticket Ley:</strong> ${cesta_usd:.2f} USD ({cesta_bs:,.2f} Bs/mes)
            """
        elif any(k in q for k in ['bcv', 'tasa', 'dolar', 'dólar']):
            return f"La Tasa Oficial BCV activa en la compañía es de <strong>{rate:.4f} Bs/USD</strong>. El Cestaticket equivalente a $40 USD se ubica en <strong>{cesta_bs:,.2f} Bs/mes</strong>."
        elif any(k in q for k in ['prestacion', 'prestaciones', '142', '144']):
            return f"Según el Art. 142 de la LOTTT, la empresa acredita 15 días trimestrales de salario integral como garantía. El trabajador tiene derecho a solicitar un anticipo de hasta el 75% para vivienda, salud o educación (Art. 144 LOTTT)."
        else:
            return f"Consulta procesada: <em>'{query}'</em>. El sistema mantiene control de la LOTTT, Tasa BCV ({rate:.4f} Bs/USD), Cestaticket (${cesta_usd} USD) y retenciones SENIAT 9%."

    # Acciones Rápidas (Prompt Chips)
    def action_quick_prestaciones(self):
        emp_name = self.employee_id.name if self.employee_id else "empleado"
        self.input_text = f"¿Cuál es el saldo acumulado de prestaciones sociales (Art. 142 LOTTT) de {emp_name}?"
        return self.action_send_message()

    def action_quick_anticipo(self):
        emp_name = self.employee_id.name if self.employee_id else "empleado"
        self.input_text = f"¿Cuánto es el monto máximo permitido para anticipo del 75% (Art. 144 LOTTT) de {emp_name}?"
        return self.action_send_message()

    def action_quick_cestaticket(self):
        self.input_text = "¿Cómo se calcula el Cestaticket Socialista de $40 USD a Tasa BCV este mes?"
        return self.action_send_message()

    def action_quick_seniat(self):
        self.input_text = "¿Cuál es el monto consolidado de masa salarial y aporte 9% de Ley de Pensiones para el SENIAT?"
        return self.action_send_message()


class HrPayrollAIMessage(models.Model):
    _name = 'hr.payroll.ai.message'
    _description = 'Mensaje de Historial de Chat IA'
    _order = 'date asc, id asc'

    session_id = fields.Many2one('hr.payroll.ai.session', string="Sesión", required=True, ondelete='cascade')
    role = fields.Selection([
        ('user', 'Usuario'),
        ('assistant', 'Nubelco AI SuperBrain'),
        ('system', 'Sistema'),
    ], string="Rol", required=True, default='user')

    content = fields.Text(string="Contenido Plano", required=True)
    content_html = fields.Html(string="Renderizado HTML Glassmorphic", compute='_compute_content_html', store=True, sanitize=False)
    date = fields.Datetime(string="Fecha / Hora", default=fields.Datetime.now, required=True)
    is_simulation = fields.Boolean(string="Es Simulación", default=False)

    @api.depends('role', 'content', 'is_simulation')
    def _compute_content_html(self):
        for rec in self:
            sim_badge = ""
            if rec.is_simulation:
                sim_badge = "<span style='background:#F59E0B; color:#000; font-size:10px; padding:2px 6px; border-radius:10px; font-weight:bold; margin-left:8px;'>SIMULACIÓN</span>"

            if rec.role == 'user':
                html = f"""
                <div style="display: flex; justify-content: flex-end; margin-bottom: 14px;">
                    <div style="background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%); color: #FFFFFF; padding: 14px 18px; border-radius: 16px 16px 2px 16px; max-width: 80%; font-family: -apple-system, sans-serif; font-size: 13px; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);">
                        <div style="font-size: 11px; color: #93C5FD; font-weight: 700; margin-bottom: 4px;">TÚ {sim_badge}</div>
                        <div>{rec.content}</div>
                    </div>
                </div>
                """
            else:
                html = f"""
                <div style="display: flex; justify-content: flex-start; margin-bottom: 14px;">
                    <div style="background: #0F172A; border: 1px solid #1E293B; color: #F8FAFC; padding: 16px 20px; border-radius: 16px 16px 16px 2px; max-width: 85%; font-family: -apple-system, sans-serif; font-size: 13px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4);">
                        <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 10px;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 16px;">🤖</span>
                                <strong style="color: #60A5FA; font-size: 12px;">Nubelco AI SuperBrain</strong>
                                {sim_badge}
                            </div>
                            <span style="color: #64748B; font-size: 10px;">{rec.date.strftime('%H:%M') if rec.date else ''}</span>
                        </div>
                        <div style="line-height: 1.7; color: #CBD5E1;">{rec.content}</div>
                    </div>
                </div>
                """
            rec.content_html = html
