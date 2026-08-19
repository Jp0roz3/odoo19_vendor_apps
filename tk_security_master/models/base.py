# -*- coding: utf-8 -*-
# Copyright (C) 2023-TODAY TechKhedut (<https://www.techkhedut.com>)
# Part of TechKhedut. See LICENSE file for full copyright and licensing details.
import logging 
from odoo import http, api, fields, models, tools, _
from odoo.http import request

_logger = logging.getLogger(__name__)

def _get_user_logged_session():
    session_id = None
    try:
        session_id = request.session.sid
    except RuntimeError:
        pass
    return session_id


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model_create_multi
    def create(self, vals_list):
        res = super(Base, self).create(vals_list)

        tk_app_status = self.env['ir.module.module'].sudo().search(
            [('name', '=', 'tk_security_master'), ('state', '=', 'installed')]).id
        if not tk_app_status:
            return res
        for rec in res:
            self._perform_activity_audit(rec, 'create')

        return res

    def write(self, vals):
        do_not_track_model = None
        user_audit_model = self.env['ir.model'].sudo().search([('model', '=', 'user.audit')]).id
        dntm_model = self.env['ir.model'].sudo().search([('model', '=', 'do.not.track.models')]).id
        if dntm_model:
            do_not_track_model = self.env['do.not.track.models'].sudo().search([('res_model', '=', self._name)]).id

        is_activate_log = True
        if (
            not user_audit_model
            or do_not_track_model
            or self._transient
            or not is_activate_log
        ):
            return super(Base, self).write(vals)

        user_audit_log_obj = self.env['user.audit'].sudo()
        ir_fields_obj = self.env['ir.model.fields'].sudo()

        session_id = None

        try:
            session_id = request.session.sid
        except RuntimeError:
            pass

        user_logged_id = self.env['user.sign.in.details'].sudo().search([('session', '=', session_id)],
                                                                        limit=1)
        if not user_logged_id:
            return super(Base, self).write(vals)

        for rec in self:
            change_logs = []
            for field in vals:
                try:
                    data = None
                    if str(rec[field]) == str(vals[field]):
                        continue
                    ir_field_id = ir_fields_obj.search([('name', '=', field), ('model', '=', rec._name)], limit=1)

                    if ir_field_id.ttype == 'many2one':
                        if rec[field].id == vals[field]:
                            continue
                        data = self._get_many2one_logs_details(rec, ir_field_id, vals, field)
                    elif ir_field_id.ttype == 'many2many':
                        if vals[field] and type(vals[field]) is list and len(vals[field][0]) == 3:
                            data = self._get_many2many_logs_details(rec, ir_field_id, vals, field)
                    elif ir_field_id.ttype == 'one2many':
                        data = self._get_one2many_logs_details(rec, ir_field_id, vals, field)
                    elif ir_field_id.ttype in ('html', 'binary', 'text'):
                        if rec and field and vals and rec[field] and type(vals[field]) is list:
                            if rec[field] in vals[field]:
                                pass
                            continue
                        data = self._get_other_fields_logs_details(rec, ir_field_id, vals, field)
                    else:
                        data = self._get_other_fields_logs_details(rec, ir_field_id, vals, field)

                    if data:
                        change_logs.append((0, 0, data))
                except IndexError as ie:
                    _logger.exception(ie)
                except TypeError as te:
                    _logger.exception(te)
                except Exception as e:
                    _logger.exception(e)
            if change_logs and user_logged_id.user_id.tu_update_logs:
                user_audit_log_obj.create({
                    'title': rec.display_name,
                    'res_model': rec._name,
                    'res_id': str(rec.id),
                    'action_type': 'update',
                    'user_session_id': user_logged_id.id,
                    'user_id': user_logged_id.user_id.id,
                    'user_audit_log_ids': change_logs,
                })
        return super(Base, self).write(vals)

    def _get_one2many_logs_details(self, rec, ir_field_id, values, field):
        commands = values.get(field)
        if not isinstance(commands, list):
            return None

        create_count = 0
        update_count = 0
        remove_count = 0

        for command in commands:
            if not isinstance(command, (list, tuple)) or not command:
                continue

            operation = command[0]
            if operation == 0:
                create_count += 1
            elif operation == 1:
                update_count += 1
            elif operation in (2, 3):
                remove_count += 1
            elif operation == 4:
                create_count += 1
            elif operation == 5:
                remove_count += len(rec[field].ids)
            elif operation == 6:
                new_ids = set(command[2] or [])
                old_ids = set(rec[field].ids)
                create_count += len(new_ids - old_ids)
                remove_count += len(old_ids - new_ids)

        if not any((create_count, update_count, remove_count)):
            return None

        operation_type = 'update'
        if create_count and not update_count and not remove_count:
            operation_type = 'new'
        elif remove_count and not create_count and not update_count:
            operation_type = 'remove'

        previous_value = ''
        new_value = ''
        if remove_count:
            previous_value = f"Removed {remove_count} related line(s)"
        if create_count or update_count:
            new_fragments = []
            if create_count:
                new_fragments.append(f"Added {create_count} line(s)")
            if update_count:
                new_fragments.append(f"Updated {update_count} line(s)")
            new_value = ', '.join(new_fragments)

        return {
            'name': ir_field_id.field_description,
            'previous_value': previous_value,
            'new_value': new_value,
            'operation_type': operation_type,
        }

    def _get_many2many_logs_details(self, rec, ir_field_id, values, field):
        ir_model = self.env[ir_field_id.relation].sudo()
        operation_type = False
        previous_value, new_value = '', ''
        if rec[field] and values[field][0][2]:
            for rec_id in values[field][0][2]:
                new_value += ir_model.browse(rec_id).display_name + ','
            for rec_id in rec[field].ids:
                previous_value += ir_model.browse(rec_id).display_name + ', '
            operation_type = 'update'
        elif not rec[field] and values[field][0][2]:
            for rec_id in values[field][0][2]:
                new_value += ir_model.browse(rec_id).display_name + ','
            operation_type = 'new'
        elif rec[field] and not values[field][0][2]:
            for rec_id in rec[field].ids:
                previous_value += ir_model.browse(rec_id).display_name + ','
            operation_type = 'remove'
        data = {
            'name': ir_field_id.field_description,
            'previous_value': previous_value,
            'new_value': new_value,
            'operation_type': operation_type,
        }
        return data

    def _get_many2one_logs_details(self, rec, ir_field_id, values, field):
        ir_model = self.env[ir_field_id.relation].sudo()
        operation_type = False
        previous_value, new_value = '', ''
        if rec[field] and values[field]:
            previous_value = ir_model.browse(rec[field].id).display_name
            if type(values[field] in (int, tuple, list, str)):
                new_value = ir_model.browse(values[field]).display_name
            else:
                new_value = ir_model.browse(values[field].id).display_name
            operation_type = 'update'
        elif not rec[field] and values[field]:
            if type(values[field] in (int, tuple, list, str)):
                new_value = ir_model.browse(values[field]).display_name
            else:
                new_value = ir_model.browse(values[field].id).display_name
            operation_type = 'new'
        elif not values[field] and rec[field]:
            previous_value = ir_model.browse(rec[field].id).display_name
            operation_type = 'remove'

        data = {
            'name': ir_field_id.field_description,
            'previous_value': previous_value,
            'new_value': new_value,
            'operation_type': operation_type,
        }

        return data

    def _get_descriptive_fields_logs_details(self, rec, ir_field_id, values, field):
        data = {
            'name': ir_field_id.field_description,
            'previous_value': rec[field],
            'new_value': values[field],
            'operation_type': 'update',
        }
        return data

    def _get_other_fields_logs_details(self, rec, ir_field_id, values, field):
        previous_value, new_value = '', ''
        operation_type = False
        if values[field] and rec[field]:
            new_value = values[field]
            previous_value = rec[field]
            operation_type = 'update'
        elif values[field] and not rec[field]:
            new_value = values[field]
            operation_type = 'new'
        elif not values[field] and rec[field]:
            previous_value = rec[field]
            operation_type = 'remove'

        data = {
            'name': ir_field_id.field_description,
            'previous_value': previous_value,
            'new_value': new_value,
            'operation_type': operation_type,
        }
        return data

    def unlink(self):
        tk_app_status = self.env['ir.module.module'].sudo().search(
            [('name', '=', 'tk_security_master'), ('state', '=', 'installed')]).id
        if not tk_app_status:
            return super(Base, self).unlink()
        for rec in self:
            if rec._name in ('user.sign.in.details', 'do.not.track.models', 'user.audit', 'user.audit.logs'):
                break
            self._perform_activity_audit(rec, 'delete')
        res = super(Base, self).unlink()
        return res

    def _perform_activity_audit(self, res, action):
        session_id = _get_user_logged_session()
        if not session_id:
            return
        user_audit_log_obj = self.env['user.audit'].sudo()
        user_logged_id = self._get_user_logged_record(session_id, res)
        if not user_logged_id:
            return

        if (action == 'delete' and user_logged_id.user_id.tu_delete_logs) or (
                action == 'create' and user_logged_id.user_id.tu_create_logs):
            user_audit_log_obj.create({
                'title': res.display_name,
                'res_model': res._name,
                'res_id': str(res.id),
                'action_type': action,
                'user_session_id': user_logged_id.id,
                'user_id': user_logged_id.user_id.id,
                'user_audit_log_ids': [],
            })

    def _get_user_logged_record(self, session_id, res):
        do_not_track_model = None
        dntm_model = self.env['ir.model'].sudo().search([('model', '=', 'do.not.track.models')]).id
        if dntm_model:
            do_not_track_model = self.env['do.not.track.models'].sudo().search([('res_model', '=', res._name)]).id

        if do_not_track_model or res._transient:
            return False
        user_logged_id = self.env['user.sign.in.details'].sudo().search([('session', '=', session_id)],
                                                                        limit=1)
        if not user_logged_id:
            return False

        return user_logged_id
