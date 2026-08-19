/** @odoo-module */
import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useState } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Input } from "@point_of_sale/app/components/inputs/input/input";
import { getDualRate, getMainSymbol, getSecondarySymbol } from "./dual_currency_utils";

export class UsdCashMovePopup extends Component {
    static template = "point_of_sale.UsdCashMovePopup";
    static components = { Input, Dialog };
    static props = { close: Function };

    setup() {
        if (super.setup) { super.setup(); }
        this.pos = usePos();
        this.state = useState({
            amount: "",
            reason: "",
            type: "in",
        });

        const rate = getDualRate(this.pos);
        const mainName = this.pos.currency ? this.pos.currency.name : '';
        const isMainUSD = mainName.includes('USD') || mainName.includes('$');

        this.secondarySymbol = getSecondarySymbol(this.pos);
        this.mainSymbol      = getMainSymbol(this.pos);
        this.rate            = rate;
        this.isMainUSD       = isMainUSD;

        this.dualMove = useState({
            hasError: false,
            errorMessage: "",
        });
    }

    get usdEquivalent() {
        const secAmount = parseFloat(this.state.amount);
        if (isNaN(secAmount) || secAmount <= 0 || this.rate <= 0) return null;
        let mainEq = 0;
        if (this.isMainUSD) {
            mainEq = secAmount / this.rate;
        } else {
            mainEq = secAmount * this.rate;
        }
        return mainEq.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    get isAmountValid() {
        const v = parseFloat(this.state.amount);
        return !isNaN(v) && v > 0;
    }

    onClickButton(type) {
        this.state.type = type;
        this.dualMove.hasError = false;
    }

    async confirm() {
        const bsAmount = parseFloat(this.state.amount);
        if (isNaN(bsAmount) || bsAmount <= 0) {
            this.dualMove.hasError = true;
            this.dualMove.errorMessage = _t("Por favor ingresa un monto válido en Bs.F.");
            return;
        }

        let amountForBackend = bsAmount;

        try {
            await this.pos.data.call(
                "pos.session",
                "try_bs_cash_in_out",
                [
                    [this.pos.session.id],
                    this.state.type,
                    amountForBackend,
                    (this.state.reason || "") + " [Bs.F]",
                    { translatedType: this.state.type }
                ],
                {},
                true
            );
            this.dualMove.hasError = false;
        } catch (error) {
            this.dualMove.hasError = true;
            this.dualMove.errorMessage = (error.data && error.data.message) || error.message || _t("Error al registrar el movimiento.");
            console.error(error);
            return;
        }

        this.props.close();
    }
}
