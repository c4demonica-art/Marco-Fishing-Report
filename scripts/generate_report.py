"""Daily Marco Island fishing report generator.

Reads template.html, asks Claude (with web search) for the day's
content as JSON, fills the 5 placeholders, writes index.html.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'template.html'
OUTPUT = ROOT / 'index.html'

PLACEHOLDERS = ('DATE', 'OVERVIEW', 'CATCHES', 'BREAKDOWN', 'SCRIPT')

SYSTEM_PROMPT = """You are the content generator for the Marco Island Fishing Report, a daily mobile web page.

You will be given today's date. Use the web_search tool (2 searches) to pull recent Marco Island / Naples / Ten Thousand Islands fishing intel from sources such as naplesfishingcharters.org, swflguideservice.com, fishingbooker.com, snookhookerfishing.com, naplesgonefishin.com, and local guide blogs.

Respond with ONE JSON object and nothing else. No prose, no markdown fences. Exact keys:

{
  "DATE": "Month D, YYYY",
  "OVERVIEW": "3-4 sentence plain-text overview of this week's bite.",
  "CATCHES_HTML": "HTML string: 5 <div class=\"catch-card\">...</div> blocks. Each block contains .catch-top > .catch-who + .catch-loc, .catch-date, .catch-tags (spans with class ct), .catch-text, .catch-src.",
  "BREAKDOWN_HTML": "HTML string: 3 <div class=\"section-card\"> sections (Inshore, Nearshore, Backwater) each with a .sec-hdr (h2 + chevron) and .sec-body of .sp-row entries. Each sp-row has .sp-name-row (.sp-name + .rating with class HOT/GOOD/SLOW and emoji) and .sp-detail.",
  "SCRIPT_TEXT": "250-320 word first-person spoken script for a D-ID avatar, conversational tone, opens with 'Hey there, anglers', covers inshore/backcountry/nearshore, closes with 'Tight lines.' Plain text with double-newline paragraph breaks; spell out numbers and dates."
}

HTML must use exactly the class names above so it renders against the existing stylesheet. Put 5 catch cards and 3 breakdown sections. Tags like 'Snook', 'Redfish', 'Tarpon'. Ratings are 'HOT' (emoji fire), 'GOOD' (check), or 'SLOW' (snowflake).
"""


def today_str() -> str:
    return datetime.now(ZoneInfo('America/New_York')).strftime('%B %-d, %Y')


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    return json.loads(text)


def generate() -> dict:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model='claude-opus-4-7',
        max_tokens=8000,
        thinking={'type': 'adaptive'},
        system=[{
            'type': 'text',
            'text': SYSTEM_PROMPT,
            'cache_control': {'type': 'ephemeral'},
        }],
        tools=[{'type': 'web_search_20260209', 'name': 'web_search', 'max_uses': 2}],
        messages=[{
            'role': 'user',
            'content': f"Today is {today_str()}. Generate the full JSON for today's report.",
        }],
    )
    text_parts = [b.text for b in response.content if getattr(b, 'type', None) == 'text']
    if not text_parts:
        raise RuntimeError(f'No text blocks in response; stop_reason={response.stop_reason}')
    return extract_json(text_parts[-1])


def fill(template: str, data: dict) -> str:
    mapping = {
        '<!--DATE-->': data['DATE'],
        '<!--OVERVIEW-->': data['OVERVIEW'],
        '<!--CATCHES-->': data['CATCHES_HTML'],
        '<!--BREAKDOWN-->': data['BREAKDOWN_HTML'],
        '<!--SCRIPT-->': data['SCRIPT_TEXT'],
    }
    out = template
    for marker, value in mapping.items():
        if marker not in out:
            raise RuntimeError(f'Template missing marker: {marker}')
        out = out.replace(marker, value)
    return out


def main() -> int:
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('ANTHROPIC_API_KEY not set', file=sys.stderr)
        return 2
    template = TEMPLATE.read_text(encoding='utf-8')
    data = generate()
    for key in ('DATE', 'OVERVIEW', 'CATCHES_HTML', 'BREAKDOWN_HTML', 'SCRIPT_TEXT'):
        if key not in data:
            raise RuntimeError(f'Model response missing key: {key}')
    OUTPUT.write_text(fill(template, data), encoding='utf-8')
    print(f'Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes) for {data["DATE"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
