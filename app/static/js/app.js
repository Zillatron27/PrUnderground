// PrUnderground JavaScript

// ========================================
// Embed Mode Detection (rPrUn iframe)
// ========================================

/**
 * Check if we're running in embed mode inside an iframe
 * Embed mode is triggered by ?embed=1 URL parameter
 */
function isEmbedMode() {
    return window.self !== window.top &&
           new URLSearchParams(window.location.search).get('embed') === '1';
}

// Show spinner during page loads (navigation, form submits)
function showSpinner() {
    document.body.classList.add('loading');
}

// Trigger spinner on link clicks (except # anchors)
// In embed mode, intercept and send postMessage to parent instead of navigating
document.addEventListener('click', function(e) {
    const link = e.target.closest('a');
    if (!link || !link.href || link.href.startsWith('#')) {
        return;
    }

    var isInternal = link.hostname === window.location.hostname;

    if (isEmbedMode()) {
        // In embed mode - send postMessage to parent instead of navigating
        e.preventDefault();

        var message = {
            type: 'pru:navigate',
            path: isInternal ? link.pathname + link.search : null,
            url: link.href
        };

        if (!isInternal) {
            message.external = true;
        }

        window.parent.postMessage(message, '*');
    } else if (isInternal) {
        // Normal mode - show spinner for internal links
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

    // Announce ready state to parent if in embed mode
    if (isEmbedMode()) {
        window.parent.postMessage({
            type: 'pru:ready',
            path: window.location.pathname + window.location.search,
            url: window.location.href
        }, '*');
    }
});

// Re-format and re-style after HTMX content swaps
document.addEventListener('htmx:afterSwap', function() {
    formatLocaleNumbers();
    // Re-apply tile style to newly loaded content (e.g., quick add chips)
    applyTileStyle(getTileStyle());
});

// ========================================
// Copy-to-Clipboard (Seller Contact)
// ========================================

/**
 * Copy text to clipboard and show brief "copied" feedback on the button.
 * Used by data-copy buttons on seller contact info.
 */
document.addEventListener('click', function(e) {
    var btn = e.target.closest('.copy-btn');
    if (!btn) return;

    var text = btn.getAttribute('data-copy');
    if (!text) return;

    navigator.clipboard.writeText(text).then(function() {
        btn.classList.add('copied');
        setTimeout(function() {
            btn.classList.remove('copied');
        }, 1500);
    });
});

// ========================================
// Theme Switching (Color Palette)
// ========================================

/**
 * Get the current color palette from DOM attribute (set by server or localStorage fallback)
 */
function getTheme() {
    return document.documentElement.getAttribute('data-theme') || 'refined-prun';
}

/**
 * Set the color palette and persist to server (falls back to localStorage for unauthenticated users)
 */
function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);

    // Update theme selector UI if present
    updateThemeSelector(theme);
    // Update live preview
    updateLivePreview();

    // Save to server (falls back to localStorage on failure/401)
    saveThemePreference('color_palette', theme);
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
 * Get the current tile style from DOM attribute (set by server or localStorage fallback)
 */
function getTileStyle() {
    return document.documentElement.getAttribute('data-tile-style') || 'filled';
}

/**
 * Set the tile style and persist to server (falls back to localStorage for unauthenticated users)
 */
function setTileStyle(style) {
    document.documentElement.setAttribute('data-tile-style', style);

    // Update style selector UI if present
    updateStyleSelector(style);
    // Apply lite class to existing tiles
    applyTileStyle(style);
    // Update live preview
    updateLivePreview();

    // Save to server (falls back to localStorage on failure/401)
    saveThemePreference('tile_style', style);
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
 * Save a theme preference to the server via AJAX POST
 * Falls back to localStorage on 401 (unauthenticated) or network error
 */
function saveThemePreference(field, value) {
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var token = csrfToken ? csrfToken.getAttribute('content') : '';

    var formData = new FormData();
    formData.append(field, value);
    formData.append('csrf_token', token);

    fetch('/auth/update-theme', {
        method: 'POST',
        body: formData,
        credentials: 'same-origin'
    }).then(function(response) {
        if (response.status === 401) {
            // Not authenticated - save to localStorage as fallback
            var storageKey = field === 'color_palette' ? 'pru-theme' : 'pru-tile-style';
            localStorage.setItem(storageKey, value);
        } else if (!response.ok) {
            console.warn('Failed to save theme preference:', response.statusText);
        }
    }).catch(function(err) {
        // Network error - save to localStorage as fallback
        var storageKey = field === 'color_palette' ? 'pru-theme' : 'pru-tile-style';
        localStorage.setItem(storageKey, value);
        console.warn('Network error saving theme, using localStorage fallback:', err);
    });
}

/**
 * Migrate localStorage theme preferences to server (one-time on page load)
 * Runs once when a user has localStorage values but server doesn't have them yet
 */
function migrateLocalStorageTheme() {
    var localTheme = localStorage.getItem('pru-theme');
    var localStyle = localStorage.getItem('pru-tile-style');

    // Only migrate if we have localStorage values
    if (!localTheme && !localStyle) {
        return;
    }

    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var token = csrfToken ? csrfToken.getAttribute('content') : '';

    var formData = new FormData();
    if (localTheme) {
        formData.append('color_palette', localTheme);
    }
    if (localStyle) {
        formData.append('tile_style', localStyle);
    }
    formData.append('csrf_token', token);

    fetch('/auth/update-theme', {
        method: 'POST',
        body: formData,
        credentials: 'same-origin'
    }).then(function(response) {
        if (response.ok) {
            // Successfully migrated - clear localStorage
            localStorage.removeItem('pru-theme');
            localStorage.removeItem('pru-tile-style');
        }
        // 401 = not authenticated, silent no-op (correct behavior)
        // Other errors = retry next page load
    }).catch(function(err) {
        // Network error - retry next page load
        console.warn('Failed to migrate theme preferences:', err);
    });
}

/**
 * Initialize both theme and style on page load
 */
function initThemeAndStyle() {
    // Theme and tile style are already applied by inline script in base.html
    // Just apply the tile style classes to elements
    var currentStyle = getTileStyle();
    applyTileStyle(currentStyle);

    // Initialize selectors if on settings page
    initThemeSelector();
    initStyleSelector();

    // Update live preview if present
    updateLivePreview();

    // Attempt to migrate localStorage preferences to server
    migrateLocalStorageTheme();
}

// Initialize theme and style when DOM is ready
document.addEventListener('DOMContentLoaded', initThemeAndStyle);
