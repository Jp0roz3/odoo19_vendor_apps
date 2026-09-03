# -*- coding: utf-8 -*-

from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fiscal_printer_active = fields.Boolean(
        related='pos_config_id.fiscal_printer_active',
        readonly=False
    )
    fiscal_printer_model = fields.Selection(
        related='pos_config_id.fiscal_printer_model',
        readonly=False
    )
    fiscal_printer_conn_type = fields.Selection(
        related='pos_config_id.fiscal_printer_conn_type',
        readonly=False
    )
    fiscal_printer_agent_url = fields.Char(
        related='pos_config_id.fiscal_printer_agent_url',
        readonly=False
    )
    fiscal_printer_port = fields.Char(
        related='pos_config_id.fiscal_printer_port',
        readonly=False
    )
    fiscal_printer_baudrate = fields.Selection(
        related='pos_config_id.fiscal_printer_baudrate',
        readonly=False
    )
    fiscal_printer_tcp_ip = fields.Char(
        related='pos_config_id.fiscal_printer_tcp_ip',
        readonly=False
    )
    fiscal_printer_tcp_port = fields.Integer(
        related='pos_config_id.fiscal_printer_tcp_port',
        readonly=False
    )
    fiscal_auto_print = fields.Boolean(
        related='pos_config_id.fiscal_auto_print',
        readonly=False
    )
    fiscal_cut_paper = fields.Boolean(
        related='pos_config_id.fiscal_cut_paper',
        readonly=False
    )
