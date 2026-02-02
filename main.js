/* =====================================================
   GLOBAL CONFIG
===================================================== */
window.API = "http://localhost:8000";
window.siteSettings = null;


/* =====================================================
   AUTH CHECK
   - Protects all pages except login.html
===================================================== */
function checkAuth() {
    fetch(`${API}/check_login`, {
        credentials: "include"
    })
        .then(r => r.json())
        .then(res => {
            if (!res.logged_in) {
                window.location.href = "login.html";
            }
        })
        .catch(() => {
            window.location.href = "login.html";
        });
}


/* =====================================================
   LOAD SITE SETTINGS (🔥 VERY IMPORTANT)
   - Loads ALL settings
   - Stores globally
   - Loads brand logo
===================================================== */
function loadSiteSettings() {
    fetch(`${API}/get_site_settings`, {
        credentials: "include"
    })
        .then(r => {
            if (!r.ok) throw new Error("Unauthorized");
            return r.json();
        })
        .then(settings => {
            // 🔥 STORE SETTINGS GLOBALLY
            window.siteSettings = settings;

            // 🔹 Load brand logo if exists
            if (settings.brand_logo) {
                const logoUrl = settings.brand_logo.startsWith("http")
                    ? settings.brand_logo
                    : `${API}${settings.brand_logo}`;

                document.querySelectorAll("#brandLogo, #logoPreview").forEach(img => {
                    if (img) img.src = logoUrl + "?t=" + Date.now();
                });
            }
        })
        .catch(err => {
            console.warn("❌ Failed to load site settings:", err);
        });
}


/* =====================================================
   APPLY FIELD SETTINGS (for addsalary.html)
===================================================== */
function applySalaryFieldSettings() {
    const wait = setInterval(() => {
        if (!window.siteSettings) return;

        clearInterval(wait);

        // PT + PF
        if (Number(siteSettings.edit_pt_pf) !== 1) {
            $("#pf, #pro_tax").prop("disabled", true);
        }

        // ESI
        if (Number(siteSettings.edit_esi) !== 1) {
            $("#esi").prop("disabled", true);
        }

        // INCOME TAX
        if (Number(siteSettings.edit_income_tax) !== 1) {
            $("#income_tax").prop("disabled", true);
        }

    }, 50);
}


/* =====================================================
   LOGOUT
===================================================== */
function logout() {
    fetch(`${API}/logout`, {
        credentials: "include"
    })
        .finally(() => {
            window.location.href = "login.html";
        });
}


/* =====================================================
   AUTO-BIND LOGOUT BUTTONS
===================================================== */
function bindLogout() {
    document.querySelectorAll(".logout").forEach(btn => {
        btn.addEventListener("click", function (e) {
            e.preventDefault();
            logout();
        });
    });
}


/* =====================================================
   INIT
===================================================== */
document.addEventListener("DOMContentLoaded", () => {

    // 🔐 Protect all pages except login
    if (!window.location.pathname.includes("login.html")) {
        checkAuth();
        loadSiteSettings();
    }

    bindLogout();

    // 🔧 Apply salary field settings only on addsalary page
    if (window.location.pathname.includes("addsalary.html")) {
        applySalaryFieldSettings();
    }

});
