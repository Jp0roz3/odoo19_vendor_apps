/** @odoo-module **/

document.addEventListener("click", function (e) {
    if (e.target && e.target.classList.contains("usr_pwd")) {
        const parent = e.target.parentElement;
        if (parent) {
            const input = parent.querySelector('#new_pwd');
            if (input) {
                input.type = input.type === "text" ? "password" : "text";
            }
        }
    }
});