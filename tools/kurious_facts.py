#!/usr/bin/env python3
"""Kurious fact pages for galapptic.com/kurious/facts/, run daily by .github/workflows/kurious-facts.yml.

Each of the app's facts gets a page at /kurious/facts/<slug> (the file <slug>.html; GitHub Pages serves it without
the .html). <slug> is the headline as lowercase ASCII words joined by hyphens, at most 60 characters and cut at a word,
then a hyphen and the first 8 characters of the topic id. The app builds the same links for its "Challenge a friend"
cards (services/factLinks.js in the kurious repo), so change both together. If they ever disagree, 404.html finds the
page by the id at the end of the link.

What a page shows (the owner's choice, 2026-11-14): past days' articles are what Kurious Explorer sells, so the web
shows only the opening.
- On the fact's own day: the headline, the hook and the main photo, then the app button.
- From the next day on: the article's first section too, then the titles of the other sections and "Read the rest in
  Kurious".
- With ?challenge=1 (the app's challenge cards), the page first asks "True or false?" about the hook, and the app
  button's campaign is ct=challenge. With ?ref=pinterest it is ct=pinterest. Otherwise it is ct=web.

The full articles are never written to this public repo: index.json keeps only what the pages show. A day after
today (America/Chicago) is never published, though the backend serves future days.

Usage: python tools/kurious_facts.py [--rebuild-all] [--today YYYY-MM-DD] [--root DIR]
Stdlib only.
"""
import argparse
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND = 'https://web-production-fe98b.up.railway.app'
SITE = 'https://galapptic.com'
FACTS_PATH = '/kurious/facts'
APP_ID = '6766752682'
PROVIDER = '128866802'
FIRST_DAY = date(2026, 7, 15)     # the app's first topics are from late July 2026
UA = 'GalappticSite/1.0 (kurious fact pages; https://galapptic.com)'
SLUG_WORDS_MAX = 60

LABELS = {
    'biology': 'Biology', 'physics': 'Physics', 'history': 'History', 'food': 'Food & Cuisine',
    'technology': 'Technology', 'mathematics': 'Mathematics', 'psychology': 'Psychology', 'astronomy': 'Astronomy',
    'artsculture': 'Arts & Culture', 'chemistry': 'Chemistry', 'earthspace': 'Earth & Space',
    'sports': 'Sports & Athletics', 'language': 'Language', 'medicine': 'Medicine', 'philosophy': 'Philosophy',
    'geography': 'Geography', 'mythology': 'Mythology & Folklore', 'law': 'Law & Justice', 'economics': 'Economics',
    'sociology': 'Sociology', 'anthropology': 'Anthropology', 'paleontology': 'Dinosaurs & Fossils',
    'ocean': 'Oceans', 'music': 'Music', 'literature': 'Books & Literature', 'architecture': 'Architecture',
    'film': 'Film & TV', 'inventions': 'Inventions', 'exploration': 'Explorers & Expeditions',
    'business': 'Business & Brands', 'games': 'Games & Puzzles',
}


# ── links ────────────────────────────────────────────────────────────────────

def slugify(text, limit=SLUG_WORDS_MAX):
    """Same steps as slugify() in the app's services/factLinks.js."""
    t = unicodedata.normalize('NFKD', text or '')
    t = re.sub('[̀-ͯ]', '', t).lower()
    t = re.sub("['’]", '', t)
    t = re.sub('[^a-z0-9]+', '-', t).strip('-')
    if len(t) > limit:
        t = t[:limit]
        cut = t.rfind('-')
        if cut > 0:
            t = t[:cut]
    return t


def fact_slug(topic):
    words = slugify(topic.get('headline', ''))
    short = str(topic['id'])[:8].lower()
    return f'{words}-{short}' if words else short


def store_link(ct):
    return f'https://apps.apple.com/app/apple-store/id{APP_ID}?pt={PROVIDER}&ct={ct}&mt=8'


# ── dates ────────────────────────────────────────────────────────────────────

