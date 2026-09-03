/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        // Interceptar validateOrder de forma segura para Odoo 19
        const originalValidate = this.validateOrder ? this.validateOrder.bind(this) : null;

        this.validateOrder = async (isForceValidate) => {
            const order = this.currentOrder;
            const config = this.pos.config;

            if (config && config.fiscal_printer_active && config.fiscal_auto_print && !order.is_fiscal_printed) {
                const fiscalPrinter = this.env.services.fiscal_printer;

                if (fiscalPrinter) {
                    this.env.services.ui.block({ message: _t("Imprimiendo Factura Fiscal SENIAT...") });
                    try {
                        const result = await fiscalPrinter.printInvoice(order);
                        this.env.services.ui.unblock();

                        if (result && result.success) {
                            order.fiscal_invoice_number = result.fiscal_invoice_number || '';
                            order.fiscal_printer_serial = result.fiscal_serial || '';
                            order.is_fiscal_printed = true;

                            this.env.services.notification.add(
                                _t("Factura Fiscal emitida con éxito N° ") + (result.fiscal_invoice_number || ''),
                                { type: "success" }
                            );
                        } else {
                            const errorMsg = (result && result.error) ? result.error : _t("Error desconocido en la impresora fiscal.");
                            this.dialog.add(AlertDialog, {
                                title: _t("Fallo de Impresión Fiscal"),
                                body: _t("No se pudo completar la impresión fiscal:\n\n") + errorMsg + _t("\n\nPor favor revise el papel, la tapa o el puerto de conexión y reintente."),
                            });
                            return; // Detiene la validación para no desfasar Odoo del rollo fiscal
                        }
                    } catch (err) {
                        this.env.services.ui.unblock();
                        this.dialog.add(AlertDialog, {
                            title: _t("Error Crítico de Impresora Fiscal"),
                            body: err.message,
                        });
                        return;
                    }
                }
            }

            if (originalValidate) {
                return await originalValidate(isForceValidate);
            } else if (super.validateOrder) {
                return await super.validateOrder(...arguments);
            }
        };
    }
});
