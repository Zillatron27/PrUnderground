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

// Re-format and re-style after HTMX content swaps
document.addEventListener('htmx:afterSwap', function() {
    formatLocaleNumbers();
    // Re-apply tile style to newly loaded content (e.g., quick add chips)
    applyTileStyle(getTileStyle());
});

// ========================================
// Theme Switching (Color Palette)
// ========================================

/**
 * Get the current color palette from localStorage
 */
function getTheme() {
    return localStorage.getItem('pru-theme') || 'refined-prun';
}

/**
 * Set the color palette and persist to localStorage
 */
function setTheme(theme) {
    localStorage.setItem('pru-theme', theme);
    document.documentElement.setAttribute('data-theme', theme);

    // Update theme selector UI if present
    updateThemeSelector(theme);
    // Update live preview
    updateLivePreview();
}

/**
 * Update theme selector UI to show selected state
 */
function updateThemeSelector(theme) {
    // Legacy theme options (full row style)
    const themeOptions = document.querySelectorAll('.theme-option');
    themeOptions.forEach(function(option) {
        const input = option.querySelector('input[type="radio"]');
        if (input && input.value === theme) {
            option.classList.add('selected');
            input.checked = true;
        } else {
            option.classList.remove('selected');
            if (input) input.checked = false;
        }
    });

    // New palette options (compact horizontal)
    const paletteOptions = document.querySelectorAll('.palette-option');
    paletteOptions.forEach(function(option) {
        const input = option.querySelector('input[type="radio"]');
        if (input && input.value === theme) {
            option.classList.add('selected');
            input.checked = true;
        } else {
            option.classList.remove('selected');
            if (input) input.checked = false;
        }
    });
}

/**
 * Initialize theme selector on page load
 */
function initThemeSelector() {
    // Legacy theme options
    const themeOptions = document.querySelectorAll('.theme-option');
    themeOptions.forEach(function(option) {
        option.addEventListener('click', function() {
            const input = this.querySelector('input[type="radio"]');
            if (input) {
                setTheme(input.value);
            }
        });
    });

    // New palette options
    const paletteOptions = document.querySelectorAll('.palette-option');
    paletteOptions.forEach(function(option) {
        option.addEventListener('click', function() {
            const input = this.querySelector('input[type="radio"]');
            if (input) {
                setTheme(input.value);
            }
        });
    });

    // Initialize UI with current theme
    const currentTheme = getTheme();
    updateThemeSelector(currentTheme);
}

// ========================================
// Tile Style (Filled vs Lite)
// ========================================

/**
 * Get the current tile style from localStorage
 */
function getTileStyle() {
    return localStorage.getItem('pru-tile-style') || 'filled';
}

/**
 * Set the tile style and persist to localStorage
 */
function setTileStyle(style) {
    localStorage.setItem('pru-tile-style', style);
    document.documentElement.setAttribute('data-tile-style', style);

    // Update style selector UI if present
    updateStyleSelector(style);
    // Apply lite class to existing tiles
    applyTileStyle(style);
    // Update live preview
    updateLivePreview();
}

/**
 * Update style selector UI to show selected state
 */
function updateStyleSelector(style) {
    const styleOptions = document.querySelectorAll('.style-option');
    styleOptions.forEach(function(option) {
        const input = option.querySelector('input[type="radio"]');
        if (input && input.value === style) {
            option.classList.add('selected');
            input.checked = true;
        } else {
            option.classList.remove('selected');
            if (input) input.checked = false;
        }
    });
}

/**
 * Apply tile style to all material tiles and chips
 */
function applyTileStyle(style) {
    const isLite = style === 'lite';

    // Material tiles
    document.querySelectorAll('.mat-tile').forEach(function(tile) {
        if (isLite) {
            tile.classList.add('lite');
        } else {
            tile.classList.remove('lite');
        }
    });

    // Quick add chips
    document.querySelectorAll('.chip[class*="chip-"]').forEach(function(chip) {
        // Only apply to category-colored chips, not .chip-more etc
        if (chip.className.match(/chip-(agricultural|consumables|fuels|liquids|plastics|ship|alloys|chemicals|construction|drones|electronic|elements|energy|gases|metals|minerals|ores|software|textiles|unit|default)/)) {
            if (isLite) {
                chip.classList.add('lite');
            } else {
                chip.classList.remove('lite');
            }
        }
    });
}

/**
 * Update live preview tiles
 */
function updateLivePreview() {
    const previewContainer = document.querySelector('.theme-live-preview-tiles');
    if (!previewContainer) return;

    const currentStyle = getTileStyle();
    const isLite = currentStyle === 'lite';

    previewContainer.querySelectorAll('.mat-tile').forEach(function(tile) {
        if (isLite) {
            tile.classList.add('lite');
        } else {
            tile.classList.remove('lite');
        }
    });
}

/**
 * Initialize style selector on page load
 */
function initStyleSelector() {
    const styleOptions = document.querySelectorAll('.style-option');
    if (styleOptions.length === 0) return;

    // Add click handlers
    styleOptions.forEach(function(option) {
        option.addEventListener('click', function() {
            const input = this.querySelector('input[type="radio"]');
            if (input) {
                setTileStyle(input.value);
            }
        });
    });

    // Initialize UI with current style
    const currentStyle = getTileStyle();
    updateStyleSelector(currentStyle);
}

/**
 * Initialize both theme and style on page load
 */
function initThemeAndStyle() {
    // Apply saved theme
    const savedTheme = getTheme();
    document.documentElement.setAttribute('data-theme', savedTheme);

    // Apply saved tile style
    const savedStyle = getTileStyle();
    document.documentElement.setAttribute('data-tile-style', savedStyle);
    applyTileStyle(savedStyle);

    // Initialize selectors if on settings page
    initThemeSelector();
    initStyleSelector();

    // Update live preview if present
    updateLivePreview();
}

// Initialize theme and style when DOM is ready
document.addEventListener('DOMContentLoaded', initThemeAndStyle);
