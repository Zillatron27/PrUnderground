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

Coming soon! 🙈

## Setup

### Prerequisites

- Python 3.10+
- A [FIO](https://fio.fnar.net/) account with API key

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

Copy `.env.example` to `.env` and adjust as needed:

```
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///./prununderground.db
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
