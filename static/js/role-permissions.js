(() => {
    const root = document.querySelector('[data-role-permissions]');
    if (!root) return;
    const fullControl = document.getElementById('id_controllo_completo');
    const specialFields = {
        anagrafica_comunicazioni_famiglie: 'id_accesso_comunicazioni_famiglie',
        sistema_backup_database: 'id_accesso_backup_database',
        sistema_cronologia_operazioni: 'id_amministratore_operativo',
        sistema_feedback_beta: 'id_amministratore_operativo',
    };
    const labels = {none: 'Divieto di accesso', view: 'Solo visualizzazione', manage: 'Visualizzazione e azione'};
    function refresh() {
        root.querySelector('[data-full-control-warning]').hidden = !fullControl?.checked;
        root.querySelectorAll('[data-permission-module]').forEach(module => {
            const defaultLevel = module.querySelector('[data-module-permission]').value;
            module.querySelectorAll('[data-page-permission]').forEach(select => {
                const special = document.getElementById(specialFields[select.dataset.pagePermission]);
                const inherited = special ? (special.checked ? 'manage' : 'none') : defaultLevel;
                const level = fullControl?.checked ? 'manage' : (select.value || inherited);
                const row = select.closest('.role-permissions-page');
                row.classList.toggle('is-custom', select.value !== '');
                row.querySelector('[data-effective-permission]').textContent = `Accesso effettivo: ${labels[level]}`;
            });
        });
    }
    root.addEventListener('click', event => {
        const button = event.target.closest('[data-bulk-level]');
        if (!button) return;
        const scope = button.closest('[data-permission-module]') || root;
        scope.querySelectorAll('[data-page-permission]').forEach(select => {
            select.value = button.dataset.bulkLevel;
        });
        refresh();
    });
    document.getElementById('ruolo-form').addEventListener('change', refresh);
    refresh();
})();
