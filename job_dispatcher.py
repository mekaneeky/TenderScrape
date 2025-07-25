#!/usr/bin/env python3
"""
job_dispatcher.py – Enhanced Job Runner with Cache-Based Processing
==================================================================
Reads tender data from local cache (populated by central_harvester.py)
and dispatches filtering/email jobs based on their schedules.

Features:
- No direct API calls (reads from local cache)
- Per-job "seen" tracking for deduplication
- Concurrency protection via file locking
- Job status tracking for dashboard
- Comprehensive error handling and recovery
- Execution history and performance metrics

Setup:
Add to crontab to run every minute:
* * * * * /usr/bin/python3 /path/to/job_dispatcher.py >>$HOME/dispatcher.log 2>&1
"""

import os, json, datetime as dt, pathlib, logging, sys, time, fcntl, requests
from typing import Dict, List, Set, Optional
from croniter import croniter_match

from tender_utils import (
    get_tender_category,
    get_tender_entity, 
    is_tender_active,
    filter_active_tenders,
    format_tender_email_line,
    format_detailed_email_body,
    EmailTracker
)


# Configuration
ROOT = pathlib.Path(__file__).resolve().parent
CFG_DIR = ROOT / "configs"
STATUS_DIR = ROOT / "status"
CACHE_DIR = ROOT / "cache"
SEEN_DIR = ROOT / "seen"
CONFIG_FILE = ROOT / "app_config.json"  # User-editable config

# Ensure directories exist
for dir_path in [CFG_DIR, STATUS_DIR, CACHE_DIR, SEEN_DIR]:
    dir_path.mkdir(exist_ok=True)

CACHE_FILE = CACHE_DIR / "tender_data.json"
LOCK_FILE = ROOT / "dispatcher.lock"
HISTORY_FILE = ROOT / "execution_history.jsonl"

# Email configuration (Resend.dev) - will be loaded from config file
def load_email_config() -> Dict:
    """Load email configuration from app_config.json with fallbacks"""
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

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

