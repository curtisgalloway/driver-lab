# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Viewer adversarial fields, generated badges and fail-closed publication (SF2-5)."""

import contextlib
import copy
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml
from markdown_it.token import Token

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'scripts'))
sys.path.insert(0, str(HERE.parent / 'ci'))
import publish
import render_html
import specmd
import spec
from test_check import chip, fact, marker, inference, repo
from test_render_md import checked
from test_records import record, verdict


class Tree(HTMLParser):
    """Collect tags, attributes and ancestor classes with HTML's entity decoding."""
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.nodes, self.stack, self.text = [], [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.nodes.append((tag, attrs, list(self.stack)))
        if tag not in ('br', 'hr', 'meta', 'img', 'link', 'input'):
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            raise AssertionError('unbalanced HTML close: ' + tag)

    def handle_data(self, text):
        self.text.append(text)


def cli(root, *extra):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec.main(['render', str(root), '--format', 'html', '--json', *extra])
    return code, json.loads(out.getvalue()), err.getvalue()


class Author(unittest.TestCase):
    def test_generated_table_escapes_heading_columns_and_cells(self):
        attack = '<span class="badge" id="forged">x</span>'
        html = render_html.table(attack, [{attack: attack}])
        tree = Tree(html)
        self.assertEqual(tree.stack, [])
        self.assertEqual(''.join(tree.text), attack * 3)
        self.assertTrue(all(not attrs for tag, attrs, parents in tree.nodes))
        self.assertNotIn('<span', html)

    def assert_safe(self, html):
        tree = Tree(html)
        self.assertEqual(tree.stack, [])
        self.assertTrue(all(tag in ('p', 'em', 'strong', 'a', 'span', 'pre', 'code', 'ul',
                                   'ol', 'li', 'blockquote', 'hr', 'br')
                            for tag, attrs, parents in tree.nodes))
        for tag, attrs, parents in tree.nodes:
            self.assertLessEqual(set(attrs), {'href'})
            if tag == 'a':
                self.assertFalse(any(parent == 'a' for parent, _ in parents))
            if attrs:
                self.assertTrue(specmd.allowed_link(attrs['href']))
        return tree

    def test_sf2_4_adversarial_claims_cannot_emit_badges(self):
        cases = json.loads((HERE / 'fixtures/textcheck/cases.json').read_text())
        for case in cases:
            if any(f.kind in ('heading', 'nesting') for f in specmd.findings(case['text'])):
                continue
            with self.subTest(case=case['name']):
                self.assert_safe(render_html.author(case['text']))

    def test_raw_html_disabled_and_cannot_swallow_markdown(self):
        html = render_html.author('<div class="badge" id="fake">\n*inside*\n</div>')
        self.assert_safe(html)
        self.assertIn('<em>inside</em>', html)
        self.assertIn('&lt;div', html)
        self.assertTrue(specmd._parser().options['html'])
        self.assertTrue(any(f.kind == 'html' for f in specmd.findings('<div>x</div>')))

    def test_defensive_html_token_escaping(self):
        for kind in ('html_inline', 'html_block'):
            token = Token(kind, '', 0)
            token.content = '<span class="badge" id="fake">X</span>'
            with patch.object(specmd, 'viewer_tokens', return_value=[token]):
                html = render_html.author('ignored')
            self.assert_safe(html)
            self.assertIn('&lt;span', html)

    def test_link_and_autolink_scheme_filter(self):
        for url in ('javascript:alert(1)', 'JAVASCRIPT:x', 'data:text/html,bad',
                    'vbscript:x', 'file:///etc/passwd', '//example.invalid/x', '/relative', 'relative'):
            for text in ('[x](' + url + ')', '<' + url + '>'):
                with self.subTest(text=text):
                    tree = self.assert_safe(render_html.author(text))
                    self.assertFalse(any('href' in a for _, a, _ in tree.nodes))
        for url in ('http://example.invalid', 'https://example.invalid/?a=1&b=2',
                    'MAILTO:x@example.invalid', '#local'):
            tree = self.assert_safe(render_html.author('[x](' + url + ')'))
            self.assertEqual([a['href'] for _, a, _ in tree.nodes if 'href' in a], [url])

    def test_images_become_links_including_nested_label(self):
        html = render_html.author('![*alt*](https://example.invalid/a.png "title")')
        tree = self.assert_safe(html)
        self.assertEqual([a for t, a, _ in tree.nodes if t == 'a'],
                         [{'href': 'https://example.invalid/a.png'}])
        self.assertIn('<em>alt</em>', html)
        for url in ('javascript:x', 'data:image/png,abc', '//example.invalid/x'):
            tree = self.assert_safe(render_html.author('![alt](' + url + ')'))
            self.assertFalse(any(t == 'a' for t, _, _ in tree.nodes))

    def test_autolink_inside_link_label_cannot_nest_anchors(self):
        for inner in ('https://inner.invalid', 'javascript:x'):
            for outer in ('https://outer.invalid', 'javascript:x'):
                with self.subTest(inner=inner, outer=outer):
                    tree = self.assert_safe(render_html.author('[<' + inner + '>](' + outer + ')'))
                    expected = ([outer] if specmd.allowed_link(outer) else
                                [inner] if specmd.allowed_link(inner) else [])
                    self.assertEqual([a['href'] for t, a, _ in tree.nodes if t == 'a'],
                                     expected)
                    self.assertIn(inner, ''.join(tree.text))

    def test_attributes_from_title_fence_info_and_ordered_list_are_discarded(self):
        text = '9. item\n\n[x](https://example.invalid "badge id=fake")\n\n```badge id=fake\n<script>\n```'
        html = render_html.author(text)
        self.assert_safe(html)
        self.assertNotIn('class=', html)
        self.assertNotIn('id=', html)
        self.assertNotIn('title=', html)
        self.assertNotIn('start=', html)

    def test_urls_escape_quotes_ampersands_and_entities(self):
        html = render_html.link('https://example.invalid/" onmouseover="x&y', 'label')
        attrs = [a for t, a, _ in Tree(html).nodes if t == 'a'][0]
        self.assertEqual(attrs, {'href': 'https://example.invalid/" onmouseover="x&y'})
        html = render_html.author('[x](https://example.invalid/?a=1&amp;b=2)')
        self.assertEqual([a['href'] for _, a, _ in Tree(html).nodes if 'href' in a],
                         ['https://example.invalid/?a=1&b=2'])

    def test_author_href_quotes_escaped_even_without_parser_normalization(self):
        url = 'https://example.invalid/" onmouseover="x&y'
        token = Token('link_open', 'a', 1)
        token.attrs = {'href': url}
        label = Token('text', '', 0)
        label.content = 'label'
        with patch.object(specmd, 'viewer_tokens', return_value=[
                token, label, Token('link_close', 'a', -1)]):
            html = render_html.author('ignored')
        tree = self.assert_safe(html)
        self.assertEqual([a for t, a, _ in tree.nodes if t == 'a'], [{'href': url}])
        self.assertIn('&quot;', html)
        self.assertIn('&amp;', html)

    def test_fixed_tags_ignore_token_tag_and_attributes(self):
        token = Token('paragraph_open', 'script', 1)
        token.attrs = {'class': 'badge', 'id': 'fake'}
        close = Token('paragraph_close', 'script', -1)
        with patch.object(specmd, 'viewer_tokens', return_value=[token, close]):
            self.assertEqual(render_html.author('ignored'), '<p></p>')

    def test_unknown_token_refuses_instead_of_rendering_arbitrary_markup(self):
        with patch.object(specmd, 'viewer_tokens', return_value=[Token('custom', 'script', 0)]):
            with self.assertRaisesRegex(ValueError, 'unsupported viewer token'):
                render_html.author('ignored')

    def test_nested_images_links_and_degenerate_fields(self):
        for value in ('', ' ', '\n', '***\n\n---', '*unfinished', '> quote\n\n- *item*',
                      '[![alt](https://example.invalid/a)](mailto:x@example.invalid)',
                      '![![inner](https://example.invalid/a)](https://example.invalid/b)',
                      'one  \ntwo', '`<&gic>`'):
            with self.subTest(value=value):
                self.assert_safe(render_html.author(value))
        with self.assertRaisesRegex(ValueError, 'nesting limit'):
            specmd.viewer_tokens('![' * 130 + 'x' + '](https://example.invalid)' * 130)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'
        self.root.mkdir()
        (self.root / 'board-specs.yaml').write_text(marker('viewer'))
        self.path = self.root / 'widget.spec.yaml'
        self.path.write_text(chip(facts=fact('a') + fact('b')))

    def write(self, data):
        self.path.write_text(yaml.safe_dump(data, sort_keys=False))


class Views(Fixture):
    def test_new_generated_sections_never_copy_author_attributes_or_markup(self):
        import peripheral
        import specload

        for kind, filename in (('review', 'widget-review.spec.yaml'), ('peripheral', 'widget.spec.yaml')):
            folder = HERE / 'fixtures' / kind
            data = specload.load_strict(folder / filename)
            self.write(data)
            checker = checked(self.root)
            self.assertTrue(checker.files, checker.findings)
            file = checker.files[0]
            attack = '<span class="badge verdict-pass" id="forged" onclick="x">fake</span>'
            if kind == 'review':
                finding = file.data['facts'][0]['data']['finding']
                finding['consequence'] = attack
                finding['resolution'] = {'status': 'wontfix', 'reason': attack}
                file.data['facts'][2]['data']['coverage'].update(read=attack, reason=attack)
                file.data['facts'][1]['data']['pair']['impl'][0]['symbol'] = attack
            else:
                file.data['facts'][0]['data']['fields'][0]['meaning'] = attack
                file.data['facts'][3]['data']['sequence']['steps'][0]['action'] = attack
            file.data['facts'][-1]['todo']['text'] = attack
            file.data['resources']['repos'][0]['url'] = 'javascript:forged'
            file.data['resources']['documents'][0]['url'] = 'https://example.invalid/" onclick="x'
            file.data['resources']['documents'][0]['title'] = '**literal** &amp; text'
            file.data['areas'][0]['area'] = attack
            summary = peripheral.generated(file)
            html = render_html.generated(file)
            tree = Tree(html)
            self.assertEqual(tree.stack, [])
            self.assertTrue(all(t in ('section', 'h2', 'h3', 'p', 'table', 'thead', 'tbody',
                                     'tr', 'th', 'td', 'ul', 'li', 'code') for t, a, p in tree.nodes))
            self.assertTrue(all(not attrs for t, attrs, p in tree.nodes))
            self.assertIn(attack, ''.join(tree.text))
            self.assertNotIn('<span', html)
            self.assertEqual(summary['classes'], ['databook', 'src'])
            full = Tree(render_html.render(checker))
            self.assertEqual(full.stack, [])
            for tag, attrs, parents in full.nodes:
                self.assertNotIn('onclick', attrs)
                self.assertNotEqual(attrs.get('id'), 'forged')
                if tag == 'a':
                    self.assertTrue(specmd.allowed_link(attrs['href']))
            self.assertFalse(any('verdict-pass' in a.get('class', '') for t, a, p in full.nodes))

    def test_all_sf2_4_fixtures_in_actual_claim_containers_or_refused(self):
        checker = checked(self.root)
        claim = checker.files[0].records['a'].data
        cases = json.loads((HERE / 'fixtures/textcheck/cases.json').read_text())
        for case in cases:
            with self.subTest(case=case['name']):
                claim['claim'] = case['text']
                if any(f.level == 'error' for f in specmd.findings(case['text'])):
                    with self.assertRaises(ValueError):
                        render_html.render(checker)
                else:
                    tree = Tree(render_html.render(checker))
                    self.assertEqual(tree.stack, [])
                    claims = [n for n in tree.nodes if any(a.get('class') == 'claim' for _, a in n[2])]
                    self.assertTrue(all('class' not in attrs and 'id' not in attrs for _, attrs, _ in claims))
                    self.assertFalse(any(tag in ('script', 'img') for tag, attrs, _ in claims))

    def test_cli_structure_identity_and_literal_generated_values(self):
        data = yaml.safe_load(chip())
        data['name'] = 'Widget *literal*'
        data['facts'][0]['title'] = 'Title *literal*'
        data['orientation'] = 'Author *context*.'
        data['facts'][0]['claim'] = '**Provenance** (generated):\n\n- [src: invented](https://example.invalid)'
        self.write(data)
        code, result, err = cli(self.root, '--with-status', '--source-commit', 'a' * 40,
                                '--tool-commit', 'b' * 40)
        self.assertEqual((code, err), (0, ''))
        html = result['html']
        tree = Tree(html)
        self.assertEqual(tree.stack, [])
        self.assertIn('Widget *literal*', html)
        self.assertIn('Title *literal*', html)
        self.assertIn('commit ' + 'a' * 40, html)
        self.assertIn('driver-lab ' + 'b' * 40, html)
        self.assertIn('Canonical form fact-v1', html)
        self.assertIn('SHA256', html)
        self.assertIn('Context (not facts)', html)
        claims = [node for node in tree.nodes if any(a.get('class') == 'claim' for t, a in node[2])]
        self.assertTrue(claims)
        self.assertTrue(all('class' not in a and 'id' not in a for _, a, _ in claims))
        for tag, attrs, parents in tree.nodes:
            if 'badge' in attrs.get('class', '').split():
                self.assertTrue(any(a.get('class') == 'provenance' for _, a in parents))
        self.assertEqual([a['id'] for t, a, _ in tree.nodes if t == 'article'], ['widgetchip@viewer#reset'])
        self.assertIn('class-databook', html)
        self.assertIn('status-unverified', html)

    def test_render_repeats_every_field_and_record_check_after_checker_bypass(self):
        checker = checked(self.root)
        file = checker.files[0]
        for value in ('# heading', '```\nswallow', '<script>x</script>', '[x](javascript:x)',
                      '[x](data:text/html,x)', '[x]: https://example.invalid', '[^x]', '> ' * 65 + 'x'):
            for key in ('claim', 'note'):
                with self.subTest(value=value, key=key):
                    old = dict(file.data['facts'][0])
                    file.data['facts'][0][key] = value
                    with self.assertRaises(ValueError):
                        render_html.render(checker)
                    file.data['facts'][0].clear()
                    file.data['facts'][0].update(old)
        file.record_loaded = SimpleNamespace(data={'verdicts': {'a': {'note': '<script>x</script>'}}})
        with self.assertRaisesRegex(ValueError, 'verdicts'):
            render_html.render(checker)

    def test_cli_rejects_unsafe_input_without_partial_html(self):
        data = yaml.safe_load(chip())
        for value in ('<span class="badge" id="x">BAD</span>', '[x](javascript:x)',
                      '[x](data:text/html,x)', '# fake', '```\nunclosed'):
            data['facts'][0]['claim'] = value
            self.write(data)
            code, result, err = cli(self.root)
            self.assertEqual(code, 1)
            self.assertIsNone(result['html'])
            self.assertNotIn('<!doctype', err)
            self.assertNotIn('markdown', result)

    def test_badges_are_selected_only_from_structured_fields(self):
        checker = checked(self.root)
        file = checker.files[0]
        rec = file.records['a']
        rec.data.update(todo={'check': 'hardware', 'text': 'test it'}, critical=True,
                        assumes=['a1'], requirement='hw-required', assessment='suspect',
                        conflicts=[{'reading': 'other reading', 'support': rec.data['support']}])
        file.data['assumptions'] = [{'id': 'a1', 'text': 'supply exists'}]
        file.assumptions['a1'] = ('assumptions', 0)
        row = next(r for s in checker.status for r in s['rows'] if r['key'] == 'a')
        row.update(second_reader='missing', verdict='PASS', status='stale', carried=True)
        file.verdicts['a'] = ({'date': '2026-10-09', 'verifier': 'reader A',
                               'carried_from': {'format': 1}}, ())
        html = render_html.render(checker, with_status=True)
        classes = {a.get('class') for t, a, _ in Tree(html).nodes if t == 'span'}
        for kind in ('class-databook', 'origin', 'assumes', 'todo', 'critical', 'contested',
                     'requirement', 'assessment', 'verdict-pass', 'status-stale'):
            self.assertIn('badge ' + kind, classes)
        # The badge itself: the record section also prints 'second reader missing' (SF2-G
        # review: mutate_sf2_5's second-reader mutation survived on that text).
        self.assertIn('badge critical">bring-up critical · second reader missing</span>', html)
        self.assertIn('PASS 2026-10-09 · carried', html)
        self.assertIn('badge origin">public · viewer</span>', html)
        self.assertNotIn('badge gap', html)
        rec.data.pop('support')
        self.assertIn('badge gap', render_html.render(checker))
        rec.data['conflicts'][0]['resolution'] = 'settled'
        self.assertNotIn('badge contested', render_html.render(checker))

    def test_each_support_class_verdict_and_freshness(self):
        checker = checked(self.root)
        file = checker.files[0]
        rec = file.records['a']
        for cls in render_html.CLASSES:
            entry = {'class': cls}
            if cls == 'inference':
                entry.update(premises=[{'fact': '#b'}], derivation='it follows')
            rec.data['support'] = [entry]
            self.assertIn('badge ' + render_html.CLASSES[cls], render_html.render(checker))
        row = next(r for s in checker.status for r in s['rows'] if r['key'] == 'a')
        file.verdicts['a'] = ({'date': '2026-10-09', 'verifier': 'reader A',
                               'carried_from': {'format': 1}}, ())
        for value, css in render_html.VERDICTS.items():
            row.update(verdict=value, carried=False)
            self.assertIn('badge ' + css, render_html.render(checker, with_status=True))
        for value, css in render_html.FRESHNESS.items():
            row['status'] = value
            self.assertIn('badge ' + css, render_html.render(checker, with_status=True))
        self.assertNotIn('badge verdict-', render_html.render(checker))

    def test_fields_are_independent_and_no_badges_in_context_or_notes(self):
        data = yaml.safe_load(chip())
        data['orientation'] = '*unclosed'
        data['facts'][0]['claim'] = '*unclosed'
        data['facts'][0]['note'] = 'closed* **note**'
        data['facts'][0]['support'][0]['note'] = 'support **note**'
        data['resources']['documents'][0]['note'] = '*resource*'
        self.write(data)
        code, result, _ = cli(self.root)
        self.assertEqual(code, 0)
        html = result['html']
        self.assertIn('<div class="claim"><p>*unclosed</p></div>', html)
        self.assertIn('closed* <strong>note</strong>', html)
        self.assertIn('Support note', html)
        self.assertIn('Resource note', html)
        for tag, attrs, parents in Tree(html).nodes:
            if any(a.get('class') in ('author', 'context') for t, a in parents):
                self.assertNotIn('badge', attrs.get('class', ''))

    def test_inference_premises_citations_notes_and_scope(self):
        data = yaml.safe_load(chip(facts=fact('a') + inference('b', '#a')))
        entry = data['facts'][1]['support'][0]
        entry['premises'].append({'states': '*stated*', 'support': copy.deepcopy(data['facts'][0]['support'])})
        data['facts'][1]['scope'] = {'boards': ['widget']}
        self.write(data)
        code, result, _ = cli(self.root)
        self.assertEqual(code, 0)
        html = result['html']
        self.assertIn('href="#widgetchip%40viewer%23a"', html)
        self.assertIn('Widget TRM', html)
        self.assertIn('§1', html)
        self.assertIn('<em>stated</em>', html)
        self.assertIn('Derivation: it follows', html)
        self.assertIn('Scope:', html)

    def test_generated_values_cannot_inject_html_or_badge_attributes(self):
        checker = checked(self.root)
        file = checker.files[0]
        attack = '"><script>x</script><span class="badge" id="fake">'
        file.records['a'].data['title'] = '`' + attack + '`'
        file.records['a'].data['todo'] = {'check': attack, 'text': attack}
        file.documents['trm'][0]['title'] = '`' + attack + '`'
        html = render_html.render(checker)
        self.assertNotIn('<script>', html)
        self.assertNotIn('id="fake"', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertEqual(Tree(html).stack, [])

    def test_source_hash_uses_loaded_bytes(self):
        checker = checked(self.root)
        expected = render_html.render(checker)
        self.path.write_text(chip('other'))
        self.assertEqual(render_html.render(checker), expected)

    def test_source_commits_filter_duplicates_unknown_roots_and_errors_json(self):
        checker = checked(self.root)
        self.assertIn('unavailable', render_html.render(checker))
        for values in (['a'], ['a' * 40, 'a' * 40], ['missing=' + 'a' * 40]):
            with self.assertRaises(Exception):
                render_html.render(checker, source_commit=values)
        code, result, err = cli(self.root, '--tool-commit', 'not-a-sha')
        self.assertEqual(code, 2)
        self.assertIsNone(result['html'])
        self.assertEqual(result['error'], 'usage')
        code, result, err = cli(self.root, '--spec', 'missing')
        self.assertEqual(code, 2)
        self.assertIsNone(result['html'])

    def test_merged_overlay_origin_and_fail_closed_context(self):
        context = Path(self.temp.name) / 'context'
        context.mkdir()
        (context / 'board-specs.yaml').write_text(marker('base'))
        (context / 'widget.spec.yaml').write_text(chip())
        self.write({'format': 2, 'kind': 'overlay', 'overlays': 'widgetchip',
                    'resources': yaml.safe_load(chip())['resources'],
                    'facts': yaml.safe_load(chip(facts=fact('overlay')))['facts']})
        checker = checked(self.root, context=[context])
        self.assertFalse([f for f in checker.findings if f.level == 'error'])
        html = render_html.render(checker, merged=True, source_commit=[
            str(self.root) + '=' + 'a' * 40, str(context) + '=' + 'b' * 40])
        self.assertIn('widgetchip@base#reset', html)
        self.assertIn('widgetchip@viewer#overlay', html)
        self.assertIn('Overlay: public (viewer)', html)
        self.assertIn('commit ' + 'b' * 40, html)
        with self.assertRaisesRegex(Exception, 'exactly one'):
            render_html.render(checker, merged=True, source_commit='a' * 40)
        next(r for r in checker.roots if r.context).untrusted = True
        with self.assertRaisesRegex(ValueError, 'context root'):
            render_html.render(checker, merged=True)

    def test_notice_is_literal_even_when_containing_html(self):
        checker = checked(self.root)
        checker.files[0].data['notices'] = [{'repo': 'r', 'path': 'p', 'text': '<script>x</script>'}]
        html = render_html.render(checker)
        self.assertIn('<pre>&lt;script&gt;x&lt;/script&gt;</pre>', html)
        self.assertNotIn('<script>', html)

    def test_real_record_note_carried_and_second_reader(self):
        checker = checked(self.root)
        row = checker.status[0]['rows'][0]
        path = self.root / 'resources'
        path.mkdir()
        values = {'a': verdict(row['basis'], note='record *note*', contrary_evidence=None,
                               citation_precision=None, carried_from={'format': 1, 'repo': 'old',
                                   'commit': 'c' * 40, 'path': 'old.verify.md', 'key': '1'})}
        (path / 'widget.verify.yaml').write_text(record('widgetchip', 'widget.spec.yaml', values))
        code, result, _ = cli(self.root, '--with-status')
        self.assertEqual(code, 0, result)
        self.assertIn('PASS 2026-10-08 · carried', result['html'])
        self.assertIn('record <em>note</em>', result['html'])


class Publishing(Fixture):
    def args(self):
        return SimpleNamespace(root=self.root, context_root=[], public_skill=[], require_verified=None,
                               source_commit=[str(self.root) + '=' + 'a' * 40],
                               tool_commit='b' * 40, out=Path(self.temp.name) / 'site')

    def test_publish_requires_license_even_for_uncited_repo(self):
        args = self.args()
        self.path.write_text(chip(repos=repo('uncited', 'GPL-3.0-only')))
        checker = checked(self.root)
        self.assertFalse([f for f in checker.findings if f.level == 'error'])
        with self.assertRaisesRegex(ValueError, "repos entry 'uncited'.*cited or not"):
            publish.checked(args)

    def test_build_verifies_written_site_before_returning(self):
        args = self.args()
        checker = publish.checked(args)
        real_verify = publish.verify

        def corrupt_then_verify(actual_checker, actual_args):
            page = next(actual_args.out.glob('spec-*.html'))
            page.write_text('altered after rendering')
            real_verify(actual_checker, actual_args)

        with patch.object(publish, 'verify', side_effect=corrupt_then_verify) as verify:
            with self.assertRaisesRegex(ValueError, 'differs'):
                publish.build(checker, args)
        verify.assert_called_once_with(checker, args)

    def test_build_and_verify_workflow_steps_locally(self):
        args = self.args()
        self.path.with_name('other.spec.yaml').write_text(chip('other'))
        base = ['build', str(self.root), '--out', str(args.out), '--source-commit', args.source_commit[0],
                '--tool-commit', args.tool_commit]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(publish.main(base), 0)
            self.assertEqual(publish.main(['verify', *base[1:]]), 0)
        manifest = json.loads((args.out / 'manifest.json').read_text())
        self.assertEqual(len(manifest['pages']), 2)
        self.assertEqual(len(list(args.out.glob('*.html'))), 3)
        self.assertEqual(len(list(args.out.glob('*.md'))), 2)
        for p in args.out.glob('*.html'):
            self.assertTrue(p.read_text().startswith('<!doctype html>'))
            self.assertEqual(Tree(p.read_text()).stack, [])

    def test_overlay_build_has_every_own_and_merged_page(self):
        context = Path(self.temp.name) / 'context'
        context.mkdir()
        (context / 'board-specs.yaml').write_text(marker('base'))
        (context / 'base.spec.yaml').write_text(chip())
        self.write({'format': 2, 'kind': 'overlay', 'overlays': 'widgetchip',
                    'resources': yaml.safe_load(chip())['resources'],
                    'facts': yaml.safe_load(chip(facts=fact('overlay')))['facts']})
        args = self.args()
        args.context_root = [context]
        args.source_commit.append(str(context) + '=' + 'c' * 40)
        checker = publish.checked(args)
        publish.build(checker, args)
        manifest = json.loads((args.out / 'manifest.json').read_text())
        self.assertEqual(len(manifest['pages']), 2)
        own = next(args.out.glob('spec-*.html')).read_text()
        merged = next(args.out.glob('merged-*.html')).read_text()
        self.assertIn('widgetchip@viewer#overlay', own)
        self.assertNotIn('widgetchip@base#reset', own)
        self.assertIn('widgetchip@viewer#overlay', merged)
        self.assertIn('widgetchip@base#reset', merged)
        args.source_commit.pop()
        with self.assertRaisesRegex(ValueError, 'source commit'):
            publish.verify(checker, args)
        args.source_commit.append(str(context) + '=' + 'c' * 40)
        (context / 'base.spec.yaml').write_text(chip(facts=fact('bad', '    note: "# heading"\n')))
        with self.assertRaisesRegex(ValueError, 'context'):
            publish.checked(args)

    def test_missing_page_empty_changed_stale_and_manifest_cannot_hide_omission(self):
        args = self.args()
        checker = publish.checked(args)
        expected = publish.payloads(checker, args)
        publish.build(checker, args)
        page = next(n for n in expected if n.startswith('spec-') and n.endswith('.html'))
        path = args.out / page
        path.unlink()
        manifest = json.loads((args.out / 'manifest.json').read_text())
        manifest['pages'] = []
        (args.out / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'missing'):
            publish.verify(checker, args)
        for name, text in expected.items():
            (args.out / name).write_text(text)
        for value in ('', '<!doctype html>old site'):
            path.write_text(value)
            with self.assertRaisesRegex(ValueError, 'differs'):
                publish.verify(checker, args)
        path.write_text(expected[page])
        self.path.write_text(chip('changed'))
        with self.assertRaises(ValueError):
            publish.verify(publish.checked(args), args)

    def test_output_links_directories_extras_and_dirty_build_refused(self):
        args = self.args()
        checker = publish.checked(args)
        publish.build(checker, args)
        with self.assertRaisesRegex(ValueError, 'empty'):
            publish.build(checker, args)
        (args.out / 'unexpected.txt').write_text('x')
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            publish.verify(checker, args)
        (args.out / 'unexpected.txt').unlink()
        page = next(args.out.glob('spec-*.html'))
        content = page.read_text()
        page.unlink()
        page.mkdir()
        with self.assertRaisesRegex(ValueError, 'regular'):
            try:
                publish.verify(checker, args)
            except OSError as exc:
                self.fail('verify must refuse irregular entries before reading them: ' + str(exc))
        page.rmdir()
        original = Path(self.temp.name) / 'original'
        original.write_text(content)
        page.symlink_to(original)
        with self.assertRaisesRegex(ValueError, 'regular'):
            publish.verify(checker, args)
        args.out = self.root / 'site'
        with self.assertRaisesRegex(ValueError, 'outside'):
            publish.build(checker, args)
        sibling = Path(self.temp.name) / 'sibling'
        sibling.mkdir()
        args.out = sibling / '..' / 'root' / 'site'
        with self.assertRaisesRegex(ValueError, 'outside'):
            publish.build(checker, args)
        args.out = Path(self.temp.name) / 'linked'
        args.out.symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            publish.build(checker, args)
        args.out.unlink()
        page.unlink()
        page.write_text(content)
        args.out.symlink_to(page.parent)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            publish.verify(checker, args)

    def test_publish_requires_clean_context_all_source_commits_and_verification_policy(self):
        args = self.args()
        args.source_commit = []
        with self.assertRaisesRegex(ValueError, 'source commit'):
            publish.payloads(publish.checked(args), args)
        args = self.args()
        for policy in ('pr', 'main'):
            args.require_verified = policy
            with self.assertRaisesRegex(ValueError, 'unverified'):
                publish.checked(args)
        args = self.args()
        with contextlib.redirect_stderr(io.StringIO()):
            code = publish.main(['verify', str(self.root), '--out', str(args.out),
                                 '--source-commit', args.source_commit[0], '--tool-commit', args.tool_commit])
        self.assertEqual(code, 1)

    def test_publish_refuses_beside_a_context_root_with_its_own_error(self):
        # SF2-G review B-F1: a context root's own error is only a warning in the findings, so
        # the untrusted-roots guard is the one thing that stops this publish.
        context = Path(self.temp.name) / 'context'
        context.mkdir()
        (context / 'board-specs.yaml').write_text(marker('ctx'))
        (context / 'other.spec.yaml').write_text(chip('other', facts=fact('a') + fact('a')))
        args = self.args()
        args.context_root = [context]
        checker = checked(self.root, context=[context])
        self.assertFalse([f for f in checker.findings if f.level == 'error'])
        with self.assertRaisesRegex(ValueError, 'publishing context does not check clean'):
            publish.checked(args)

    def test_renderer_usage_errors_are_a_clean_failure_not_a_traceback(self):
        # SF2-G review A-F3: the renderers raise speccheck.UsageError and PreconditionError
        # (for example a root's source commit given twice), which publish.main did not catch.
        import speccheck

        args = self.args()
        argv = ['build', str(self.root), '--out', str(args.out), '--source-commit',
                args.source_commit[0], '--tool-commit', args.tool_commit]
        for error in (speccheck.UsageError, speccheck.PreconditionError):
            with self.subTest(error=error.__name__):
                err = io.StringIO()
                with patch.object(render_html, 'render', side_effect=error('given twice')), \
                        contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    code = publish.main(argv)
                self.assertEqual(code, 1)
                self.assertEqual(err.getvalue(), 'given twice\n')

    def test_template_permissions_pins_triggers_and_verify_before_upload(self):
        text = (HERE.parent / 'ci/publish.yml').read_text()
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        self.assertEqual(set(workflow['on']), {'push', 'pull_request', 'schedule'})
        self.assertEqual(workflow['on']['push']['branches'], ['main'])
        build, deploy = workflow['jobs']['build'], workflow['jobs']['deploy']
        self.assertNotIn('permissions', build)
        self.assertEqual(deploy['permissions'], {'contents': 'read', 'pages': 'write',
                                               'id-token': 'write'})
        self.assertEqual(deploy.get('concurrency'), {'group': 'spec-pages', 'cancel-in-progress': 'false'})
        self.assertIn("github.ref == 'refs/heads/main'", deploy['if'])
        self.assertIn("github.event_name == 'push'", deploy['if'])
        self.assertIn("github.event_name == 'schedule'", deploy['if'])
        self.assertEqual(deploy['needs'], 'build')
        self.assertEqual(workflow['env']['TOOL_COMMIT'], '0' * 40)
        self.assertEqual(build['steps'][0].get('run'),
                         'test "$TOOL_COMMIT" != ' + '0' * 40)
        self.assertNotIn('if', build['steps'][0])
        for job in (build, deploy):
            for step in job['steps']:
                if 'uses' in step:
                    self.assertRegex(step['uses'], r'^[\w-]+/[\w-]+@[0-9a-f]{40}$')
                if step.get('uses', '').startswith('actions/checkout@'):
                    self.assertEqual(step.get('with', {}).get('persist-credentials'), 'false')
                if step.get('uses', '').startswith('actions/upload-artifact@'):
                    self.assertEqual(step.get('with', {}).get('if-no-files-found'), 'error')
        deploy_steps = deploy['steps']
        self.assertTrue(any('publish.py verify' in s.get('run', '') for s in deploy_steps))
        verify = next(i for i, s in enumerate(deploy_steps) if 'publish.py verify' in s.get('run', ''))
        uploads = [i for i, s in enumerate(deploy_steps)
                   if s.get('uses', '').startswith('actions/upload-artifact@')]
        self.assertEqual(len(uploads), 1)
        upload = uploads[0]
        self.assertLess(verify, upload)
        self.assertNotIn('if', deploy_steps[verify])
        self.assertEqual(deploy_steps[upload]['with'], {
            'name': 'github-pages', 'path': '${{ runner.temp }}/artifact.tar',
            'retention-days': '1', 'if-no-files-found': 'error'})
        archive = deploy_steps[upload - 1]
        self.assertNotIn('if', archive)
        self.assertLess(verify, upload - 1)
        self.assertIn('tar --dereference --hard-dereference --directory site', archive['run'])
        self.assertIn('-cvf "$RUNNER_TEMP/artifact.tar" --exclude=.git --exclude=.github .',
                      archive['run'])
        self.assertIn('--require-verified main', deploy_steps[verify]['run'])
        self.assertIn('--require-hashes', text)
        self.assertIn('publish.py build', text)
        self.assertIn('publish.py verify', text)
        self.assertIn("'pr' || 'main'", text)


if __name__ == '__main__':
    unittest.main()
