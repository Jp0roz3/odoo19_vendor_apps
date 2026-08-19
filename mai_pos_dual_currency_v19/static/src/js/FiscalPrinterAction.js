/** @odoo-module **/

import { registry } from "@web/core/registry";

async function posFiscalPrinterAction(env, action) {
    const params = action.params || {};
    const orm = env.services.orm;
    const notification = env.services.notification;
    const fiscalPrinter = env.services.fiscal_printer;

    try {
        // Fetch driver config from the pos.config if not already set or connected
        if (params.pos_config_id && !fiscalPrinter.state.isConnected) {
            const configs = await orm.read('pos.config', [params.pos_config_id], ['fiscal_printer_driver']);
            if (configs.length > 0) {
                fiscalPrinter.initFromConfig(configs[0]);
            }
        }

        // Connect if not connected
        if (!fiscalPrinter.state.isConnected) {
            notification.add('Conectando con la impresora fiscal...', { type: 'info' });
            const connected = await fiscalPrinter.connect();
            if (!connected) {
                notification.add('No se pudo conectar con la impresora fiscal.', { type: 'danger' });
                return { type: 'ir.actions.act_window_close' };
            }
        }

        // Execute requested action
        let success = false;
        if (params.action === 'print_z_report') {
            if (params.z_start === 0 && params.z_end === 0) {
                // If both are 0, we can assume it's a standard daily Z report or it's invalid.
                // We'll call the standard Z report just in case, or by number.
                success = await fiscalPrinter.printZReport();
            } else {
                success = await fiscalPrinter.printZReportByNumber(params.z_start, params.z_end);
            }
        } else if (params.action === 'print_invoices') {
            success = await fiscalPrinter.printAuditInvoices(params.audit_start, params.audit_end);
        } else if (params.action === 'print_credit_notes') {
            success = await fiscalPrinter.printAuditCreditNotes(params.audit_start, params.audit_end);
        }

        if (success) {
            notification.add('Orden enviada exitosamente a la impresora.', { type: 'success' });
        } else {
            notification.add('Error al enviar la orden a la impresora.', { type: 'danger' });
        }

    } catch (error) {
        console.error("Error in posFiscalPrinterAction:", error);
        notification.add('Ocurrió un error inesperado de comunicación.', { type: 'danger' });
    }

    // Close the wizard window automatically
    return { type: 'ir.actions.act_window_close' };
}

registry.category("actions").add("pos_fiscal_printer_action", posFiscalPrinterAction, { force: true });
