#!/usr/bin/env python3
"""
Kenyan PPIP Tender Monitor (Cache-Aware Version)
===============================================
Can operate in two modes:
1. CACHE MODE: Reads from local cache (populated by central_harvester.py) - FAST
2. DIRECT MODE: Fetches directly from API - for manual testing/standalone use

Cache mode is used by job_dispatcher.py for production efficiency.
Direct mode is available for testing and standalone operation.

Usage examples
--------------
# Cache mode (default if cache exists and is fresh)
python tender_scraper.py --classes Works

# Force direct API mode
python tender_scraper.py --classes Works --direct

# Cache mode with specific cache file
python tender_scraper.py --classes Works --cache-file /path/to/cache.json
"""

from __future__ import annotations
import os, json, datetime, requests, argparse, time, pathlib
from typing import List, Dict, Set, Optional

from tender_utils import (
    get_tender_category,
    filter_active_tenders,
    format_tender_email_line,
    format_detailed_email_body
)


###############################################################################
# CONFIG
###############################################################################
ROOT = pathlib.Path(__file__).resolve().parent
CACHE_DIR = ROOT / "cache"
DEFAULT_CACHE_FILE = CACHE_DIR / "tender_data.json"
CONFIG_FILE = ROOT / "app_config.json"

API_URL = "https://tenders.go.ke/api/active-tenders?page={page}&perpage=200&order=desc"
CACHE_FILE = os.getenv("PPIP_CACHE", "ppip_seen.json")

# Email configuration (load from config file with fallbacks)
def load_email_config() -> Dict:
    """Load email configuration from app_config.json with fallbacks to environment"""
    default_config = {
        "api_key": os.getenv("RESEND_API_KEY", ""),
        "from_email": os.getenv("EMAIL_FROM", "noreply@yourdomain.com"),
        "subject_prefix": os.getenv("EMAIL_SUBJECT_PREFIX", "[TenderDash]"),
    }
    
    if not CONFIG_FILE.exists():
        return default_config
    
    try:
        user_config = json.loads(CONFIG_FILE.read_text())
        return {
            "api_key": user_config.get("resend_api_key", default_config["api_key"]),
            "from_email": user_config.get("email_from", default_config["from_email"]),
            "subject_prefix": user_config.get("email_subject_prefix", default_config["subject_prefix"]),
        }
    except Exception:
        return default_config

RECIPIENTS = os.getenv("PPIP_RECIPIENTS", "").split(",") if os.getenv("PPIP_RECIPIENTS") else []

# Rate limiting for direct API mode
RATE_LIMIT_DELAY = 2.0  # seconds between requests
MAX_RETRIES = 3

###############################################################################
# CACHE OPERATIONS
###############################################################################

def load_from_cache(cache_file: pathlib.Path = DEFAULT_CACHE_FILE) -> Optional[List[Dict]]:
    """Load tender data from cache file - FIXED FOR WINDOWS ENCODING"""
    if not cache_file.exists():
        return None
    
    try:
        # Use UTF-8 encoding explicitly
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        data = cache_data.get("data", [])
        timestamp = cache_data.get("timestamp")
        
        if timestamp:
            cache_time = datetime.datetime.fromisoformat(timestamp)
            age_minutes = (datetime.datetime.now() - cache_time).total_seconds() / 60
            print(f"Using cache data from {age_minutes:.1f} minutes ago ({len(data)} records)")
            
            # Warn if cache is stale
            if age_minutes > 30:
                print(f"WARNING: Cache is {age_minutes:.1f} minutes old - consider running central_harvester.py")
        
        return data
    except (json.JSONDecodeError, Exception) as e:
        print(f"Cache read error: {e}")
        return None

def is_cache_fresh(cache_file: pathlib.Path = DEFAULT_CACHE_FILE, max_age_minutes: int = 20) -> bool:
    """Check if cache is fresh enough for normal use - FIXED FOR WINDOWS ENCODING"""
    if not cache_file.exists():
        return False
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        timestamp = cache_data.get("timestamp")
        if not timestamp:
            return False
        
        cache_time = datetime.datetime.fromisoformat(timestamp)
        age_minutes = (datetime.datetime.now() - cache_time).total_seconds() / 60
        return age_minutes <= max_age_minutes
    except Exception:
        return False

###############################################################################
# DIRECT API OPERATIONS (with rate limiting)
###############################################################################

