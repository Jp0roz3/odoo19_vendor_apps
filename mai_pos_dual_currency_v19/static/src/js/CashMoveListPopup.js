/** @odoo-module */

import { CashMoveListPopup } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_list_popup/cash_move_list_popup";
import { patch } from "@web/core/utils/patch";
import { formatFloat } from "@web/core/utils/numbers";
import { markup } from "@odoo/owl";
import { getDualRate, getMainSymbol, getSecondarySymbol, isMainCurrencyUSD } from "./dual_currency_utils";

patch(CashMoveListPopup.prototype, {
    getAmount(cm) {
        // cm is the cash move object returned by get_cash_in_out_list
        let amount = Math.abs(cm.amount);
        let rate = getDualRate(this.pos);
        let isMainUSD = isMainCurrencyUSD(this.pos);
        
        let usdSym = isMainUSD ? getMainSymbol(this.pos) : getSecondarySymbol(this.pos);
        let bsSym = isMainUSD ? getSecondarySymbol(this.pos) : getMainSymbol(this.pos);
        
        let usd_amount, bs_amount;
        
        if (cm.is_bs) {
            bs_amount = amount;
            usd_amount = rate > 0 ? amount / rate : 0;
        } else if (cm.is_usd) {
            usd_amount = amount;
            bs_amount = amount * rate;
        } else {
            usd_amount = isMainUSD ? amount : (rate > 0 ? amount / rate : 0);
            bs_amount = isMainUSD ? amount * rate : amount;
        }
        
        let decimals = this.pos.currency.decimal_places || 2;
        let usd_str = `${formatFloat(usd_amount, { digits: [69, 2] })} ${usdSym}`;
        let bs_str = `${formatFloat(bs_amount, { digits: [69, decimals] })} ${bsSym}`;
        
        let colored_usd_str = `<span class="text-danger fw-bold">${usd_str}</span>`;
        let colored_bs_str = `<span>${bs_str}</span>`;
        
        if (cm.is_usd) {
            return markup(`${colored_usd_str} / ${colored_bs_str}`);
        } else if (cm.is_bs) {
            return markup(`${colored_bs_str} / ${colored_usd_str}`);
        }
        
        // Fallback for non-cash or undefined 
        return markup(this.env.utils.formatCurrency(amount));
    }
});
