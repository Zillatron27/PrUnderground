# PrUnderground

A community trade registry for [Prosperous Universe](https://prosperousuniverse.com/) players. List what you sell, find what you need.

## What is this?

Discord trading channels aren't great for finding buyers and sellers off market - messages scroll away, searches are of questionable value and not *everyone* wants to make an elaborate spreadsheet.

PrUnderground fixes that. Connect your FIO account, list what you're selling, and share your storefront with your corp or community. One click copies a formatted post to Discord with a link to your live listings.

## Intended Use

PrUnderground is designed to be hosted by a community (corp, faction, trading group) as a shared registry for members. Think of it as your community's private marketplace.

You *can* run it just for yourself as a personal storefront, but the real value comes when your community uses it.

## Features

- **FIO Integration** - Login with your FIO username and API key. We pull your company info, bases, and storage locations automatically. Data is cached for 10 minutes with manual refresh option.
- **Live Inventory** - Link listings to your actual storage. Shows "FIO-real-time" availability (stock minus your defined reserve).
- **Flexible Pricing** - Set absolute prices, CX-relative prices (e.g., "CX - 10%"), or just "Contact me" for negotiated deals.
- **Expiring Deals** - Mark listings as specials with optional expiry dates. Expired listings auto-hide.
- **Public Profiles** - Shareable link to your listings page. Send it to your corp, pin it in Discord, whatever.
- **Copy to Discord** - One click generates a formatted message ready to paste into any channel.
- **Browse & Search** - Filter by material or location. Find who's selling what you need.

## Screenshots
<img width="1024" height="768" alt="login" src="https://github.com/user-attachments/assets/ad45758e-068e-4597-b751-8cd1264b6eae" />

<img width="1024" height="768" alt="dashboard" src="https://github.com/user-attachments/assets/d1cfaf9c-a735-4c02-a3b6-96026298c3e3" />

<img width="1024" height="768" alt="publicprofile" src="https://github.com/user-attachments/assets/1aa5d7dd-7957-4f34-b9b3-c9838e052cc3" />

<img width="1024" height="768" alt="browse" src="https://github.com/user-attachments/assets/cc3712e0-6929-4800-b872-87890384af69" />

<img width="1024" height="768" alt="account" src="https://github.com/user-attachments/assets/ba3024ca-20a1-47df-960d-0ca2a193c9f9" />

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

## Tech Stack

- **Backend**: Python, FastAPI
- **Database**: SQLite (easy to swap for Postgres later)
- **Frontend**: Jinja2 templates, HTMX, vanilla JS, APEX-inspired dark theme
- **Data**: [FIO API](https://doc.fnar.net/) for Prosperous Universe game data

## Roadmap

- [x] UI polish and mobile responsiveness
- [ ] Mobile UI improvements
- [ ] Multi-part listings
- [ ] Discord integration
- [ ] Custom copy templates
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
