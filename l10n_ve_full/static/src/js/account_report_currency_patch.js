/** @odoo-module **/
/**
 * Venezuela360: Selector Bimoneda [💱 Moneda: Bs.F / $] en Reportes Financieros
 * ==============================================================================
 * Conecta el selector de moneda interactivo con el controlador AccountReport
 * de Odoo Enterprise, permitiendo alternar al instante entre Bs.F y USD.
 *
 * Autor: JeanPerozo / Nubelco
 */

import { patch } from "@web/core/utils/patch";

// Inyector universal de botón bimoneda en la barra de control de Odoo Enterprise
function injectCurrencyWidgetToDOM(reportInstance) {
    try {
        if (typeof document === "undefined" || !document.body) return;

        // Verificar si estamos en un reporte contable
        const isReport = document.querySelector(
            ".o_account_reports_page, .o_account_report, .o_account_reports_body, .o_account_reports_table, .o_account_reports_header"
        );
        if (!isReport) return;

        const cp = document.querySelector(".o_control_panel");
        if (!cp) return;

        // Buscar el contenedor de filtros / navegación del reporte
        const nav = cp.querySelector(".o_control_panel_navigation")
                 || cp.querySelector(".o_account_reports_filters")
                 || cp.querySelector(".o_control_panel_actions")
                 || cp.querySelector(".o_search_options")
                 || cp;

        if (!nav) return;

        const options = (reportInstance && reportInstance.options) || {};
        const curr = options.l10n_ve_currency || "bs";

        // Si ya existe el widget, sincronizar su texto
        let widget = cp.querySelector(".l10n_ve_currency_widget");
        if (widget) {
            const label = widget.querySelector(".l10n_ve_curr_label");
            if (label) label.textContent = curr === "usd" ? "$" : "Bs.F";
            const badge = widget.querySelector(".l10n_ve_badge");
            if (badge) badge.textContent = curr === "usd" ? "En .$" : "En .Bs.F";
            return;
        }

        // Crear el widget visual idéntico a las fotos de referencia
        widget = document.createElement("div");
        widget.className = "l10n_ve_currency_widget d-inline-flex align-items-center ms-1 me-1";
        widget.style.cssText = "display: inline-flex !important; align-items: center; z-index: 1050; margin: 2px 4px; vertical-align: middle;";

        widget.innerHTML = `
            <div class="btn-group dropdown" style="position: relative; display: inline-flex;">
                <button class="btn btn-secondary dropdown-toggle l10n_ve_btn"
                        type="button"
                        style="display: inline-flex; align-items: center; gap: 4px; font-size: 13px; font-weight: 500; padding: 4px 10px; border: 1px solid #ced4da; cursor: pointer; background-color: #ffffff; color: #212529; border-radius: 4px;">
                    <i class="fa fa-money me-1" style="color: #0d6efd;"></i>
                    <span>Moneda:</span>
                    <span class="ms-1 fw-bold l10n_ve_curr_label" style="color: #dc3545;">${curr === "usd" ? "$" : "Bs.F"}</span>
                </button>
                <ul class="dropdown-menu dropdown-menu-end shadow l10n_ve_menu" style="min-width: 140px; position: absolute; z-index: 1090; display: none; top: 100%; right: 0; background-color: #ffffff; border: 1px solid rgba(0,0,0,0.15); border-radius: 4px; box-shadow: 0 0.5rem 1rem rgba(0,0,0,0.15);">
                    <li>
                        <a class="dropdown-item d-flex align-items-center gap-2 py-2" href="#" data-curr="bs" style="cursor: pointer; color: #212529;">
                            <i class="fa ${curr !== "usd" ? "fa-check text-success" : "fa-fw"} me-1"></i>
                            <span class="fw-bold">Bs.F</span>
                        </a>
                    </li>
                    <li>
                        <a class="dropdown-item d-flex align-items-center gap-2 py-2" href="#" data-curr="usd" style="cursor: pointer; color: #212529;">
                            <i class="fa ${curr === "usd" ? "fa-check text-success" : "fa-fw"} me-1"></i>
                            <span class="fw-bold">$</span>
                        </a>
                    </li>
                </ul>
            </div>
            <span class="badge rounded-pill align-self-center ms-1 me-1 l10n_ve_badge"
                  style="background-color: #f1f3f5; color: #495057; font-weight: 600; padding: 6px 10px; font-size: 12px; border: 1px solid #ced4da; border-radius: 50rem; display: inline-block;">
                ${curr === "usd" ? "En .$" : "En .Bs.F"}
            </span>
        `;

        const toggleBtn = widget.querySelector(".l10n_ve_btn");
        const menu = widget.querySelector(".l10n_ve_menu");

        toggleBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const isOpen = menu.style.display === "block";
            document.querySelectorAll(".l10n_ve_menu").forEach(m => m.style.display = "none");
            menu.style.display = isOpen ? "none" : "block";
        });

        widget.querySelectorAll("[data-curr]").forEach((item) => {
            item.addEventListener("click", async (e) => {
                e.preventDefault();
                e.stopPropagation();
                menu.style.display = "none";
                const chosen = item.getAttribute("data-curr");

                // Buscar el componente AccountReport activo en OWL
                let activeCtrl = reportInstance;
                if (!activeCtrl || typeof activeCtrl.setL10nVeCurrency !== "function") {
                    const pageEl = document.querySelector(".o_account_reports_page, .o_account_report");
                    if (pageEl && pageEl.__owl__ && pageEl.__owl__.component) {
                        activeCtrl = pageEl.__owl__.component;
                    }
                }

                if (activeCtrl && typeof activeCtrl.setL10nVeCurrency === "function") {
                    await activeCtrl.setL10nVeCurrency(chosen);
                } else {
                    // Fallback directo a través de los botones nativos
                    const switchBtn = document.querySelector(".o_control_panel_actions button, .o_statusbar_buttons button");
                    if (switchBtn) switchBtn.click();
                }
            });
        });

        nav.appendChild(widget);
    } catch (err) {
        console.warn("[Venezuela360] Error in injectCurrencyWidgetToDOM:", err);
    }
}

