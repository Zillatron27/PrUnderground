// PrUnderground JavaScript

// Show spinner during page loads (navigation, form submits)
function showSpinner() {
    document.body.classList.add('loading');
}

// Trigger spinner on link clicks (except # anchors and external links)
document.addEventListener('click', function(e) {
    const link = e.target.closest('a');
    if (link && link.href && !link.href.startsWith('#') && link.hostname === window.location.hostname) {
        showSpinner();
    }
});

// Trigger spinner on form submissions
document.addEventListener('submit', function() {
    showSpinner();
});

// HTMX support (if used)
document.addEventListener('htmx:beforeRequest', function() {
    document.body.classList.add('loading');
});

document.addEventListener('htmx:afterRequest', function() {
    document.body.classList.remove('loading');
});

// Format numbers according to user's locale
function formatLocaleNumbers() {
    const formatter = new Intl.NumberFormat(undefined, {
        maximumFractionDigits: 0
    });

    document.querySelectorAll('[data-locale-number]').forEach(el => {
        const num = parseFloat(el.dataset.localeNumber);
        if (!isNaN(num)) {
            const suffix = el.dataset.localeSuffix || '';
            el.textContent = formatter.format(num) + suffix;
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    // Format numbers on page load
    formatLocaleNumbers();

    // Auto-uppercase material ticker inputs
    const tickerInputs = document.querySelectorAll('input[name="material_ticker"]');
    tickerInputs.forEach(input => {
        input.addEventListener('input', function() {
            this.value = this.value.toUpperCase();
        });
    });

    // Auto-uppercase location inputs (optional, planets are usually caps)
    const locationInputs = document.querySelectorAll('input[name="location"]');
    locationInputs.forEach(input => {
        input.addEventListener('blur', function() {
            // Capitalize first letter of each word
            this.value = this.value.replace(/\b\w/g, l => l.toUpperCase());
        });
    });
});

// Re-format after HTMX content swaps
document.addEventListener('htmx:afterSwap', function() {
    formatLocaleNumbers();
});