def _nth_sunday(year, month, n):
    d = date(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def chicago_today(now=None):
    """Today in America/Chicago (US daylight saving rules; zoneinfo isn't always there on Windows)."""
    now = now or datetime.now(timezone.utc)
    y = now.year
    dst_start = datetime(y, 3, _nth_sunday(y, 3, 2).day, 8, tzinfo=timezone.utc)    # 2am CST
    dst_end = datetime(y, 11, _nth_sunday(y, 11, 1).day, 7, tzinfo=timezone.utc)    # 2am CDT
    offset = -5 if dst_start <= now < dst_end else -6
    return (now + timedelta(hours=offset)).date()


def nice_date(d):
    return f'{d:%B} {d.day}, {d.year}'


# ── fetching ─────────────────────────────────────────────────────────────────

def get_json(url, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:      # noqa: BLE001 (network: retry, then give up on this one)
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'{url}: {last}')


def day_topics(d):
    return get_json(f'{BACKEND}/topics/by-date/{d.isoformat()}').get('topics') or []


def commons_file(url):
    """'File:Name.jpg' for a Wikimedia Commons image URL (full size or thumbnail), else None. English Wikipedia's own
    uploads (/wikipedia/en/) are fair-use images and are never shown here."""
    m = re.search(r'/wikipedia/commons/(?:thumb/)?[0-9a-f]/[0-9a-f]{2}/([^/?#]+)', url or '')
    return 'File:' + urllib.parse.unquote(m.group(1)) if m else None


def strip_tags(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', s or ''))).strip()


def commons_credit(file_title):
    """'Author, Licence' for a Commons file, or '' if it can't be read."""
    try:
        q = urllib.parse.urlencode({'action': 'query', 'titles': file_title, 'prop': 'imageinfo',
                                    'iiprop': 'extmetadata', 'format': 'json', 'formatversion': 2})
        page = get_json(f'https://commons.wikimedia.org/w/api.php?{q}', tries=2)['query']['pages'][0]
        meta = page['imageinfo'][0]['extmetadata']
        artist = strip_tags(meta.get('Artist', {}).get('value', ''))
        artist = re.sub(r'^(?:photo(?:graph)?(?:\s+by)?|by)\s*:?\s+', '', artist, flags=re.I)[:80]
        licence = strip_tags(meta.get('LicenseShortName', {}).get('value', ''))[:40]
        return ', '.join(p for p in (artist, licence) if p)
    except Exception:               # noqa: BLE001 (the plain Commons link still credits it)
        return ''


# ── one fact ─────────────────────────────────────────────────────────────────

def main_photo(topic):
    """(url, caption) of the first Commons photo in the topic, or (None, None)."""
    options = [(topic.get('image_url'), None)]
    options += [(b.get('url'), b.get('caption')) for b in (topic.get('blocks') or []) if b.get('type') == 'img']
    for k in range(1, 6):
        options.append((topic.get(f'layer_{k}_image'), topic.get(f'layer_{k}_image_caption')))
    for url, caption in options:
        if url and commons_file(url):
            return url, re.sub(r'\s*\(via Wikipedia\)\s*$', '', caption or '').strip() or None
    return None, None


def opening_and_rest(topic):
    """(paragraphs of the first section, titles of the other sections)."""
    blocks = topic.get('blocks') or []
    if blocks:
        opening, rest, in_first = [], [], True
        for b in blocks:
            if b.get('type') == 'h':
                in_first = False
                if (b.get('text') or '').strip():
                    rest.append(b['text'].strip())
            elif in_first and b.get('type') == 'p' and (b.get('text') or '').strip():
                opening.append(b['text'].strip())
        return opening, rest
    n = int(topic.get('num_layers') or 5)
    opening = [p.strip() for p in (topic.get('layer_1_body') or '').split('\n') if p.strip()]
    rest = [topic.get(f'layer_{k}_title').strip() for k in range(2, n + 1) if (topic.get(f'layer_{k}_title') or '').strip()]
    return opening, rest


def entry_for(topic, old=None):
    """What index.json keeps about a fact: only what its page shows, never the rest of the article."""
    url, caption = main_photo(topic)
    file_title = commons_file(url) if url else None
    credit = (old or {}).get('credit') if old and old.get('image') == url else None
    if credit is None and file_title:
        credit = commons_credit(file_title)
    opening, rest = opening_and_rest(topic)
    page = urllib.parse.quote(file_title.replace(' ', '_'), safe=':') if file_title else None
    return {
        'id': str(topic['id']), 'slug': fact_slug(topic), 'date': topic['date'], 'category': topic.get('tier', ''),
        'label': LABELS.get(topic.get('tier', ''), (topic.get('tier') or 'Facts').title()),
        'headline': (topic.get('headline') or '').strip(), 'hook': (topic.get('hook') or '').strip(),
        'image': url, 'caption': caption, 'credit': credit or '',
        'cover': bool(url) and url == topic.get('image_url'),   # the fact's own cover photo, not one from further in
        'credit_url': f'https://commons.wikimedia.org/wiki/{page}' if page else None,
        'opening': opening, 'rest': rest,
    }


# ── HTML ─────────────────────────────────────────────────────────────────────

E = html.escape
FONT = '<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap" rel="stylesheet">'

CSS = """
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#080c14;--panel:#0f1522;--line:rgba(122,138,160,.2);--t1:#f0f4ff;--t2:#b4c2d8;--t3:#7a8aa0;
--green:#188C67;--green-hi:#21a87d;--yellow:#FFD54A;--blue:#3d9aff}
html{-webkit-text-size-adjust:100%}
body{background:var(--bg);color:var(--t1);font-family:Montserrat,system-ui,sans-serif;line-height:1.6;min-height:100vh}
a{color:inherit}
.top{border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:0;z-index:5}
.top-in{max-width:760px;margin:0 auto;padding:10px 16px;display:flex;align-items:center;gap:10px}
.brand{display:flex;align-items:center;gap:9px;text-decoration:none;font-weight:800;font-size:1.05rem}
.brand img{width:32px;height:32px;border-radius:8px}
.brand small{font-weight:600;color:var(--t3);font-size:.78rem;margin-left:2px}
.top .app-btn{margin-left:auto;padding:8px 14px;font-size:.85rem}
.wrap{max-width:680px;margin:0 auto;padding:28px 16px 48px}
.meta{font-size:.8rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--t3);margin-bottom:12px}
.meta .cat{color:var(--yellow)}
h1{overflow-wrap:anywhere;font-weight:800;font-size:clamp(1.7rem,6vw,2.5rem);line-height:1.12;letter-spacing:-.02em;margin-bottom:16px}
.lead{font-family:"Source Serif 4",Georgia,serif;font-size:1.25rem;line-height:1.55;color:var(--t1);margin-bottom:22px}
figure{margin:0 0 24px}
figure img{width:100%;height:auto;max-height:460px;object-fit:cover;border-radius:14px;background:var(--panel);display:block}
figcaption{font-size:.78rem;color:var(--t3);margin-top:8px;line-height:1.5}
figcaption a{color:var(--t3)}
.body p{font-family:"Source Serif 4",Georgia,serif;font-size:1.1rem;line-height:1.75;color:var(--t2);margin-bottom:18px}
.more{border:1px solid var(--line);background:var(--panel);border-radius:16px;padding:22px 20px;margin:30px 0}
.more h2{font-size:1.2rem;font-weight:800;margin-bottom:6px}
.more p{color:var(--t2);font-size:.95rem;margin-bottom:14px}
.toc{list-style:none;margin:0 0 18px;border-left:3px solid var(--green);padding-left:14px}
.toc li{font-family:"Source Serif 4",Georgia,serif;color:var(--t1);padding:3px 0}
.app-btn{display:inline-flex;align-items:center;gap:8px;background:var(--green);color:#fff;text-decoration:none;
font-weight:800;border-radius:999px;padding:13px 22px;font-size:1rem;border:0;cursor:pointer}
.app-btn:hover{background:var(--green-hi)}
.fine{font-size:.8rem;color:var(--t3);margin-top:10px}
.same h2,.list h2{font-size:.85rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--t3);margin:34px 0 10px}
.same ul,.list ul{list-style:none}
.same li,.list li{border-top:1px solid var(--line)}
.same a,.list a{display:block;padding:12px 0;text-decoration:none;font-weight:700;line-height:1.35}
.same a span,.list a span{display:block;font-size:.72rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--t3);margin-bottom:2px}
.same a:hover,.list a:hover{color:var(--yellow)}
.challenge{display:none;text-align:center;padding:12px 0 8px}
.challenge .tf{font-weight:800;color:var(--yellow);letter-spacing:.08em;text-transform:uppercase;font-size:.9rem;margin-bottom:14px}
.challenge .claim{font-family:"Source Serif 4",Georgia,serif;font-size:1.45rem;line-height:1.5;margin-bottom:26px}
.challenge .row{display:flex;gap:12px;justify-content:center}
.challenge button{font:inherit;font-weight:800;font-size:1.05rem;padding:14px 0;width:140px;border-radius:999px;cursor:pointer;
border:2px solid var(--t1);background:transparent;color:var(--t1)}
.challenge button:hover{background:rgba(255,255,255,.08)}
.challenge .by{font-size:.85rem;color:var(--t3);margin-top:20px}
.verdict{display:none;font-weight:800;font-size:1.1rem;color:var(--yellow);margin-bottom:10px}
body.ask .challenge{display:block}
body.ask #fact{display:none}
body.told .verdict{display:block}
footer{border-top:1px solid var(--line);padding:22px 16px 40px;text-align:center;font-size:.85rem;color:var(--t3)}
footer a{color:var(--t2);text-decoration:none;margin:0 8px;white-space:nowrap}
footer a:hover{color:var(--t1)}
.intro{color:var(--t2);margin-bottom:22px}
"""

SCRIPT = """
(function(){
  var q = new URLSearchParams(location.search);
  var challenge = q.has('challenge');
  var ref = (q.get('ref') || q.get('utm_source') || '').toLowerCase().replace(/[^a-z0-9_]/g, '').slice(0, 30);
  var ct = challenge ? 'challenge' : (ref || 'web');
  document.querySelectorAll('a[data-store]').forEach(function(a){
    a.href = 'https://apps.apple.com/app/apple-store/id%(app)s?pt=%(pt)s&ct=' + ct + '&mt=8';
  });
  if (!challenge || !document.getElementById('ask')) return;
  document.body.classList.add('ask');
  document.querySelectorAll('#ask button').forEach(function(b){
    b.addEventListener('click', function(){
      var right = b.getAttribute('data-guess') === 'true';
      document.getElementById('verdict').textContent = right ? 'You got it: it\\u2019s true.' : 'Surprise: it\\u2019s true.';
      document.body.classList.remove('ask');
      document.body.classList.add('told');
      window.scrollTo(0, 0);
    });
  });
})();
""" % {'app': APP_ID, 'pt': PROVIDER}


def head(title, description, canonical, image=None, kind='article', extra='', share_title=None):
    """share_title replaces the title in link previews (Messages, Facebook) but not in search results."""
    tags = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta name="apple-itunes-app" content="app-id={APP_ID}">',
        f'<title>{E(title)}</title>',
        f'<meta name="description" content="{E(description)}">',
        f'<link rel="canonical" href="{E(canonical)}">',
        f'<meta property="og:type" content="{kind}">',
        '<meta property="og:site_name" content="Kurious">',
        f'<meta property="og:title" content="{E(share_title or title)}">',
        f'<meta property="og:description" content="{E(description)}">',
        f'<meta property="og:url" content="{E(canonical)}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}">',
        '<link rel="icon" type="image/png" href="/kurious/assets/kurious-icon-180.png">',
        '<link rel="apple-touch-icon" href="/kurious/assets/kurious-icon-180.png">',
        '<meta name="theme-color" content="#080c14">',
        '<meta name="referrer" content="strict-origin-when-cross-origin">',
    ]
    if image:
        tags.append(f'<meta property="og:image" content="{E(image)}">')
    return '\n'.join(tags) + '\n' + FONT + '\n<link rel="stylesheet" href="/kurious/assets/facts.css">\n' + extra


def top_bar():
    return ('<header class="top"><div class="top-in">'
            '<a class="brand" href="/kurious/facts/"><img src="/kurious/assets/kurious-icon-180.png" alt="" width="32" height="32">'
            'Kurious <small>by Galapptic</small></a>'
            f'<a class="app-btn" data-store href="{store_link("web")}">Get the app</a>'
            '</div></header>')


def footer():
    return ('<footer><a href="/kurious/facts/">All facts</a><a href="/app-kurious.html">About Kurious</a>'
            '<a href="/">Galapptic</a><a href="/kurious-privacy.html">Privacy</a></footer>')


def fact_page(e, same_day, today):
    d = date.fromisoformat(e['date'])
    past = d < today
    url = f'{SITE}{FACTS_PATH}/{e["slug"]}'
    description = e['hook'] or e['headline']
    if len(description) > 160:
        description = description[:157].rsplit(' ', 1)[0] + '...'
    ld = {'@context': 'https://schema.org', '@type': 'Article', 'headline': e['headline'][:110],
          'description': description, 'datePublished': e['date'], 'url': url, 'articleSection': e['label'],
          'publisher': {'@type': 'Organization', 'name': 'Galapptic', 'url': SITE}}
    if e['image']:
        ld['image'] = e['image']
    ld_json = json.dumps(ld, ensure_ascii=False).replace('</', '<\\/')
    extra = f'<script type="application/ld+json">{ld_json}</script>'
    out = ['<!doctype html><html lang="en"><head>',
           # Link previews ask the question rather than give the answer: these links are mostly the app's challenges
           head(f'{e["headline"]} | Kurious', description, url, e['image'], extra=extra,
                share_title='True or false?' if e['hook'] else None),
           '</head><body>', top_bar(), '<main class="wrap">']
    if e['hook']:
        out.append('<section class="challenge" id="ask" aria-label="True or false?">'
                   '<p class="tf">True or false?</p>'
                   f'<p class="claim">{E(e["hook"])}</p>'
                   '<div class="row"><button type="button" data-guess="true">True</button>'
                   '<button type="button" data-guess="false">False</button></div>'
                   '<p class="by">A friend challenged you with this fact from Kurious.</p></section>')
    out.append('<article id="fact">')
    out.append('<p class="verdict" id="verdict"></p>')
    out.append(f'<p class="meta"><span class="cat">{E(e["label"])}</span> &middot; {E(nice_date(d))}</p>')
    out.append(f'<h1>{E(e["headline"])}</h1>')
    if e['hook']:
        out.append(f'<p class="lead">{E(e["hook"])}</p>')
    if e['image']:
        alt = e['caption'] or e['headline']
        cap = E(e['caption']) + ' ' if e['caption'] else ''
        credit = f'Photo: {E(e["credit"])}, via Wikimedia Commons' if e['credit'] else 'Photo: Wikimedia Commons'
        link = f'<a href="{E(e["credit_url"])}" rel="nofollow noopener" target="_blank">{credit}</a>' if e['credit_url'] else credit
        out.append(f'<figure><img src="{E(e["image"])}" alt="{E(alt)}" loading="eager" decoding="async">'
                   f'<figcaption>{cap}{link}</figcaption></figure>')
    if past and e['opening']:
        out.append('<div class="body">' + ''.join(f'<p>{E(p)}</p>' for p in e['opening']) + '</div>')
    out.append('<aside class="more">')
    if past:
        out.append('<h2>Read the rest in Kurious</h2>')
        if e['rest']:
            out.append('<p>Still to come in this story:</p><ul class="toc">' +
                       ''.join(f'<li>{E(t)}</li>' for t in e['rest']) + '</ul>')
    else:
        out.append('<h2>Today&rsquo;s full story is in Kurious</h2>'
                   '<p>Kurious gives you seven new facts like this every day, each with the whole story behind it.</p>')
    out.append(f'<a class="app-btn" data-store href="{store_link("web")}">Get Kurious, free</a>'
               '<p class="fine">7 new facts every day &middot; Free on the App Store for iPhone and iPad</p></aside>')
    others = [o for o in same_day if o['id'] != e['id']]
    if others:
        out.append(f'<nav class="same"><h2>More facts from {E(nice_date(d))}</h2><ul>' +
                   ''.join(f'<li><a href="{FACTS_PATH}/{o["slug"]}"><span>{E(o["label"])}</span>{E(o["headline"])}</a></li>'
                           for o in others) + '</ul></nav>')
    out.append('</article></main>')
    out.append(footer())
    out.append('<script src="/kurious/assets/facts.js"></script></body></html>')
    return '\n'.join(out)


def index_page(entries):
    url = f'{SITE}{FACTS_PATH}/'
    desc = 'Surprising, true facts from Kurious, a new set of seven every day, with the story behind each one.'
    out = ['<!doctype html><html lang="en"><head>',
           head('Fun facts of the day | Kurious', desc, url, kind='website'),
           '</head><body>', top_bar(), '<main class="wrap">',
           '<h1>Fun facts of the day</h1>',
           '<p class="intro">Every day Kurious finds seven surprising, true facts and tells the story behind each one. '
           'Here is every fact so far; the whole stories are in the app.</p>',
           f'<a class="app-btn" data-store href="{store_link("web")}">Get Kurious, free</a>']
    by_day = {}
    for e in entries:
        by_day.setdefault(e['date'], []).append(e)
    for day in sorted(by_day, reverse=True):
        out.append(f'<section class="list"><h2>{E(nice_date(date.fromisoformat(day)))}</h2><ul>' +
                   ''.join(f'<li><a href="{FACTS_PATH}/{e["slug"]}"><span>{E(e["label"])}</span>{E(e["headline"])}</a></li>'
                           for e in by_day[day]) + '</ul></section>')
    out.append('</main>')
    out.append(footer())
    out.append('<script src="/kurious/assets/facts.js"></script></body></html>')
    return '\n'.join(out)


def sitemap(entries, today):
    urls = [(f'{SITE}{FACTS_PATH}/', today.isoformat())]
    for e in entries:
        d = date.fromisoformat(e['date'])
        urls.append((f'{SITE}{FACTS_PATH}/{e["slug"]}', min(d + timedelta(days=1), today).isoformat()))
    body = ''.join(f'<url><loc>{E(u)}</loc><lastmod>{m}</lastmod></url>' for u, m in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>\n')


# ── the run ──────────────────────────────────────────────────────────────────

PUBLIC_KEYS = ('id', 'slug', 'date', 'category', 'label', 'headline', 'hook', 'image', 'cover', 'credit', 'credit_url')


def run(root, today, rebuild_all=False, fetch=day_topics, log=print):
    """Fetch the days that need it, write their pages, then the list page, the sitemap, index.json (small: for the
    404 redirect and the Friday Pinterest pins) and _state.json (what the pages show, for the next run; Jekyll leaves
    files starting with _ off the site)."""
    facts = Path(root) / 'kurious' / 'facts'
    facts.mkdir(parents=True, exist_ok=True)
    assets = Path(root) / 'kurious' / 'assets'     # shared by every page, so a design change rewrites two files
    assets.mkdir(parents=True, exist_ok=True)
    (assets / 'facts.css').write_text(CSS.strip() + '\n', encoding='utf-8')
    (assets / 'facts.js').write_text(SCRIPT.strip() + '\n', encoding='utf-8')
    state_file = facts / '_state.json'
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {}
    days = state.get('days', {})                       # date -> ids, including days with none
    entries = {e['id']: e for e in state.get('facts', [])}

    all_days = [FIRST_DAY + timedelta(days=k) for k in range((today - FIRST_DAY).days + 1)]
    wanted = [d for d in all_days if d.isoformat() not in days or d >= today - timedelta(days=1)]
    log(f'Fetching {len(wanted)} day(s), up to {today}')
    changed_days = set()
    for d in wanted:
        key = d.isoformat()
        try:
            topics = [t for t in fetch(d) if t.get('id') and t.get('headline') and t.get('date') == key]
        except Exception as ex:     # noqa: BLE001 (leave that day as it was; the next run tries again)
            log(f'  {key}: {ex}')
            continue
        old_ids = days.get(key, [])
        new = [entry_for(t, entries.get(str(t['id']))) for t in topics]
        for gone in set(old_ids) - {e['id'] for e in new}:
            old = entries.pop(gone, None)
            if old:
                (facts / f'{old["slug"]}.html').unlink(missing_ok=True)
        for e in new:
            old = entries.get(e['id'])
            if old and old['slug'] != e['slug']:
                (facts / f'{old["slug"]}.html').unlink(missing_ok=True)
            entries[e['id']] = e
        days[key] = [e['id'] for e in new]
        changed_days.add(key)
        if topics:
            log(f'  {key}: {len(topics)} fact(s)')

    ordered = sorted(entries.values(), key=lambda e: e['label'])
    ordered = sorted((e for e in ordered if e['date'] <= today.isoformat()), key=lambda e: e['date'], reverse=True)
    by_day = {}
    for e in sorted(ordered, key=lambda e: e['label']):
        by_day.setdefault(e['date'], []).append(e)
    written = 0
    for e in ordered:
        page = facts / f'{e["slug"]}.html'
        if rebuild_all or e['date'] in changed_days or not page.exists():
            page.write_text(fact_page(e, by_day[e['date']], today), encoding='utf-8')
            written += 1
    (facts / 'index.html').write_text(index_page(ordered), encoding='utf-8')
    (facts / 'sitemap.xml').write_text(sitemap(ordered, today), encoding='utf-8')
    state_file.write_text(json.dumps({
        'about': 'Kurious fact pages (tools/kurious_facts.py). Only what the pages show; never the full articles.',
        'days': dict(sorted(days.items())),
        'facts': ordered,
    }, ensure_ascii=False, indent=0), encoding='utf-8')
    (facts / 'index.json').write_text(json.dumps({
        'updated': today.isoformat(),
        'facts': [{k: e[k] for k in PUBLIC_KEYS} for e in ordered],
    }, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    log(f'Wrote {written} page(s); {len(ordered)} facts in all')
    return ordered


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rebuild-all', action='store_true', help='rewrite every page (after a design change); the days '
                    'already done come from _state.json, not the backend')
    ap.add_argument('--today', help='YYYY-MM-DD (default: today in America/Chicago)')
    ap.add_argument('--root', default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else chicago_today()
    run(args.root, today, rebuild_all=args.rebuild_all)


if __name__ == '__main__':
    sys.exit(main())
