# -*- coding: utf-8 -*-
"""
Venezuela360: Extensión de stock.picking para Guías de Despacho
===============================================================
Añade campos de control fiscal para emisión de Guías de Despacho
conforme a la Providencia SENIAT 00071:
- Número de Control de Guía de Despacho
- Conductor (Nombre y Cédula/RIF)
- Vehículo (Placa, Modelo, Marca)
- Motivo de Traslado (Venta, Traslado, Consignación, Reparación, etc.)
- Dirección de Origen y Destino

Autor: JeanPerozo / Nubelco
"""
from odoo import models, fields, api, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ------------------------------------------------------------------
    # Datos de Guía de Despacho Fiscal (SENIAT Providencia 00071)
    # ------------------------------------------------------------------
    l10n_ve_is_delivery_guide = fields.Boolean(
        string='Es Guía de Despacho Fiscal',
        default=False,
        help='Indica si este movimiento emite una Guía de Despacho fiscal con número de control SENIAT.',
    )
    l10n_ve_delivery_guide_number = fields.Char(
        string='N° Guía de Despacho',
        copy=False,
        help='Número de la guía de despacho asignado.',
    )
    l10n_ve_control_number = fields.Char(
        string='N° de Control Guía',
        size=14,
        copy=False,
        help='Número de control fiscal asignado a la guía de despacho (ej: 00-00000001).',
    )
    l10n_ve_driver_name = fields.Char(
        string='Nombre del Conductor',
        help='Nombre y apellido de la persona encargada del transporte.',
    )
    l10n_ve_driver_vat = fields.Char(
        string='C.I. / RIF del Conductor',
        help='Cédula de identidad o RIF del transportista.',
    )
    l10n_ve_vehicle_plate = fields.Char(
        string='Placa del Vehículo',
        size=15,
        help='Placa del vehículo de carga o transporte.',
    )
    l10n_ve_vehicle_model = fields.Char(
        string='Marca / Modelo de Vehículo',
        help='Marca, modelo o tipo de vehículo de transporte.',
    )
    l10n_ve_transport_reason = fields.Selection([
        ('sale', 'Venta'),
        ('transfer', 'Traslado entre Almacenes / Sucursales'),
        ('consignment', 'Consignación'),
        ('repair', 'Reparación / Mantenimiento'),
        ('return', 'Devolución'),
        ('import_export', 'Importación / Exportación'),
        ('other', 'Otro Motivo'),
    ], string='Motivo de Traslado', default='sale', help='Motivo legal de transporte exigido por el SENIAT.')

    l10n_ve_transport_route = fields.Char(
        string='Ruta de Traslado',
        help='Ruta o itinerario de transporte.',
    )

    def action_assign_delivery_guide_control(self):
        """Asigna número de control a la guía de despacho si no lo tiene."""
        for picking in self:
            if not picking.l10n_ve_control_number:
                seq = self.env['ir.sequence'].search([
                    ('code', '=', 'l10n_ve.delivery_guide_control'),
                    ('company_id', 'in', [picking.company_id.id, False])
                ], limit=1)
                if seq:
                    picking.l10n_ve_control_number = seq.next_by_id()
                picking.l10n_ve_is_delivery_guide = True
        return True
