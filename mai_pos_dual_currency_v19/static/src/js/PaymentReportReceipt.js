/** @odoo-module */

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class PaymentReportReceipt extends Component {
    static template = "mai_pos_dual_currency_v19.PaymentReportReceipt";

    setup() {
        this.printer = useService("printer");
        this.pos = useService("pos");
    }

    get receipt() {
        return this.props.data;
    }
}
