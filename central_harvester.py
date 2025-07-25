#!/usr/bin/env python3
"""
central_harvester.py – Single Point Data Collection
==================================================
Fetches tender data from PPIP API once and caches locally.
All jobs read from this cache instead of hitting the API directly.

Benefits:
- No rate limiting issues (single API consumer)
- Faster job execution (local reads)
- Fault isolation (network issues don't affect individual jobs)
- Respectful to tenders.go.ke servers

Setup:
Add to crontab to run every 10 minutes:
*/10 * * * * /usr/bin/python3 /path/to/central_harvester.py >>$HOME/harvester.log 2>&1
"""

import os, json, requests, datetime as dt, pathlib, logging, sys
from typing import List, Dict, Optional

# Configuration
ROOT = pathlib.Path(__file__).resolve().parent
CACHE_DIR = ROOT / "cache"
CACHE_DIR.mkdir(exist_ok=True)

CACHE_FILE = CACHE_DIR / "tender_data.json"
HARVEST_LOG = CACHE_DIR / "harvest.log"
API_URL = "https://tenders.go.ke/api/active-tenders?page={page}&perpage=200&order=desc"
MAX_PAGES = int(os.getenv("PPIP_MAX_PAGES", "3"))  # Limit to prevent overload
REQUEST_TIMEOUT = 45

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(HARVEST_LOG),
        logging.StreamHandler(sys.stdout)
    ]
)

def fetch_page(page: int) -> Optional[List[Dict]]:
    """Fetch single page from API with error handling"""
    try:
        response = requests.get(
            API_URL.format(page=page),
            headers={
                "User-Agent": "TenderMonitor/2.0 (+https://github.com/procurement-tools)",
                "Accept": "application/json, text/plain, */*",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        logging.info(f"Fetched page {page}: {len(data)} records")
        return data
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch page {page}: {e}")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON response from page {page}: {e}")
        return None

def fetch_all_data() -> List[Dict]:
    """Fetch all pages with retry logic"""
    all_data = []
    failed_pages = []
    
    for page_num in range(1, MAX_PAGES + 1):
        data = fetch_page(page_num)
        if data is not None:
            if not data:  # Empty page means we've reached the end
                logging.info(f"No more data after page {page_num - 1}")
                break
            all_data.extend(data)
        else:
            failed_pages.append(page_num)
    
    # Retry failed pages once
    for page_num in failed_pages:
        logging.info(f"Retrying failed page {page_num}")
        data = fetch_page(page_num)
        if data is not None:
            all_data.extend(data)
    
    return all_data

def load_existing_cache() -> Dict:
    """Load existing cache with error handling"""
    if not CACHE_FILE.exists():
        return {"timestamp": None, "data": [], "stats": {}}
    
    try:
        return json.loads(CACHE_FILE.read_text())
    except (json.JSONDecodeError, Exception) as e:
        logging.warning(f"Corrupted cache file, starting fresh: {e}")
        return {"timestamp": None, "data": [], "stats": {}}

def save_cache(data: List[Dict]) -> None:
    """Save data to cache with metadata - handles missing fields"""
    now = dt.datetime.now()
    
    # Calculate statistics
    stats = {
        "total_records": len(data),
        "harvest_time": now.isoformat(),
        "categories": {},
        "entities": {},
    }
    
    # Analyze data for statistics
    for record in data:
        # Try multiple field names for category
        category = record.get("category_name", record.get("category", "Unknown"))
        stats["categories"][category] = stats["categories"].get(category, 0) + 1
        
        # Handle entity name from different structures
        entity = "Unknown"
        if "pe" in record and isinstance(record["pe"], dict):
            entity = record["pe"].get("name", "Unknown")
        elif "entity" in record:
            entity = record.get("entity", "Unknown")
        
        stats["entities"][entity] = stats["entities"].get(entity, 0) + 1
    
    cache_data = {
        "timestamp": now.isoformat(),
        "data": data,
        "stats": stats,
        "version": "2.0"
    }
    
    try:
        # Atomic write (write to temp file then rename)
        temp_file = CACHE_FILE.with_suffix('.tmp')
        
        # IMPORTANT: Use UTF-8 encoding explicitly for Windows
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        
        # Rename temp file to final location
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()  # Delete existing file first on Windows
        temp_file.rename(CACHE_FILE)
        
        logging.info(f"Cache updated: {len(data)} records, {len(stats['categories'])} categories")
    except Exception as e:
        logging.error(f"Failed to save cache: {e}")
        if temp_file.exists():
            temp_file.unlink()
            
def should_harvest() -> bool:
    """Check if we need to harvest (avoid duplicate work)"""
    existing = load_existing_cache()
    if not existing.get("timestamp"):
        return True
    
    last_harvest = dt.datetime.fromisoformat(existing["timestamp"])
    time_since_harvest = dt.datetime.now() - last_harvest
    
    # Only harvest if more than 8 minutes have passed (prevents overlapping runs)
    return time_since_harvest.total_seconds() > 480

def cleanup_old_logs():
    """Keep harvest log size manageable"""
    if HARVEST_LOG.exists() and HARVEST_LOG.stat().st_size > 10 * 1024 * 1024:  # 10MB
        # Keep last 1000 lines
        lines = HARVEST_LOG.read_text().splitlines()
        if len(lines) > 1000:
            HARVEST_LOG.write_text('\n'.join(lines[-1000:]) + '\n')
            logging.info("Rotated harvest log")

def main():
    """Main harvest routine"""
    cleanup_old_logs()
    
    if not should_harvest():
        logging.info("Skipping harvest (too recent)")
        return
    
    logging.info("Starting data harvest")
    start_time = dt.datetime.now()
    
    # Fetch fresh data
    data = fetch_all_data()
    
    if not data:
        logging.error("No data retrieved - keeping existing cache")
        return
    
    # Save to cache
    save_cache(data)
    
    # Log completion
    duration = (dt.datetime.now() - start_time).total_seconds()
    logging.info(f"Harvest complete: {len(data)} records in {duration:.1f}s")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Harvest interrupted by user")
    except Exception as e:
        logging.error(f"Harvest failed: {e}", exc_info=True)