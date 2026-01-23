// PrUnderground JavaScript

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