class JobDispatcher:
    def __init__(self):
        self.start_time = dt.datetime.now()
        self.lock_file = None
        self.email_tracker = EmailTracker(ROOT / "email_tracking.json")  # ADD THIS LINE

    
    def acquire_lock(self) -> bool:
        """Acquire exclusive lock to prevent concurrent execution"""
        try:
            self.lock_file = open(LOCK_FILE, 'w')
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_file.write(f"PID: {os.getpid()}\nStarted: {self.start_time.isoformat()}\n")
            self.lock_file.flush()
            return True
        except (IOError, OSError):
            if self.lock_file:
                self.lock_file.close()
            return False
    
    def release_lock(self):
        """Release the execution lock"""
        if self.lock_file:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            self.lock_file.close()
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
    
    def load_cache_data(self) -> Optional[List[Dict]]:
        """Load tender data from cache - FIXED FOR WINDOWS ENCODING"""
        if not CACHE_FILE.exists():
            logging.error("No cache file found - run central_harvester.py first")
            return None
        
        try:
            # Use UTF-8 encoding explicitly
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            
            data = cache.get("data", [])
            cache_time = cache.get("timestamp")
            
            if cache_time:
                cache_dt = dt.datetime.fromisoformat(cache_time)
                age_minutes = (dt.datetime.now() - cache_dt).total_seconds() / 60
                if age_minutes > 30:
                    logging.warning(f"Cache is {age_minutes:.1f} minutes old")
            
            logging.info(f"Loaded {len(data)} records from cache")
            return data
        except (json.JSONDecodeError, Exception) as e:
            logging.error(f"Failed to load cache: {e}")
            return None
    
    def load_job_configs(self) -> List[Dict]:
        """Load all job configurations with error recovery"""
        jobs = []
        for config_file in CFG_DIR.glob("*.json"):
            try:
                job_data = json.loads(config_file.read_text())
                if self.validate_job_config(job_data):
                    jobs.append(job_data)
                else:
                    logging.warning(f"Invalid job config: {config_file.name}")
            except (json.JSONDecodeError, Exception) as e:
                logging.error(f"Corrupted job config {config_file.name}: {e}")
                # Attempt auto-repair or skip
                self.attempt_job_repair(config_file)
        
        return jobs
    
    def validate_job_config(self, job: Dict) -> bool:
        """Validate job configuration"""
        required_fields = ["id", "recipients", "schedule"]
        return all(field in job for field in required_fields) and job["recipients"]
    
    def attempt_job_repair(self, config_file: pathlib.Path):
        """Try to repair corrupted job config"""
        try:
            # Try to extract job ID from filename
            job_id = config_file.stem
            repair_data = {
                "id": job_id,
                "classes": [],
                "recipients": ["repair@needed.com"],
                "schedule": "*/30 * * * *",
                "interval": "30min"
            }
            config_file.write_text(json.dumps(repair_data, indent=2))
            logging.info(f"Auto-repaired job config: {config_file.name}")
        except Exception:
            logging.error(f"Could not repair {config_file.name}, removing")
            config_file.unlink()
    
    def is_job_due(self, job: Dict) -> bool:
        """Check if job should run now"""
        schedule = job.get("schedule", "*/30 * * * *")
        now = dt.datetime.now().replace(second=0, microsecond=0)
        
        try:
            return croniter_match(schedule, now)
        except Exception as e:
            logging.error(f"Invalid schedule for job {job['id']}: {e}")
            return False
    
    def load_job_seen_cache(self, job_id: str) -> Set[str]:
        """Load job-specific seen tender cache"""
        seen_file = SEEN_DIR / f"seen_{job_id}.json"
        if not seen_file.exists():
            return set()
        
        try:
            return set(json.loads(seen_file.read_text()))
        except (json.JSONDecodeError, Exception):
            logging.warning(f"Corrupted seen cache for job {job_id}, starting fresh")
            return set()
    
    def save_job_seen_cache(self, job_id: str, seen_ids: Set[str]):
        """Save job-specific seen tender cache"""
        seen_file = SEEN_DIR / f"seen_{job_id}.json"
        try:
            seen_file.write_text(json.dumps(sorted(seen_ids), indent=2))
        except Exception as e:
            logging.error(f"Failed to save seen cache for job {job_id}: {e}")
    
    def filter_data_for_job(self, data: List[Dict], job: Dict, seen_ids: Set[str]) -> tuple[List[Dict], bool]:
        """Filter tender data for specific job requirements - returns (tenders, is_new_recipient)"""
        allowed_classes = set(job.get("classes", []))
        fresh_tenders = []
        all_active_tenders = []
        
        # Check if any recipients are new
        recipients = job.get("recipients", [])
        has_new_recipients = any(self.email_tracker.is_new_recipient(email) for email in recipients)
        
        # Get config for new recipient behavior
        config = load_app_config()
        send_all_active_to_new = config.get("new_recipient_mode", "new_only") == "all_active"
        
        for tender in data:
            tender_id = str(tender.get("id", ""))
            if not tender_id:  # Skip if no ID
                continue
            
            # Get category using proper extraction
            category = get_tender_category(tender)
            
            # Apply class filter (empty classes means accept all)
            if allowed_classes:
                # Check if category matches any allowed class
                category_matches = any(
                    allowed_class.lower() in category.lower() 
                    for allowed_class in allowed_classes
                )
                if not category_matches:
                    continue
            
            # Check if tender is active
            if is_tender_active(tender):
                all_active_tenders.append(tender)
                
                # Add to fresh if not seen before
                if tender_id not in seen_ids:
                    fresh_tenders.append(tender)
        
        # If we have new recipients and config says to send all active
        if has_new_recipients and send_all_active_to_new:
            # Return all active tenders that haven't been sent to ANY of the new recipients
            unsent_to_new = []
            for tender in all_active_tenders:
                tender_id = str(tender.get("id", ""))
                # Check if any new recipient hasn't received this tender
                for email in recipients:
                    if self.email_tracker.is_new_recipient(email):
                        if tender_id not in self.email_tracker.get_sent_tenders(email):
                            unsent_to_new.append(tender)
                            break
            return unsent_to_new, True
        
        return fresh_tenders, False


    
    def format_email_body(self, tenders: List[Dict], job_id: str, is_catch_up: bool = False) -> str:
        """Format tender data for email using the new utilities"""
        config = load_app_config()
        show_expired = config.get("show_expired_in_emails", False)
        
        if is_catch_up:
            header = f"Catch-up email for new recipient(s) - Job {job_id}"
        else:
            header = ""
        
        body = format_detailed_email_body(tenders, job_id, show_expired)
        
        if header:
            body = f"{header}\n{'=' * len(header)}\n\n{body}"
        
        return body

    
    def send_email(self, job: Dict, tenders: List[Dict], is_catch_up: bool = False) -> bool:
        """Send email notification via Resend.dev with tracking"""
        # Load email configuration
        email_config = load_email_config()
        
        if not email_config["api_key"]:
            logging.warning(f"Resend API key not configured for job {job['id']}")
            return False
        
        try:
            subject_suffix = " (catch-up)" if is_catch_up else ""
            subject = f"{email_config['subject_prefix']} {len(tenders)} new tender(s) - {dt.date.today()}{subject_suffix}"
            body = self.format_email_body(tenders, job["id"], is_catch_up)
            recipients = job["recipients"]
            
            # Resend API payload
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
                # Track which tenders were sent to which recipients
                tender_ids = [str(t.get("id", "")) for t in tenders if t.get("id")]
                for email in recipients:
                    self.email_tracker.mark_tenders_sent(email, tender_ids)
                self.email_tracker.save()
                
                logging.info(f"Email sent for job {job['id']}: {len(tenders)} tenders to {len(recipients)} recipients")
                return True
            else:
                logging.error(f"Resend API failed for job {job['id']}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"Failed to send email for job {job['id']}: {e}")
            return False

    
    def update_job_status(self, job_id: str, status: str, **kwargs):
        """Update job status for dashboard"""
        status_file = STATUS_DIR / f"{job_id}.json"
        try:
            # Load existing status
            if status_file.exists():
                current_status = json.loads(status_file.read_text())
            else:
                current_status = {}
            
            # Update status
            current_status.update({
                "status": status,
                "last_update": dt.datetime.now().isoformat(),
                **kwargs
            })
            
            status_file.write_text(json.dumps(current_status, indent=2))
        except Exception as e:
            logging.error(f"Failed to update status for job {job_id}: {e}")
    
    def log_execution_history(self, job_id: str, success: bool, tenders_found: int, duration: float, error: str = None):
        """Log job execution to history file"""
        try:
            history_entry = {
                "timestamp": dt.datetime.now().isoformat(),
                "job_id": job_id,
                "success": success,
                "tenders_found": tenders_found,
                "duration_seconds": round(duration, 2),
                "error": error
            }
            
            with open(HISTORY_FILE, 'a') as f:
                f.write(json.dumps(history_entry) + '\n')
        except Exception as e:
            logging.error(f"Failed to log execution history: {e}")
    
    def process_job(self, job: Dict, all_data: List[Dict]) -> bool:
        """Process a single job with email tracking"""
        job_id = job["id"]
        start_time = time.time()
        
        try:
            self.update_job_status(job_id, "running", last_run_start=dt.datetime.now().isoformat())
            
            # Load job's seen cache
            seen_ids = self.load_job_seen_cache(job_id)
            
            # Filter data for this job (now returns tuple)
            fresh_tenders, is_catch_up = self.filter_data_for_job(all_data, job, seen_ids)
            
            # Send email if new tenders found
            email_sent = False
            if fresh_tenders:
                email_sent = self.send_email(job, fresh_tenders, is_catch_up)
            
            # Update seen cache with all current tender IDs (not just new ones)
            all_current_ids = {str(t["id"]) for t in all_data if t.get("id")}
            self.save_job_seen_cache(job_id, all_current_ids)
            
            # Update status
            duration = time.time() - start_time
            self.update_job_status(
                job_id, "idle",
                last_run_end=dt.datetime.now().isoformat(),
                last_run_duration=round(duration, 2),
                last_run_tenders=len(fresh_tenders),
                last_run_success=True,
                last_run_was_catchup=is_catch_up
            )
            
            # Log to history
            self.log_execution_history(job_id, True, len(fresh_tenders), duration)
            
            if fresh_tenders:
                action = "catch-up" if is_catch_up else "regular"
                logging.info(f"Job {job_id} completed ({action}): {len(fresh_tenders)} tenders, email {'sent' if email_sent else 'failed'}")
            else:
                logging.info(f"Job {job_id} completed: no new tenders")
            
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            
            self.update_job_status(
                job_id, "error",
                last_run_end=dt.datetime.now().isoformat(),
                last_run_error=error_msg,
                last_run_success=False
            )
            
            self.log_execution_history(job_id, False, 0, duration, error_msg)
            logging.error(f"Job {job_id} failed: {error_msg}")
            return False

    
    def cleanup_old_files(self):
        """Clean up old files to prevent disk bloat"""
        try:
            # Existing cleanup code...
            
            # Cleanup old email tracking entries (optional - remove recipients not in any job)
            if hasattr(self, 'email_tracker'):
                active_recipients = set()
                for job in self.load_job_configs():
                    active_recipients.update(job.get("recipients", []))
                
                # Remove tracking for emails no longer in use
                current_recipients = set(self.email_tracker.data.get("recipients", {}).keys())
                orphaned = current_recipients - active_recipients
                
                if orphaned:
                    for email in orphaned:
                        del self.email_tracker.data["recipients"][email]
                        logging.info(f"Removed tracking for orphaned email: {email}")
                    self.email_tracker.save()
                    
        except Exception as e:
            logging.error(f"Cleanup failed: {e}")
    
    def run(self):
        """Main dispatcher routine"""
        # Acquire lock to prevent concurrent execution
        if not self.acquire_lock():
            logging.info("Another dispatcher instance is running, exiting")
            return
        
        try:
            # Load cache data
            all_data = self.load_cache_data()
            if not all_data:
                logging.error("No data available, skipping job processing")
                return
            
            # Load job configurations
            jobs = self.load_job_configs()
            if not jobs:
                logging.info("No valid jobs configured")
                return
            
            # Process due jobs
            due_jobs = [job for job in jobs if self.is_job_due(job)]
            
            if not due_jobs:
                logging.info(f"No jobs due at {dt.datetime.now().strftime('%H:%M')}")
                return
            
            logging.info(f"Processing {len(due_jobs)} due job(s)")
            
            success_count = 0
            for job in due_jobs:
                if self.process_job(job, all_data):
                    success_count += 1
            
            logging.info(f"Batch complete: {success_count}/{len(due_jobs)} jobs successful")
            
            # Periodic cleanup
            if dt.datetime.now().minute % 10 == 0:  # Every 10 minutes
                self.cleanup_old_files()
                
        finally:
            self.release_lock()

    def get_email_tracking_stats(self) -> Dict:
        """Get email tracking statistics for dashboard display"""
        return self.email_tracker.get_stats()


def main():
    dispatcher = JobDispatcher()
    try:
        dispatcher.run()
    except KeyboardInterrupt:
        logging.info("Dispatcher interrupted by user")
    except Exception as e:
        logging.error(f"Dispatcher failed: {e}", exc_info=True)
    finally:
        dispatcher.release_lock()

if __name__ == "__main__":
    main()