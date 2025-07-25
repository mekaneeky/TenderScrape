#!/usr/bin/env python3
"""
TenderDash – SOLAR BRUTALIST Revolution Dashboard
===============================================
Information is power. Design is warfare. Aesthetics are ideology.
This is the visual language of insurrection through scraping.
"""
from __future__ import annotations

import json, os, uuid, subprocess, pathlib, datetime as dt
from functools import wraps
from typing import Dict, List, Optional

from flask import (
    Flask, render_template, request, redirect, url_for, Response, flash
)
from jinja2 import DictLoader
import sys
import traceback

from tender_utils import (
    get_tender_category, 
    get_tender_entity,
    is_tender_active,
    format_tender_summary,
    filter_active_tenders
)


# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parent
CFG_DIR = ROOT / "configs"
STATUS_DIR = ROOT / "status"
CACHE_DIR = ROOT / "cache"
SEEN_DIR = ROOT / "seen"  # ADD THIS LINE
CONFIG_FILE = ROOT / "app_config.json"  # User-editable config
CFG_DIR.mkdir(exist_ok=True)
STATUS_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)
SEEN_DIR.mkdir(exist_ok=True)  # ADD THIS LINE

PASSWORD = os.getenv("DASH_PASSWORD", "changeme")
PORT = int(os.getenv("PORT", 5000))

# ---------------------------------------------------------------------------
# Interval to Cron Mapping (NO CUSTOM OPTIONS - KEEP IT SIMPLE)
# ---------------------------------------------------------------------------
INTERVALS = {
    "15min": ("Every 15 minutes", "*/15 * * * *"),
    "30min": ("Every 30 minutes", "*/30 * * * *"), 
    "1hour": ("Every hour", "0 * * * *"),
    "2hour": ("Every 2 hours", "0 */2 * * *"),
    "6hour": ("Every 6 hours", "0 */6 * * *"),
    "daily": ("Daily at 9 AM", "0 9 * * *"),
}

# ---------------------------------------------------------------------------
# Flask setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "super-secret-key")

