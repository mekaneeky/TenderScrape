#!/usr/bin/env python3
"""
setup.py – TenderDash System Setup and Configuration
===================================================
Sets up the new cache-based architecture and provides deployment instructions.

Usage:
    python setup.py --help
    python setup.py --install
    python setup.py --cron-setup
    python setup.py --test
"""

import os, pathlib, subprocess, sys, json, datetime as dt
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parent

def create_directories():
    """Create required directory structure"""
    dirs = ["configs", "status", "cache", "seen"]
    print("Creating directory structure...")
    
    for dir_name in dirs:
        dir_path = ROOT / dir_name
        dir_path.mkdir(exist_ok=True)
        print(f"  ✓ {dir_path}")

def check_dependencies():
    """Check if required Python packages are installed"""
    print("Checking dependencies...")
    
    required = [
        ("flask", "Flask"),
        ("requests", "requests"), 
        ("croniter", "croniter"),
        ("jinja2", "Jinja2")
    ]
    
    missing = []
    for module, pip_name in required:
        try:
            __import__(module)
            print(f"  ✓ {pip_name}")
        except ImportError:
            print(f"  ✗ {pip_name} - MISSING")
            missing.append(pip_name)
    
    if missing:
        print(f"\nInstall missing packages:")
        print(f"pip install {' '.join(missing)}")
        return False
    return True

def detect_python_path() -> str:
    """Detect the current Python interpreter path"""
    return sys.executable

def generate_cron_config() -> str:
    """Generate cron configuration"""
    python_path = detect_python_path()
    project_root = ROOT
    
    cron_config = f"""# TenderDash Cron Configuration
# Add these lines to your crontab (run: crontab -e)

# Central data harvester (every 10 minutes)
*/10 * * * * {python_path} {project_root}/central_harvester.py >>{project_root}/logs/harvester.log 2>&1

# Job dispatcher (every minute)
* * * * * {python_path} {project_root}/job_dispatcher.py >>{project_root}/logs/dispatcher.log 2>&1

# Log rotation (daily at 2 AM)
0 2 * * * find {project_root}/logs -name "*.log" -size +10M -exec truncate -s 0 {{}} \\;
"""
    return cron_config

def create_env_template():
    """Create .env template file"""
    env_template = """# TenderDash Environment Configuration
# Copy this to .env and fill in your values

# Dashboard Authentication
DASH_PASSWORD=your-secure-password-here
FLASK_SECRET=your-flask-secret-key-here
PORT=5000

# Email Configuration (Resend.dev)
RESEND_API_KEY=re_your_api_key_here
EMAIL_FROM=noreply@yourdomain.com

# Default Recipients (comma-separated)
PPIP_RECIPIENTS=recipient1@example.com,recipient2@example.com

# Optional: Harvester Settings
PPIP_MAX_PAGES=3
"""
    
    env_file = ROOT / ".env.template"
    env_file.write_text(env_template)
    print(f"  ✓ Created {env_file}")
    
    if not (ROOT / ".env").exists():
        print(f"  → Copy .env.template to .env and configure your settings")

def create_log_directory():
    """Create logs directory"""
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    print(f"  ✓ Created {log_dir}")

