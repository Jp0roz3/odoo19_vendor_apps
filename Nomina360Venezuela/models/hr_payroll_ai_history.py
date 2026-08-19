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
    bcv_rate_display = fields.Float(string="Tasa BCV", compute='_compute_bcv_display', digits=(12, 4))

    @api.depends('company_id')
    def _compute_bcv_display(self):
        for rec in self:
            rec.bcv_rate_display = rec.company_id.get_bcv_rate() or 757.74

    @api.depends('message_ids', 'message_ids.content_html')
    def _compute_history_html(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)
            if not rec.message_ids:
                rec.history_html = """
                <div class="card p-4 text-center border-dashed my-3">
                    <div class="display-6 text-primary mb-2">🤖</div>
                    <h5 class="fw-bold mb-1">Sesión Inteligente Lista</h5>
                    <p class="text-muted mb-0 small">Escribe una pregunta o haz clic en uno de los accesos rápidos a continuación para comenzar.</p>
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
            <div class="mb-2"><strong class="text-primary">Expediente de {emp.name}</strong> <span class="badge bg-secondary">CI {emp.identification_id or 'N/A'}</span></div>
            <ul class="list-unstyled mb-0">
                <li>• <strong>Cargo:</strong> {emp.job_title or 'No asignado'}</li>
                <li>• <strong>Sueldo Pactado:</strong> ${wage_usd:,.2f} USD <span class="text-muted">({wage_bs:,.2f} Bs a BCV {rate:.4f})</span></li>
                <li>• <strong>Fondo Prestaciones (Art. 142 LOTTT):</strong> <strong class="text-success">{fondo_bs:,.2f} Bs</strong> (${fondo_usd:,.2f} USD)</li>
                <li>• <strong>Disponible Anticipo 75% (Art. 144 LOTTT):</strong> <strong class="text-warning">{max_75:,.2f} Bs</strong></li>
                <li>• <strong>Cestaticket Ley:</strong> ${cesta_usd:.2f} USD ({cesta_bs:,.2f} Bs/mes)</li>
            </ul>
            """
        elif any(k in q for k in ['bcv', 'tasa', 'dolar', 'dólar']):
            return f"La Tasa Oficial BCV activa es de <strong class='text-primary'>{rate:.4f} Bs/USD</strong>. Cestaticket ($40 USD): <strong class='text-success'>{cesta_bs:,.2f} Bs/mes</strong>."
        elif any(k in q for k in ['prestacion', 'prestaciones', '142', '144']):
            return f"Según el <strong>Art. 142 de la LOTTT</strong>, la empresa acredita 15 días trimestrales de salario integral como garantía. El trabajador tiene derecho a solicitar un anticipo de hasta el 75% para vivienda, salud o educación (<strong>Art. 144 LOTTT</strong>)."
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
    content_html = fields.Html(string="Renderizado Nativo Odoo UI", compute='_compute_content_html', store=True, sanitize=False)
    date = fields.Datetime(string="Fecha / Hora", default=fields.Datetime.now, required=True)
    is_simulation = fields.Boolean(string="Es Simulación", default=False)

    @api.depends('role', 'content', 'is_simulation')
    def _compute_content_html(self):
        for rec in self:
            sim_badge = ""
            if rec.is_simulation:
                sim_badge = '<span class="badge text-bg-warning ms-2">SIMULACIÓN</span>'

            if rec.role == 'user':
                html = f"""
                <div class="d-flex justify-content-end mb-3">
                    <div class="card bg-primary text-white border-0 shadow-sm" style="max-width: 80%; border-radius: 16px 16px 2px 16px;">
                        <div class="card-body p-3">
                            <div class="d-flex justify-content-between align-items-center mb-1 small opacity-75">
                                <span class="fw-bold">TÚ</span>
                                {sim_badge}
                            </div>
                            <div class="small">{rec.content}</div>
                        </div>
                    </div>
                </div>
                """
            else:
                html = f"""
                <div class="d-flex justify-content-start mb-3">
                    <div class="card border shadow-sm w-100" style="border-radius: 16px 16px 16px 2px;">
                        <div class="card-header bg-body-tertiary d-flex justify-content-between align-items-center py-2 px-3">
                            <div class="d-flex align-items-center gap-2">
                                <span class="fs-5">🤖</span>
                                <strong class="text-primary small">Nubelco AI SuperBrain</strong>
                                {sim_badge}
                            </div>
                            <small class="text-muted">{rec.date.strftime('%H:%M') if rec.date else ''}</small>
                        </div>
                        <div class="card-body p-3 small text-body">
                            {rec.content}
                        </div>
                    </div>
                </div>
                """
            rec.content_html = html