# ---------------------------------------------------------------------------
# SOLAR BRUTALIST Template definitions
# ---------------------------------------------------------------------------
TEMPLATES = {
    "base.html": """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>⬢ TENDERDASH ∴ SCRAPING SWARM</title>
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Oswald:wght@400;600;700&display=swap');
        
        :root {
            --void: #000000;
            --amber-core: #FFB000;
            --amber-burn: #FF8C00;
            --amber-dim: #FFA500;
            --neural-gray: #1a1a1a;
            --data-green: #00FF41;
            --warning-red: #FF073A;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            background: linear-gradient(135deg, var(--void) 0%, #0a0a0a 100%);
            color: var(--amber-core);
            font-family: 'JetBrains Mono', monospace;
            min-height: 100vh;
            overflow-x: hidden;
        }
        
        .swarm-container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
            position: relative;
        }
        
        .neural-header {
            text-align: center;
            margin-bottom: 3rem;
            position: relative;
        }
        
        .neural-header::before {
            content: "⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢⬢";
            position: absolute;
            top: -20px;
            left: 50%;
            transform: translateX(-50%);
            color: var(--amber-dim);
            opacity: 0.3;
            font-size: 0.8rem;
            letter-spacing: 4px;
        }
        
        .neural-header h1 {
            font-family: 'Oswald', sans-serif;
            font-size: 4rem;
            font-weight: 800;
            letter-spacing: 8px;
            background: linear-gradient(45deg, var(--amber-burn), var(--amber-core), var(--amber-dim));
            background-size: 400% 400%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: solar-pulse 3s ease-in-out infinite;
            text-shadow: 0 0 30px var(--amber-core);
        }
        
        @keyframes solar-pulse {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        
        .subtitle {
            font-size: 1.2rem;
            color: var(--amber-dim);
            margin-top: 1rem;
            letter-spacing: 3px;
        }
        
        .flash-swarm {
            background: var(--neural-gray);
            border: 2px solid var(--amber-core);
            border-radius: 0;
            padding: 1rem;
            margin: 2rem 0;
            box-shadow: 0 0 20px var(--amber-core);
            font-weight: bold;
        }
        
        .action-matrix {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 2rem;
            margin: 3rem 0;
            align-items: center;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, var(--amber-burn), var(--amber-core));
            border: none;
            color: var(--void);
            padding: 1rem 2rem;
            font-family: 'Oswald', sans-serif;
            font-size: 1.2rem;
            font-weight: 700;
            letter-spacing: 2px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(255, 176, 0, 0.3);
            text-transform: uppercase;
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(255, 176, 0, 0.5);
            background: linear-gradient(135deg, var(--amber-core), var(--amber-burn));
        }
        
        .scraping-grid {
            background: var(--neural-gray);
            border: 2px solid var(--amber-dim);
            width: 100%;
            border-collapse: collapse;
            font-family: 'JetBrains Mono', monospace;
            box-shadow: 0 0 30px rgba(255, 176, 0, 0.2);
        }
        
        .scraping-grid thead {
            background: linear-gradient(90deg, var(--amber-burn), var(--amber-core));
            color: var(--void);
        }
        
        .scraping-grid th {
            padding: 1.5rem 1rem;
            font-family: 'Oswald', sans-serif;
            font-weight: 700;
            letter-spacing: 2px;
            text-transform: uppercase;
            border: 1px solid var(--amber-core);
        }
        
        .scraping-grid td {
            padding: 1rem;
            border: 1px solid var(--amber-dim);
            vertical-align: middle;
        }
        
        .scraping-grid tbody tr:nth-child(even) {
            background: rgba(255, 176, 0, 0.05);
        }
        
        .scraping-grid tbody tr:hover {
            background: rgba(255, 176, 0, 0.1);
            box-shadow: inset 0 0 10px rgba(255, 176, 0, 0.3);
        }
        
        .status-badge {
            padding: 0.5rem 1rem;
            border-radius: 0;
            font-weight: bold;
            font-size: 0.8rem;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        
        .status-active { background: var(--data-green); color: var(--void); }
        .status-idle { background: var(--amber-dim); color: var(--void); }
        .status-running { background: var(--amber-burn); color: var(--void); animation: pulse 1s infinite; }
        .status-error { background: var(--warning-red); color: white; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        
        .countdown-timer {
            font-weight: bold;
            color: var(--amber-core);
            font-family: 'JetBrains Mono', monospace;
        }
        
        .btn-action {
            background: var(--neural-gray);
            border: 1px solid var(--amber-dim);
            color: var(--amber-core);
            padding: 0.5rem 1rem;
            margin: 0 0.25rem;
            font-family: 'JetBrains Mono', monospace;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .btn-action:hover {
            background: var(--amber-core);
            color: var(--void);
            transform: scale(1.05);
        }
        
        .form-brutalist {
            background: var(--neural-gray);
            border: 2px solid var(--amber-core);
            padding: 2rem;
            margin: 2rem 0;
            box-shadow: 0 0 20px rgba(255, 176, 0, 0.2);
        }
        
        .form-brutalist label {
            display: block;
            color: var(--amber-core);
            font-weight: bold;
            margin-bottom: 0.5rem;
            font-family: 'Oswald', sans-serif;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        
        .form-brutalist input, .form-brutalist select {
            width: 100%;
            background: var(--void);
            border: 1px solid var(--amber-dim);
            color: var(--amber-core);
            padding: 1rem;
            margin-bottom: 1.5rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 1rem;
        }
        
        .form-brutalist input:focus, .form-brutalist select:focus {
            outline: none;
            border-color: var(--amber-core);
            box-shadow: 0 0 10px rgba(255, 176, 0, 0.5);
        }
        
        .empty-state {
            text-align: center;
            color: var(--amber-dim);
            font-style: italic;
            padding: 2rem;
        }
        
        .error-flash {
            background: var(--warning-red);
            color: white;
            padding: 1rem;
            margin: 1rem 0;
            border: 2px solid #FF073A;
        }
    </style>
</head>
<body>
    <div class="swarm-container">
        <div class="neural-header">
            <h1>TENDERDASH</h1>
            <div class="subtitle">∴ SCRAPING SWARM ∴ PROCUREMENT SCRAPING ∴</div>
        </div>
        
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for m in messages %}
                    <div class="flash-swarm">⬢ {{ m }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% block body %}{% endblock %}
    </div>
</body>
</html>""",##Base over

    "index.html": """{% extends 'base.html' %}
{% block body %}
<div class="action-matrix">
    <div style="display: flex; gap: 1rem; align-items: center;">
        <button class="btn-action" onclick="location.href='{{ url_for('cache_view') }}'">⬢ VIEW CACHE</button>
        <button class="btn-action" onclick="location.href='{{ url_for('config_page') }}'">⬢ SYSTEM CONFIG</button>
        <button class="btn-action" 
                onclick="forceHarvest()" 
                id="harvest-btn"
                style="background: var(--amber-burn); color: var(--void);">
            ⚡ FORCE HARVEST
        </button>
        <span id="harvest-status" style="color: var(--amber-dim); font-size: 0.9rem; margin-left: 1rem;"></span>
    </div>
    <button class="btn-primary" onclick="location.href='{{ url_for('new_job') }}'">⬢ INITIATE NEW SCRAPING</button>
</div>

<table class="scraping-grid">
    <thead>
        <tr>
            <th>∴ ID</th>
            <th>∴ TARGET CLASSES</th>
            <th>∴ RECIPIENTS</th>
            <th>∴ FREQUENCY</th>
            <th>∴ STATUS</th>
            <th>∴ NEXT SCAN</th>
            <th>∴ ACTIONS</th>
        </tr>
    </thead>
    <tbody hx-get="{{ url_for('jobs_partial') }}" hx-trigger="load, every 10s" hx-swap="innerHTML"></tbody>
</table>

<script>
function forceHarvest() {
    const btn = document.getElementById('harvest-btn');
    const status = document.getElementById('harvest-status');
    
    // Disable button and show loading state
    btn.disabled = true;
    btn.textContent = '⟳ HARVESTING...';
    btn.style.animation = 'pulse 1s infinite';
    status.textContent = 'Fetching data from tenders.go.ke...';
    
    fetch('{{ url_for("force_harvest") }}', {
        method: 'POST',
        credentials: 'same-origin'
    })
    .then(response => response.text())
    .then(result => {
        // Show result in alert
        alert(result);
        
        // Reset button
        btn.disabled = false;
        btn.textContent = '⚡ FORCE HARVEST';
        btn.style.animation = '';
        
        // Update status
        if (result.includes('SUCCESSFUL')) {
            status.textContent = '✓ Harvest complete';
            // Reload the page after 2 seconds to show new data
            setTimeout(() => location.reload(), 2000);
        } else {
            status.textContent = '✗ Harvest failed';
        }
    })
    .catch(error => {
        alert('Harvest Error:\\n\\n' + error.message);
        btn.disabled = false;
        btn.textContent = '⚡ FORCE HARVEST';
        btn.style.animation = '';
        status.textContent = '✗ Error occurred';
    });
}

// Check harvest status on page load
fetch('{{ url_for("harvest_status") }}')
    .then(response => response.json())
    .then(data => {
        const status = document.getElementById('harvest-status');
        if (data.harvesting) {
            status.textContent = `⟳ Harvest in progress (${data.harvest_duration})`;
        } else if (data.status === 'available') {
            status.textContent = `Cache: ${data.records} records, ${data.age}`;
        } else if (data.status === 'missing') {
            status.textContent = '⚠ No cache data - run harvest';
        }
    })
    .catch(() => {});
</script>
{% endblock %}""", ##index over

    "rows.html": """{% for j in jobs %}
<tr id="row-{{j.id}}">
    <td><strong>{{j.id[:8]}}</strong></td>
    <td>{{ j.classes_display }}</td>
    <td>{{ ", ".join(j.recipients[:2]) }}{% if j.recipients|length > 2 %} +{{j.recipients|length - 2}} more{% endif %}</td>
    <td>{{ j.interval_display }}</td>
    <td><span class="status-badge status-{{ j.status }}">{{ j.status_display }}</span></td>
    <td><span class="countdown-timer">{{ j.next_run_display }}</span></td>
    <td>
        <button class="btn-action" onclick="testJob('{{j.id}}')">⚡ TEST</button>
        <button class="btn-action" onclick="location.href='{{ url_for('edit_job', jid=j.id) }}'">⚙ EDIT</button>
        <button class="btn-action" hx-delete="{{ url_for('del_job', jid=j.id) }}" hx-confirm="Terminate this scraping operation?" hx-target="#row-{{j.id}}" hx-swap="outerHTML">⬢ DELETE</button>
    </td>
</tr>
{% endfor %}
{% if not jobs %}
<tr><td colspan="7" class="empty-state">⬢ NO ACTIVE SCRAPING OPERATIONS ⬢<br/>The swarm awaits your command...</td></tr>
{% endif %}

<script>
function testJob(jobId) {
    // Open test results in a new window
    window.open('{{ url_for("run_job", jid="PLACEHOLDER") }}'.replace('PLACEHOLDER', jobId), 
                'test_' + jobId, 
                'width=800,height=600,toolbar=no,menubar=no,scrollbars=yes');
}
</script>""",

    "config.html": """{% extends 'base.html' %}
{% block body %}
<div class="action-matrix">
    <div style="color: var(--amber-dim); font-family: 'JetBrains Mono', monospace;">
        ⬢ SYSTEM CONFIGURATION ⬢ MODIFY EMAIL SETTINGS ⬢ NO RESTART REQUIRED
    </div>
    <button class="btn-action" onclick="location.href='{{ url_for(\"index\") }}'">⬢ BACK TO DASHBOARD</button>
</div>

<div class="form-brutalist">
    <form method="post">
        <h3 style="color: var(--amber-core); font-family: 'Oswald', sans-serif; margin-bottom: 2rem; font-size: 1.5rem; letter-spacing: 2px;">
            ∴ EMAIL DELIVERY CONFIGURATION
        </h3>
        
        <label>∴ RESEND.DEV API KEY</label>
        <input name="resend_api_key" 
               value="{{ config.resend_api_key or '' }}" 
               placeholder="re_xxxxxxxxxxxxxxx (get from resend.com dashboard)" 
               required />
        <small style="color: var(--amber-dim); display: block; margin-bottom: 1rem;">
            Sign up at resend.com - free tier includes 3000 emails/month
        </small>
        
        <label>∴ SENDER EMAIL ADDRESS</label>
        <input name="email_from" 
               value="{{ config.email_from or '' }}" 
               placeholder="noreply@yourdomain.com" 
               required />
        <small style="color: var(--amber-dim); display: block; margin-bottom: 1rem;">
            Must match a verified domain in your Resend.dev account
        </small>
        
        <label>∴ DEFAULT EMAIL SUBJECT PREFIX</label>
        <input name="email_subject_prefix" 
               value="{{ config.email_subject_prefix or '[TenderDash]' }}" 
               placeholder="[TenderDash]" />
        <small style="color: var(--amber-dim); display: block; margin-bottom: 1rem;">
            Will appear as: &quot;[TenderDash] 5 new tender(s) - 2025-01-08&quot;
        </small>
        
        <label>∴ DEFAULT RECIPIENTS (FALLBACK)</label>
        <input name="default_recipients" 
               value="{{ config.default_recipients or '' }}" 
               placeholder="admin@yourdomain.com, alerts@yourdomain.com" />
        <small style="color: var(--amber-dim); display: block; margin-bottom: 1rem;">
            Used when job configurations don't specify recipients
        </small>
        
        <h3 style="color: var(--amber-core); font-family: 'Oswald', sans-serif; margin: 3rem 0 2rem 0; font-size: 1.5rem; letter-spacing: 2px;">
            ∴ SYSTEM BEHAVIOR SETTINGS
        </h3>
        
        <label>∴ DATA HARVESTING FREQUENCY</label>
        <select name="harvest_frequency">
            <option value="5" {{ 'selected' if config.harvest_frequency == 5 else '' }}>Every 5 minutes (High frequency)</option>
            <option value="10" {{ 'selected' if config.harvest_frequency == 10 else '' }}>Every 10 minutes (Recommended)</option>
            <option value="15" {{ 'selected' if config.harvest_frequency == 15 else '' }}>Every 15 minutes (Standard)</option>
            <option value="30" {{ 'selected' if config.harvest_frequency == 30 else '' }}>Every 30 minutes (Low frequency)</option>
        </select>
        <small style="color: var(--amber-dim); display: block; margin-bottom: 1rem;">
            How often the system fetches new data from tenders.go.ke
        </small>
        
        <label>∴ MAXIMUM API PAGES TO FETCH</label>
        <select name="max_pages">
            <option value="1" {{ 'selected' if config.max_pages == 1 else '' }}>1 page (200 records - Fast)</option>
            <option value="2" {{ 'selected' if config.max_pages == 2 else '' }}>2 pages (400 records - Balanced)</option>
            <option value="3" {{ 'selected' if config.max_pages == 3 else '' }}>3 pages (600 records - Comprehensive)</option>
            <option value="5" {{ 'selected' if config.max_pages == 5 else '' }}>5 pages (1000 records - Maximum)</option>
        </select>

        <label>∴ NEW RECIPIENT BEHAVIOR</label>
        <select name="new_recipient_mode">
            <option value="new_only" {{ 'selected' if config.new_recipient_mode == 'new_only' else '' }}>Send only new tenders (default)</option>
            <option value="all_active" {{ 'selected' if config.new_recipient_mode == 'all_active' else '' }}>Send all active unsent tenders</option>
        </select>
        <small style="color: var(--amber-dim); display: block; margin-bottom: 1rem;">
            When adding new email recipients to a job, should they receive all active tenders or only new ones?
        </small>

        <small style="color: var(--amber-dim); display: block; margin-bottom: 1rem;">
            More pages = more complete data but slower harvesting
        </small>
        
        <div style="display: flex; gap: 1rem; margin-top: 3rem;">
            <button type="submit" class="btn-primary" style="flex: 1;">⬢ SAVE CONFIGURATION</button>
            <button type="button" class="btn-action" onclick="testEmailConfig()">⬢ TEST EMAIL</button>
        </div>
    </form>
</div>

<script>
function testEmailConfig() {
    var form = document.querySelector('form');
    var formData = new FormData(form);
    
    fetch('{{ url_for(\"test_email_config\") }}', {
        method: 'POST',
        body: formData
    })
    .then(function(response) { return response.text(); })
    .then(function(result) {
        alert('Test Result:\\n\\n' + result);
    })
    .catch(function(error) {
        alert('Test Failed:\\n\\n' + error);
    });
}
</script>
{% endblock %}""",##Config over

    "cache.html": """{% extends 'base.html' %}
{% block body %}
<div class="action-matrix">
    <div>
        {% if cache_info %}
        <div style="color: var(--amber-dim); font-family: 'JetBrains Mono', monospace;">
            ⬢ CACHE STATUS: {{ cache_info.age_display }} | 
            TOTAL: {{ cache_info.total_records }} | 
            ACTIVE: {{ cache_info.active_records }} | 
            EXPIRED: {{ cache_info.expired_records }} | 
            UPDATED: {{ cache_info.last_update }}
        </div>
        {% endif %}
    </div>
    <div style="display: flex; gap: 1rem;">
        {% if show_all %}
            <button class="btn-action" onclick="location.href='{{ url_for(\"cache_view\", show_all=\"false\") }}'">
                ⬢ SHOW ACTIVE ONLY
            </button>
        {% else %}
            <button class="btn-action" onclick="location.href='{{ url_for(\"cache_view\", show_all=\"true\") }}'">
                ⬢ SHOW ALL (INC. EXPIRED)
            </button>
        {% endif %}
        <button class="btn-primary" onclick="location.reload()">⬢ REFRESH VIEW</button>
    </div>
</div>

{% if error %}
<div class="error-flash">⬢ {{ error }}</div>
{% elif not tenders %}
<div class="empty-state">
    {% if cache_info and cache_info.filter_active and cache_info.expired_records > 0 %}
        ⬢ NO ACTIVE TENDERS ⬢<br/>
        ({{ cache_info.expired_records }} expired tenders hidden - click "SHOW ALL" to view)
    {% else %}
        ⬢ NO CACHE DATA AVAILABLE ⬢<br/>
        Run central_harvester.py to populate cache
    {% endif %}
</div>
{% else %}
<div style="margin: 1rem 0; color: var(--amber-dim);">
    Showing {{ cache_info.showing_count }} {{ 'active' if not show_all else 'total' }} tenders
    {% if tenders|length >= 50 %}(limited to first 50){% endif %}
</div>

<table class="scraping-grid">
    <thead>
        <tr>
            <th>∴ ID</th>
            <th>∴ REF</th>
            <th>∴ TITLE</th>
            <th>∴ CATEGORY</th>
            <th>∴ ENTITY</th>
            <th>∴ CLOSES</th>
            <th>∴ STATUS</th>
        </tr>
    </thead>
    <tbody>
        {% for tender in tenders %}
        <tr {% if tender.is_expired %}style="opacity: 0.6;"{% endif %}>
            <td><strong>{{ tender.id }}</strong></td>
            <td>{{ (tender.tender_ref or '')[:15] }}{% if tender.tender_ref and tender.tender_ref|length > 15 %}...{% endif %}</td>
            <td>{{ tender.title[:50] }}{% if tender.title|length > 50 %}...{% endif %}</td>
            <td><span class="status-badge status-active">{{ tender.category_display }}</span></td>
            <td>{{ tender.entity_display[:25] }}{% if tender.entity_display|length > 25 %}...{% endif %}</td>
            <td>{{ tender.close_at }}</td>
            <td>
                {% if tender.is_expired %}
                    <span class="status-badge status-error">EXPIRED</span>
                {% else %}
                    <span class="status-badge status-active">ACTIVE</span>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>

{% if tenders|length >= 50 %}
<div style="text-align: center; margin-top: 2rem; color: var(--amber-dim);">
    ⬢ Showing first 50 records ({{ cache_info.total_records }} total) ⬢
</div>
{% endif %}

{% endif %}
{% endblock %}""",


"form.html":"""{% extends 'base.html' %}
{% block body %}
<div class="form-brutalist">
    <form method="post">
        <label>∴ TARGET PROCUREMENT CLASSES</label>
        <input name="classes" 
               value="{{ job and ', '.join(job.classes) or '' }}" 
               placeholder="Goods, Works, Consultancy Services (leave empty for ALL categories)" />
        
        <label>∴ SCRAPING RECIPIENTS</label>
        <input name="recipients" 
               value="{{ job and ', '.join(job.recipients) or '' }}" 
               placeholder="agent1@domain.com, agent2@domain.com" 
               required />
        
        <label>∴ SCRAPING FREQUENCY</label>
        <select name="interval" required>
            {% for key, (display, cron) in intervals.items() %}
                <option value="{{ key }}" {{ 'selected' if job and job.interval == key else '' }}>{{ display }}</option>
            {% endfor %}
        </select>
        
        <button type="submit" class="btn-primary">⬢ ACTIVATE SCRAPING</button>
        <button type="button" class="btn-action" onclick="history.back()">⬢ ABORT</button>
    </form>
</div>
{% endblock %}""",
}

