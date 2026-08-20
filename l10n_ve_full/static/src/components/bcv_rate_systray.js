/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class BcvRateSystray extends Component {
    static template = "l10n_ve_full.BcvRateSystray";

    setup() {
        this.orm = useService("orm");
        this.company = useService("company");
        this.state = useState({
            rate: "45.5000",
            companyName: "",
        });

        onWillStart(async () => {
            const currentCompany = this.company.currentCompany;
            if (currentCompany) {
                this.state.companyName = currentCompany.name;
            }
            try {
                const today = new Date().toISOString().split("T")[0];
                const rates = await this.orm.searchRead(
                    "l10n_ve.exchange.rate",
                    [["date", "=", today]],
                    ["rate"],
                    { limit: 1 }
                );
                if (rates && rates.length > 0) {
                    this.state.rate = rates[0].rate.toFixed(4);
                }
            } catch (e) {
                // Fallback silencioso si no hay tasa registrada para hoy
            }
        });
    }
}

export const bcvRateSystrayItem = {
    Component: BcvRateSystray,
};

registry.category("systray").add("bcv_rate_systray", bcvRateSystrayItem, { sequence: 1 });