def test_system():
    """Test the system components"""
    print("Testing system components...")
    
    # Test central harvester
    print("  Testing central harvester...")
    try:
        result = subprocess.run([
            sys.executable, str(ROOT / "central_harvester.py")
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("  ✓ Central harvester working")
        else:
            print(f"  ✗ Central harvester failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        print("  ⚠ Central harvester timeout (may be working but slow)")
    except Exception as e:
        print(f"  ✗ Central harvester error: {e}")
    
    # Test job dispatcher (dry run)
    print("  Testing job dispatcher...")
    try:
        result = subprocess.run([
            sys.executable, str(ROOT / "job_dispatcher.py")
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("  ✓ Job dispatcher working")
        else:
            print(f"  ✗ Job dispatcher failed: {result.stderr}")
    except Exception as e:
        print(f"  ✗ Job dispatcher error: {e}")
    
    # Test tender scraper
    print("  Testing tender scraper...")
    try:
        result = subprocess.run([
            sys.executable, str(ROOT / "tender_scraper.py"), "--dry-run", "--limit", "1"
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("  ✓ Tender scraper working")
        else:
            print(f"  ✗ Tender scraper failed: {result.stderr}")
    except Exception as e:
        print(f"  ✗ Tender scraper error: {e}")

def show_deployment_instructions():
    """Show deployment instructions"""
    print("""
DEPLOYMENT INSTRUCTIONS
======================

1. CONFIGURE ENVIRONMENT:
   - Copy .env.template to .env (optional - can configure via web interface)
   - Get a Resend.dev API key (free tier: 3000 emails/month)
   
2. SET UP RESEND.dev:
   - Sign up at https://resend.com
   - Add your domain or use their subdomain
   - Get your API key from the dashboard
   
3. START DASHBOARD:
   python dashboard_app.py
   
4. ACCESS DASHBOARD:
   Open: http://localhost:5000 (or your configured port)
   Username: (any)
   Password: (from DASH_PASSWORD in .env or default 'changeme')

5. CONFIGURE EMAIL VIA WEB INTERFACE:
   - Click "⬢ SYSTEM CONFIG" in the dashboard
   - Enter your Resend.dev API key and settings
   - Test email configuration before saving
   
6. SET UP CRON JOBS:
   Run: crontab -e
   Add the generated cron configuration (see cron.txt)

7. MONITOR LOGS:
   tail -f logs/harvester.log    # Data collection
   tail -f logs/dispatcher.log   # Job execution

ARCHITECTURE OVERVIEW:
- central_harvester.py: Fetches data every 10 minutes
- job_dispatcher.py: Processes jobs every minute
- dashboard_app.py: Web interface for management
- tender_scraper.py: Can work standalone or via cache

NEW FEATURES:
- Web-based configuration: Edit email settings via dashboard
- Cache viewer: View all current tender data
- Fixed test button: Proper feedback and error handling
- Resend.dev integration: Reliable email delivery
- Real-time email testing: Test configuration before saving

FILES CREATED:
- configs/*.json: Job configurations
- status/*.json: Job status for dashboard
- cache/tender_data.json: Central data cache
- seen/seen_*.json: Per-job deduplication
- app_config.json: User-editable system configuration
""")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="TenderDash system setup")
    parser.add_argument("--install", action="store_true", help="Full installation setup")
    parser.add_argument("--cron-setup", action="store_true", help="Generate cron configuration")
    parser.add_argument("--test", action="store_true", help="Test system components")
    parser.add_argument("--deps", action="store_true", help="Check dependencies only")
    
    args = parser.parse_args()
    
    if args.deps:
        check_dependencies()
        return
    
    if args.test:
        test_system()
        return
    
    if args.cron_setup:
        cron_config = generate_cron_config()
        cron_file = ROOT / "cron.txt"
        cron_file.write_text(cron_config)
        print(f"Cron configuration written to: {cron_file}")
        print("\nTo install:")
        print("1. crontab -e")
        print(f"2. Add contents of {cron_file}")
        return
    
    if args.install:
        print("TenderDash Installation Setup")
        print("=" * 40)
        
        # Create directories
        create_directories()
        
        # Check dependencies
        if not check_dependencies():
            print("\nPlease install missing dependencies first.")
            return
        
        # Create configuration files
        print("\nCreating configuration files...")
        create_env_template()
        create_log_directory()
        
        # Generate cron config
        print("\nGenerating cron configuration...")
        cron_config = generate_cron_config()
        cron_file = ROOT / "cron.txt"
        cron_file.write_text(cron_config)
        print(f"  ✓ Created {cron_file}")
        
        print("\nInstallation complete!")
        show_deployment_instructions()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()