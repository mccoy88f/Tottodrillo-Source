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
                continue
        
        # Estrai informazioni sulla paginazione
        total_pages = 1
        next_page_url = None
        try:
            # Cerca il blocco di paginazione (ul.pagination)
            pagination_ul = soup.find('ul', class_=lambda x: x and 'pagination' in str(x).lower())
            if pagination_ul:
                # Trova tutti i link di pagina (sia numerici che "Next")
                page_links = pagination_ul.find_all('a', href=True)
                page_numbers = []
                
                for link in page_links:
                    href = link.get('href', '')
                    if not href:
                        continue
                    
                    # Gestisci i due formati diversi:
                    # 1. Homepage: /nintendo-switch-roms/page/2
                    # 2. Ricerca: /page/2/?s=query
                    if search_key:
                        # Formato ricerca: /page/\d+/?s=...
                        match = re.search(r'/page/(\d+)/', href)
                        if match:
                            page_num = int(match.group(1))
                            page_numbers.append(page_num)
                    else:
                        # Formato homepage: /nintendo-switch-roms/page/\d+
                        match = re.search(r'/nintendo-switch-roms/page/(\d+)', href)
                        if match:
                            page_num = int(match.group(1))
                            page_numbers.append(page_num)
                    
                    # Cerca anche il link "Next" o "Further"
                    link_text = link.get_text(strip=True).lower()
                    if ('next' in link_text or 'further' in link_text) and not next_page_url:
                        # Assicurati che l'URL sia completo
                        if href.startswith('http'):
                            next_page_url = href
                        else:
                            next_page_url = f"https://nswpedia.com{href}"
                
                if page_numbers:
                    total_pages = max(page_numbers)
                    
                # Se non abbiamo trovato next_page_url ma ci sono più pagine, costruiscilo
                if not next_page_url and total_pages > page:
                    if search_key:
                        next_page_url = f"https://nswpedia.com/page/{page + 1}/?s={urllib.parse.quote(search_key)}"
                    else:
                        next_page_url = f"https://nswpedia.com/nintendo-switch-roms/page/{page + 1}/"
        except Exception as e:
            print(f"⚠️ [search_roms] Errore estrazione paginazione: {e}", file=sys.stderr)
            pass
        
        result = {
            "roms": roms,
            "total_results": len(roms) * total_pages if total_pages > 1 else len(roms),  # Stima
            "current_results": len(roms),
            "current_page": page,
            "total_pages": total_pages
        }
        
        # Aggiungi URL pagina successiva se disponibile
        if next_page_url:
            result["next_page_url"] = next_page_url
        
        return json.dumps(result)
        
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
                    break
        
        # Fallback: cerca h1 o title se non trovato in "App name"
        if not title:
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text(strip=True)
        
        if not title:
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text(strip=True)
                # Rimuovi suffissi comuni
                title = re.sub(r'\s*-\s*NSWpedia.*$', '', title, flags=re.IGNORECASE)
        
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
        download_button = None
        if btn_block:
            # Cerca il link dentro btn-block che ha href che inizia con /download/
            download_button = btn_block.find('a', href=re.compile(r'/download/'))
        
        # Leggi l'URL dal pulsante trovato
        if download_button:
            download_page_url = download_button.get('href', '')
            if download_page_url:
                # Assicurati che l'URL sia completo
                if not download_page_url.startswith('http'):
                    download_page_url = f"https://nswpedia.com{download_page_url}"
            else:
                pass
        else:
            pass
        
        download_links = []
        
        # Estrai download links solo se richiesto
        if not include_download_links:
            pass
        elif not download_page_url:
            pass
        else:
            
            # Visita la pagina di download
            # Gestisce il caso in cui la pagina fa redirect a un popup fuori dal dominio nswpedia.com
            download_soup = None
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries and download_soup is None:
                try:
                    download_response = session.get(download_page_url, headers=get_browser_headers(referer=page_url), timeout=15, allow_redirects=True)
                    download_response.raise_for_status()
                    
                    # Controlla se l'URL finale è fuori dal dominio nswpedia.com (popup)
                    final_url = download_response.url
                    parsed_final = urllib.parse.urlparse(final_url)
                    parsed_original = urllib.parse.urlparse(download_page_url)
                    
                    # Se l'URL finale è su un dominio diverso da nswpedia.com, è un popup
                    if parsed_final.netloc != parsed_original.netloc and 'nswpedia.com' not in parsed_final.netloc:
                        print(f"⚠️ [get_entry] Rilevato popup fuori dal dominio: {final_url}", file=sys.stderr)
                        print(f"   URL originale: {download_page_url}", file=sys.stderr)
                        retry_count += 1
                        if retry_count < max_retries:
                            print(f"   Riprovo (tentativo {retry_count + 1}/{max_retries})...", file=sys.stderr)
                            # Attendi un po' prima di riprovare
                            import time
                            time.sleep(1)
                            continue
                        else:
                            print(f"   ⚠️ Massimo numero di tentativi raggiunto, salto questa pagina", file=sys.stderr)
                            break
                    
                    # Se siamo ancora su nswpedia.com, verifica che la pagina contenga le tabelle di download
                    download_soup = BeautifulSoup(download_response.content, 'html.parser')
                    download_tables_check = download_soup.find_all('div', class_='table-download')
                    
                    # Se non ci sono tabelle di download, potrebbe essere una pagina popup o errore
                    if not download_tables_check:
                        print(f"⚠️ [get_entry] Pagina caricata ma nessuna tabella download trovata: {final_url}", file=sys.stderr)
                        retry_count += 1
                        if retry_count < max_retries:
                            print(f"   Riprovo (tentativo {retry_count + 1}/{max_retries})...", file=sys.stderr)
                            import time
                            time.sleep(1)
                            download_soup = None
                            continue
                        else:
                            print(f"   ⚠️ Massimo numero di tentativi raggiunto, salto questa pagina", file=sys.stderr)
                            download_soup = None
                            break
                    
                    print(f"✅ [get_entry] Pagina download caricata correttamente: {final_url} ({len(download_tables_check)} tabelle trovate)", file=sys.stderr)
                    break
                    
                except Exception as e:
                    print(f"❌ [get_entry] Errore caricamento pagina download: {e}", file=sys.stderr)
                    import traceback
                    print(f"   Traceback: {traceback.format_exc()}", file=sys.stderr)
                    retry_count += 1
                    if retry_count < max_retries:
                        import time
                        time.sleep(1)
                        continue
                    else:
                        download_soup = None
                        break
            
            if download_soup:
                # Trova tutte le tabelle di download
                download_tables = download_soup.find_all('div', class_='table-download')
            
                for table_div in download_tables:
                    try:
                        # Leggi il titolo della tabella per capire se è "Direct" o altro
                        h3 = table_div.find('h3')
                        table_title = h3.get_text(strip=True) if h3 else ""
                        
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
                            continue
                        
                        tbody = table.find('tbody')
                        if not tbody:
                            continue
                        
                        rows = tbody.find_all('tr')
                        for row in rows:
                            try:
                                cells = row.find_all('td')
                                if len(cells) < 3:
                                    continue
                                
                                # Prima cella: link con nome file
                                link_cell = cells[0]
                                link_elem = link_cell.find('a')
                                if not link_elem:
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
                                
                                # Per i link diretti, NON estrarre l'URL finale
                                # Cloudflare richiede una challenge JavaScript che richiede ~20 secondi
                                # Il WebView deve aprire la pagina intermedia per completare la challenge e ottenere il cookie cf_clearance
                                # Poi il WebView può intercettare il download quando parte
                                final_url = link_url
                                intermediate_url = link_url if is_direct else None  # URL della pagina intermedia per WebView
                                
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
                                    "delay_seconds": 20 if is_direct else None,  # Link diretti richiedono 20 secondi per challenge Cloudflare
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