// Cerrar menús abiertos al hacer clic fuera
if (typeof document !== "undefined") {
    document.addEventListener("click", () => {
        document.querySelectorAll(".l10n_ve_menu").forEach(m => m.style.display = "none");
    });
}

// Parchear la clase AccountReport en OWL
try {
    const reportMod = odoo?.loader?.modules?.get("@account_reports/components/account_report/account_report");
    if (reportMod && reportMod.AccountReport && !reportMod.AccountReport._l10n_ve_patched) {
        reportMod.AccountReport._l10n_ve_patched = true;
        patch(reportMod.AccountReport.prototype, {
            setup() {
                super.setup(...arguments);
                setTimeout(() => injectCurrencyWidgetToDOM(this), 150);
            },
            async render() {
                const res = await super.render(...arguments);
                setTimeout(() => injectCurrencyWidgetToDOM(this), 100);
                return res;
            },
            async setL10nVeCurrency(currency) {
                if (!this.options) return;
                this.options.l10n_ve_currency = currency;
                this.options.l10n_ve_currency_label = currency === 'bs' ? 'Bs.F' : '$';
                this.options.l10n_ve_badge_label = currency === 'bs' ? 'En .Bs.F' : 'En .$';

                const newOptions = {
                    ...this.options,
                    l10n_ve_currency: currency,
                    l10n_ve_currency_label: currency === 'bs' ? 'Bs.F' : '$',
                    l10n_ve_badge_label: currency === 'bs' ? 'En .Bs.F' : 'En .$',
                };

                if (typeof this.reload === "function") {
                    await this.reload({ options: newOptions });
                } else if (typeof this.updateOptions === "function") {
                    await this.updateOptions(newOptions);
                } else if (this.controller && typeof this.controller.reload === "function") {
                    await this.controller.reload({ options: newOptions });
                }
                setTimeout(() => injectCurrencyWidgetToDOM(this), 250);
            },
        });
    }
} catch (e) {}

// Timer continuo e infalible para montar en navegación SPA
setInterval(() => {
    try {
        const isReport = document.querySelector(".o_account_reports_page, .o_account_report, .o_account_reports_body, .o_account_reports_table");
        const cp = document.querySelector(".o_control_panel");
        if (isReport && cp && !cp.querySelector(".l10n_ve_currency_widget")) {
            const owlComp = isReport.__owl__?.component;
            injectCurrencyWidgetToDOM(owlComp);
        }
    } catch (e) {}
}, 300);
