# PrUnderground

A community trade registry for [Prosperous Universe](https://prosperousuniverse.com/) players. List what you sell, find what you need.

📈 Live at https://prunderground.app — no setup required, just log in with your FIO key.

## What is this?

Discord trading channels aren't great for finding buyers and sellers off market - messages scroll away, searches are of questionable value and not *everyone* wants to make an elaborate spreadsheet.

PrUnderground fixes that. Connect your FIO account, list what you're selling, and share your storefront with your corp or community. One click copies a formatted post to Discord with a link to your live listings.

## Intended Use

PrUnderground is designed to be hosted by a community (corp, faction, trading group) as a shared registry for members. Think of it as your community's private marketplace.

You *can* run it just for yourself as a personal storefront, but the real value comes when your community uses it.

## Features

- **FIO Integration** - Login with your FIO username and API key. We pull your company info, bases, and storage locations automatically. Data syncs on login and refreshes on demand.
- **Live Inventory** - Link listings to your actual storage. Shows "FIO-real-time" availability (stock minus your defined reserve).
- **Flexible Pricing** - Set absolute prices, CX-relative prices (percentage or fixed offset from Ask), or just "Contact me" for negotiated deals. CX prices sync automatically every 30 minutes.
- **Bundles** - Sell multiple items together as a package at a single price. Status indicators show IN STOCK / LOW / OUT / MTO / ∞ with responsive display.
- **Expiring Deals** - Mark listings as specials with optional expiry dates. Expired listings auto-hide.
- **Public Profiles** - Shareable link to your listings page. Send it to your corp, pin it in Discord, whatever.
- **Copy to Discord** - One click generates a formatted message (grouped by location) ready to paste into any channel. Customize the format with your own template.
- **Browse & Search** - Filter by material or location. Collapsible filters with active filter pills. Multi-column sorting with visual sort builder.
- **Import/Export** - Backup and restore your listings and bundles as JSON. Extensible format for future integrations.
- **APEX Embed Support** - Embed PrUnderground in Refined PrUn's XIT WEB tiles with full authentication.
- **Theme Customization** - 4 color palettes (Refined PrUn, PrUn Default, High Contrast, Monochrome) × 2 tile styles (Filled, Lite). Live preview in Account Settings.

## Screenshots

<img width="1447" height="1602" alt="image" src="https://github.com/user-attachments/assets/bf15dd83-90b8-4191-b79c-f8e7f316d0f0" />
<img width="1752" height="1903" alt="image" src="https://github.com/user-attachments/assets/db912f27-8594-4fce-82e4-b872b19860db" />
<img width="1440" height="1761" alt="image" src="https://github.com/user-attachments/assets/ac0e72e7-b5e6-41f4-baa8-35bd9f29a071" />
<img width="1452" height="1068" alt="image" src="https://github.com/user-attachments/assets/afcc38c7-3a28-4e4b-8a82-601d2c51db98" />
<img width="1452" height="1553" alt="image" src="https://github.com/user-attachments/assets/89415144-7a9d-4711-aaa2-6d47fa9696df" />
<img width="1452" height="549" alt="image" src="https://github.com/user-attachments/assets/9f949f2a-d25f-46c3-aabc-487471ba77df" />

## Setup

### Prerequisites

- Python 3.10+
- A [FIO](https://fio.fnar.net/) account with API key (users need this to log in, not required for hosting)

### Installation

**Note:** While you can run this as a personal tool, PrUnderground is designed to be hosted by a community - a corp, faction, or trading group. The more people using the same instance, the more useful it becomes.

```bash
# Clone the repo
git clone https://github.com/Zillatron27/PrUnderground.git
cd PrUnderground

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy example env and configure
cp .env.example .env

# Run the app
uvicorn app.main:app --reload
```

Then open http://localhost:8000 in your browser.

### Configuration

Copy `.env.example` to `.env` and generate secrets:

```bash
# Generate secrets (run each command and paste the output into .env)
python -c "import secrets; print(secrets.token_hex(32))"
```

Required environment variables:

```
# Security secrets (generate unique values for each)
SECRET_KEY=your-secret-key-here
SESSION_SECRET=your-session-secret-here
CSRF_SECRET=your-csrf-secret-here

# Database (SQLite by default, or use PostgreSQL connection string)
DATABASE_URL=sqlite:///./prununderground.db

# FIO API (default is fine unless you're running a local FIO instance)
FIO_API_BASE=https://rest.fnar.net
```

### Migrations

If upgrading an existing installation, run any new migration scripts:

```bash
python scripts/add_bundle_tables.py
python scripts/add_cx_absolute_column.py
python scripts/encrypt_existing_keys.py  # v1.0.3: Encrypt FIO API keys at rest

# v1.0.5 migrations:
python scripts/add_low_stock_threshold.py
python scripts/add_discord_template.py
python scripts/add_exchange_table.py
python scripts/add_usage_stats.py
```

## Tech Stack

- **Backend**: Python, FastAPI
- **Database**: SQLite (easy to swap for Postgres later)
- **Frontend**: Jinja2 templates, HTMX, vanilla JS, APEX-inspired dark theme
- **Data**: [FIO API](https://doc.fnar.net/) for Prosperous Universe game data

## Roadmap

- [x] UI polish and mobile responsiveness
- [x] User data export/import
- [x] Bundles (multi-item packages)
- [x] Multi-column sorting
- [x] CX absolute offset pricing
- [x] Mobile UI improvements
- [x] Custom Discord templates
- [x] CX price display with auto-sync
- [ ] Discord bot integration
- [ ] Multi-community support

## Contributing

Early days - feedback welcome! Open an issue or ping me on [Discord](https://discordapp.com/users/175185041997955072).

## Related Tools

PrUnderground fills a specific gap in the PrUn tooling ecosystem:

| Tool | Focus |
|------|-------|
| [Refined PrUn](https://github.com/refined-prun/refined-prun) | In-game UI enhancements |
| [FIO](https://fio.fnar.net/) | Game data API |
| [PRUNplanner](https://prunplanner.org/) | Empire & base planning |
| **PrUnderground** | Community trade coordination |


## Acknowledgments

- [FIO/FNAR](https://fnar.net/) for the API that makes this possible
- The ADI community for feedback
