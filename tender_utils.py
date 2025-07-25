#!/usr/bin/env python3
"""
tender_utils.py - Enhanced tender data processing utilities
==========================================================
Provides common functions for processing tender data with proper field handling,
active tender filtering, and email tracking capabilities.
"""

import datetime as dt
import json
import pathlib
from typing import Dict, List, Optional, Set, Tuple

def get_tender_category(tender: Dict) -> str:
    """Extract category from tender data with multiple fallbacks"""
    # Try nested procurement_category first (correct structure)
    if "procurement_category" in tender and isinstance(tender["procurement_category"], dict):
        return tender["procurement_category"].get("title", "Unknown")
    
    # Fallback to old field names
    if "category_name" in tender:
        return tender["category_name"]
    if "category" in tender:
        return tender["category"]
    
    # Show ID if available
    if "procurement_category_id" in tender:
        return f"Category #{tender['procurement_category_id']}"
    
    return "Unknown"

def get_tender_entity(tender: Dict) -> str:
    """Extract entity name from tender data with multiple fallbacks"""
    # Try nested PE entity structure (correct structure)
    if "pe" in tender and isinstance(tender["pe"], dict):
        return tender["pe"].get("name", "Unknown")
    
    # Fallback to entity field
    if "entity" in tender:
        return tender["entity"]
    
    # Show PE ID if available
    if "pe_id" in tender:
        return f"Entity #{tender['pe_id']}"
    
    return "Unknown"

def is_tender_active(tender: Dict, reference_date: Optional[dt.datetime] = None) -> bool:
    """Check if tender is still active (not expired)"""
    if reference_date is None:
        reference_date = dt.datetime.now()
    
    close_at_str = tender.get("close_at", "")
    if not close_at_str:
        return True  # No close date means we assume it's active
    
    try:
        # Handle different date formats
        if "T" in close_at_str:
            close_date = dt.datetime.fromisoformat(close_at_str.replace("Z", "+00:00"))
        elif " " in close_at_str:
            close_date = dt.datetime.strptime(close_at_str, "%Y-%m-%d %H:%M:%S")
        else:
            close_date = dt.datetime.strptime(close_at_str, "%Y-%m-%d")
        
        return close_date >= reference_date
    except (ValueError, TypeError):
        return True  # If we can't parse the date, assume active

def format_tender_summary(tender: Dict, detailed: bool = False) -> Dict:
    """Format tender data for display with proper field extraction"""
    summary = {
        "id": tender.get("id", "Unknown"),
        "title": tender.get("title", "No title"),
        "category": get_tender_category(tender),
        "entity": get_tender_entity(tender),
        "close_at": tender.get("close_at", "Unknown"),
        "is_active": is_tender_active(tender),
        "tender_ref": tender.get("tender_ref", ""),
        "published_at": tender.get("published_at", ""),
    }
    
    if detailed:
        # Add more fields for detailed view
        summary.update({
            "procurement_method": tender.get("procurement_method", {}).get("title", "Unknown"),
            "venue": tender.get("venue", "Not specified"),
            "tender_fee": tender.get("tender_fee", 0),
            "financial_year": tender.get("financial_year", {}).get("name", "Unknown"),
            "addendum_count": len(tender.get("addenda", [])),
            "document_count": len(tender.get("documents", [])),
        })
    
    return summary

def filter_active_tenders(tenders: List[Dict]) -> List[Dict]:
    """Filter only active (non-expired) tenders"""
    return [t for t in tenders if is_tender_active(t)]