app.jinja_loader = DictLoader(TEMPLATES)

# ---------------------------------------------------------------------------
# Auth decorator (HTTP Basic)
# ---------------------------------------------------------------------------

def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.password != PASSWORD:
            return Response(
                "⬢ ACCESS DENIED ⬢", 401,
                {"WWW-Authenticate": 'Basic realm="SOLAR BRUTALIST SCRAPING"'}
            )
        return view(*args, **kwargs)
    return wrapped

# ---------------------------------------------------------------------------
# Status tracking utilities
# ---------------------------------------------------------------------------

def get_job_status(jid: str) -> Dict:
    """Get current status of a job"""
    status_file = STATUS_DIR / f"{jid}.json"
    if not status_file.exists():
        return {"status": "idle", "last_run": None, "next_run": None}
    
    try:
        return json.loads(status_file.read_text())
    except (json.JSONDecodeError, Exception):
        return {"status": "idle", "last_run": None, "next_run": None}

def update_job_status(jid: str, status: str, **kwargs):
    """Update job status"""
    status_file = STATUS_DIR / f"{jid}.json"
    current = get_job_status(jid)
    current.update({"status": status, **kwargs})
    status_file.write_text(json.dumps(current, indent=2))

def calculate_next_run(interval_key: str) -> Optional[str]:
    """Calculate next run time based on interval"""
    if interval_key not in INTERVALS:
        return None
    
    from croniter import croniter
    cron_expr = INTERVALS[interval_key][1]
    now = dt.datetime.now()
    cron = croniter(cron_expr, now)
    next_run = cron.get_next(dt.datetime)
    
    # Calculate time remaining
    delta = next_run - now
    if delta.total_seconds() < 60:
        return f"{int(delta.total_seconds())}s"
    elif delta.total_seconds() < 3600:
        return f"{int(delta.total_seconds() / 60)}m"
    else:
        hours = int(delta.total_seconds() / 3600)
        minutes = int((delta.total_seconds() % 3600) / 60)
        return f"{hours}h {minutes}m"