def fetch_page_with_retry(page: int, retry_count: int = 0) -> Optional[List[Dict]]:
    """Fetch single page with retry logic and rate limiting"""
    if retry_count > 0:
        time.sleep(RATE_LIMIT_DELAY * (2 ** retry_count))  # Exponential backoff
    
    try:
        print(f"Fetching page {page} (attempt {retry_count + 1})")
        
        r = requests.get(
            API_URL.format(page=page),
            headers={
                "User-Agent": "TenderMonitor/2.0 (+https://github.com/procurement-tools)",
                "Accept": "application/json, text/plain, */*",
            },
            timeout=45,
        )
        r.raise_for_status()
        
        data = r.json().get("data", [])
        print(f"Page {page}: {len(data)} records")
        
        # Rate limiting delay between requests
        if page > 1:
            time.sleep(RATE_LIMIT_DELAY)
        
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"Request failed for page {page}: {e}")
        if retry_count < MAX_RETRIES:
            return fetch_page_with_retry(page, retry_count + 1)
        return None
    except json.JSONDecodeError as e:
        print(f"Invalid JSON from page {page}: {e}")
        return None

def fetch_active_tenders_direct(pages: int = 1) -> List[Dict]:
    """Fetch from API directly with rate limiting and error handling"""
    print(f"Fetching data directly from API ({pages} pages)")
    rows: List[Dict] = []
    
    for p in range(1, pages + 1):
        chunk = fetch_page_with_retry(p)
        if chunk is None:
            print(f"Skipping page {p} due to errors")
            continue
        if not chunk:  # Empty page
            print(f"No more data after page {p-1}")
            break
        rows.extend(chunk)
    
    print(f"Fetched {len(rows)} total records from API")
    return rows

###############################################################################
# DATA PROCESSING
###############################################################################

def load_seen() -> Set[str]:
    """Load seen tender IDs"""
    if not os.path.exists(CACHE_FILE):
        return set()
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            return set(json.load(fh))
    except (json.JSONDecodeError, Exception):
        print(f"Warning: Corrupted seen cache, starting fresh")
        return set()

