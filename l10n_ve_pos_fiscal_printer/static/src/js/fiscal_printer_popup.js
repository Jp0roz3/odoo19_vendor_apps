/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

export class FiscalPrinterPopup extends Component {
    static template = "l10n_ve_pos_fiscal_printer.FiscalPrinterPopup";
    static components = { Dialog };
    static props = {
        close: { type: Function },
    };

    setup() {
        this.fiscalPrinter = useService("fiscal_printer");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            loading: false,
            message: '',
            error: '',
        });
    }

    async testConnection() {
        this.state.loading = true;
        this.state.message = '';
        this.state.error = '';

        const res = await this.fiscalPrinter.connect();
        this.state.loading = false;
        if (res.success) {
            this.state.message = res.message || _t("Conexión exitosa con la impresora fiscal.");
            this.notification.add(this.state.message, { type: "success" });
        } else {
            this.state.error = res.error || _t("Fallo al conectar con la impresora fiscal.");
            this.notification.add(this.state.error, { type: "danger" });
        }
    }

    async printReportX() {
        this.state.loading = true;
        const res = await this.fiscalPrinter.printReportX();
        this.state.loading = false;
        if (res.success) {
            this.notification.add(_t("Reporte X impreso correctamente."), { type: "success" });
            this.props.close();
        } else {
            this.notification.add(res.error || _t("Error al emitir Reporte X."), { type: "danger" });
        }
    }

    async printReportZ() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Confirmar Cierre Z"),
            body: _t("¿Está seguro de que desea emitir el Reporte Z de Cierre Diario? Esta operación es definitiva en la memoria fiscal."),
            confirm: async () => {
                this.state.loading = true;
                const res = await this.fiscalPrinter.printReportZ();
                this.state.loading = false;
                if (res.success) {
                    this.notification.add(_t("Reporte Z emitido exitosamente."), { type: "success" });
                    this.props.close();
                } else {
                    this.notification.add(res.error || _t("Error al emitir Reporte Z."), { type: "danger" });
                }
            },
            cancel: () => {},
        });
    }

    async openDrawer() {
        const res = await this.fiscalPrinter.openDrawer();
        if (res.success) {
            this.notification.add(_t("Gaveta abierta."), { type: "success" });
        }
    }

    async cancelDocument() {
        const res = await this.fiscalPrinter.cancelDocument();
        if (res.success) {
            this.notification.add(_t("Documento fiscal cancelado."), { type: "warning" });
            this.props.close();
        }
    }
}
