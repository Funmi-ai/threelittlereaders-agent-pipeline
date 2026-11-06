#!/usr/bin/env python3
"""
Weekly Report - Lead Generation Analytics

Generates weekly performance report:
- Leads sourced by source
- Pipeline status breakdown
- Response rates
- Conversion metrics
- Recommendations

USAGE:
  python3 weekly_report.py              # Print to console
  python3 weekly_report.py -o report.md # Save to file
  python3 weekly_report.py --json       # Output as JSON
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List
import requests
from dotenv import load_dotenv

load_dotenv()

# Airtable config
API_KEY = os.getenv('AIRTABLE_API_KEY')
BASE_ID = 'appfrjsXGlWrFPhKQ'
TABLE = 'Leads'
URL = f'https://api.airtable.com/v0/{BASE_ID}/{TABLE}'
HEADERS = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}


def fetch_all_leads() -> List[Dict]:
    """Fetch all leads from Airtable"""
    leads = []
    offset = None

    while True:
        params = {}
        if offset:
            params['offset'] = offset

        resp = requests.get(URL, headers=HEADERS, params=params)
        if resp.status_code != 200:
            print(f"Error fetching leads: {resp.text}")
            break

        data = resp.json()
        leads.extend(data.get('records', []))

        offset = data.get('offset')
        if not offset:
            break

    return leads


def calculate_metrics(leads: List[Dict]) -> Dict:
    """Calculate pipeline metrics from leads"""

    # Status counts
    status_counts = {
        'Not Contacted': 0,
        'Contacted': 0,
        'Followed Up': 0,
        'Engaged': 0,
        'Call Booked': 0,
        'Closed': 0,
        'Nurture': 0
    }

    # Reply status counts
    reply_counts = {
        'No Reply': 0,
        'Replied': 0
    }

    # Source counts (if tracked)
    source_counts = {}

    for lead in leads:
        fields = lead.get('fields', {})

        # Status
        status = fields.get('Lead Gen Progress', 'Not Contacted')
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts[status] = 1

        # Reply status
        reply = fields.get('Reply Status', 'No Reply')
        if reply in reply_counts:
            reply_counts[reply] += 1

        # Source (from notes or URL pattern)
        linkedin_url = fields.get('LinkedIn URL', '')
        if 'conference' in linkedin_url.lower():
            source = 'Conference'
        elif fields.get('Source'):
            source = fields.get('Source')
        else:
            source = 'Other'

        source_counts[source] = source_counts.get(source, 0) + 1

    # Calculate rates
    total = len(leads)
    contacted = status_counts.get('Contacted', 0) + status_counts.get('Followed Up', 0)
    replied = reply_counts.get('Replied', 0)
    calls_booked = status_counts.get('Call Booked', 0)
    closed = status_counts.get('Closed', 0)

    metrics = {
        'total_leads': total,
        'status_breakdown': status_counts,
        'reply_breakdown': reply_counts,
        'source_breakdown': source_counts,
        'rates': {
            'contact_rate': round((contacted / total * 100), 1) if total > 0 else 0,
            'reply_rate': round((replied / contacted * 100), 1) if contacted > 0 else 0,
            'book_rate': round((calls_booked / replied * 100), 1) if replied > 0 else 0,
            'close_rate': round((closed / calls_booked * 100), 1) if calls_booked > 0 else 0,
            'overall_conversion': round((closed / total * 100), 1) if total > 0 else 0
        },
        'funnel': {
            'leads': total,
            'contacted': contacted,
            'replied': replied,
            'calls_booked': calls_booked,
            'closed': closed
        }
    }

    return metrics


def generate_recommendations(metrics: Dict) -> List[str]:
    """Generate actionable recommendations based on metrics"""
    recommendations = []

    rates = metrics.get('rates', {})
    funnel = metrics.get('funnel', {})

    # Not enough leads
    if funnel.get('leads', 0) < 40:
        recommendations.append(
            "📊 **Source more leads** - Target 40+ warm leads/week. "
            "Run `python3 execution/lead_pipeline.py --limit 40`"
        )

    # Low contact rate
    if rates.get('contact_rate', 0) < 50:
        recommendations.append(
            "📤 **Increase outreach velocity** - Only {:.0f}% of leads contacted. "
            "Aim for 80%+ contact rate.".format(rates.get('contact_rate', 0))
        )

    # Low reply rate
    if rates.get('reply_rate', 0) < 20 and funnel.get('contacted', 0) > 10:
        recommendations.append(
            "✉️ **Improve messaging** - Reply rate is {:.0f}%. "
            "Test different Touch 1 openers. Review voice compliance.".format(rates.get('reply_rate', 0))
        )

    # Low book rate
    if rates.get('book_rate', 0) < 30 and funnel.get('replied', 0) > 5:
        recommendations.append(
            "📞 **Improve call conversion** - Only {:.0f}% of replies book calls. "
            "Try offering AI Readiness Audit as free value.".format(rates.get('book_rate', 0))
        )

    # Good progress
    if funnel.get('closed', 0) > 0:
        recommendations.append(
            "🎉 **Celebrate wins** - {} deals closed! "
            "Document what worked for case study.".format(funnel.get('closed', 0))
        )

    # Default if no issues
    if not recommendations:
        recommendations.append(
            "✅ **Keep going** - Metrics look healthy. "
            "Continue the weekly cadence."
        )

    return recommendations


def format_report(metrics: Dict, recommendations: List[str]) -> str:
    """Format metrics into readable report"""
    lines = []

    lines.append("# Weekly Lead Generation Report")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Funnel overview
    lines.append("## Pipeline Funnel")
    lines.append("")
    funnel = metrics.get('funnel', {})
    lines.append("```")
    lines.append(f"Leads:        {funnel.get('leads', 0):>5}")
    lines.append(f"Contacted:    {funnel.get('contacted', 0):>5}")
    lines.append(f"Replied:      {funnel.get('replied', 0):>5}")
    lines.append(f"Calls Booked: {funnel.get('calls_booked', 0):>5}")
    lines.append(f"Closed:       {funnel.get('closed', 0):>5}")
    lines.append("```")
    lines.append("")

    # Conversion rates
    lines.append("## Conversion Rates")
    lines.append("")
    rates = metrics.get('rates', {})
    lines.append(f"| Metric | Rate |")
    lines.append(f"|--------|------|")
    lines.append(f"| Contact Rate | {rates.get('contact_rate', 0)}% |")
    lines.append(f"| Reply Rate | {rates.get('reply_rate', 0)}% |")
    lines.append(f"| Book Rate | {rates.get('book_rate', 0)}% |")
    lines.append(f"| Close Rate | {rates.get('close_rate', 0)}% |")
    lines.append(f"| **Overall Conversion** | **{rates.get('overall_conversion', 0)}%** |")
    lines.append("")

    # Status breakdown
    lines.append("## Status Breakdown")
    lines.append("")
    status = metrics.get('status_breakdown', {})
    for s, count in sorted(status.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            lines.append(f"- **{s}:** {count}")
    lines.append("")

    # Source breakdown
    lines.append("## Lead Sources")
    lines.append("")
    sources = metrics.get('source_breakdown', {})
    for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- **{source}:** {count}")
    lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    for rec in recommendations:
        lines.append(f"- {rec}")
    lines.append("")

    # Target vs actual
    lines.append("## Weekly Targets")
    lines.append("")
    lines.append("| Metric | Target | Actual | Status |")
    lines.append("|--------|--------|--------|--------|")

    targets = {
        'Leads sourced': (100, funnel.get('leads', 0)),
        'Contacted': (40, funnel.get('contacted', 0)),
        'Replies': (10, funnel.get('replied', 0)),
        'Calls booked': (3, funnel.get('calls_booked', 0))
    }

    for metric, (target, actual) in targets.items():
        status = "✅" if actual >= target else "⚠️"
        lines.append(f"| {metric} | {target} | {actual} | {status} |")

    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='Generate weekly lead gen report')
    parser.add_argument('--output', '-o', help='Save report to file')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    print("Fetching leads from Airtable...")
    leads = fetch_all_leads()
    print(f"Found {len(leads)} leads")

    print("Calculating metrics...")
    metrics = calculate_metrics(leads)

    print("Generating recommendations...")
    recommendations = generate_recommendations(metrics)

    if args.json:
        output = {
            'generated_at': datetime.now().isoformat(),
            'metrics': metrics,
            'recommendations': recommendations
        }
        print(json.dumps(output, indent=2))
    else:
        report = format_report(metrics, recommendations)
        print("\n" + report)

        if args.output:
            with open(args.output, 'w') as f:
                f.write(report)
            print(f"\nSaved to: {args.output}")


if __name__ == '__main__':
    main()
