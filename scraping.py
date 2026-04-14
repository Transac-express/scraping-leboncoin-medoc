"""
Scraper terrains à bâtir - Axe Médoc
Cibles : Lesparre, Castelnau, Moulis, Ludon, Parempuyre, Vendays-Montalivet
Sources : LeBonCoin, SeLoger, Ouest-France Immo, Logic-Immo

Usage : python scraper_terrains_medoc.py
Output : terrains_medoc_YYYY-MM-DD.csv

Dépendances :
    pip install playwright pandas beautifulsoup4
    playwright install chromium

ATTENTION : respecte les CGU des sites. Usage personnel/étude de marché.
Pour un volume important, utilise plutôt l'API officielle ou un service
comme Apify/Bright Data.
"""

import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

# --- CONFIG ---
COMMUNES = [
    ("lesparre-medoc_33340", "Lesparre-Médoc"),
    ("castelnau-de-medoc_33480", "Castelnau-de-Médoc"),
    ("moulis-en-medoc_33480", "Moulis-en-Médoc"),
    ("ludon-medoc_33290", "Ludon-Médoc"),
    ("parempuyre_33290", "Parempuyre"),
    ("vendays-montalivet_33930", "Vendays-Montalivet"),
]

SURFACE_MIN = 300   # m²
SURFACE_MAX = 800   # m²
PRIX_MAX = 120000   # € (terrain nu constructible diffus)

OUTPUT = Path(f"terrains_medoc_{datetime.now():%Y-%m-%d}.csv")


async def scrape_leboncoin(page, commune_slug, commune_nom):
    """Scrape LeBonCoin rubrique terrains."""
    url = (
        f"https://www.leboncoin.fr/recherche"
        f"?category=9&locations={commune_slug}"
        f"&real_estate_type=3"  # terrain
        f"&square={SURFACE_MIN}-{SURFACE_MAX}"
        f"&price=min-{PRIX_MAX}"
    )
    print(f"  → LBC: {commune_nom}")
    results = []
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)
        # Gestion cookies
        try:
            await page.click('button[aria-label="Accepter"]', timeout=3000)
        except Exception:
            pass
        await page.wait_for_timeout(1500)

        cards = await page.query_selector_all('article[data-test-id="ad"]')
        for c in cards[:30]:
            try:
                title = await c.query_selector_eval('a p', 'el => el.textContent')
                price = await c.query_selector_eval(
                    '[data-test-id="price"]', 'el => el.textContent'
                )
                link_el = await c.query_selector('a')
                href = await link_el.get_attribute('href') if link_el else ''
                # Surface souvent dans le titre ou sous-titre
                subtitle = ''
                try:
                    subtitle = await c.query_selector_eval(
                        'p[data-test-id="ad-subtitle"]', 'el => el.textContent'
                    )
                except Exception:
                    pass
                surface_match = re.search(r'(\d+)\s*m²', f'{title} {subtitle}')
                surface = int(surface_match.group(1)) if surface_match else None
                prix_num = int(re.sub(r'\D', '', price)) if price else None
                prix_m2 = round(prix_num / surface, 0) if prix_num and surface else None

                results.append({
                    'source': 'LBC',
                    'commune': commune_nom,
                    'titre': title.strip() if title else '',
                    'prix_€': prix_num,
                    'surface_m²': surface,
                    'prix_€_m²': prix_m2,
                    'url': f"https://www.leboncoin.fr{href}" if href else '',
                    'date_extraction': datetime.now().isoformat(timespec='minutes'),
                })
            except Exception as e:
                print(f"    ⚠ annonce ignorée : {e}")
                continue
    except Exception as e:
        print(f"  ✗ échec LBC {commune_nom}: {e}")
    return results


async def main():
    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # True après mise au point
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
        )
        page = await context.new_page()

        for slug, nom in COMMUNES:
            print(f"\n=== {nom} ===")
            results = await scrape_leboncoin(page, slug, nom)
            print(f"  {len(results)} annonces récupérées")
            all_results.extend(results)
            await page.wait_for_timeout(3000)  # anti rate-limit

        await browser.close()

    # Écriture CSV
    if all_results:
        keys = list(all_results[0].keys())
        with OUTPUT.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(all_results)
        print(f"\n✅ {len(all_results)} annonces → {OUTPUT}")
    else:
        print("\n⚠ Aucune annonce récupérée.")


if __name__ == "__main__":
    asyncio.run(main())