# ---------------------------------------------------------------------------
# Configuration management
# ---------------------------------------------------------------------------

def load_app_config() -> Dict:
    """Load application configuration with fallbacks to environment variables"""
    default_config = {
        "resend_api_key": os.getenv("RESEND_API_KEY", ""),
        "email_from": os.getenv("EMAIL_FROM", "noreply@yourdomain.com"),
        "email_subject_prefix": os.getenv("EMAIL_SUBJECT_PREFIX", "[TenderDash]"),
        "default_recipients": os.getenv("PPIP_RECIPIENTS", ""),
        "harvest_frequency": int(os.getenv("HARVEST_FREQUENCY", "10")),
        "max_pages": int(os.getenv("PPIP_MAX_PAGES", "3"))
    }
    
    if not CONFIG_FILE.exists():
        # Create default config file
        save_app_config(default_config)
        return default_config
    
    try:
        user_config = json.loads(CONFIG_FILE.read_text())
        # Merge with defaults (user config takes priority)
        default_config.update(user_config)
        return default_config
    except (json.JSONDecodeError, Exception) as e:
        print(f"Config file corrupted, using defaults: {e}")
        return default_config

def str_to_bool(value: str) -> bool:
    """Convert string to boolean for query parameters"""
    if value is None:
        return False
    return value.lower() in ('true', '1', 'yes', 'on')


