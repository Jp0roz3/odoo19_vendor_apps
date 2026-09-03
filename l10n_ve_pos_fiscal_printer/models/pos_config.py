# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class PosConfig(models.Model):
    _inherit = 'pos.config'

    fiscal_printer_active = fields.Boolean(
        string="Activar Impresora Fiscal",
        default=False,
        help="Habilita la emisión y control fiscal SENIAT para este Punto de Venta."
    )
    fiscal_printer_model = fields.Selection([
        ('srp812', 'Bixolon SRP-812 (The Factory HKA)'),
        ('dt230', 'Bixolon DT-230 (The Factory HKA)'),
        ('hka80', 'The Factory HKA-80'),
        ('pp9', 'Dascom PP9 / PP9-Plus (The Factory HKA)'),
        ('pd3100dl', 'Dascom PD3100DL'),
        ('td1140', 'Dascom TD-1140'),
        ('generic_tfhka', 'Impresora Fiscal Genérica (Protocolo TFHKA)'),
        ('mock', 'Simulador Virtual (Pruebas sin Hardware)'),
    ], string="Modelo de Impresora", default='srp812', required=True)

    fiscal_printer_conn_type = fields.Selection([
        ('local_agent', 'Agente Fiscal Local en PC Caja (Recomendado - 100% Estable)'),
        ('web_serial', 'Web Serial API Directo (Navegador Chrome/Edge)'),
        ('tcp', 'Conexión Directa Red TCP/IP (Ethernet / WiFi)'),
        ('mock', 'Simulador Virtual en Memoria'),
    ], string="Método de Comunicación", default='local_agent', required=True,
       help="Selecciona cómo el Punto de Venta enviará los comandos a la impresora fiscal.")

    fiscal_printer_agent_url = fields.Char(
        string="URL Agente Local",
        default="http://localhost:9069",
        help="Dirección donde corre el micro-agente fiscal en la computadora de la caja (ej: http://localhost:9069 o http://127.0.0.1:9069)."
    )

    fiscal_printer_port = fields.Char(
        string="Puerto Serial (COM / USB)",
        default="COM1",
        help="Puerto serial asignado a la impresora en el Administrador de Dispositivos de Windows (ej: COM1, COM2, COM3, COM4)."
    )

    fiscal_printer_baudrate = fields.Selection([
        ('9600', '9600 bps (Estándar SRP-812)'),
        ('19200', '19200 bps'),
        ('38400', '38400 bps'),
        ('115200', '115200 bps'),
    ], string="Velocidad (Baudios)", default='9600', required=True)

    fiscal_printer_tcp_ip = fields.Char(
        string="Dirección IP de la Impresora",
        default="192.168.1.200",
        help="Dirección IP local de la impresora fiscal o del conversor Serial-Ethernet."
    )

    fiscal_printer_tcp_port = fields.Integer(
        string="Puerto TCP",
        default=9100,
        help="Puerto de escucha de red (usualmente 9100 o 10001)."
    )

    fiscal_printer_serial = fields.Char(
        string="Serial Fiscal Registrado",
        readonly=True,
        copy=False,
        help="Serial fiscal leído automáticamente desde la memoria de la impresora (ej: Z1A8120000)."
    )

    fiscal_auto_print = fields.Boolean(
        string="Impresión Automática en Pago",
        default=True,
        help="Envía la factura a la impresora fiscal inmediatamente al validar el pago en el POS."
    )

    fiscal_cut_paper = fields.Boolean(
        string="Corte Automático de Papel",
        default=True,
        help="Envía comando de corte total/parcial al finalizar la impresión fiscal."
    )

    def _load_pos_data_read(self, pos_data):
        read_records = super()._load_pos_data_read(pos_data)
        if not read_records:
            return read_records

        rec_list = read_records if isinstance(read_records, list) else [read_records]
        config_rec = self.env['pos.config'].browse(rec_list[0]['id']) if 'id' in rec_list[0] else self

        for record in rec_list:
            record['fiscal_printer_active']    = bool(getattr(config_rec, 'fiscal_printer_active', False))
            record['fiscal_printer_model']     = getattr(config_rec, 'fiscal_printer_model', 'srp812') or 'srp812'
            record['fiscal_printer_conn_type'] = getattr(config_rec, 'fiscal_printer_conn_type', 'local_agent') or 'local_agent'
            record['fiscal_printer_agent_url'] = getattr(config_rec, 'fiscal_printer_agent_url', 'http://localhost:9069') or 'http://localhost:9069'
            record['fiscal_printer_port']      = getattr(config_rec, 'fiscal_printer_port', 'COM1') or 'COM1'
            record['fiscal_printer_baudrate']  = getattr(config_rec, 'fiscal_printer_baudrate', '9600') or '9600'
            record['fiscal_printer_tcp_ip']    = getattr(config_rec, 'fiscal_printer_tcp_ip', '192.168.1.200') or '192.168.1.200'
            record['fiscal_printer_tcp_port']  = getattr(config_rec, 'fiscal_printer_tcp_port', 9100) or 9100
            record['fiscal_printer_serial']    = getattr(config_rec, 'fiscal_printer_serial', '') or ''
            record['fiscal_auto_print']        = bool(getattr(config_rec, 'fiscal_auto_print', True))
            record['fiscal_cut_paper']         = bool(getattr(config_rec, 'fiscal_cut_paper', True))

        return read_records
