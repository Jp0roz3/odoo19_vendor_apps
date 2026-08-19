# -*- coding: utf-8 -*-
# Copyright (C) 2023-TODAY TechKhedut (<https://www.techkhedut.com>)
# Part of TechKhedut. See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api
import ipaddress
from odoo.exceptions import ValidationError, AccessDenied
from odoo import _, exceptions


class BlockedIPs(models.Model):
    """Model to define a range of blocked IPv4 addresses for a specific user."""
    _name = "blocked.ips"
    _description = __doc__

    user_id = fields.Many2one("res.users", string="User", help="Select the user for whom the IP access is being configured.")
    ip_range_start = fields.Char(string="Starting IP Address", help="Specify the starting IP address of the range.")
    ip_range_end = fields.Char(string="Ending IP Address", help="Specify the ending IP address of the range.")

    @api.constrains("ip_range_start", "ip_range_end")
    def _check_ip_format(self):
        for record in self:
            if not record.ip_range_start or not record.ip_range_end:
                raise ValidationError("Both Starting and Ending IP Address fields are required.")
            if (record.ip_range_start and not record.ip_range_end) or (
                    not record.ip_range_start and record.ip_range_end
            ):
                raise ValidationError(
                    _(
                        "Both 'IP Range Start' and 'IP Range End' must be provided together."
                    )
                )

            if not record.ip_range_start and not record.ip_range_end:
                continue

            try:
                if record.ip_range_start:
                    start_ip = ipaddress.IPv4Address(record.ip_range_start)
                if record.ip_range_end:
                    end_ip = ipaddress.IPv4Address(record.ip_range_end)
            except ValueError:
                raise ValidationError(
                    _("IP addresses must be valid IPv4 or IPv6 addresses.")
                )

            if start_ip == end_ip:
                raise ValidationError(
                    _("Starting and Ending range of IP address must be different.")
                )

            if start_ip > end_ip:
                raise ValidationError(
                    _("Ending range of IP address must be greater than starting IP address.")
                )


class BlockedSingleIPs(models.Model):
    """Model to define a single blocked IPv4 address for a specific user."""
    _name = "blocked.single.ips"
    _description = __doc__

    user_id = fields.Many2one("res.users", string="User", help="Select the user for whom the IP access is being configured.")
    ip_address = fields.Char(string='Blocked IP', help='The blocked IP address'
                                                       ' for the User.')

    @api.constrains("ip_address")
    def _check_ip_format(self):
        for record in self:
            if not record.ip_address:
                raise ValidationError("IP Address fields are required.")
            try:
                if record.ip_address:
                    ipaddress.IPv4Address(record.ip_address)
            except ValueError:
                raise ValidationError(
                    _("IP addresses must be valid IPv4 addresses.")
                )