def save_app_config(config: Dict) -> bool:
    """Save application configuration to file"""
    try:
        CONFIG_FILE.write_text(json.dumps(config, indent=2))
        return True
    except Exception as e:
        print(f"Failed to save config: {e}")
        return False

def get_email_config() -> Dict:
    """Get current email configuration for use by email functions"""
    config = load_app_config()
    return {
        "api_key": config.get("resend_api_key", ""),
        "from_email": config.get("email_from", "noreply@yourdomain.com"),
        "subject_prefix": config.get("email_subject_prefix", "[TenderDash]"),
        "default_recipients": [r.strip() for r in config.get("default_recipients", "").split(",") if r.strip()]
    }

# ---------------------------------------------------------------------------
# Enhanced job utilities with error handling
# ---------------------------------------------------------------------------

def load_cache_data() -> tuple[Optional[List[Dict]], Optional[Dict]]:
    """Load cache data and metadata for display - FIXED FOR WINDOWS ENCODING"""
    cache_file = CACHE_DIR / "tender_data.json"
    if not cache_file.exists():
        return None, None
    
    try:
        # Use UTF-8 encoding explicitly
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        tenders = cache_data.get("data", [])
        
        # Calculate cache info
        timestamp = cache_data.get("timestamp")
        cache_info = None
        if timestamp:
            cache_time = dt.datetime.fromisoformat(timestamp)
            age_minutes = (dt.datetime.now() - cache_time).total_seconds() / 60
            
            if age_minutes < 60:
                age_display = f"{int(age_minutes)}m ago"
            elif age_minutes < 1440:  # 24 hours
                age_display = f"{int(age_minutes/60)}h ago"
            else:
                age_display = f"{int(age_minutes/1440)}d ago"
            
            # Count active vs expired
            active_count = sum(1 for t in tenders if is_tender_active(t))
            expired_count = len(tenders) - active_count
            
            cache_info = {
                "age_display": age_display,
                "total_records": len(tenders),
                "active_records": active_count,
                "expired_records": expired_count,
                "last_update": cache_time.strftime("%Y-%m-%d %H:%M"),
                "age_minutes": age_minutes
            }
        
        return tenders, cache_info
    except (json.JSONDecodeError, Exception) as e:
        return None, {"error": f"Cache read error: {e}"}

