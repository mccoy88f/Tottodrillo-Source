"""
Wrapper Python per integrare NSWpedia.com come sorgente Tottodrillo
Implementa l'interfaccia SourceExecutor
"""
import json
import re
import sys
import os
import urllib.parse
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup

def get_random_ua() -> str:
    """Genera un User-Agent casuale"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
    ]
    import random
    return random.choice(user_agents)

def get_browser_headers(referer: Optional[str] = None) -> Dict[str, str]:
    """Genera header browser-like per le richieste"""
    headers = {
        "User-Agent": get_random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Cache-Control": "max-age=0"
    }
    if referer:
        headers["Referer"] = referer
    return headers

def search_roms(params: Dict[str, Any], source_dir: str) -> str:
    """
    Cerca ROM su NSWpedia.com
    - Se search_key è vuoto: usa la pagina categoria https://nswpedia.com/nintendo-switch-roms
    - Se search_key è presente: usa la ricerca https://nswpedia.com/?s=query
    """
    try:
        search_key = params.get("search_key", "").strip()
        max_results = params.get("max_results", 50)
        page = params.get("page", 1)
        
        # Costruisci URL
        if not search_key:
            # Nessuna query: usa la pagina categoria
            if page == 1:
                search_url = "https://nswpedia.com/nintendo-switch-roms"
            else:
                search_url = f"https://nswpedia.com/nintendo-switch-roms/page/{page}/"
            print(f"🔍 [search_roms] Caricamento pagina categoria (pagina {page}): {search_url}", file=sys.stderr)
        else:
            # Query presente: usa la ricerca
            if page == 1:
                search_url = f"https://nswpedia.com/?s={urllib.parse.quote(search_key)}"
            else:
                search_url = f"https://nswpedia.com/page/{page}/?s={urllib.parse.quote(search_key)}"
            print(f"🔍 [search_roms] Cercando: {search_key} su {search_url}", file=sys.stderr)
        
        # Fai la richiesta
        session = requests.Session()
        headers = get_browser_headers()
        response = session.get(search_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Trova tutti i blocchi ROM (class="soft-item shadow-sm")
        rom_blocks = soup.find_all('div', class_=lambda x: x and 'soft-item' in x and 'shadow-sm' in x)
        
        roms = []
        for block in rom_blocks[:max_results]:
            try:
                # URL e titolo dal link
                link_elem = block.find('a', class_='link-title')
                if not link_elem:
                    continue
                
                rom_url = link_elem.get('href', '')
                if not rom_url:
                    continue
                
                title_elem = link_elem.find('h2', class_='soft-item-title')
                title = title_elem.get_text(strip=True) if title_elem else ""
                
                # Immagine dal div icon-big
                img_elem = None
                icon_div = block.find('div', class_=lambda x: x and 'icon-big' in x and 'icon' in x)
                if icon_div:
                    # Cerca l'img dentro il picture
                    img_elem = icon_div.find('img')
                
                box_image = img_elem.get('src', '') if img_elem else None
                
                # Slug dall'URL (es: "paper-mario-the-origami-king-89" da "https://nswpedia.com/nintendo-switch-roms/action/paper-mario-the-origami-king-89")
                slug_match = re.search(r'/([^/]+)/?$', rom_url)
                slug = slug_match.group(1) if slug_match else rom_url.split('/')[-1]
                
                roms.append({
                    "slug": slug,
                    "rom_id": rom_url,  # Usiamo l'URL completo come rom_id
                    "title": title,
                    "platform": "switch",  # Sempre Switch
                    "box_image": box_image,
                    "regions": [],  # Non disponibili nella lista
                    "links": []  # Verranno recuperati in get_entry
                })
            except Exception as e:
                print(f"⚠️ [search_roms] Errore parsing ROM: {e}", file=sys.stderr)
                continue
        
        print(f"✅ [search_roms] Trovate {len(roms)} ROM", file=sys.stderr)
        
        # Estrai informazioni sulla paginazione
        total_pages = 1
        try:
            # Cerca il blocco di paginazione (potrebbe essere in vari formati)
            nav_links = soup.find('nav', class_=lambda x: x and 'pagination' in str(x).lower()) or soup.find('div', class_=lambda x: x and 'pagination' in str(x).lower())
            if nav_links:
                # Trova tutti i link di pagina
                page_links = nav_links.find_all('a', href=re.compile(r'/page/\d+'))
                page_numbers = []
                for link in page_links:
                    href = link.get('href', '')
                    match = re.search(r'/page/(\d+)/', href)
                    if match:
                        page_numbers.append(int(match.group(1)))
                
                if page_numbers:
                    total_pages = max(page_numbers)
                    print(f"📄 [search_roms] Paginazione: pagina {page} di {total_pages}", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ [search_roms] Errore estrazione paginazione: {e}", file=sys.stderr)
        
        return json.dumps({
            "roms": roms,
            "total_results": len(roms) * total_pages if total_pages > 1 else len(roms),  # Stima
            "current_results": len(roms),
            "current_page": page,
            "total_pages": total_pages
        })
        
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"❌ [search_roms] Errore: {error_msg}", file=sys.stderr)
        return json.dumps({"error": error_msg})

def get_entry(params: Dict[str, Any], source_dir: str) -> str:
    """
    Ottiene i dettagli completi di una ROM
    """
    try:
        slug = params.get("slug", "")
        include_download_links = params.get("include_download_links", True)
        if not slug:
            return json.dumps({"entry": None})
        
        # Costruisci URL (lo slug può essere un URL completo o solo lo slug)
        if slug.startswith("http"):
            page_url = slug
        else:
            # Lo slug potrebbe essere solo il nome finale o l'URL completo
            if slug.startswith("nintendo-switch-roms/"):
                page_url = f"https://nswpedia.com/{slug}"
            else:
                # Prova prima senza categoria
                page_url = f"https://nswpedia.com/nintendo-switch-roms/{slug}"
        
        print(f"🔗 [get_entry] Recupero dettagli: {page_url}", file=sys.stderr)
        
        # Fai la richiesta alla pagina ROM
        session = requests.Session()
        headers = get_browser_headers()
        response = None
        try:
            response = session.get(page_url, headers=headers, timeout=15)
            
            # Se 404, prova con categoria "action" (categoria comune)
            if response.status_code == 404 and not slug.startswith("http") and "/action/" not in page_url:
                fallback_url = f"https://nswpedia.com/nintendo-switch-roms/action/{slug}"
                print(f"🔄 [get_entry] 404, provo URL alternativo: {fallback_url}", file=sys.stderr)
                response = session.get(fallback_url, headers=headers, timeout=15)
                if response.status_code == 200:
                    page_url = fallback_url
                    print(f"✅ [get_entry] URL alternativo funziona: {page_url}", file=sys.stderr)
            
            if response.status_code == 404:
                print(f"⚠️ [get_entry] Pagina non trovata (404) per: {page_url}", file=sys.stderr)
                return json.dumps({"entry": None})
            
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                print(f"⚠️ [get_entry] Pagina non trovata (404) per: {page_url}", file=sys.stderr)
                return json.dumps({"entry": None})
            raise
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Estrai titolo dal campo "App name" (stesso formato della ricerca)
        title = None
        
        # Cerca il div info-block scora che contiene "App name"
        info_blocks = soup.find_all('div', class_=lambda x: x and 'info-block' in str(x) and 'scora' in str(x))
        for info_block in info_blocks:
            spans = info_block.find_all('span', class_='body-2')
            if len(spans) >= 2:
                # Il primo span contiene la label, il secondo il valore
                label_span = spans[0]
                value_span = spans[1]
                label_text = label_span.get_text(strip=True).lower()
                if 'app name' in label_text:
                    title = value_span.get_text(strip=True)
                    print(f"✅ [get_entry] Titolo estratto da 'App name': {title}", file=sys.stderr)
                    break
        
        # Fallback: cerca h1 o title se non trovato in "App name"
        if not title:
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text(strip=True)
                print(f"✅ [get_entry] Titolo estratto da h1: {title}", file=sys.stderr)
        
        if not title:
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text(strip=True)
                # Rimuovi suffissi comuni
                title = re.sub(r'\s*-\s*NSWpedia.*$', '', title, flags=re.IGNORECASE)
                print(f"✅ [get_entry] Titolo estratto da title tag: {title}", file=sys.stderr)
        
        if title:
            title = title.strip()
        
        # Estrai immagine box art (stessa logica della lista)
        box_image = None
        icon_div = soup.find('div', class_=lambda x: x and 'icon-big' in str(x) and 'icon' in str(x))
        if icon_div:
            img_elem = icon_div.find('img')
            if img_elem:
                box_image = img_elem.get('src', '')
        
        # Fallback: cerca prima immagine valida nell'articolo
        if not box_image:
            article = soup.find('article') or soup.find('main')
            if article:
                img_elem = article.find('img', src=re.compile(r'\.(jpg|jpeg|png|webp)', re.I))
                if img_elem:
                    box_image = img_elem.get('src', '')
        
        # Estrai screenshot (primi 2)
        screen_images = []
        screenshots_div = soup.find('div', id='lightgallery', class_='screenshots_row')
        if screenshots_div:
            screenshot_links = screenshots_div.find_all('a', class_='screen_shot')[:2]
            for link in screenshot_links:
                img = link.find('img')
                if img:
                    img_url = img.get('src', '')
                    if img_url:
                        screen_images.append(img_url)
        
        # Trova il pulsante "Download for Free" e leggi l'URL dalla pagina
        # NON calcolare l'URL, deve essere letto dal pulsante
        download_button = None
        download_page_url = None
        
        # Metodo 1: cerca dentro div.btn-block (metodo più affidabile)
        btn_block = soup.find('div', class_='btn-block')
        if btn_block:
            # Cerca il link dentro btn-block che ha href che inizia con /download/
            download_button = btn_block.find('a', href=re.compile(r'/download/'))
            if download_button:
                print(f"✅ [get_entry] Pulsante trovato in btn-block", file=sys.stderr)
        
        # Metodo 2: cerca link con class che contiene "green" e href contiene "/download/"
        if not download_button:
            download_button = soup.find('a', class_=lambda x: x and 'green' in str(x), href=re.compile(r'/download/'))
            if download_button:
                print(f"✅ [get_entry] Pulsante trovato per class green", file=sys.stderr)
        
        # Metodo 3: cerca link con testo "Download for Free" o simile
        if not download_button:
            all_links = soup.find_all('a', href=re.compile(r'/download/'))
            for link in all_links:
                link_text = link.get_text(strip=True).lower()
                if 'download' in link_text and ('free' in link_text or 'for' in link_text):
                    download_button = link
                    print(f"✅ [get_entry] Pulsante trovato per testo: {link_text[:50]}", file=sys.stderr)
                    break
        
        # Metodo 4: ultimo fallback - primo link con /download/ che ha class btn
        if not download_button:
            all_links = soup.find_all('a', href=re.compile(r'/download/'))
            for link in all_links:
                classes = link.get('class', [])
                if any('btn' in str(c).lower() for c in classes):
                    download_button = link
                    print(f"✅ [get_entry] Pulsante trovato per class btn", file=sys.stderr)
                    break
        
        # Leggi l'URL dal pulsante trovato
        if download_button:
            download_page_url = download_button.get('href', '')
            if download_page_url:
                # Assicurati che l'URL sia completo
                if not download_page_url.startswith('http'):
                    download_page_url = f"https://nswpedia.com{download_page_url}"
                print(f"✅ [get_entry] URL pagina download letto dal pulsante: {download_page_url}", file=sys.stderr)
            else:
                print(f"⚠️ [get_entry] Pulsante trovato ma href vuoto", file=sys.stderr)
        else:
            # Debug: cerca tutti i link con /download/ per capire cosa c'è nella pagina
            all_download_links = soup.find_all('a', href=re.compile(r'/download/'))
            print(f"⚠️ [get_entry] Pulsante 'Download for Free' non trovato. Trovati {len(all_download_links)} link con '/download/' nella pagina", file=sys.stderr)
            if all_download_links:
                for i, link in enumerate(all_download_links[:5]):  # Primi 5 per debug
                    href = link.get('href', '')
                    classes = link.get('class', [])
                    text = link.get_text(strip=True)
                    print(f"  Link {i+1}: href={href[:80]}, class={classes}, text='{text[:50]}'", file=sys.stderr)
        
        download_links = []
        
        # Estrai download links solo se richiesto
        if not include_download_links:
            print(f"ℹ️ [get_entry] include_download_links=False, salto estrazione link", file=sys.stderr)
        elif not download_page_url:
            print(f"⚠️ [get_entry] download_page_url è None, non posso estrarre link", file=sys.stderr)
        else:
            print(f"🔗 [get_entry] Estrazione link download da: {download_page_url}", file=sys.stderr)
            
            # Visita la pagina di download
            try:
                download_response = session.get(download_page_url, headers=get_browser_headers(referer=page_url), timeout=15)
                download_response.raise_for_status()
                download_soup = BeautifulSoup(download_response.content, 'html.parser')
                print(f"✅ [get_entry] Pagina download caricata, dimensione: {len(download_response.content)} bytes", file=sys.stderr)
            except Exception as e:
                print(f"❌ [get_entry] Errore caricamento pagina download: {e}", file=sys.stderr)
                import traceback
                print(f"   Traceback: {traceback.format_exc()}", file=sys.stderr)
                download_soup = None
            
            if download_soup:
                # Trova tutte le tabelle di download
                download_tables = download_soup.find_all('div', class_='table-download')
                print(f"📊 [get_entry] Trovate {len(download_tables)} tabelle di download", file=sys.stderr)
            
                for table_div in download_tables:
                    try:
                        # Leggi il titolo della tabella per capire se è "Direct" o altro
                        h3 = table_div.find('h3')
                        table_title = h3.get_text(strip=True) if h3 else ""
                        print(f"📋 [get_entry] Processando tabella: {table_title}", file=sys.stderr)
                        
                        # Determina se richiede webview e estrai nome del sito
                        is_direct = "Direct" in table_title
                        requires_webview = not is_direct
                        
                        # Estrai nome del sito dal titolo (es: "Downloads List - 1Fichier" -> "1Fichier")
                        site_name = None
                        if not is_direct and "Downloads List -" in table_title:
                            # Estrai il nome dopo "Downloads List -"
                            parts = table_title.split("Downloads List -")
                            if len(parts) > 1:
                                site_name = parts[1].strip()
                        elif is_direct:
                            site_name = "Diretto"  # Sarà localizzato dall'app
                        
                        # Trova la tabella
                        table = table_div.find('table')
                        if not table:
                            print(f"⚠️ [get_entry] Tabella non trovata in div.table-download", file=sys.stderr)
                            continue
                        
                        tbody = table.find('tbody')
                        if not tbody:
                            print(f"⚠️ [get_entry] tbody non trovato nella tabella", file=sys.stderr)
                            continue
                        
                        rows = tbody.find_all('tr')
                        print(f"📝 [get_entry] Trovate {len(rows)} righe nella tabella '{table_title}'", file=sys.stderr)
                        for row in rows:
                            try:
                                cells = row.find_all('td')
                                if len(cells) < 3:
                                    print(f"⚠️ [get_entry] Riga con meno di 3 celle, salto", file=sys.stderr)
                                    continue
                                
                                # Prima cella: link con nome file
                                link_cell = cells[0]
                                link_elem = link_cell.find('a')
                                if not link_elem:
                                    print(f"⚠️ [get_entry] Link non trovato nella prima cella", file=sys.stderr)
                                    continue
                                
                                link_url = link_elem.get('href', '')
                                if not link_url.startswith('http'):
                                    link_url = f"https://nswpedia.com{link_url}"
                                
                                # Codifica correttamente l'URL (gestisce spazi e caratteri speciali)
                                parsed = urllib.parse.urlparse(link_url)
                                encoded_path = urllib.parse.quote(parsed.path, safe='/')
                                link_url = urllib.parse.urlunparse((
                                    parsed.scheme,
                                    parsed.netloc,
                                    encoded_path,
                                    parsed.params,
                                    parsed.query,
                                    parsed.fragment
                                ))
                                
                                file_name = link_elem.get_text(strip=True)
                                
                                # Seconda cella: size
                                size_str = cells[1].get_text(strip=True)
                                
                                # Terza cella: type
                                format_type = cells[2].get_text(strip=True).upper()
                                
                                print(f"📥 [get_entry] Link trovato: {file_name} ({format_type}, {size_str}, direct={is_direct})", file=sys.stderr)
                                
                                # Per i link diretti, NON estrarre l'URL finale
                                # Cloudflare richiede una challenge JavaScript che richiede ~20 secondi
                                # Il WebView deve aprire la pagina intermedia per completare la challenge e ottenere il cookie cf_clearance
                                # Poi il WebView può intercettare il download quando parte
                                final_url = link_url
                                intermediate_url = link_url if is_direct else None  # URL della pagina intermedia per WebView
                                
                                if is_direct:
                                    print(f"ℹ️ [get_entry] Link diretto: uso pagina intermedia per WebView (Cloudflare challenge)", file=sys.stderr)
                                    print(f"   URL pagina intermedia: {link_url}", file=sys.stderr)
                                    # Per i link diretti, usiamo l'URL della pagina intermedia
                                    # Il WebView completerà la challenge Cloudflare e intercetterà il download
                                
                                # Costruisci il nome del link: mostra "Diretto" o il nome del sito alla fine tra parentesi
                                link_name = file_name
                                if site_name:
                                    # Se è diretto, mostra "nome file (Diretto)", altrimenti "nome file (NomeSito)"
                                    if is_direct:
                                        link_name = f"{file_name} (Diretto)"
                                    else:
                                        link_name = f"{file_name} ({site_name})"
                                
                                download_links.append({
                                    "name": link_name,
                                    "type": "ROM",
                                    "format": format_type or "unknown",
                                    "url": intermediate_url if is_direct else final_url,  # Per link diretti, usa pagina intermedia per WebView
                                    "size": None,
                                    "size_str": size_str,
                                    "requires_webview": True if is_direct else requires_webview,  # Link diretti richiedono WebView per Cloudflare
                                    "delay_seconds": None,  # Non più necessario, gestito dal WebView
                                    "intermediate_url": None  # Non più necessario, url punta già alla pagina intermedia
                                })
                                print(f"✅ [get_entry] Link aggiunto alla lista: {link_name}", file=sys.stderr)
                            except Exception as e:
                                print(f"⚠️ [get_entry] Errore parsing riga tabella: {e}", file=sys.stderr)
                                import traceback
                                print(f"   Traceback: {traceback.format_exc()}", file=sys.stderr)
                                continue
                    except Exception as e:
                        print(f"⚠️ [get_entry] Errore parsing tabella download: {e}", file=sys.stderr)
                        import traceback
                        print(f"   Traceback: {traceback.format_exc()}", file=sys.stderr)
                        continue
                
                print(f"✅ [get_entry] Trovati {len(download_links)} link download totali", file=sys.stderr)
        
        # Estrai regioni (non disponibili su NSWpedia)
        regions = []
        
        entry = {
            "slug": slug.split('/')[-1].rstrip('/'),
            "rom_id": page_url,
            "title": title or "Unknown",
            "platform": "switch",
            "box_image": box_image,
            "screen_image": screen_images[0] if screen_images else None,
            "regions": regions,
            "links": download_links
        }
        
        return json.dumps({"entry": entry})
        
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"❌ [get_entry] Errore: {error_msg}", file=sys.stderr)
        return json.dumps({"error": error_msg})

def get_platforms(source_dir: str) -> str:
    """Ritorna le piattaforme supportate (solo Switch)"""
    platforms = {
        "switch": {
            "name": "Nintendo Switch",
            "brand": "Nintendo"
        }
    }
    return json.dumps({"platforms": platforms})

def get_regions() -> str:
    """Ritorna le regioni supportate"""
    regions = {}
    return json.dumps({"regions": regions})

def execute(params_json: str) -> str:
    """
    Entry point principale per l'esecuzione dello script
    """
    try:
        params = json.loads(params_json)
        method = params.get("method", "")
        source_dir = params.get("source_dir", os.path.dirname(__file__))
        
        if method == "searchRoms":
            return search_roms(params, source_dir)
        elif method == "getEntry":
            return get_entry(params, source_dir)
        elif method == "getPlatforms":
            return get_platforms(source_dir)
        elif method == "getRegions":
            return get_regions()
        else:
            return json.dumps({"error": f"Metodo sconosciuto: {method}"})
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"❌ [execute] Errore: {error_msg}", file=sys.stderr)
        return json.dumps({"error": error_msg})

if __name__ == "__main__":
    # Test locale
    if len(sys.argv) > 1:
        params_json = sys.argv[1]
        result = execute(params_json)
        print(result)
    else:
        print("Usage: python nswpedia_source.py <params_json>")

