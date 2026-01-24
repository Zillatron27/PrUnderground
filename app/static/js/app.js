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

document.addEventListener('DOMContentLoaded', function() {
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