def save_seen(ids: Set[str]):
    """Save seen tender IDs with error handling"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(sorted(ids), fh, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Could not save seen cache: {e}")

def filter_rows(rows: List[Dict], seen: Set[str], allowed: Set[str], active_only: bool = True) -> List[Dict]:
    """Filter tender rows based on seen cache, allowed classes, and active status"""
    # First filter by active status if requested
    if active_only:
        rows = filter_active_tenders(rows)
    
    fresh = []
    for row in rows:
        rid = str(row.get("id", ""))
        if not rid:  # Skip if no ID
            continue
        
        # Skip if already seen
        if rid in seen:
            continue
        
        # Get category using proper extraction
        category = get_tender_category(row)
        
        # Apply class filter if specified
        if allowed:
            # Check if category matches any allowed class (case-insensitive partial match)
            category_matches = any(
                allowed_class.lower() in category.lower() 
                for allowed_class in allowed
            )
            if not category_matches:
                continue
        
        fresh.append(row)
    
    return fresh



def email_body(rows: List[Dict], show_details: bool = True) -> str:
    """Format tender data for email using enhanced formatting"""
    if show_details:
        return format_detailed_email_body(rows, show_expired=False)
    else:
        # Simple format for backward compatibility
        if not rows:
            return "No new tenders found."
        
        lines = [f"Found {len(rows)} new tender(s):", ""]
        for r in rows:
            lines.append(format_tender_email_line(r))
        return "\n".join(lines)


def send_mail(subject: str, body: str, recipients: List[str], dry: bool):
    """Send email via Resend.dev with error handling"""
    if dry:
        print(f"\n=== DRY-RUN EMAIL ===")
        print(f"To: {', '.join(recipients)}")
        print(f"Subject: {subject}")
        print(f"Body:\n{body}\n")
        return
    
    # Load email config (supports both env vars and config file)
    email_config = load_email_config()
    
    if not email_config["api_key"]:
        print("Email not configured (missing RESEND_API_KEY)")
        return
    
    if not recipients:
        print("No recipients specified")
        return
    
    try:
        payload = {
            "from": email_config["from_email"],
            "to": recipients,
            "subject": subject,
            "text": body
        }
        
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {email_config['api_key']}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"Email sent to {len(recipients)} recipient(s)")
        else:
            print(f"Email failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Email failed: {e}")

###############################################################################
# MAIN LOGIC
###############################################################################

def determine_data_source(args) -> tuple[List[Dict], bool]:
    """Determine whether to use cache or direct API based on args and cache state"""
    
    # Force direct mode if requested
    if args.direct:
        print("Using direct API mode (forced)")
        return fetch_active_tenders_direct(args.limit), True
    
    # Force cache mode if cache file specified
    if args.cache_file:
        cache_path = pathlib.Path(args.cache_file)
        data = load_from_cache(cache_path)
        if data is not None:
            print(f"Using specified cache file: {cache_path}")
            return data, False
        else:
            print(f"Could not load cache file {cache_path}, falling back to API")
            return fetch_active_tenders_direct(args.limit), True
    
    # Auto-detect: use cache if fresh, otherwise API
    if is_cache_fresh():
        data = load_from_cache()
        if data is not None:
            print("Using fresh cache data")
            return data, False
    
    print("Cache not available or stale, using direct API")
    return fetch_active_tenders_direct(args.limit), True

def main():
    parser = argparse.ArgumentParser(description="PPIP tender monitor")
    parser.add_argument("--classes", action="append", help="Comma-separated class list or repeat flag")
    parser.add_argument("--limit", type=int, default=1, help="API pages to fetch (direct mode only)")
    parser.add_argument("--dry-run", action="store_true", help="Don't send email")
    parser.add_argument("--direct", action="store_true", help="Force direct API mode (ignore cache)")
    parser.add_argument("--cache-file", help="Use specific cache file")
    parser.add_argument("--recipients", help="Comma-separated email list (overrides env)")
    parser.add_argument("--active-only", action="store_true", default=True, 
                    help="Filter to show only active (non-expired) tenders")
    parser.add_argument("--show-all", action="store_true", 
                        help="Show all tenders including expired ones")
    parser.add_argument("--detailed-email", action="store_true", default=True,
                        help="Use detailed email format with category grouping")

    args = parser.parse_args()

    # Build allowed classes set
    allowed: Set[str] = set()
    if args.classes:
        allowed = {
            c.strip() for flag in args.classes for c in flag.split(",") if c.strip()
        }
    else:
        env_classes = os.getenv("PPIP_CLASSES", "")
        if env_classes:
            allowed = {c.strip() for c in env_classes.split(",") if c.strip()}

    # Determine recipients
    recipients = RECIPIENTS
    if args.recipients:
        recipients = [r.strip() for r in args.recipients.split(",") if r.strip()]

    print(f"Target classes: {', '.join(sorted(allowed)) if allowed else 'ALL'}")
    print(f"Recipients: {len(recipients)} configured")

    # Get data (cache or direct)
    start_time = time.time()
    rows, used_api = determine_data_source(args)
    
    if not rows:
        print("No data available")
        return

    fetch_time = time.time() - start_time
    print(f"Data loaded in {fetch_time:.1f}s")

    # Process data
    seen = load_seen()
    active_only = not args.show_all  # Show all overrides active-only
    fresh = filter_rows(rows, seen, allowed, active_only=active_only)


    if fresh:
        email_config = load_email_config()
        body = email_body(fresh, show_details=args.detailed_email)
        subject = f"{email_config['subject_prefix']} {len(fresh)} new tender(s) – {datetime.date.today()}"
        send_mail(subject, body, recipients, args.dry_run)
        
        # Update seen cache with all current IDs (prevents re-notifications)
        all_ids = {str(r["id"]) for r in rows if r.get("id")}
        save_seen(all_ids)
        
        filter_desc = f"{'active ' if active_only else ''}tenders"
        if allowed:
            filter_desc += f" in {','.join(sorted(allowed))}"
        print(f"Processed {len(fresh)} new {filter_desc}")
    else:
        when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        filter_desc = ','.join(sorted(allowed)) if allowed else 'all categories'
        status = 'active' if active_only else 'all'
        print(f"No new {status} tenders ({filter_desc}) – {when}")


    # Performance info
    total_time = time.time() - start_time
    print(f"Total execution time: {total_time:.1f}s ({'API' if used_api else 'cache'})")

    if args.dry_run and rows:
        # Show statistics
        total = len(rows)
        active = sum(1 for r in rows if is_tender_active(r))
        expired = total - active
        
        print(f"\nCache Statistics:")
        print(f"  Total tenders: {total}")
        print(f"  Active: {active}")
        print(f"  Expired: {expired}")
        
        if allowed:
            # Show category breakdown
            from collections import Counter
            categories = Counter(get_tender_category(r) for r in rows)
            print(f"\nCategory Distribution:")
            for cat, count in categories.most_common(10):
                print(f"  {cat}: {count}")

if __name__ == "__main__":
    main()