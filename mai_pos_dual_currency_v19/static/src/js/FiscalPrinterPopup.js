/** @odoo-module **/

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export class FiscalPrinterPopup extends Component {
    static template = "point_of_sale.FiscalPrinterPopup";
    static components = { Dialog };
    static props = { close: Function };

    setup() {
        if (super.setup) { super.setup(); }
        this.fiscalPrinter = useService("fiscal_printer");
        this.orm = useService("orm");
        this.notification = useService("notification");
        if (this.env.services.pos && this.env.services.pos.config) {
            this.fiscalPrinter.initFromConfig(this.env.services.pos.config);
        }
    }

    async connectPrinter() {
        await this.fiscalPrinter.connect();
        this.render(true);
    }

    async disconnectPrinter() {
        await this.fiscalPrinter.disconnect();
        this.render(true);
    }

    async printZReport() {
        const success = await this.fiscalPrinter.printZReport();
        if (success) {
            this.notification.add(_t("Comando Reporte Z enviado exitosamente al driver " + this.fiscalPrinter.state.driver), { type: "success" });
            
            try {
                let zNumber = parseInt(localStorage.getItem('mock_z_number') || '1000');
                let lastInvoice = parseInt(localStorage.getItem('mock_last_invoice') || '0');
                
                zNumber += 1;
                let firstInvoice = lastInvoice + 1;
                let newLastInvoice = lastInvoice + Math.floor(Math.random() * 50) + 5;
                
                localStorage.setItem('mock_z_number', zNumber);
                localStorage.setItem('mock_last_invoice', newLastInvoice);

                const rate = parseFloat(this.env.services.pos.config.show_currency_rate) || 1;
                const zData = {
                    pos_config_id: this.env.services.pos.config.id,
                    z_number: zNumber,
                    first_invoice_number: firstInvoice,
                    last_invoice_number: newLastInvoice,
                    exempt_sales_usd: 0.0,
                    taxable_sales_usd: 100.0,
                    tax_amount_usd: 16.0,
                    total_sales_usd: 116.0,
                    igtf_amount_usd: 0.0,
                    exempt_sales_bs: 0.0 * rate,
                    taxable_sales_bs: 100.0 * rate,
                    tax_amount_bs: 16.0 * rate,
                    total_sales_bs: 116.0 * rate,
                    igtf_amount_bs: 0.0,
                    time: new Date().toLocaleTimeString('en-US', { hour12: false })
                };
                await this.orm.call("pos.fiscal.z.report", "save_z_report", [zData]);
                this.notification.add(_t("Reporte Z guardado en la base de datos exitosamente."), { type: "info" });
            } catch (error) {
                console.error("Error guardando Reporte Z en Odoo:", error);
            }
        }
    }

    async printXReport() {
        this.notification.add(_t("Enviando comando Reporte X a la impresora..."), { type: "info" });
        const res = await this.fiscalPrinter.printXReport();
        if (res && res.success !== false) {
            this.notification.add(_t("Reporte X impreso exitosamente."), { type: "success" });
        } else {
            const err = (res && res.error) ? res.error : "Verifique la conexión o estado de la impresora";
            this.notification.add(_t("Error al imprimir Reporte X: " + err), { type: "danger" });
        }
    }

    async cancelOpenDocument() {
        this.notification.add(_t("Enviando comando de anulación/desbloqueo '7'..."), { type: "info" });
        const res = await this.fiscalPrinter.cancelOpenDocument();
        if (res && res.success !== false) {
            this.notification.add(_t("Comando de anulación enviado. Impresora desbloqueada."), { type: "success" });
        } else {
            this.notification.add(_t("Error al anular: " + ((res && res.error) || "Consulte consola")), { type: "warning" });
        }
    }
}
