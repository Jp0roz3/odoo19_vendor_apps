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

// Inyector visual robusto en el DOM del reporte
function injectCurrencyWidget(reportInstance) {
    if (!reportInstance) return;

    // Buscar el elemento contenedor del reporte o panel de control
    const rootEl = reportInstance.el || document.querySelector(".o_account_reports_page") || document.querySelector(".o_account_report");
    if (!rootEl) return;

    // Buscar la barra de filtros o navegación
    const filterContainer = rootEl.querySelector(".o_account_reports_filters") 
        || rootEl.querySelector(".o_control_panel_navigation")
        || rootEl.querySelector(".o_control_panel_actions")
        || rootEl.querySelector(".o_search_options")
        || document.querySelector(".o_account_reports_filters")
        || document.querySelector(".o_control_panel_navigation");

    if (!filterContainer) return;

    // Si ya existe el widget, actualizar su estado y no duplicar
    const existing = filterContainer.querySelector(".l10n_ve_currency_widget");
    const options = reportInstance.options || {};
    const currentCurr = options.l10n_ve_currency || "bs";

    if (existing) {
        const labelEl = existing.querySelector(".l10n_ve_curr_label");
        if (labelEl) labelEl.textContent = currentCurr === "usd" ? "$" : "Bs.F";
        const badgeEl = existing.querySelector(".l10n_ve_badge");
        if (badgeEl) badgeEl.textContent = currentCurr === "usd" ? "En .$" : "En .Bs.F";
        return;
    }

    // Crear el widget visual idéntico a las fotos de referencia
    const widget = document.createElement("div");
    widget.className = "l10n_ve_currency_widget d-inline-flex align-items-center ms-1 me-1";
    widget.style.cssText = "display: inline-flex !important; align-items: center; z-index: 100; margin: 2px 4px;";

    widget.innerHTML = `
        <div class="btn-group dropdown" style="position: relative;">
            <button class="btn btn-secondary dropdown-toggle l10n_ve_btn"
                    type="button"
                    style="display: inline-flex; align-items: center; gap: 4px; font-size: 13px; font-weight: 500; padding: 4px 10px; border: 1px solid #ced4da; cursor: pointer;">
                <i class="fa fa-money me-1" style="color: #0d6efd;"></i>
                <span>Moneda:</span>
                <span class="ms-1 fw-bold l10n_ve_curr_label" style="color: #dc3545;">${currentCurr === "usd" ? "$" : "Bs.F"}</span>
            </button>
            <ul class="dropdown-menu dropdown-menu-end shadow l10n_ve_menu" style="min-width: 140px; position: absolute; z-index: 1050; display: none; top: 100%; right: 0;">
                <li>
                    <a class="dropdown-item d-flex align-items-center gap-2 py-2" href="#" data-curr="bs">
                        <i class="fa ${currentCurr !== "usd" ? "fa-check text-success" : "fa-fw"} me-1"></i>
                        <span class="fw-bold">Bs.F</span>
                    </a>
                </li>
                <li>
                    <a class="dropdown-item d-flex align-items-center gap-2 py-2" href="#" data-curr="usd">
                        <i class="fa ${currentCurr === "usd" ? "fa-check text-success" : "fa-fw"} me-1"></i>
                        <span class="fw-bold">$</span>
                    </a>
                </li>
            </ul>
        </div>
        <span class="badge rounded-pill align-self-center ms-1 me-1 l10n_ve_badge"
              style="background-color: #f1f3f5; color: #495057; font-weight: 600; padding: 6px 10px; font-size: 12px; border: 1px solid #ced4da; display: inline-block;">
            ${currentCurr === "usd" ? "En .$" : "En .Bs.F"}
        </span>
    `;

    const toggleBtn = widget.querySelector(".l10n_ve_btn");
    const menu = widget.querySelector(".l10n_ve_menu");

    toggleBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = menu.style.display === "block";
        // Cerrar otros menús abiertos
        document.querySelectorAll(".l10n_ve_menu").forEach(m => m.style.display = "none");
        menu.style.display = isOpen ? "none" : "block";
    });

    widget.querySelectorAll("[data-curr]").forEach((item) => {
        item.addEventListener("click", async (e) => {
            e.preventDefault();
            e.stopPropagation();
            menu.style.display = "none";
            const chosen = item.getAttribute("data-curr");
            if (typeof reportInstance.setL10nVeCurrency === "function") {
                await reportInstance.setL10nVeCurrency(chosen);
            }
        });
    });

    filterContainer.appendChild(widget);
}

// Cerrar menú al hacer clic fuera
document.addEventListener("click", () => {
    document.querySelectorAll(".l10n_ve_menu").forEach(m => m.style.display = "none");
});

// Parchear la clase AccountReport en OWL
try {
    const reportMod = odoo.loader.modules.get("@account_reports/components/account_report/account_report");
    if (reportMod && reportMod.AccountReport && !reportMod.AccountReport._l10n_ve_patched) {
        reportMod.AccountReport._l10n_ve_patched = true;
        patch(reportMod.AccountReport.prototype, {
            setup() {
                super.setup(...arguments);
                // Inyectar en ciclo de vida
                setTimeout(() => injectCurrencyWidget(this), 200);
            },
            async render() {
                const res = await super.render(...arguments);
                setTimeout(() => injectCurrencyWidget(this), 100);
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
                setTimeout(() => injectCurrencyWidget(this), 300);
            },
        });
    }
} catch (e) {}

// Observador periódico para garantizar que aparezca en cualquier cambio de vista o pestaña
setInterval(() => {
    const reportEl = document.querySelector(".o_account_reports_page") || document.querySelector(".o_account_report");
    if (reportEl && !reportEl.querySelector(".l10n_ve_currency_widget")) {
        if (window.__owl__) {
            const comp = reportEl.__owl__?.component;
            if (comp) {
                injectCurrencyWidget(comp);
            }
        }
    }
}, 600);
