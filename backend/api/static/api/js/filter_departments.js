(function() {
    function filterDepartments(companySelect, departmentSelect) {
        if (!companySelect || !departmentSelect) return;
        var selectedCompany = companySelect.value;
        var options = departmentSelect.querySelectorAll('option');
        var selectedValueStillValid = false;

        options.forEach(function(opt) {
            if (!opt.value) {
                // Empty placeholder option "---------"
                opt.hidden = false;
                opt.disabled = false;
                return;
            }
            var optCompany = opt.getAttribute('data-company');
            if (!selectedCompany) {
                // When no company is selected, hide/disable all department choices
                opt.hidden = true;
                opt.disabled = true;
            } else if (optCompany === selectedCompany) {
                opt.hidden = false;
                opt.disabled = false;
                if (opt.value === departmentSelect.value) {
                    selectedValueStillValid = true;
                }
            } else {
                opt.hidden = true;
                opt.disabled = true;
            }
        });

        if (departmentSelect.value && !selectedValueStillValid) {
            departmentSelect.value = '';
        }
    }

    function initRow(companySelect, departmentSelect) {
        if (!companySelect || !departmentSelect) return;
        companySelect.addEventListener('change', function() {
            filterDepartments(companySelect, departmentSelect);
        });
        filterDepartments(companySelect, departmentSelect);
    }

    function init() {
        // 1. Standalone EmployeeProfile admin form
        var mainCompany = document.getElementById('id_company');
        var mainDepartment = document.getElementById('id_department');
        if (mainCompany && mainDepartment) {
            initRow(mainCompany, mainDepartment);
        }

        // 2. Tabular inline in User admin: id_employee_profiles-0-company, etc.
        var inlines = document.querySelectorAll('[id^="id_employee_profiles-"][id$="-company"]');
        inlines.forEach(function(compInput) {
            var prefix = compInput.id.replace(/-company$/, '');
            var deptInput = document.getElementById(prefix + '-department');
            if (deptInput) {
                initRow(compInput, deptInput);
            }
        });

        // 3. Listen for dynamically added inline rows in Django admin
        document.addEventListener('formset:added', function(event) {
            var row = event.target;
            var compInput = row.querySelector('[id$="-company"]');
            var deptInput = row.querySelector('[id$="-department"]');
            if (compInput && deptInput) {
                initRow(compInput, deptInput);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
