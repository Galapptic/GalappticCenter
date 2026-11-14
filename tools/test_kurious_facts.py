"""Offline tests for tools/kurious_facts.py. Run: python -m unittest discover tools"""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kurious_facts as k  # noqa: E402

# The same cases are checked against the app's services/factLinks.js; keep them in step.
SLUG_CASES = [
    ("Flying Buttresses Don't Hold Up Walls—They Hold Them Down", 'flying-buttresses-dont-hold-up-walls-they-hold-them-down'),
    ('The Sahara Was Green Just 5,000 Years Ago', 'the-sahara-was-green-just-5-000-years-ago'),
    ('Why Pokémon Names Change in Café Menus', 'why-pokemon-names-change-in-cafe-menus'),
    ('The Game Your Grandparents Played Has Been Mathematically Perfected', 'the-game-your-grandparents-played-has-been-mathematically'),
    ('???', ''),
]

TOPIC = {
    'id': 'F0A479E9-1a97-4481-bb50-a5f9db87e795', 'date': '2026-11-13', 'tier': 'architecture',
    'headline': 'Flying Buttresses Hold Walls Down', 'hook': 'They push against the building, not gravity.',
    'image_url': 'https://upload.wikimedia.org/wikipedia/en/thumb/a/ab/Fair.jpg/330px-Fair.jpg',
    'blocks': [
        {'type': 'p', 'text': 'First paragraph.'}, {'type': 'p', 'text': 'Second <paragraph>.'},
        {'type': 'h', 'text': 'The problem'}, {'type': 'p', 'text': 'SECRET body text.'},
        {'type': 'img', 'url': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/28/Notre_Dame_de_Chartres.jpg/960px-Notre_Dame_de_Chartres.jpg',
         'caption': 'Chartres Cathedral (via Wikipedia)'},
        {'type': 'h', 'text': 'Thrust'}, {'type': 'p', 'text': 'More SECRET text.'},
    ],
}


class Links(unittest.TestCase):
    def test_slugs(self):
        for headline, want in SLUG_CASES:
            self.assertEqual(k.slugify(headline), want, headline)

    def test_fact_slug_ends_in_the_id(self):
        self.assertEqual(k.fact_slug(TOPIC), 'flying-buttresses-hold-walls-down-f0a479e9')
        self.assertEqual(k.fact_slug(dict(TOPIC, headline='???')), 'f0a479e9')

    def test_chicago_today(self):
        self.assertEqual(k.chicago_today(datetime(2026, 11, 14, 5, 59, tzinfo=timezone.utc)), date(2026, 11, 13))
        self.assertEqual(k.chicago_today(datetime(2026, 11, 14, 6, 0, tzinfo=timezone.utc)), date(2026, 11, 14))
        self.assertEqual(k.chicago_today(datetime(2026, 7, 4, 4, 59, tzinfo=timezone.utc)), date(2026, 7, 3))
        self.assertEqual(k.chicago_today(datetime(2026, 7, 4, 5, 0, tzinfo=timezone.utc)), date(2026, 7, 4))


class Pages(unittest.TestCase):
    def setUp(self):
        self.saved = k.commons_credit
        k.commons_credit = lambda title: 'Jane Doe, CC BY 3.0'

    def tearDown(self):
        k.commons_credit = self.saved

    def test_entry_keeps_only_the_opening_and_skips_fair_use_photos(self):
        e = k.entry_for(TOPIC)
        self.assertEqual(e['opening'], ['First paragraph.', 'Second <paragraph>.'])
        self.assertEqual(e['rest'], ['The problem', 'Thrust'])
        self.assertIn('/commons/', e['image'])                       # the en.wikipedia fair-use cover is skipped
        self.assertFalse(e['cover'])                                  # so the photo is one from further in
        self.assertEqual(e['caption'], 'Chartres Cathedral')
        self.assertEqual(e['credit_url'], 'https://commons.wikimedia.org/wiki/File:Notre_Dame_de_Chartres.jpg')
        self.assertNotIn('SECRET', json.dumps(e))

    def test_today_shows_no_opening_and_later_days_do(self):
        e = k.entry_for(TOPIC)
        on_the_day = k.fact_page(e, [e], date(2026, 11, 13))
        later = k.fact_page(e, [e], date(2026, 11, 14))
        self.assertNotIn('First paragraph.', on_the_day)
        self.assertIn('Today&rsquo;s full story is in Kurious', on_the_day)
        self.assertIn('First paragraph.', later)
        self.assertIn('Second &lt;paragraph&gt;.', later)               # escaped
        self.assertIn('<li>Thrust</li>', later)
        for page in (on_the_day, later):
            self.assertIn('True or false?', page)
            self.assertIn('app-id=6766752682', page)
            self.assertIn('ct=web', page)
            self.assertNotIn('SECRET', page)

    def test_run_writes_pages_and_never_a_future_day(self):
        future = dict(TOPIC, id='aaaaaaaa-0000', date='2026-11-15', headline='Tomorrow')
        days = {'2026-11-13': [TOPIC], '2026-11-14': [], '2026-11-15': [future]}
        asked = []

        def fetch(d):
            asked.append(d.isoformat())
            return days.get(d.isoformat(), [])

        saved = k.FIRST_DAY
        k.FIRST_DAY = date(2026, 11, 12)
        try:
            with tempfile.TemporaryDirectory() as root:
                k.run(root, date(2026, 11, 14), fetch=fetch, log=lambda *_: None)
                facts = Path(root) / 'kurious' / 'facts'
                self.assertTrue((facts / 'flying-buttresses-hold-walls-down-f0a479e9.html').exists())
                index = json.loads((facts / 'index.json').read_text(encoding='utf-8'))
                self.assertEqual([f['slug'] for f in index['facts']], ['flying-buttresses-hold-walls-down-f0a479e9'])
                self.assertNotIn('opening', index['facts'][0])
                self.assertIn('flying-buttresses-hold-walls-down-f0a479e9', (facts / 'sitemap.xml').read_text())
                # the next run only asks for days it hasn't seen, plus yesterday and today
                asked.clear()
                k.run(root, date(2026, 11, 14), fetch=fetch, log=lambda *_: None)
                self.assertEqual(asked, ['2026-11-13', '2026-11-14'])
        finally:
            k.FIRST_DAY = saved
        self.assertNotIn('2026-11-15', asked)


if __name__ == '__main__':
    unittest.main()
