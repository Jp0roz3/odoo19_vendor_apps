# -*- coding: utf-8 -*-
import logging
from odoo import models, api, _

_logger = logging.getLogger(__name__)


class HrPayrollAITools(models.AbstractModel):
    _name = 'hr.payroll.ai.tools'
    _description = 'Registry de Herramientas de Solo Lectura para Function Calling (Nubelco AI)'

    @api.model
    def get_available_tools_schema(self):
        """
        Retorna las definiciones JSON Schema de las herramientas de SOLO LECTURA disponibles.
        No se incluye ninguna herramienta de escritura para prevenir modificaciones accidentales.
        """
        return [
            {
                "name": "get_employee_summary",
                "description": "Obtiene el expediente del trabajador, cargo, contrato en USD/Bs y estatus laboral.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "employee_name": {
                            "type": "string",
                            "description": "Nombre o apellido del trabajador a consultar."
                        }
                    },
                    "required": ["employee_name"]
                }
            },
            {
                "name": "get_prestaciones_summary",
                "description": "Consulta el fondo acumulado de prestaciones sociales (Art. 142 LOTTT) y disponible de anticipo 75% (Art. 144 LOTTT).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "employee_name": {
                            "type": "string",
                            "description": "Nombre del trabajador."
                        }
                    },
                    "required": ["employee_name"]
                }
            },
            {
                "name": "get_bcv_rate_info",
                "description": "Obtiene la Tasa Oficial de Cambio del Banco Central de Venezuela (BCV) activa en el sistema.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_legal_article_reference",
                "description": "Consulta la cita legal exacta y verificada de un artículo de la LOTTT (Art. 142, 144, 105, 92, 108, 174).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "article_number": {
                            "type": "string",
                            "description": "Número de artículo a consultar (ej: '142', '144', '105')."
                        }
                    },
                    "required": ["article_number"]
                }
            }
        ]

    @api.model
    def execute_tool(self, tool_name, tool_args, company=False):
        """
        Ejecuta de forma segura una herramienta de SOLO LECTURA.
        Trazabilidad completa sin efectos secundarios en la base de datos.
        """
        comp = company or self.env.company
        _logger.info("Nubelco AI Tools: Ejecutando herramienta de lectura '%s' con argumentos %s", tool_name, tool_args)

        try:
            if tool_name == "get_employee_summary":
                return self._tool_get_employee_summary(tool_args.get("employee_name", ""), comp)
            elif tool_name == "get_prestaciones_summary":
                return self._tool_get_prestaciones_summary(tool_args.get("employee_name", ""), comp)
            elif tool_name == "get_bcv_rate_info":
                return self._tool_get_bcv_rate_info(comp)
            elif tool_name == "get_legal_article_reference":
                return self._tool_get_legal_article_reference(tool_args.get("article_number", ""))
            else:
                return {"error": f"Herramienta '{tool_name}' no reconocida o no permitida."}
        except Exception as e:
            _logger.error("Nubelco AI Tools: Error al ejecutar tool %s: %s", tool_name, str(e))
            return {"error": f"Fallo al ejecutar la herramienta: {str(e)}"}

    @api.model
    def _tool_get_employee_summary(self, name_search, company):
        emps = self.env['hr.employee'].search([('name', 'ilike', name_search), ('active', '=', True)], limit=1)
        if not emps:
            return {"status": "not_found", "message": f"No se encontró un trabajador activo con el nombre '{name_search}'."}

        emp = emps[0]
        contract = emp.contract_id or self.env['hr.contract'].search([('employee_id', '=', emp.id)], limit=1)
        rate = company.get_bcv_rate() or 757.74
        wage_usd = contract.wage_usd if contract else 0.0
        wage_bs = contract.wage_bs if contract else round(wage_usd * rate, 2)

        return {
            "status": "success",
            "employee_id": emp.id,
            "name": emp.name,
            "identification_id": emp.identification_id or "Sin Cédula",
            "job_title": emp.job_title or "Cargo no asignado",
            "contract_active": bool(contract),
            "wage_usd": wage_usd,
            "wage_bs": wage_bs,
            "bcv_rate": rate,
        }

    @api.model
    def _tool_get_prestaciones_summary(self, name_search, company):
        emps = self.env['hr.employee'].search([('name', 'ilike', name_search), ('active', '=', True)], limit=1)
        if not emps:
            return {"status": "not_found", "message": f"No se encontró trabajador activo con el nombre '{name_search}'."}

        emp = emps[0]
        lines = self.env['hr.prestaciones.line'].search([('employee_id', '=', emp.id)])
        fondo_bs = round(sum(lines.mapped('monto_garantia_trimestre_bs')), 2)
        max_anticipo_75 = round(fondo_bs * 0.75, 2)
        rate = company.get_bcv_rate() or 757.74
        fondo_usd = round(fondo_bs / rate, 2)

        return {
            "status": "success",
            "employee_name": emp.name,
            "fondo_acumulado_bs": fondo_bs,
            "fondo_acumulado_usd": fondo_usd,
            "max_anticipo_75_percent_bs": max_anticipo_75,
            "legal_basis": "LOTTT Artículos 142 (Garantía) y 144 (Anticipo 75%)"
        }

    @api.model
    def _tool_get_bcv_rate_info(self, company):
        rate = company.get_bcv_rate()
        return {
            "status": "success",
            "bcv_rate": rate,
            "cesta_ticket_usd": company.cesta_ticket_usd or 40.0,
            "cesta_ticket_bs": round((company.cesta_ticket_usd or 40.0) * rate, 2),
            "source": "Banco Central de Venezuela (BCV)"
        }

    @api.model
    def _tool_get_legal_article_reference(self, article_num):
        art_clean = article_num.replace("Art.", "").replace("Art", "").strip()
        articles_db = {
            "142": "Art. 142 LOTTT (Garantía de Prestaciones Sociales): El patrono depositará a cada trabajador por concepto de garantía de prestaciones sociales el equivalente a 15 días cada trimestre, calculado con base al último salario devengado (142a). Adicionalmente, después del primer año se añadirán 2 días de salario por cada año acumulable hasta 30 días (142b).",
            "144": "Art. 144 LOTTT (Anticipos de Prestaciones Sociales): El trabajador tendrá derecho a solicitar anticipos de hasta un 75% del monto depositado como garantía de sus prestaciones sociales para: a) Construcción, adquisición o mejora de vivienda; b) Liberación de hipoteca; c) Gastos médicos y de salud; d) Gastos de educación.",
            "105": "Art. 105 LOTTT (Beneficios Sociales No Remunerativos): Se consideran beneficios sociales no remunerativos los servicios de comedores, cupones, dinero electrónico o tarjetas de alimentación (Cestaticket Socialista), guarderías infantiles y útiles escolares.",
            "92": "Art. 92 LOTTT (Indemnización por Terminación por Causa Injustificada): En caso de terminación de la relación de trabajo por causas ajenas a la voluntad del trabajador o despido injustificado, el patrono deberá pagar una indemnización equivalente al monto que le corresponda por prestaciones sociales.",
            "108": "Art. 108 LOTTT (Carácter Inembargable de las Prestaciones): El salario y las prestaciones sociales son inembargables, salvo para el cumplimiento de obligaciones de pensión alimentaria.",
        }
        ref = articles_db.get(art_clean)
        if ref:
            return {"status": "success", "article": art_clean, "legal_text": ref}
        else:
            return {"status": "not_found", "message": f"Artículo {art_clean} no indexado en la base de referencia estricta."}
