# -*- coding: utf-8 -*-
# Copyright (C) 2023-TODAY TechKhedut (<https://www.techkhedut.com>)
# Part of TechKhedut. See LICENSE file for full copyright and licensing details.
from odoo import models, fields


class UnauthorizedAccessLog(models.Model):
    _name = 'unauthorized.access.log'
    _description = 'Unauthorized Access Log'
    _rec_name = 'ip_address'
    user_id = fields.Many2one('res.users', string="User", readonly=True, help="The user who attempted to access the system without authorization.")
    ip_address = fields.Char(string="IP Address", readonly=True, help="The IP address from which the unauthorized access attempt was made.")
    attempt_date = fields.Datetime(string="Attempt Date and Time", default=fields.Datetime.now, readonly=True ,help="The date and time of the unauthorized access attempt.")
    
