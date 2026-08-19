# -*- coding: utf-8 -*-
import json
import logging
import urllib.request
import urllib.error
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class HrPayrollAIService(models.AbstractModel):
    _name = 'hr.payroll.ai.service'
    _description = 'Servicio Integrado de IA Multi-Proveedor con Modo Simulación y Fallback (Nubelco AI)'

    @api.model
    def process_chat_query(self, query_text, employee_id=False, company_id=False, session_id=False):
        """
        Procesa una consulta de usuario sobre la nómina / LOTTT.
        - Soporta memoria multi-turno si se provee session_id.
        - Si ai_provider == 'heuristic_fallback', cae al motor local.
        - Si ai_simulation_mode == True, agrega trazabilidad explicativa sin alterar producción.
        - Si ocurre cualquier falla de API o timeout, retorna None (fallback seguro).
        """
        company = company_id or self.env.company
        provider = company.ai_provider or 'heuristic_fallback'

        if provider == 'heuristic_fallback':
            _logger.info("Nubelco AI Service: Usando Motor Determinista Local (modo fallback por configuración).")
            return None

        api_key = (company.ai_api_key or '').strip()
        base_url = (company.ai_base_url or '').strip().rstrip('/')
        model_name = (company.ai_model_name or 'deepseek-chat').strip()
        is_simulation = company.ai_simulation_mode

        if provider in ['deepseek', 'openai', 'anthropic'] and not api_key:
            _logger.warning("Nubelco AI Service: API Key no configurada para %s. Retornando a motor determinista.", provider)
            return None

        # Sanitizar entrada del usuario
        clean_query = (query_text or '').strip()[:1000]

        # Memoria Conversacional Multi-turno
        session_memory = ""
        if session_id:
            past_msgs = self.env['hr.payroll.ai.message'].search([('session_id', '=', session_id)], order='date desc', limit=6)
            if past_msgs:
                memory_lines = []
                for m in reversed(past_msgs):
                    role_name = "Usuario" if m.role == 'user' else "Asistente AI"
                    memory_lines.append(f"{role_name}: {m.content[:250]}")
                session_memory = "Memoria Conversacional Anterior (Multi-turno):\n" + "\n".join(memory_lines)

        # Contexto de herramientas de solo lectura si están activadas
        tools_summary = ""
        if company.ai_tools_enabled:
            tools_summary = self._gather_readonly_context(clean_query, employee_id, company)

        # Inyección RAG de citas legales verificadas
        rag_context = ""
        if company.ai_rag_enabled:
            rag_context = self._gather_rag_legal_context(clean_query)

        rate = company.get_bcv_rate() or 757.74
        cesta_usd = company.cesta_ticket_usd or 40.0
        cesta_bs = round(cesta_usd * rate, 2)

        sim_header = ""
        if is_simulation:
            sim_header = "[MODO SIMULACIÓN Y BORRADOR ACTIVADO - Respuestas de prueba sin efectos en BD]\n"

        system_prompt = (
            f"{sim_header}"
            "Eres Nubelco AI SuperBrain, un Asistente Experto en Recursos Humanos y Nómina Venezolana bajo la LOTTT.\n"
            f"Parámetros Oficiales: Tasa BCV={rate:.4f} Bs/USD, Cestaticket=${cesta_usd:.2f} USD ({cesta_bs:.2f} Bs/mes), Ley Pensiones SENIAT=9%.\n"
            f"{session_memory}\n"
            f"{tools_summary}\n"
            f"{rag_context}\n"
            "Reglas Estrictas:\n"
            "1. Responde de forma profesional, clara y precisa en español.\n"
            "2. Fundamenta tus explicaciones ÚNICAMENTE en artículos VERIFICADOS de la LOTTT (Art. 142 garantía, Art. 144 anticipos 75%, Art. 105 cestaticket, Art. 92 indemnización, Art. 108 inembargabilidad).\n"
            "3. NUNCA inventes artículos de ley, números de decretos ficticios ni cálculos no respaldados.\n"
            "4. Si la consulta involucra una acción de modificación (como registrar anticipos), debes declarar que requiere confirmación explícita del usuario y NO ejecutar la acción directamente."
        )

        try:
            if provider in ['deepseek', 'openai', 'ollama']:
                response_text = self._call_openai_compatible_api(base_url, api_key, model_name, company.ai_temperature or 0.2, system_prompt, clean_query)
            elif provider == 'anthropic':
                response_text = self._call_anthropic_api(base_url, api_key, model_name, company.ai_temperature or 0.2, system_prompt, clean_query)
            else:
                response_text = None

            if response_text and is_simulation:
                response_text = f"<div style='background:#1E293B; border-left:4px solid #F59E0B; padding:8px 12px; margin-bottom:12px; font-size:12px; color:#FCD34D;'>⚠️ <strong>[Modo Simulación / Borrador]</strong> Esta respuesta es una prueba de evaluación y no altera registros de nómina ni contratos.</div>{response_text}"

            return response_text
        except Exception as e:
            _logger.error("Nubelco AI Service: Fallo al consultar el proveedor LLM %s (%s). Activando fallback determinista de respaldo.", provider, str(e))
            return None

    @api.model
    def _gather_readonly_context(self, query, employee_id, company):
        tools_model = self.env['hr.payroll.ai.tools']
        context_parts = []

        if employee_id:
            emp = self.env['hr.employee'].browse(employee_id)
            if emp.exists():
                emp_data = tools_model.execute_tool("get_employee_summary", {"employee_name": emp.name}, company)
                pres_data = tools_model.execute_tool("get_prestaciones_summary", {"employee_name": emp.name}, company)
                context_parts.append(f"Datos Expediente: {json.dumps(emp_data, ensure_ascii=False)}")
                context_parts.append(f"Datos Prestaciones: {json.dumps(pres_data, ensure_ascii=False)}")

        bcv_data = tools_model.execute_tool("get_bcv_rate_info", {}, company)
        context_parts.append(f"Datos BCV: {json.dumps(bcv_data, ensure_ascii=False)}")

        return "Contexto ORM Solo Lectura: " + " | ".join(context_parts)

    @api.model
    def _gather_rag_legal_context(self, query):
        q_lower = query.lower()
        tools_model = self.env['hr.payroll.ai.tools']
        citations = []

        if any(k in q_lower for k in ['142', 'garantía', 'garantia', 'trimestral', 'prestacion', 'prestaciones']):
            res = tools_model.execute_tool("get_legal_article_reference", {"article_number": "142"})
            if res.get("status") == "success":
                citations.append(res.get("legal_text"))

        if any(k in q_lower for k in ['144', 'anticipo', '75%', 'vivienda', 'salud', 'hipoteca']):
            res = tools_model.execute_tool("get_legal_article_reference", {"article_number": "144"})
            if res.get("status") == "success":
                citations.append(res.get("legal_text"))

        if any(k in q_lower for k in ['105', 'cestaticket', 'alimentacion', 'alimentación', 'bono']):
            res = tools_model.execute_tool("get_legal_article_reference", {"article_number": "105"})
            if res.get("status") == "success":
                citations.append(res.get("legal_text"))

        if citations:
            return "Base Legal Verificada RAG (LOTTT):\n" + "\n".join(f"- {c}" for c in citations)
        return ""

    @api.model
    def _call_openai_compatible_api(self, base_url, api_key, model, temperature, system_prompt, user_query):
        url = f"{base_url}/chat/completions" if not base_url.endswith('/chat/completions') else base_url
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_query}
            ],
            'temperature': max(0.0, min(1.0, temperature)),
        }

        data_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method='POST')

        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status == 200:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body)
                choices = res_json.get('choices', [])
                if choices and len(choices) > 0:
                    return choices[0].get('message', {}).get('content', '')
        return None

    @api.model
    def _call_anthropic_api(self, base_url, api_key, model, temperature, system_prompt, user_query):
        url = f"{base_url}/v1/messages" if not base_url.endswith('/messages') else base_url
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01'
        }

        payload = {
            'model': model,
            'max_tokens': 1500,
            'system': system_prompt,
            'messages': [{'role': 'user', 'content': user_query}],
            'temperature': max(0.0, min(1.0, temperature)),
        }

        data_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method='POST')

        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status == 200:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body)
                contents = res_json.get('content', [])
                if contents and len(contents) > 0:
                    return contents[0].get('text', '')
        return None