def job_path(jid: str) -> pathlib.Path:
    return CFG_DIR / f"{jid}.json"

def list_jobs() -> List[Dict]:
    """List all jobs with enhanced display info and error recovery"""
    jobs = []
    for p in CFG_DIR.glob("*.json"):
        try:
            job_data = json.loads(p.read_text())
            jid = job_data["id"]
            
            # Enhanced display info
            classes = job_data.get("classes", [])
            job_data["classes_display"] = ", ".join(classes) if classes else "⬢ ALL CATEGORIES"
            
            # Convert old cron schedule to interval if needed
            schedule = job_data.get("schedule", "*/30 * * * *")
            interval_key = None
            for key, (display, cron) in INTERVALS.items():
                if cron == schedule:
                    interval_key = key
                    break
            
            if not interval_key:
                interval_key = "30min"  # Default fallback
                
            job_data["interval"] = interval_key
            job_data["interval_display"] = INTERVALS[interval_key][0]
            
            # Status info
            status = get_job_status(jid)
            job_data["status"] = status.get("status", "idle")
            job_data["status_display"] = status["status"].upper()
            job_data["next_run_display"] = calculate_next_run(interval_key) or "∞"
            
            jobs.append(job_data)
            
        except (json.JSONDecodeError, KeyError, Exception) as e:
            # Auto-repair corrupted files
            print(f"⬢ CORRUPTED DATA DETECTED: {p.name} - {e}")
            try:
                # Try to salvage what we can
                partial_data = {"id": p.stem, "classes": [], "recipients": ["repair@needed.com"], "interval": "30min"}
                p.write_text(json.dumps(partial_data, indent=2))
                print(f"⬢ AUTO-REPAIRED: {p.name}")
            except Exception:
                # If repair fails, remove the corrupted file
                p.unlink()
                print(f"⬢ PURGED CORRUPTED FILE: {p.name}")
    
    return sorted(jobs, key=lambda x: x["id"])

def save_job(data: Dict):
    """Save job with enhanced error handling"""
    try:
        job_path(data["id"]).write_text(json.dumps(data, indent=2))
        # Initialize status tracking
        update_job_status(data["id"], "idle")
    except Exception as e:
        raise Exception(f"Failed to save job: {e}")

def delete_job(jid: str):
    """Delete job and its status"""
    job_file = job_path(jid)
    status_file = STATUS_DIR / f"{jid}.json"
    
    if job_file.exists():
        job_file.unlink()
    if status_file.exists():
        status_file.unlink()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
@require_auth
def index():
    return render_template("index.html")

@app.route("/jobs")
@require_auth
def jobs_partial():
    return render_template("rows.html", jobs=list_jobs())

@app.route("/job/new")
@require_auth
def new_job():
    return render_template("form.html", job=None, intervals=INTERVALS)

@app.route("/job", methods=["POST"])
@require_auth
def create_job():
    jid = uuid.uuid4().hex[:8]
    interval_key = request.form.get("interval", "30min")
    
    data = {
        "id": jid,
        "classes": [c.strip() for c in request.form["classes"].split(",") if c.strip()],
        "recipients": [r.strip() for r in request.form["recipients"].split(",") if r.strip()],
        "interval": interval_key,
        "schedule": INTERVALS[interval_key][1],  # Store cron for compatibility
    }
    
    try:
        save_job(data)
        flash(f"⬢ SCRAPING OPERATION {jid} ACTIVATED")
    except Exception as e:
        flash(f"⬢ OPERATION FAILED: {e}")
    
    return redirect(url_for("index"))

@app.route("/job/<jid>", methods=["GET", "POST"])
@require_auth
def edit_job(jid):
    if request.method == "POST":
        interval_key = request.form.get("interval", "30min")
        
        data = {
            "id": jid,
            "classes": [c.strip() for c in request.form["classes"].split(",") if c.strip()],
            "recipients": [r.strip() for r in request.form["recipients"].split(",") if r.strip()],
            "interval": interval_key,
            "schedule": INTERVALS[interval_key][1],
        }
        
        try:
            save_job(data)
            flash(f"⬢ SCRAPING OPERATION {jid} UPDATED")
        except Exception as e:
            flash(f"⬢ UPDATE FAILED: {e}")
        
        return redirect(url_for("index"))

    try:
        job_data = json.loads(job_path(jid).read_text())
        return render_template("form.html", job=job_data, intervals=INTERVALS)
    except Exception:
        flash(f"⬢ OPERATION {jid} NOT FOUND OR CORRUPTED")
        return redirect(url_for("index"))

@app.route("/job/<jid>", methods=["DELETE"])
@require_auth
def del_job(jid):
    delete_job(jid)
    #Response(f"⬢ TEST EXECUTION COMPLETE ⬢\n\n{res.stdout}\n{res.stderr}", 
    #                   mimetype="text/plain")
    return "", 204

