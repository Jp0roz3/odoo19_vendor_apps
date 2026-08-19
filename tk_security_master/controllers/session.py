# -*- coding: utf-8 -*-
# Copyright (C) 2023-TODAY TechKhedut (<https://www.techkhedut.com>)
# Part of TechKhedut. See LICENSE file for full copyright and licensing details.
try:
    import httpagentparser
except ImportError:
    httpagentparser = None

import json
import requests
from datetime import datetime
import logging

import odoo
from odoo import http, _
from odoo.http import request
from odoo.addons.web.controllers import home
import ipaddress
from odoo.addons.web.controllers import session


_logger = logging.getLogger(__name__)

SIGN_UP_REQUEST_PARAMS = {
    'db', 'login', 'debug', 'token', 'message', 'error', 'scope', 'mode',
    'redirect', 'redirect_hostname', 'email', 'name', 'partner_id',
    'password', 'confirm_password', 'city', 'country_id', 'lang', 'signup_email'
}


def _parse_ip_candidate(value):
    if not value:
        return None

    candidate = value.split(',')[0].strip()
    if not candidate:
        return None

    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def get_client_ip():
    http_request = request.httprequest

    for candidate in getattr(http_request, 'access_route', []) or []:
        parsed_ip = _parse_ip_candidate(candidate)
        if parsed_ip:
            return parsed_ip

    for header_name in ('HTTP_X_REAL_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR'):
        parsed_ip = _parse_ip_candidate(http_request.environ.get(header_name))
        if parsed_ip:
            return parsed_ip

    return _parse_ip_candidate(getattr(http_request, 'remote_addr', None))


def get_data_from_ip_api_vendor(ip_address):
    url = f'http://ip-api.com/json/{ip_address}'
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException:
        return None

    if payload.get('status') == 'success':
        return payload
    return None


class Home(home.Home):

    @http.route('/web/login', type='http', auth="none")
    def web_login(self, redirect=None, **kw):
        home.ensure_db()
        active_usr = True
        request.params['login_success'] = False

        if request.httprequest.method == 'POST':
            ip_address = get_client_ip()
            login = request.params.get('login')
            user_rec = request.env['res.users'].sudo().search([('login', '=', login)], limit=1)

            # Only check IP if restriction is enabled
            # if user_rec and user_rec.is_restriction_ip_access:
                # if self._is_ip_blocked(user_rec, ip_address):
            self._log_login_attempt(user_rec, ip_address, login, False)
                    # notification_enabled = request.env['ir.config_parameter'].sudo().get_param(
                    #     'tk_security_master.unauthorized_notification_enabled', default=False)
                    # if notification_enabled:
                    #     data_login_attempt = detect_user_login_attempt()
                    #     self._send_blocked_login_email(user_rec, data_login_attempt, ip_address)
            # values = {
            #     'error': _(
            #         "Login blocked from this IP address. Please contact your administrator."),
            #     'login': login
            # }
            # return request.render('web.login', values)

        # Proceed with standard login flow
        response = super(Home, self).web_login(redirect, **kw)

        if request.httprequest.method == 'POST':
            data = detect_user_login_attempt()
            if request.params['login_success']:
                if request.session.uid:
                    data['user_id'] = request.session.uid
            else:
                tried_user = request.env['res.users'].sudo().search([('login', '=', request.params['login'])], limit=1)
                if tried_user:
                    data['user_id'] = tried_user.id
                data['is_anonymous'] = True
                data['active'] = False
                data['status'] = 'inactive'
                request.env['user.sign.in.details'].sudo().create(data)
        return response

    def _is_ip_blocked(self, user_rec, ip_address):
        try:
            ip = ipaddress.ip_address(ip_address)

            if user_rec.restriction_ip_type == 'range':
                for rec in user_rec.blocked_ip_ids:
                    if rec.ip_range_start and rec.ip_range_end:
                        start_ip = ipaddress.IPv4Address(rec.ip_range_start)
                        end_ip = ipaddress.IPv4Address(rec.ip_range_end)
                        if start_ip <= ip <= end_ip:
                            return True

            elif user_rec.restriction_ip_type == 'single':
                for rec in user_rec.blocked_single_ip_ids:
                    if rec.ip_address and ip == ipaddress.IPv4Address(rec.ip_address):
                        return True

        except ValueError as e:
            _logger.error("Invalid IP format: %s", e)
        return False

    def _log_login_attempt(self, user_rec, ip_address, login, success):
        if not success:
            request.env['unauthorized.access.log'].sudo().create({
                'user_id': user_rec.id if user_rec else None,
                'ip_address': ip_address,
                'attempt_date': datetime.now(),
            })
        _logger.info("Login attempt (%s) for user: %s from IP: %s",
                     "success" if success else "failed", login, ip_address)

    def _send_blocked_login_email(self, user_rec, data, ip_address):
        mail_template = request.env.ref(
            'tk_security_master.blocked_ip_user_alert_template',
            raise_if_not_found=False)
        if mail_template:
            ctx = {
                'logged_datetime': data['logged_datetime'],
                'ip_address': ip_address,
                'platform': data['platform'],
                'browser': data['browser'],
                'city': data['city'],
                'region': data['region'],
                'country': data['country']
            }
            mail_template.sudo().with_context(ctx).send_mail(user_rec.id, force_send=True,
                                                             email_values={
                                                                 "author_id": request.env.company.partner_id.id})

    def _login_redirect(self, uid, redirect=None):
        if request.session.uid and request.env.user.has_group('base.group_user'):
            data = detect_user_login_attempt()
            data["user_id"] = request.session.uid
            request.env["user.sign.in.details"].sudo().create(data)
        return super()._login_redirect(uid, redirect)

    @http.route(['/web', '/odoo', '/odoo/<path:subpath>', '/scoped_app/<path:subpath>'], type='http', auth="none")
    def web_client(self, s_action=None, **kw):
        response = super(Home, self).web_client(s_action, **kw)
        user_session = request.env['user.sign.in.details'].sudo().search([('user_id', '=', request.uid),
                                                                          ('session', '=', False)], order='id desc',
                                                                         limit=1)
        if user_session:
            user_session.session = request.session.sid
        return response

