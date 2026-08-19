/** @odoo-module */
/**
 * CashOpeningPopup Patch — Apertura de caja dual Bs.F + USD (Odoo 19)
 * ════════════════════════════════════════════════════════════════════════
 * Adds "Efectivo Inicial Bs.F" field to the opening popup.
 * When cashier confirms, both values (USD + Bs.F) are saved to pos.session.
 *
 * Odoo 19 Architecture:
 *  - CashOpeningPopup is a standalone Component (NOT inheriting from a popup base)
 *  - Its setup() already calls usePos() → this.pos is set there
 *  - confirm() calls this.pos.data.call('pos.session', 'set_opening_control', ...)
 *  - We patch setup() and confirm() using patch() — calling super.setup() correctly
 *  - session: this.pos.session  (NOT this.pos.pos_session)
 */
import { OpeningControlPopup } from "@point_of_sale/app/components/popups/opening_control_popup/opening_control_popup";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { getDualRate, fmt2, getSecondarySymbol, getMainSymbol, getRateLabel, mainToSecondary, secondaryToMain } from "./dual_currency_utils";

patch(OpeningControlPopup.prototype, {

    setup() {
        // super.setup() calls usePos() which sets this.pos
        // and creates this.state = useState({ notes, openingCash })
        if (super.setup) { super.setup(...arguments); }

        // After super.setup(), this.pos is available
        this.dualState = useState({
            openingCashBs:   0.0,
            openingPmBs:     0.0,
            rateLabel:       '',
            secondarySymbol: 'Bs.F',
            mainSymbol:      '$',
            isDualEnabled:   false,
        });

        this._initDualState();
    },

    _initDualState() {
        try {
            const cfg = this.pos.config;
            if (!cfg || !cfg.show_dual_currency) return;

            this.dualState.isDualEnabled   = true;
            this.dualState.secondarySymbol = getSecondarySymbol(this.pos);
            this.dualState.mainSymbol      = getMainSymbol(this.pos);
            this.dualState.rateLabel       = getRateLabel(this.pos);
            this.dualState.openingCashBs   = parseFloat(this.pos.session?.opening_cash_bs || 0);
            this.dualState.openingPmBs     = parseFloat(this.pos.session?.opening_pm_bs || 0);
        } catch (e) {
            console.warn('[DualCurrency] _initDualState error:', e);
        }
    },

    /** Called when the Bs.F input changes */
    onBsInput(ev) {
        this.dualState.openingCashBs = parseFloat(ev.target.value) || 0;
    },

    /** Called when the Pago Movil input changes */
    onPmInput(ev) {
        this.dualState.openingPmBs = parseFloat(ev.target.value) || 0;
    },

    /**
     * Live: how many Bs.F is the USD amount the user is typing?
     */
    get usdToBsEquiv() {
        try {
            if (!this.dualState.isDualEnabled) return '';
            let raw = (this.state.openingCash || '0').toString();
            raw = raw.replace(/[^0-9.,-]/g, '').replace(',', '.');
            const usd = parseFloat(raw) || 0;
            if (usd === 0) return '';
            return `≈ ${fmt2(secondaryToMain(usd, this.pos))} ${this.dualState.mainSymbol}`;
        } catch (e) { return ''; }
    },

    /**
     * Live: how many USD is the Bs.F amount the user is typing?
     */
    get bsToUsdEquiv() {
        try {
            if (!this.dualState.isDualEnabled) return '';
            const bs = parseFloat(this.dualState.openingCashBs) || 0;
            if (bs === 0) return '';
            return `≈ ${fmt2(mainToSecondary(bs, this.pos))} ${this.dualState.secondarySymbol}`;
        } catch (e) { return ''; }
    },

    /**
     * Summary: "10.00 USD | Bs.F 10000.00 = USD 23.81"
     */
    get dualOpeningSummary() {
        try {
            if (!this.dualState.isDualEnabled) return '';
            let raw = (this.state.openingCash || '0').toString();
            raw = raw.replace(/[^0-9.,-]/g, '').replace(',', '.');
            const usdAmount = parseFloat(raw) || 0;
            const bsCash  = parseFloat(this.dualState.openingCashBs) || 0;
            const bsPm    = parseFloat(this.dualState.openingPmBs) || 0;
            const bsAmount = bsCash + bsPm;
            const bsInUsd   = mainToSecondary(bsAmount, this.pos);
            const totalUsd  = usdAmount + bsInUsd;
            const mainSym   = this.dualState.mainSymbol;
            const secSym    = this.dualState.secondarySymbol;
            return `${fmt2(usdAmount)} ${secSym} | ${mainSym} ${fmt2(bsAmount)} = ${secSym} ${fmt2(totalUsd)}`;
        } catch (e) { return ''; }
    },

    /**
     * Override confirm: save Bs.F opening and call native set_opening_control.
     * V19: native confirm() calls this.pos.data.call('pos.session', 'set_opening_control', ...)
     */
    async confirm() {
        const cfg = this.pos.config;
        if (cfg && cfg.show_dual_currency) {
            try {
                const bsAmount = parseFloat(this.dualState.openingCashBs) || 0;
                const pmBsAmount = parseFloat(this.dualState.openingPmBs) || 0;
                let raw = (this.state.openingCash || '0').toString();
                raw = raw.replace(/[^0-9.,-]/g, '').replace(',', '.');
                const usdAmount = parseFloat(raw) || 0;

                // Save Bs opening in session state immediately (optimistic)
                this.pos.session.opening_cash_bs = bsAmount;
                this.pos.session.opening_cash_usd = usdAmount;
                this.pos.session.opening_pm_bs = pmBsAmount;

                // Await to ensure it saves before the POS UI reloads or closes the popup
                await this.pos.data.call(
                    'pos.session',
                    'set_dual_opening_cash',
                    [[this.pos.session.id], bsAmount, usdAmount, pmBsAmount]
                );

            } catch (e) {
                console.warn('[DualCurrency] confirm error:', e);
            }
        }
        // Call native confirm() which handles set_opening_control + close
        return super.confirm(...arguments);
    },
});
