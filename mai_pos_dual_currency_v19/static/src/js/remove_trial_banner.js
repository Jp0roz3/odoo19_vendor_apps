/** @odoo-module **/

/**
 * Auto-Cleaner for Odoo.sh Trial Banner and UI Blockers
 * Automatically removes trial notification overlays and restores pointer events.
 */
function autoCleanTrialBanner() {
    const clean = () => {
        try {
            const elements = document.querySelectorAll('.o_trial_banner, .o_dialog, .modal-backdrop');
            elements.forEach(e => {
                if (e && e.innerText && (e.innerText.includes('trial project') || e.innerText.includes('Odoo.sh'))) {
                    e.remove();
                }
            });
            if (document.body && document.body.style.pointerEvents === 'none') {
                document.body.style.pointerEvents = 'auto';
            }
        } catch (e) {}
    };

    clean();
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', clean);
    }
    window.addEventListener('load', clean);
    setInterval(clean, 1000);
}

autoCleanTrialBanner();