class Session(session.Session):

    @http.route('/web/session/logout', type='http', auth="none")
    def logout(self, redirect='/odoo'):
        session_details = request.env['user.sign.in.details'].sudo().search([('session', '=', request.session.sid)],
                                                                            limit=1)
        if session_details:
            session_details.write({'status': 'inactive', 'active': False, 'logout_datetime': datetime.now()})
        response = super(Session, self).logout(redirect)
        return response

    @http.route('/user/read/operation', type='jsonrpc', auth="none")
    def user_read_operation_log(self, **kw):
        session_id = request.session.sid
        browser_hash = kw.get('url_hash', {})
        dntm, user_logged_id = None, None
        title = ''
        model = ''
        res_model = browser_hash.get('model', False)
        dntm_model = request.env['ir.model'].sudo().search([('model', '=', 'do.not.track.models')]).id
        if dntm_model and res_model:
            dntm = request.env['do.not.track.models'].sudo().search([('res_model', '=', res_model)]).id
        if session_id:
            user_logged_id = request.env['user.sign.in.details'].sudo().search([('session', '=', session_id)],
                                                                               limit=1)
        if user_logged_id:
            user_logged_id.write({'last_active_time': datetime.now()})
            if browser_hash.get('action') and browser_hash.get('action') != 'menu' and browser_hash.get(
                    'action') != 'studio':
                action = browser_hash.get('action')
                if isinstance(action, int):
                    if isinstance(browser_hash.get('action'), int):
                        act_rec = request.env['ir.actions.actions'].sudo().browse(int(browser_hash.get('action')))
                        window_act_rec = request.env['ir.actions.act_window'].sudo().search([('name', '=', act_rec.name)])
                        if act_rec and window_act_rec:
                            title = act_rec.name
                            model = window_act_rec[0].res_model
                        else:
                            title = 'N/A'
                            model = ''
                    else:
                        title = 'N/A'
                        model = ''
                else:
                    window_act_rec = request.env['ir.actions.act_window'].sudo().search([('name', '=', browser_hash.get('action').capitalize())])
                    if window_act_rec:
                        title = browser_hash.get('action')
                        model = window_act_rec[0].res_model
                    else:
                        title = 'N/A'
                        model = ''

            if not dntm and user_logged_id.user_id.tu_read_logs and title != 'N/A':
                request.env['user.audit'].sudo().create({
                    'title': title,
                    'res_url': kw.get('browser_url') if kw.get('browser_url') else '',
                    'res_model': model if model else '',
                    'res_id': browser_hash.get('resId') if browser_hash.get('resId') else '',
                    'view_type': browser_hash.get('view_type') if browser_hash.get('view_type') else "",
                    'action_type': 'read',
                    'user_session_id': user_logged_id.id,
                    'user_id': user_logged_id.user_id.id,
                })


def detect_user_login_attempt():
    data = {}
    agent = request.httprequest.environ.get('HTTP_USER_AGENT')
    agent_details = httpagentparser.detect(agent) if httpagentparser and agent else {}
    platform_info = agent_details.get('platform') or {}
    browser_info = agent_details.get('browser') or {}
    platform_name = platform_info.get('name') or ''
    browser_name = browser_info.get('name') or ''

    platform = get_os_details(platform_name)
    data['platform'] = platform
    if platform == "Other":
        data['other_platform'] = platform_name
    data['platform_version'] = platform_info.get('version', '')
    data['is_bot'] = bool(agent_details.get('bot'))
    browser = find_browser(browser_name)
    data['browser'] = browser
    if browser == "Other":
        data['other_browser'] = browser_name
    data['browser_version'] = browser_info.get('version', '')
    ip_address = get_client_ip()
    if ip_address:
        _logger.info('User logged ip_address: %s', ip_address)
        data['ip_address'] = ip_address
    data['logged_datetime'] = datetime.now()
    data['last_active_time'] = datetime.now()
    data['active'] = True
    data['status'] = 'active'
    user_data = None
    # --- FIX: Only call get_data_from_ip_api_vendor if ip_address exists ---
    if 'ip_address' in data and data['ip_address']:
        try:
            user_data = get_data_from_ip_api_vendor(data['ip_address'])
        except requests.exceptions.ConnectionError:
            pass
    if user_data:
        data['city'] = user_data.get('city', '')
        data['region'] = user_data.get('region', '')
        data['country'] = user_data.get('country', '')
        data['isp'] = user_data.get('isp', '')
        data['postal_code'] = user_data.get('zip', '')
        data['timezone'] = user_data.get('timezone', '')
        data['latitude'] = user_data.get('lat', '')
        data['longitude'] = user_data.get('lon', '')
    return data


def find_browser(browser_name):
    browsers = ('Chrome', 'Firefox', 'Safari', 'ChromiumEdge', 'Opera')
    if browser_name in browsers:
        return browser_name
    else:
        return "Other"


def get_os_details(platform):
    platforms = ('Windows', 'Linux', 'Mac OS', 'Android', 'iOS')
    if platform in platforms:
        return platform
    else:
        return "Other"