# Email tracking functionality
class EmailTracker:
    """Track which tenders have been sent to which email addresses"""
    
    def __init__(self, tracking_file: pathlib.Path):
        self.tracking_file = tracking_file
        self.data = self._load_tracking_data()
    
    def _load_tracking_data(self) -> Dict:
        """Load tracking data from file"""
        if not self.tracking_file.exists():
            return {"recipients": {}, "last_updated": None}
        
        try:
            with open(self.tracking_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return {"recipients": {}, "last_updated": None}
    
    def save(self):
        """Save tracking data to file"""
        self.data["last_updated"] = dt.datetime.now().isoformat()
        try:
            with open(self.tracking_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"Failed to save email tracking: {e}")
    
    def get_sent_tenders(self, email: str) -> Set[str]:
        """Get set of tender IDs already sent to this email"""
        return set(self.data["recipients"].get(email, {}).get("sent_tenders", []))
    
    def get_unsent_tenders(self, email: str, all_tender_ids: List[str], active_only: bool = True) -> List[str]:
        """Get list of tender IDs not yet sent to this email"""
        sent = self.get_sent_tenders(email)
        unsent = [tid for tid in all_tender_ids if str(tid) not in sent]
        return unsent
    
    def mark_tenders_sent(self, email: str, tender_ids: List[str]):
        """Mark tenders as sent to an email address"""
        if email not in self.data["recipients"]:
            self.data["recipients"][email] = {
                "first_seen": dt.datetime.now().isoformat(),
                "sent_tenders": []
            }
        
        # Add new tender IDs to sent list
        existing = set(self.data["recipients"][email]["sent_tenders"])
        existing.update(str(tid) for tid in tender_ids)
        self.data["recipients"][email]["sent_tenders"] = sorted(existing)
        self.data["recipients"][email]["last_sent"] = dt.datetime.now().isoformat()
    
    def is_new_recipient(self, email: str) -> bool:
        """Check if this is a new recipient"""
        return email not in self.data["recipients"]
    
    def get_stats(self) -> Dict:
        """Get tracking statistics"""
        stats = {
            "total_recipients": len(self.data["recipients"]),
            "recipients": {}
        }
        
        for email, info in self.data["recipients"].items():
            stats["recipients"][email] = {
                "tenders_sent": len(info.get("sent_tenders", [])),
                "first_seen": info.get("first_seen"),
                "last_sent": info.get("last_sent")
            }
        
        return stats

def format_tender_email_line(tender: Dict, include_status: bool = False) -> str:
    """Format a single tender line for email"""
    summary = format_tender_summary(tender)
    
    # Shorten the tender ref if it's too long
    tender_ref = summary['tender_ref']
    if len(tender_ref) > 20:
        tender_ref = tender_ref[:17] + "..."
    
    line = (
        f"ID: {summary['id']} | Ref: {tender_ref} | "
        f"{summary['title'][:60]}{'...' if len(summary['title']) > 60 else ''} | "
        f"{summary['category']} | "
        f"Closes: {summary['close_at']} | "
        f"{summary['entity'][:30]}{'...' if len(summary['entity']) > 30 else ''}"
    )
    
    if include_status:
        status = "ACTIVE" if summary['is_active'] else "EXPIRED"
        line += f" | Status: {status}"
    
    return line

def group_tenders_by_category(tenders: List[Dict]) -> Dict[str, List[Dict]]:
    """Group tenders by category for organized display"""
    grouped = {}
    for tender in tenders:
        category = get_tender_category(tender)
        if category not in grouped:
            grouped[category] = []
        grouped[category].append(tender)
    
    return grouped

def format_detailed_email_body(tenders: List[Dict], job_id: str = "", show_expired: bool = False) -> str:
    """Format tender data for email with category grouping and better formatting"""
    if not tenders:
        return f"No new tenders found for job {job_id}."
    
    # Filter active/expired
    if not show_expired:
        active_tenders = filter_active_tenders(tenders)
        if not active_tenders:
            return f"No active tenders found for job {job_id} (found {len(tenders)} expired tenders)."
        tenders = active_tenders
    
    # Group by category
    grouped = group_tenders_by_category(tenders)
    
    lines = [
        f"Found {len(tenders)} tender(s)",
        f"{'=' * 80}",
        ""
    ]
    
    for category, category_tenders in sorted(grouped.items()):
        lines.append(f"\n{category.upper()} ({len(category_tenders)} tenders)")
        lines.append("-" * len(f"{category} ({len(category_tenders)} tenders)"))
        
        for tender in sorted(category_tenders, key=lambda t: t.get("close_at", "")):
            lines.append(format_tender_email_line(tender, include_status=show_expired))
        lines.append("")
    
    # Add summary
    lines.extend([
        f"{'=' * 80}",
        f"Total: {len(tenders)} tenders",
        f"Categories: {', '.join(sorted(grouped.keys()))}",
        f"Report generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ])
    
    return "\n".join(lines)