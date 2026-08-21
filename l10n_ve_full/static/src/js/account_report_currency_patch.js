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

// Parchear componentes de reportes contables para capturar la instancia raíz de AccountReport
function ensureAccountReportPatched() {
    try {
        const reportMod = odoo?.loader?.modules?.get("@account_reports/components/account_report/account_report");
        if (reportMod && reportMod.AccountReport && !reportMod.AccountReport._l10n_ve_patched) {
            reportMod.AccountReport._l10n_ve_patched = true;
            patch(reportMod.AccountReport.prototype, {
                setup() {
                    super.setup(...arguments);
                    // Capturar la instancia raíz del componente que tiene report_id y reload()
                    window.__activeAccountReportRoot = this;
                    window.__activeAccountReport = this;
                },
                async setL10nVeCurrency(currency) {
                    this.options = this.options || {};
                    this.options.l10n_ve_currency = currency;
                    this.options.l10n_ve_currency_label = currency === 'bs' ? 'Bs.F' : '$';
                    this.options.l10n_ve_badge_label = currency === 'bs' ? 'En .Bs.F' : 'En .$';

                    if (this.controller && this.controller.options) {
                        this.controller.options.l10n_ve_currency = currency;
                        this.controller.options.l10n_ve_currency_label = currency === 'bs' ? 'Bs.F' : '$';
                        this.controller.options.l10n_ve_badge_label = currency === 'bs' ? 'En .Bs.F' : 'En .$';
                    }

                    try {
                        await this.reload();
                    } catch (e) {
                        console.warn("[Venezuela360] Reload fallback attempt:", e);
                        if (this.controller && typeof this.controller.reload === "function") {
                            try {
                                await this.controller.reload();
                            } catch (err) {}
                        }
                    }
                },
            });
        }
    } catch (e) {}
}

// Inyector universal de botón bimoneda en la barra de control de Odoo Enterprise
function injectCurrencyWidgetToDOM() {
    try {
        if (typeof document === "undefined" || !document.body) return;

        ensureAccountReportPatched();

        const cp = document.querySelector(".o_control_panel");
        if (!cp) return;

        const cpText = cp.textContent || "";
        const isFinancialReport = cpText.includes("PDF") 
            || cpText.includes("XLSX")
            || cpText.includes("Balance")
            || cpText.includes("Resultados")
            || cpText.includes("flujo")
            || document.querySelector(".o_account_reports_body, .o_account_report, .o_account_reports_table");

        if (!isFinancialReport) return;

        // Encontrar el contenedor exacto de las píldoras de filtro en el header
        let filterTarget = null;
        const buttonsAndPills = cp.querySelectorAll("button, .btn, .badge, .dropdown, div");
        for (const el of buttonsAndPills) {
            const txt = el.textContent || "";
            if (txt.includes("diarios") || txt.includes("Comparación") || txt.includes("Asientos") || txt.includes("En .")) {
                filterTarget = el.parentElement;
                break;
            }
        }

        if (!filterTarget) {
            filterTarget = cp.querySelector(".o_control_panel_navigation")
                        || cp.querySelector(".o_account_reports_filters")
                        || cp.querySelector(".o_control_panel_actions")
                        || cp.querySelector(".d-flex.flex-wrap")
                        || cp;
        }

        if (!filterTarget) return;

        // Determinar moneda activa
        const ctrl = window.__activeAccountReportRoot || window.__activeAccountReport;
        const options = (ctrl && ctrl.options) || {};
        const curr = options.l10n_ve_currency || "bs";

        // Si ya existe el widget, sincronizar etiquetas
        let widget = cp.querySelector(".l10n_ve_currency_widget");
        if (widget) {
            const label = widget.querySelector(".l10n_ve_curr_label");
            if (label) label.textContent = curr === "usd" ? "$" : "Bs.F";
            const badge = widget.querySelector(".l10n_ve_badge");
            if (badge) badge.textContent = curr === "usd" ? "En .$" : "En .Bs.F";
            return;
        }

        // Crear el widget idéntico a la Imagen 4 de referencia
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

                // Actualizar inmediatamente etiquetas del widget
                const label = widget.querySelector(".l10n_ve_curr_label");
                if (label) label.textContent = chosen === "usd" ? "$" : "Bs.F";
                const badge = widget.querySelector(".l10n_ve_badge");
                if (badge) badge.textContent = chosen === "usd" ? "En .$" : "En .Bs.F";

                widget.querySelectorAll("[data-curr]").forEach(el => {
                    const isThis = el.getAttribute("data-curr") === chosen;
                    const icon = el.querySelector("i");
                    if (icon) icon.className = isThis ? "fa fa-check text-success me-1" : "fa fa-fw me-1";
                });

                // Obtener la instancia raíz del reporte
                let activeReport = window.__activeAccountReportRoot || window.__activeAccountReport;

                if (!activeReport) {
                    const reportNodes = document.querySelectorAll(".o_account_reports_body, .o_account_report, .o_content, .o_action_manager");
                    for (const node of reportNodes) {
                        if (node.__owl__ && node.__owl__.component) {
                            activeReport = node.__owl__.component;
                            break;
                        }
                    }
                }

                if (activeReport) {
                    if (typeof activeReport.setL10nVeCurrency === "function") {
                        await activeReport.setL10nVeCurrency(chosen);
                    } else {
                        activeReport.options = activeReport.options || {};
                        activeReport.options.l10n_ve_currency = chosen;
                        activeReport.options.l10n_ve_currency_label = chosen === 'bs' ? 'Bs.F' : '$';
                        activeReport.options.l10n_ve_badge_label = chosen === 'bs' ? 'En .Bs.F' : 'En .$';

                        if (typeof activeReport.reload === "function") {
                            await activeReport.reload();
                        } else if (activeReport.controller && typeof activeReport.controller.reload === "function") {
                            await activeReport.controller.reload();
                        }
                    }
                }
            });
        });

        filterTarget.appendChild(widget);
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

// Iniciar monitoreo activo para parchear y montar en SPA
setInterval(injectCurrencyWidgetToDOM, 250);
