/** @odoo-module **/

import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { FiscalPrinterPopup } from "./fiscal_printer_popup";

patch(Navbar.prototype, {
    openFiscalPopup() {
        this.dialog.add(FiscalPrinterPopup);
    }
});