@app.route("/job/<jid>/run", methods=["GET", "POST"])
@require_auth
def run_job(jid):
    """Run a job manually with better output handling"""
    try:
        cfg = json.loads(job_path(jid).read_text())
        update_job_status(jid, "running")
        
        # Check cache status first
        cache_file = CACHE_DIR / "tender_data.json"
        cache_info = f"Cache exists: {cache_file.exists()}"
        if cache_file.exists():
            cache_info += f", Size: {cache_file.stat().st_size} bytes"
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    cache_info += f", Records: {len(cache_data.get('data', []))}"
            except:
                cache_info += ", Error reading cache"
        
        # Get current email config
        email_config = get_email_config()
        
        # Determine recipients
        recipients = cfg.get("recipients", [])
        if not recipients:
            recipients = email_config["default_recipients"]
        
        # Run in cache mode by default (remove --direct flag)
        cmd = [
            sys.executable, str(ROOT / "tender_scraper.py"),
            "--dry-run",
            "--limit", "1"
        ]
        
        # Add classes if specified
        if cfg.get("classes"):
            cmd.extend(["--classes", ",".join(cfg["classes"])])
        
        # Add recipients if available
        if recipients:
            cmd.extend(["--recipients", ",".join(recipients)])
        
        # Set environment variables
        env = os.environ.copy()
        env.update({
            "RESEND_API_KEY": email_config["api_key"],
            "EMAIL_FROM": email_config["from_email"],
            "EMAIL_SUBJECT_PREFIX": email_config["subject_prefix"],
            "PPIP_CACHE": str(SEEN_DIR / f"seen_{jid}.json")  # Job-specific seen cache
        })
        
        # Run with proper working directory
        res = subprocess.run(
            cmd, 
            env=env, 
            capture_output=True, 
            text=True, 
            timeout=120,
            cwd=str(ROOT)
        )
        
        update_job_status(jid, "idle", last_test=dt.datetime.now().isoformat())
        
        # Format output for display
        output = f"""⬢ TEST EXECUTION COMPLETE ⬢

Job ID: {jid}
Cache Status: {cache_info}
Command: {' '.join(cmd)}
Recipients: {', '.join(recipients) if recipients else 'None configured'}
Working Directory: {ROOT}

=== STDOUT ===
{res.stdout if res.stdout else "(no output)"}

=== STDERR ===
{res.stderr if res.stderr else "(no errors)"}

Return code: {res.returncode}
"""
        
        # Create a simple HTML response that shows in a new window
        html_response = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Test Results - Job {jid}</title>
    <style>
        body {{
            background: #000;
            color: #FFB000;
            font-family: 'Courier New', monospace;
            padding: 20px;
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>{output}</body>
</html>
"""
        
        return Response(html_response, mimetype="text/html")
        
    except Exception as e:
        update_job_status(jid, "error")
        error_output = f"""⬢ EXECUTION FAILED ⬢

Error: {str(e)}
Traceback:
{traceback.format_exc()}
"""
        html_response = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Test Error - Job {jid}</title>
    <style>
        body {{
            background: #000;
            color: #FF073A;
            font-family: 'Courier New', monospace;
            padding: 20px;
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>{error_output}</body>
</html>
"""
        return Response(html_response, mimetype="text/html")


@app.route("/cache")
@require_auth
def cache_view():
    """View current cache contents with active/all filter"""
    # Get filter preference
    show_all = str_to_bool(request.args.get('show_all', 'false'))
    
    # Debug info
    cache_file = CACHE_DIR / "tender_data.json"
    debug_info = {
        "cache_dir": str(CACHE_DIR),
        "cache_file": str(cache_file),
        "exists": cache_file.exists(),
        "size": cache_file.stat().st_size if cache_file.exists() else 0
    }
    
    tenders, cache_info = load_cache_data()
    
    if tenders is None:
        error_msg = f"Cache file not found or corrupted. Debug: {json.dumps(debug_info, indent=2)}"
        return render_template("cache.html", 
                             tenders=None, 
                             cache_info=None,
                             error=error_msg,
                             show_all=show_all)
    
    # Filter tenders if needed
    if not show_all:
        display_tenders = filter_active_tenders(tenders)
    else:
        display_tenders = tenders
    
    # Process tenders to add display fields
    now = dt.datetime.now()
    for tender in display_tenders:
        # Use the utility functions for proper field extraction
        tender['category_display'] = get_tender_category(tender)
        tender['entity_display'] = get_tender_entity(tender)
        tender['is_expired'] = not is_tender_active(tender)
    
    # Limit display to first 50 for performance
    display_tenders = display_tenders[:50] if display_tenders else []
    
    # Add debug info to cache_info
    if cache_info:
        cache_info["debug"] = debug_info
        cache_info["filter_active"] = not show_all
        cache_info["showing_count"] = len(display_tenders)
    
    return render_template("cache.html", 
                         tenders=display_tenders,
                         cache_info=cache_info,
                         show_all=show_all)


@app.route("/config", methods=["GET", "POST"])
@require_auth
def config_page():
    """System configuration page"""
    if request.method == "POST":
        # Save configuration
        new_config = {
            "resend_api_key": request.form.get("resend_api_key", ""),
            "email_from": request.form.get("email_from", ""),
            "email_subject_prefix": request.form.get("email_subject_prefix", "[TenderDash]"),
            "default_recipients": request.form.get("default_recipients", ""),
            "harvest_frequency": int(request.form.get("harvest_frequency", "10")),
            "max_pages": int(request.form.get("max_pages", "3"))
        }
        
        if save_app_config(new_config):
            # Update environment variables for the harvester
            os.environ["PPIP_MAX_PAGES"] = str(new_config["max_pages"])
            flash("⬢ CONFIGURATION SAVED SUCCESSFULLY")
        else:
            flash("⬢ CONFIGURATION SAVE FAILED")
        
        return redirect(url_for("config_page"))
    
    # Load current configuration
    config = load_app_config()
    return render_template("config.html", config=config)

@app.route("/test-email", methods=["POST"])
@require_auth
def test_email_config():
    """Test email configuration"""
    try:
        # Get test configuration from form
        test_config = {
            "api_key": request.form.get("resend_api_key", ""),
            "from_email": request.form.get("email_from", ""),
            "subject_prefix": request.form.get("email_subject_prefix", "[TenderDash]"),
        }
        
        if not test_config["api_key"]:
            return "Error: Resend API key is required", 400
        
        if not test_config["from_email"]:
            return "Error: Sender email is required", 400
        
        # Get test recipient (first from default recipients or current user's assumed email)
        recipients = request.form.get("default_recipients", "").split(",")
        test_recipient = recipients[0].strip() if recipients and recipients[0].strip() else test_config["from_email"]
        
        # Send test email
        import requests
        payload = {
            "from": test_config["from_email"],
            "to": [test_recipient],
            "subject": f"{test_config['subject_prefix']} Test Email",
            "text": f"""This is a test email from TenderDash.

Configuration Test Results:
- API Key: {'✓ Configured' if test_config['api_key'] else '✗ Missing'}
- From Email: {test_config['from_email']}
- Subject Prefix: {test_config['subject_prefix']}
- Test Recipient: {test_recipient}

If you received this email, your configuration is working correctly!

--
TenderDash Procurement Monitoring System
"""
        }
        
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {test_config['api_key']}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            return f"Success! Test email sent to {test_recipient}\n\nCheck your inbox.", 200
        else:
            error_detail = response.json() if response.headers.get('content-type') == 'application/json' else response.text
            return f"Failed to send test email.\n\nStatus: {response.status_code}\nError: {error_detail}", 400
            
    except requests.exceptions.RequestException as e:
        return f"Network error: {str(e)}", 500
    except Exception as e:
        return f"Error: {str(e)}", 500

# Add this route to dashboard_app.py (after the other routes)

@app.route("/harvest", methods=["POST"])
@require_auth
def force_harvest():
    """Force run the central harvester with enhanced debugging"""
    try:
        # Check if harvester is already running
        harvest_lock = ROOT / "harvester.lock"
        if harvest_lock.exists():
            lock_age = (dt.datetime.now() - dt.datetime.fromtimestamp(harvest_lock.stat().st_mtime)).total_seconds()
            if lock_age < 300:  # 5 minutes
                return Response("⬢ HARVEST ALREADY IN PROGRESS ⬢\n\nAnother harvest is currently running. Please wait.", 
                               mimetype="text/plain", status=409)
        
        # Get current app config for environment
        app_config = load_app_config()
        
        # Log cache file location
        cache_file = CACHE_DIR / "tender_data.json"
        debug_info = [
            f"Cache directory: {CACHE_DIR}",
            f"Cache file path: {cache_file}",
            f"Cache exists before harvest: {cache_file.exists()}",
        ]
        
        if cache_file.exists():
            debug_info.append(f"Cache size before: {cache_file.stat().st_size} bytes")
        
        # Run the harvester
        env = os.environ.copy()
        env.update({
            "PPIP_MAX_PAGES": str(app_config.get("max_pages", 3))
        })
        
        result = subprocess.run(
            [sys.executable, str(ROOT / "central_harvester.py")],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            cwd=str(ROOT)  # Ensure correct working directory
        )
        
        # Check cache after harvest
        cache_exists_after = cache_file.exists()
        debug_info.append(f"Cache exists after harvest: {cache_exists_after}")
        
        if cache_exists_after:
            debug_info.append(f"Cache size after: {cache_file.stat().st_size} bytes")
            # Try to read and validate cache
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    records_in_cache = len(cache_data.get("data", []))
                    debug_info.append(f"Records in cache file: {records_in_cache}")
            except Exception as e:
                debug_info.append(f"Error reading cache: {e}")
        
        # Parse results from output
        output_lines = result.stdout.splitlines() if result.stdout else []
        records_found = 0
        duration = 0
        
        for line in output_lines:
            if "Harvest complete:" in line:
                import re
                match = re.search(r'(\d+) records', line)
                if match:
                    records_found = int(match.group(1))
                match = re.search(r'in ([\d.]+)s', line)
                if match:
                    duration = float(match.group(1))
        
        # Build response with debug info
        if result.returncode == 0:
            response_text = f"""⬢ HARVEST SUCCESSFUL ⬢

Records Retrieved: {records_found}
Duration: {duration:.1f} seconds
Status: Data cache updated

DEBUG INFO:
{chr(10).join(debug_info)}

OUTPUT:
{result.stdout}

The cache has been refreshed. All monitoring jobs will use the new data."""
        else:
            response_text = f"""⬢ HARVEST FAILED ⬢

Return Code: {result.returncode}

DEBUG INFO:
{chr(10).join(debug_info)}

STDOUT:
{result.stdout}

STDERR:
{result.stderr}

Please check the logs for more details."""
        
        return Response(response_text, mimetype="text/plain")
        
    except subprocess.TimeoutExpired:
        return Response("⬢ HARVEST TIMEOUT ⬢\n\nThe harvest operation took too long and was terminated.", 
                       mimetype="text/plain", status=500)
    except Exception as e:
        return Response(f"⬢ HARVEST ERROR ⬢\n\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}", 
                       mimetype="text/plain", status=500)

# Also add a status check endpoint
@app.route("/harvest/status")
@require_auth
def harvest_status():
    """Check harvest status and cache info"""
    cache_info = {"status": "unknown", "age": "N/A", "records": 0}
    
    # Check cache status
    tenders, info = load_cache_data()
    if info and not info.get("error"):
        cache_info = {
            "status": "available",
            "age": info.get("age_display", "Unknown"),
            "records": info.get("total_records", 0),
            "last_update": info.get("last_update", "Never")
        }
    elif info and info.get("error"):
        cache_info = {"status": "error", "error": info["error"]}
    else:
        cache_info = {"status": "missing", "error": "No cache file found"}
    
    # Check if harvester is running
    harvest_lock = ROOT / "harvester.lock"
    if harvest_lock.exists():
        lock_age = (dt.datetime.now() - dt.datetime.fromtimestamp(harvest_lock.stat().st_mtime)).total_seconds()
        if lock_age < 300:  # 5 minutes
            cache_info["harvesting"] = True
            cache_info["harvest_duration"] = f"{int(lock_age)}s"
    
    return cache_info


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)