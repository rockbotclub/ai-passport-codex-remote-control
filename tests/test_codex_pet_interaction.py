"""Exercise cross-session isolation, stale approvals, explicit review and wire auth."""
import sys
from contextlib import closing
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/codex_pet'))
from interaction import (Broker, Review, SecureChannel, SelectionMemory, exact,
                         WIDTH, HEIGHT, PIXELS, MAX_RECORD, LIST_ENTRIES, LIST_LINE_HEIGHT)
import socket
import threading
import time
import unittest
from unittest.mock import patch
import tempfile
import sqlite3

class Desktop:
    """Model the native UI payload, not a bridge-side transcript cache."""
    def __init__(self): self.sent, self.drafts, self.actions = [], {}, []
    def sessions(self): return [{'id': 'one', 'title': 'First', 'project': 'Alpha'}, {'id': 'two', 'title': 'Second', 'project': 'Beta'}]
    def projects(self):
        return list({s.get('project_id', s['project']): {'id': s.get('project_id', s['project']), 'name': s['project']}
                     for s in self.sessions()}.values())
    def composer_action(self, thread, action): self.actions.append((thread, action))
    def invalidate_sessions(self): pass
    def open_new_chat(self, project):
        if project == '__projectless__': raise ValueError('saved project required')
        self.actions.append((project, 'new'))
        return {'id': '@new:pending', 'title': '新会话', 'project_id': project,
                'project': next(p['name'] for p in self.projects() if p['id'] == project)}
    def send(self, thread):
        text = self.drafts.get(thread, '')
        if not text.strip(): return False
        self.sent.append((thread, text))
        return True

class Renderer:
    def __init__(self): self.last = ''
    def pages(self, text): return text.split('|') or ['']
    def bitmap(self, text, selection=None, fixed_rows=None):
        self.last, self.selection, self.fixed_rows = text, selection, fixed_rows
        return bytes(PIXELS)
    def summary(self, text, count=1): return [text]

class ProjectNavigationTests(unittest.TestCase):
    def setUp(self):
        self.desktop, self.broker = Desktop(), Broker()
        self.rows = [{'id':'one','title':'First','project':'Same name','project_id':'a'},
                     {'id':'two','title':'Second','project':'Same name','project_id':'a'},
                     {'id':'other','title':'Other project chat','project':'Same name','project_id':'b'}]
        self.desktop.sessions = lambda: list(self.rows)
        self.desktop.projects = lambda: [{'id':'a','name':'Same name'}, {'id':'b','name':'Same name'},
                                         {'id':'empty','name':'Empty project'}]
        self.review = Review(self.desktop, self.broker, Renderer())
        self.review.pc_dictation_capable = True
        self.review.sync()
    def action(self, name): return self.review.action(name, self.review.token)
    def test_wake_enters_sessions_without_moving_or_sending_and_restores_choice(self):
        self.assertTrue(self.review.action('sessions', 'stale-navigation-token'))
        self.assertEqual(self.review.mode, 1)
        self.assertEqual(self.review.target, 'one')
        self.action('down')
        self.action('back')
        self.action('down') # Browsing another project is not selecting a chat.
        self.assertEqual(self.review.project, 'b')
        self.assertTrue(self.review.action('sessions', 'stale-navigation-token'))
        self.assertEqual((self.review.project, self.review.target), ('a', 'two'))
        self.assertEqual(self.desktop.sent, [])
        self.assertEqual(self.desktop.actions, [])

    def test_selection_survives_reconnection_and_private_file_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'selection.json'
            memory = SelectionMemory(path)
            self.review.selection = memory
            self.action('ok'); self.action('down')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for selection in (memory, SelectionMemory(path)):
                restored = Review(self.desktop, self.broker, Renderer(), selection)
                restored.action('sessions', '')
                self.assertEqual((restored.mode, restored.project, restored.target), (1, 'a', 'two'))

    def test_closed_remembered_chat_falls_back_and_corrupt_memory_is_ignored(self):
        memory = SelectionMemory(); memory.remember('a', 'closed')
        restored = Review(self.desktop, self.broker, Renderer(), memory)
        restored.action('sessions', '')
        self.assertEqual(restored.target, 'one')
        self.assertEqual(memory.target, 'one')
        self.rows.clear(); restored.refresh_at = 0
        restored.action('sessions', '')
        self.assertIsNone(restored.target)
        self.assertFalse(restored.action('record', restored.token))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'selection.json'
            for data in ('broken', '[]', '{"project":1,"target":null}', 'x' * 8193):
                path.write_text(data)
                self.assertIsNone(SelectionMemory(path).target)

    def test_startup_is_projects_and_does_not_select_or_record_a_chat(self):
        frame = self.review.screen()
        self.assertEqual(frame[0], 7)
        self.assertIsNone(self.review.target)
        self.assertNotIn('First', self.review.renderer.last)
        self.assertEqual(self.review.renderer.last.splitlines(), ['Same name', 'Same name', 'Empty project'])
        self.assertEqual(self.review.renderer.selection, (0, 1))
        self.assertEqual(self.review.renderer.fixed_rows, LIST_ENTRIES)
        self.assertNotIn('sessions', self.review.renderer.last)
        self.assertNotRegex(self.review.renderer.last, r'\[\d+/\d+\]')
        self.assertFalse(self.action('record'))
        self.assertEqual(self.desktop.actions, [])
    def test_enter_filters_by_id_and_back_restores_project_and_chat_selection(self):
        self.assertTrue(self.action('ok'))
        self.review.screen()
        self.assertNotIn('Other project chat', self.review.renderer.last)
        self.action('down'); self.assertEqual(self.review.target, 'two')
        self.action('back'); self.assertEqual(self.review.mode, 7)
        self.assertEqual(self.review.project, 'a'); self.assertIsNone(self.review.target)
        self.action('ok'); self.assertEqual(self.review.target, 'two')
        self.action('back'); self.action('down'); self.action('ok')
        self.assertEqual(self.review.target, 'other')
        self.review.screen(); self.assertNotIn('Second', self.review.renderer.last)
    def test_empty_project_and_missing_desktop_remain_navigable(self):
        self.action('up'); self.action('ok')
        self.assertIsNone(self.review.target)
        self.assertIn(b'\x01', self.review.screen()[:1])
        self.assertIn('暂无会话', self.review.renderer.last)
        self.assertFalse(self.action('record')); self.assertFalse(self.action('ok'))
        self.action('back'); self.assertEqual(self.review.project, 'empty')
        self.desktop.projects = lambda: []
        self.rows.clear(); self.review.refresh_at = 0
        self.review.screen()
        self.assertFalse(self.action('up')); self.assertFalse(self.action('new'))
        self.assertFalse(self.action('ok'))
    def test_refresh_invalidates_old_screen_even_when_selected_chat_survives(self):
        self.action('ok'); token = self.review.token
        self.rows.reverse(); self.review.refresh_at = 0
        self.assertFalse(self.review.action('record', token))
        self.assertEqual(self.review.target, 'one')
        token = self.review.token
        self.rows[:] = [s for s in self.rows if s['id'] != 'one']
        self.review.refresh_at = 0
        self.assertFalse(self.review.action('record', token))
        self.assertEqual(self.review.target, 'two')
        self.assertEqual(self.desktop.actions, [])

    def test_recording_rejects_back_and_new_without_retargeting(self):
        self.action('ok'); self.action('record')
        self.assertFalse(self.action('back')); self.assertFalse(self.action('new'))
        self.assertEqual(self.review.target, 'one'); self.assertEqual(self.review.mode, 10)
    def test_unassigned_sessions_have_a_group_and_cannot_create_in_another_project(self):
        from interaction import PROJECTLESS
        self.rows.append({'id':'loose','title':'Standalone','project':'无项目','project_id':PROJECTLESS})
        self.review.refresh_at = 0; self.review.sync(); self.action('up')
        self.assertEqual(self.review.project, PROJECTLESS)
        self.assertTrue(self.action('new')); self.assertEqual(self.desktop.actions, [])
        self.action('back'); self.action('ok'); self.assertEqual(self.review.target, 'loose')

    def test_new_uses_selected_project_and_first_message_native_controls_once(self):
        self.action('down')
        token = self.review.token
        self.assertTrue(self.review.action('new', token))
        self.assertFalse(self.review.action('new', token))
        self.assertEqual(self.desktop.actions, [('b', 'new')])
        self.assertEqual((self.review.mode, self.review.target), (1, '@new:pending'))
        self.assertIsNone(self.review.selection.target) # Drafts never survive bridge restarts.
        self.review.action('sessions', '')
        self.assertEqual((self.review.project, self.review.target), ('b', '@new:pending'))
        self.review.screen(); self.assertIn('长按确认键语音输入', self.review.renderer.last)
        self.action('record'); self.review.finish_dictation()
        self.assertEqual(self.desktop.actions[-2:], [('@new:pending', 'dictate-start'),
                                                    ('@new:pending', 'dictate-stop')])
        self.assertEqual(self.desktop.sent, [])
        self.desktop.drafts['@new:pending'] = 'PC-owned first message'
        token = self.review.token
        self.assertTrue(self.review.action('ok', token))
        self.assertFalse(self.review.action('ok', token))
        self.assertFalse(self.action('ok')); self.assertFalse(self.action('record'))
        self.assertEqual(len(self.desktop.sent), 1)
        self.rows.insert(0, {'id': 'created', 'title': 'New saved chat', 'project_id': 'b', 'project': 'Same name'})
        self.review.refresh_at = 0; self.review.sync()
        self.assertEqual(self.review.target, 'created'); self.assertIsNone(self.review.draft)
        self.review.action('sessions', '')
        self.assertEqual((self.review.project, self.review.target), ('b', 'created'))
        self.assertNotIn('@new:pending', [s['id'] for s in self.review.sessions])

    def test_empty_project_can_create_and_back_retains_unsent_draft(self):
        self.action('up'); self.action('new')
        self.action('back'); self.assertEqual(self.review.project, 'empty')
        self.action('ok'); self.assertEqual(self.review.target, '@new:pending')

    def test_failed_new_consumes_token_and_returns_to_selected_project(self):
        import subprocess
        token = self.review.token
        with patch.object(self.desktop, 'open_new_chat', side_effect=subprocess.TimeoutExpired('open', 5)) as create:
            self.assertTrue(self.review.action('new', token))
            self.assertFalse(self.review.action('new', token)); create.assert_called_once_with('a')
        self.assertEqual(self.review.mode, 4)
        self.assertIsNone(self.review.draft)
        self.action('cancel'); self.assertEqual((self.review.mode, self.review.project), (7, 'a'))

    def test_new_chat_empty_input_remains_editable_but_uncertain_send_cannot_repeat(self):
        from interaction import ComposerActionError
        self.action('new')
        with patch.object(self.desktop, 'send', side_effect=ComposerActionError('send-input-required')):
            self.action('ok')
        self.assertFalse(self.review.draft['submitted'])
        self.action('cancel')
        self.assertTrue(self.action('record')); self.review.finish_dictation()
        with patch.object(self.desktop, 'send', side_effect=ComposerActionError('press-not-acknowledged')) as send:
            self.action('ok'); self.action('cancel')
            self.assertFalse(self.action('ok')); self.assertFalse(self.action('record'))
            send.assert_called_once()
        self.assertTrue(self.review.draft['submitted'])

class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.desktop, self.broker = Desktop(), Broker()
        self.review = Review(self.desktop, self.broker, Renderer())
        self.review.pc_dictation_capable = True
        self.review.sync()
        self.review.action('ok', self.review.token)
    def action(self, name): return self.review.action(name, self.review.token)
    def test_confirm_from_sessions_sends_current_pc_input_once(self):
        self.desktop.drafts['one'] = 'Typed on PC'
        self.desktop.drafts['two'] = 'Other chat'
        token = self.review.token
        self.assertTrue(self.review.action('ok', token))
        self.assertFalse(self.review.action('ok', token))
        self.assertEqual(self.desktop.sent, [('one', 'Typed on PC')])

    def test_session_list_displays_only_titles_in_five_fixed_slots(self):
        self.review.screen()
        content = self.review.renderer.last
        self.assertIn('First', content)
        self.assertNotRegex(content, r'\[\d+/\d+\]')
        self.assertNotIn('Alpha', content)
        self.assertNotIn('Second', content)
        self.assertNotIn('Beta', content)
        self.assertEqual(self.review.renderer.selection,(0,1))
        self.assertEqual(self.review.renderer.fixed_rows, LIST_ENTRIES)
        self.action('back'); self.action('down'); self.action('ok'); self.review.screen()
        self.assertIn('Second', self.review.renderer.last)
        self.assertNotRegex(self.review.renderer.last, r'\[\d+/\d+\]')
        self.assertEqual(self.review.renderer.selection,(0,1))
    def test_stale_token_cannot_send_to_another_session(self):
        old = self.review.token
        self.action('down')
        self.assertFalse(self.review.action('record', old))
        self.assertEqual(self.desktop.sent, [])
    def test_approval_bound_to_session_and_all_pages(self):
        pending = self.broker.add({'session_id': 'one', 'tool_name': 'Bash', 'tool_input': {'command': 'first|second'}})
        self.review.pc_dictation_capable = True
        self.review.sync()
        self.assertEqual(self.review.mode, 3)
        self.assertFalse(self.action('ok'))
        self.assertFalse(self.broker.resolve(pending['id'], 'two', 'allow'))
        self.action('up')
        old = self.review.token
        self.assertTrue(self.action('ok'))
        self.assertEqual(pending['answer'], 'allow')
        self.assertFalse(self.review.action('ok', old))
        self.assertFalse(self.broker.resolve(pending['id'], 'one', 'allow'))
    def test_decline_expiry_and_interrupt(self):
        for reason in ('down', 'expiry', 'interrupt'):
            pending = self.broker.add({'session_id':'one', 'tool_name':'Bash'})
            self.review.sync()
            if reason == 'down':
                self.action('down'); self.assertEqual(pending['answer'], 'deny')
            else:
                token = self.review.token
                if reason == 'expiry': pending['expires'] = 0
                else: self.broker.invalidate('one')
                self.assertFalse(self.review.action('ok', token))
                self.assertIsNone(pending['answer'])

    def test_eof_is_not_infinite_loop(self):
        a,b=socket.socketpair();b.close()
        with a, self.assertRaises(EOFError): exact(a, 4)
    def test_encrypted_control_and_reply(self):
        try: import cryptography
        except ImportError: self.skipTest('Install bridge requirements to test AES-GCM')
        a,b = socket.socketpair()
        errors = []
        def server():
            try:
                with b:
                    wire=SecureChannel(b,'a'*32,True)
                    self.assertEqual(wire.receive(), b'\x01private control')
                    wire.send(b'\x01reply')
            except BaseException as error: errors.append(error)
        t=threading.Thread(target=server);t.start()
        with a:
            wire=SecureChannel(a,'a'*32)
            wire.send(b'\x01private control');self.assertEqual(wire.receive(),b'\x01reply')
        t.join(2); self.assertFalse(t.is_alive()); self.assertEqual(errors,[])

    def test_wrong_pairing_key_rejected(self):
        try: import cryptography
        except ImportError: self.skipTest('Install bridge requirements to test AES-GCM')
        a,b=socket.socketpair()
        def server():
            with b:
                try: SecureChannel(b,'a'*32,True)
                except EOFError: pass
        t=threading.Thread(target=server);t.start()
        with a, self.assertRaises(ValueError): SecureChannel(a,'b'*32)
        t.join(2);self.assertFalse(t.is_alive())

    def test_record_authentication_failure_closes_transport(self):
        try: import cryptography
        except ImportError: self.skipTest('Install bridge requirements to test AES-GCM')
        import struct
        a,b=socket.socketpair();errors=[]
        def server():
            try:
                with b:
                    wire=SecureChannel(b,'a'*32,True)
                    wire.receive()
            except Exception as error:errors.append(error)
        t=threading.Thread(target=server);t.start()
        with a:
            SecureChannel(a,'a'*32)
            a.sendall(struct.pack('!H',17)+bytes(17))
        t.join(2);self.assertFalse(t.is_alive())
        self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],ValueError)
        self.assertEqual(str(errors[0]),'数据包认证失败')

    def test_reconnect_uses_fresh_keys_and_rejects_previous_record(self):
        try: import cryptography
        except ImportError: self.skipTest('Install bridge requirements to test AES-GCM')
        class RecordingSocket:
            def __init__(self,sock): self.sock,self.records=sock,[]
            def __getattr__(self,name): return getattr(self.sock,name)
            def sendall(self,data): self.records.append(data);self.sock.sendall(data)
        previous=None
        for cycle in range(3):
            a,b=socket.socketpair();received=[];errors=[]
            def server():
                try:
                    with b:
                        wire=SecureChannel(b,'a'*32,True)
                        received.append(wire.receive())
                except Exception as error: errors.append(error)
            t=threading.Thread(target=server);t.start()
            with a:
                capture=RecordingSocket(a)
                wire=SecureChannel(capture,'a'*32)
                capture.records.clear()
                if cycle==2: a.sendall(previous)
                else:
                    wire.send(b'\x01sync')
                    if cycle==0:previous=capture.records[0]
            t.join(2);self.assertFalse(t.is_alive())
            if cycle==2:
                self.assertEqual(received,[])
                self.assertEqual(len(errors),1)
                self.assertIsInstance(errors[0],ValueError)
            else:
                self.assertEqual(received,[b'\x01sync'])
                self.assertEqual(errors,[])

class RendererTests(unittest.TestCase):
    def test_control_bitmap_matches_firmware_wire_size(self):
        import re
        source = (Path(__file__).resolve().parents[1] / 'main/pet_control_layout.h').read_text()
        width = int(re.search(r'#define PET_CONTROL_WIDTH (\d+)', source)[1])
        height = int(re.search(r'#define PET_CONTROL_HEIGHT (\d+)', source)[1])
        self.assertEqual((WIDTH, HEIGHT), (width, height))
        self.assertEqual(PIXELS, width * height // 8)

    def test_list_windows_cover_small_lists_and_every_selection(self):
        desktop = Desktop()
        for count in range(1, 10):
            desktop.projects = lambda: [{'id':str(i), 'name':f'Project {i}'} for i in range(count)]
            desktop.sessions = lambda: [{'id':str(i), 'title':f'Chat {i}', 'project':'Project 0',
                                        'project_id':'0'} for i in range(count)]
            review = Review(desktop, Broker(), Renderer()); review.sync()
            for index in range(count):
                review.project = str(index)
                lines, selected = review.project_rows()
                names = [line.strip() for line in lines if line.strip().startswith('Project ')]
                self.assertEqual(len(names), min(count, LIST_ENTRIES))
                self.assertIn(f'Project {index}', lines[selected[0]:selected[1]])
                self.assertEqual(names, sorted(names, key=lambda name: int(name.split()[-1])))
                self.assertNotRegex('\n'.join(lines), r'\[\d+/\d+\]')
                review.project, review.target = '0', str(index)
                lines, selected = review.session_rows()
                titles = [line.strip() for line in lines if line.strip().startswith('Chat ')]
                self.assertEqual(len(titles), min(count, LIST_ENTRIES))
                self.assertIn(f'Chat {index}', lines[selected[0]:selected[1]])
                self.assertEqual(titles, sorted(titles, key=lambda title: int(title.split()[-1])))
                self.assertNotRegex('\n'.join(lines), r'\[\d+/\d+\]')

    def test_list_bitmap_stays_within_transport_and_rejects_overflow(self):
        try:
            from interaction import Renderer as ActualRenderer
            renderer = ActualRenderer()
        except (ImportError,OSError): self.skipTest('Local CJK renderer unavailable')
        self.assertLessEqual(17 + PIXELS + 16, MAX_RECORD)
        limit = HEIGHT // LIST_LINE_HEIGHT
        self.assertEqual(len(renderer.bitmap('\n'.join(['Fits'] * limit),
                                             selection=(limit - 2, limit))), PIXELS)
        with self.assertRaises(ValueError):
            renderer.bitmap('\n'.join(['Overflow'] * (limit + 1)), selection=(limit - 1, limit + 1))

    def test_project_rows_fit_long_chinese_names_and_all_selection_positions(self):
        try:
            from interaction import Renderer as ActualRenderer
            renderer = ActualRenderer()
        except (ImportError,OSError): self.skipTest('Local CJK renderer unavailable')
        from PIL import Image
        desktop = Desktop()
        desktop.projects = lambda: [{'id':str(i),'name':'中文项目名称与两层会话导航测试 '*4} for i in range(8)]
        desktop.sessions = lambda: []
        review = Review(desktop, Broker(), renderer); review.sync()
        for index in range(8):
            review.project = str(index)
            frame = review.screen(); lines, selected = review.project_rows()
            self.assertEqual(frame[0], 7); self.assertEqual(len(frame), 17 + PIXELS)
            self.assertEqual(len(lines), LIST_ENTRIES); self.assertIn('…', '\n'.join(lines))
            self.assertEqual(selected[1] - selected[0], 1)
            self.assertNotRegex('\n'.join(lines), r'\[\d+/\d+\]')
            self.assertNotIn('sessions', '\n'.join(lines))
            pixels = Image.frombytes('1', (WIDTH,HEIGHT), frame[17:])
            row_height = HEIGHT // LIST_ENTRIES
            top = (HEIGHT - LIST_ENTRIES * row_height) // 2
            for line in range(len(lines)):
                y = top + line * row_height + row_height // 2
                self.assertEqual(bool(pixels.getpixel((0,y))), selected[0] <= line < selected[1])
                self.assertEqual(bool(pixels.getpixel((215,y))), selected[0] <= line < selected[1])
    def test_selected_chat_has_full_width_inverted_card_at_every_position(self):
        try:
            from interaction import Renderer as ActualRenderer
            renderer=ActualRenderer()
        except (ImportError,OSError):self.skipTest('Local CJK renderer unavailable')
        from PIL import Image
        desktop=Desktop()
        desktop.sessions=lambda:[{'id':str(i),'title':'会话选择测试标题 '*3,'project':'AI Passport'} for i in range(8)]
        review=Review(desktop,Broker(),renderer);review.sync();review.action('ok',review.token)
        for index in range(8):
            review.target=str(index)
            frame=review.screen()
            self.assertEqual(len(frame),17 + PIXELS)
            image=Image.frombytes('1',(WIDTH,HEIGHT),frame[17:])
            lines,selected=review.session_rows()
            first,end=selected
            self.assertEqual(len(lines), LIST_ENTRIES)
            self.assertEqual(end - first, 1)
            self.assertNotIn('AI Passport', '\n'.join(lines))
            self.assertNotRegex('\n'.join(lines), r'\[\d+/\d+\]')
            row_height = HEIGHT // LIST_ENTRIES
            top = (HEIGHT - LIST_ENTRIES * row_height) // 2
            for line in range(len(lines)):
                y = top + line * row_height + row_height // 2
                self.assertEqual(bool(image.getpixel((0,y))),first <= line < end)
                self.assertEqual(bool(image.getpixel((215,y))),first <= line < end)
            self.assertEqual(renderer.bitmap('\n'.join(lines),selection=selected,
                                             fixed_rows=LIST_ENTRIES),frame[17:])
            self.assertNotEqual(renderer.bitmap('\n'.join(lines)),frame[17:])

    def test_both_lists_keep_fixed_rows_for_small_lists_and_long_names(self):
        try:
            from interaction import Renderer as ActualRenderer
            renderer = ActualRenderer()
        except (ImportError, OSError):
            self.skipTest('Local CJK renderer unavailable')
        from PIL import Image
        titles = ['Short', '中文名称混合 English 123，' * 30,
                  'W' * 300, 'Multiple\nlines\tstay on one row', '\U0010ffff']
        desktop = Desktop()
        row_height = HEIGHT // LIST_ENTRIES
        top = (HEIGHT - LIST_ENTRIES * row_height) // 2
        self.assertLessEqual(HEIGHT - LIST_ENTRIES * row_height, 4)
        highlight_sizes = set()
        for mode in (1, 7):
            for count in range(1, LIST_ENTRIES + 1):
                desktop.projects = lambda: [{'id': str(i), 'name': titles[i]} for i in range(count)]
                desktop.sessions = lambda: [{'id': f'chat-{i}', 'title': titles[i], 'project_id': '0',
                                             'project': 'Hidden project \U0010ffff'} for i in range(count)]
                review = Review(desktop, Broker(), renderer); review.sync()
                if mode == 1:
                    review.action('ok', review.token)
                previous_lines = None
                for index in range(count):
                    review.target = f'chat-{index}' if mode == 1 else None
                    review.project = '0' if mode == 1 else str(index)
                    frame = review.screen()
                    lines, selection = review.session_rows() if mode == 1 else review.project_rows()
                    self.assertEqual(len(lines), count)
                    self.assertEqual(selection, (index, index + 1))
                    self.assertNotIn('Hidden project', '\n'.join(lines))
                    self.assertNotIn('chat-', '\n'.join(lines))
                    self.assertNotIn('sessions', '\n'.join(lines))
                    if previous_lines is not None:
                        self.assertEqual(lines, previous_lines)
                    previous_lines = lines
                    for line in lines:
                        self.assertNotIn('\n', line)
                        self.assertLessEqual(renderer.font.getlength(line), WIDTH - 8)
                    if count > 1:
                        self.assertTrue(lines[1].endswith('…'))
                    if count > 2:
                        self.assertTrue(lines[2].endswith('…'))
                    if count > 4:
                        self.assertEqual(lines[4], '请在电脑上查看会话标题' if mode == 1 else '请在电脑上查看项目')
                    pixels = Image.frombytes('1', (WIDTH, HEIGHT), frame[17:])
                    highlighted = [y for y in range(HEIGHT) if pixels.getpixel((0, y))]
                    self.assertTrue(highlighted)
                    self.assertGreaterEqual(min(highlighted), top + index * row_height)
                    self.assertLess(max(highlighted), top + (index + 1) * row_height)
                    highlight_sizes.add(len(highlighted))
                    # Every unused slot remains empty; short lists never stretch their rows.
                    self.assertIsNone(pixels.crop((0, top + count * row_height, WIDTH, HEIGHT)).getbbox())
        self.assertEqual(len(highlight_sizes), 1)

    def test_long_chinese_titles_and_projects_fit_list_and_review_panel(self):
        try:
            from interaction import Renderer as ActualRenderer, LINE_SPACING
            renderer = ActualRenderer()
        except (ImportError,OSError):self.skipTest('Local CJK renderer unavailable')
        from PIL import Image,ImageDraw
        desktop=Desktop()
        desktop.sessions=lambda:[{'id':str(i),'title':'中文会话标题与项目列表显示测试 '*4,
                                  'project':'中文项目名称'} for i in range(8)]
        review=Review(desktop,Broker(),renderer);review.sync();review.action('ok',review.token);review.action('down',review.token)
        review.screen();content=review.session_list()
        self.assertEqual(len(content.splitlines()), LIST_ENTRIES)
        bounds=ImageDraw.Draw(Image.new('1',(WIDTH,HEIGHT))).multiline_textbbox((4,0),content,font=renderer.font,spacing=LINE_SPACING)
        self.assertLessEqual(bounds[2],WIDTH);self.assertLessEqual(bounds[3],HEIGHT)
        self.assertNotIn('中文项目名称',content)
        self.assertIn('…',content)
        self.assertNotRegex(content, r'\[\d+/\d+\]')
        self.assertEqual(len(renderer.bitmap(content)),PIXELS)
        for page in renderer.pages('中文转写文字 '*100):
            bounds=ImageDraw.Draw(Image.new('1',(WIDTH,HEIGHT))).multiline_textbbox((4,0),page+'\n[1/99]',font=renderer.font,spacing=LINE_SPACING)
            self.assertLessEqual(bounds[3],144)

    def test_chinese_coverage_and_missing_glyph_blocks_review(self):
        try:
            import PIL, fontTools
        except ImportError:
            self.skipTest('Renderer needs the local bridge environment')
        font = Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
        if not font.is_file():
            self.skipTest('Configure a local CJK font outside macOS')
        from interaction import Renderer as ActualRenderer, UnsupportedText
        renderer = ActualRenderer(font)
        self.assertTrue(renderer.pages('\u4e2d\u6587 ABC 123'))
        self.assertEqual(len(renderer.bitmap('\u4e2d\u6587')), PIXELS)
        with self.assertRaises(UnsupportedText): renderer.pages('\U0010ffff')
        review = Review(Desktop(), Broker(), renderer)
        review.sync();review.action('ok',review.token)
        pending = review.broker.add({'session_id':review.target,'tool_name':'\U0010ffff'})
        review.change(3, pending['text'], pending['id'])
        self.assertEqual(review.mode,4)
        review.action('cancel',review.token)
        self.assertEqual(pending['answer'],'deny')

class DesktopReconnectTests(unittest.TestCase):
    def setUp(self):
        from interaction import Desktop as ActualDesktop
        native_action = ActualDesktop.composer_action
        self.native_press = lambda desktop, thread: native_action(desktop, thread, 'send')
        self.press = self.enterContext(patch.object(ActualDesktop, 'composer_action'))
        self.enterContext(patch('interaction.sys.platform', 'darwin'))
        self.enterContext(patch('interaction.time.sleep'))

    def write_draft(self, directory, text):
        import json
        state = {'electron-persisted-atom-state': {'composer-prompt-drafts-v2': {
            'local:one': {'prompt': text, 'pullRequestChecks': []},
            'local:other': {'prompt': 'other draft', 'pullRequestChecks': []}}}}
        (Path(directory) / '.codex-global-state.json').write_text(json.dumps(state))

    def test_confirm_uses_live_ui_without_reading_debounced_draft_or_owner(self):
        from interaction import Desktop as ActualDesktop
        desktop = ActualDesktop()
        with patch.object(desktop, 'project_state', side_effect=AssertionError('must not serialize UI input')), \
                patch.object(desktop, 'activity_snapshot') as owner, patch.object(desktop, '_ipc_socket') as request, \
                patch('interaction.time.sleep') as sleep:
            self.assertTrue(desktop.send('one'))
        self.press.assert_called_once_with('one', 'send')
        owner.assert_not_called(); request.assert_not_called(); sleep.assert_not_called()

    def test_confirm_without_voice_consumes_token_and_presses_once(self):
        from interaction import Desktop as ActualDesktop
        desktop = ActualDesktop()
        with patch.object(desktop, 'sessions', return_value=Desktop().sessions()), \
                patch.object(desktop, 'projects', return_value=Desktop().projects()), \
                patch.object(desktop, '_ipc_socket') as request:
            review = Review(desktop, Broker(), Renderer()); review.sync(); review.action('ok', review.token)
            token = review.token
            self.assertTrue(review.action('ok', token))
            self.assertFalse(review.action('ok', token))
        request.assert_not_called()
        self.press.assert_called_once_with('one', 'send')

    def test_press_errors_consume_confirmation_without_retry_or_claiming_sent(self):
        import subprocess
        from interaction import Desktop as ActualDesktop, ComposerActionError
        errors = (ComposerActionError('press-not-acknowledged'), ComposerActionError('helper-failed'),
                  subprocess.TimeoutExpired('composer-action', 6), OSError('helper unavailable'))
        for error in errors:
            with self.subTest(error=type(error).__name__):
                desktop = ActualDesktop()
                self.press.reset_mock(); self.press.side_effect = error
                with patch.object(desktop, 'sessions', return_value=Desktop().sessions()), \
                        patch.object(desktop, 'projects', return_value=Desktop().projects()), \
                        patch.object(desktop, '_ipc_socket') as request:
                    review = Review(desktop, Broker(), Renderer()); review.sync(); review.action('ok', review.token)
                    token = review.token
                    review.action('ok', token)
                    self.assertEqual(review.mode, 4)
                    self.assertIn('尚未确认发送结果', review.text)
                    self.assertNotIn('消息已发送', review.text)
                    self.assertFalse(review.action('ok', token))
                    review.sync(); review.screen()
                self.press.assert_called_once_with('one', 'send'); request.assert_not_called()

    def test_send_prepress_failures_show_actionable_cause_without_uncertain_send_warning(self):
        from interaction import Desktop as ActualDesktop, ComposerActionError
        reasons = {'chat-not-found': '未找到所选会话', 'chat-changed': '所选会话已变化',
                   'composer-button-unavailable': '暂时无法发送', 'send-disabled': '发送按钮不可用',
                   'send-input-required': '暂无可发送内容',
                   'multiple-writable-editors': '发现多个输入框',
                   'multiple-composer-buttons': '发现多个发送按钮',
                   'accessibility-tree-limit': '无法读取 Codex 界面'}
        for reason, message in reasons.items():
            with self.subTest(reason=reason):
                desktop = ActualDesktop()
                self.press.reset_mock(); self.press.side_effect = ComposerActionError(reason)
                with patch.object(desktop, 'sessions', return_value=Desktop().sessions()), \
                        patch.object(desktop, 'projects', return_value=Desktop().projects()):
                    review = Review(desktop, Broker(), Renderer()); review.sync(); review.action('ok', review.token)
                    token = review.token
                    review.action('ok', token)
                    self.assertEqual(review.mode, 4)
                    self.assertIn(message, review.text)
                    self.assertNotIn('尚未确认发送结果', review.text)
                    self.assertNotIn('消息已发送', review.text)
                    self.assertFalse(review.action('ok', token))
                    review.sync(); review.screen()
                self.press.assert_called_once_with('one', 'send')

    def test_ui_submission_does_not_rewrite_or_clear_saved_drafts(self):
        from interaction import Desktop as ActualDesktop
        with tempfile.TemporaryDirectory() as directory:
            desktop = ActualDesktop(directory)
            self.write_draft(directory, 'current text')
            state = Path(directory) / '.codex-global-state.json'
            before = state.read_bytes()
            self.assertTrue(desktop.send('one'))
            self.assertEqual(state.read_bytes(), before)

    def test_native_press_opens_exact_chat_without_prompt_and_reuses_compilation(self):
        import json
        import subprocess
        from interaction import Desktop as ActualDesktop
        from urllib.parse import urlparse
        with tempfile.TemporaryDirectory() as directory:
            desktop = ActualDesktop(directory)
            with patch('interaction.subprocess.run') as launch:
                self.native_press(desktop, 'one')
            self.addCleanup(desktop._composer_helper_dir.cleanup)
            self.assertEqual(launch.call_count, 3)
            compile_args = launch.call_args_list[0].args[0]
            self.assertEqual(compile_args[0], '/usr/bin/clang')
            self.assertTrue(any(arg.endswith('/composer_action.m') for arg in compile_args))
            route = urlparse(launch.call_args_list[1].args[0][-1])
            self.assertEqual((route.scheme, route.netloc, route.path, route.query), ('codex', 'threads', '/one', ''))
            args, options = launch.call_args.args[0], launch.call_args.kwargs
            self.assertEqual(len(args), 1)
            self.assertTrue(args[0].endswith('/composer-action'))
            self.assertEqual(json.loads(options['input']), {'thread': 'one', 'action': 'send'})
            self.assertEqual(options['stdout'], subprocess.DEVNULL)
            self.assertEqual(options['stderr'], subprocess.PIPE)
            self.assertTrue(options['check'])
            with patch('interaction.subprocess.run') as launch:
                self.native_press(desktop, 'two')
            self.assertEqual(launch.call_count, 2)
            self.assertEqual(json.loads(launch.call_args.kwargs['input']), {'thread': 'two', 'action': 'send'})

    def test_navigation_failure_never_invokes_native_press(self):
        import subprocess
        from interaction import Desktop as ActualDesktop
        with tempfile.TemporaryDirectory() as directory:
            desktop = ActualDesktop(directory)
            with patch('interaction.subprocess.run', side_effect=[None, subprocess.CalledProcessError(1, 'open')]) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    self.native_press(desktop, 'one')
            self.addCleanup(desktop._composer_helper_dir.cleanup)
            self.assertEqual(run.call_count, 2)

    def test_accessibility_denial_reports_permission_without_claiming_send(self):
        from interaction import Desktop as ActualDesktop, ComposerActionError
        desktop = ActualDesktop()
        self.press.side_effect = ComposerActionError('accessibility-denied')
        with patch.object(desktop, 'sessions', return_value=Desktop().sessions()), \
                patch.object(desktop, 'projects', return_value=Desktop().projects()):
            review = Review(desktop, Broker(), Renderer()); review.sync(); review.action('ok', review.token)
            token = review.token
            review.action('ok', token)
            self.assertEqual(review.mode, 4)
            self.assertIn('开启辅助功能权限', review.text)
            self.assertNotIn('消息已发送', review.text)
            self.assertFalse(review.action('ok', token))
        self.press.assert_called_once_with('one', 'send')

    def test_native_failures_log_only_reason_and_never_retry_press(self):
        import subprocess
        from interaction import Desktop as ActualDesktop, ComposerActionError
        for code, reason in ((10, 'accessibility-denied'), (13, 'chat-not-found'),
                             (22, 'composer-button-unavailable'), (28, 'send-disabled'),
                             (29, 'send-input-required'),
                             (19, 'press-not-acknowledged')):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                desktop = ActualDesktop(directory)
                with patch('interaction.subprocess.run', side_effect=[None, None, subprocess.CalledProcessError(code, 'composer-action')]) as run, \
                        patch('builtins.print') as output:
                    with self.assertRaises(ComposerActionError) as result:
                        self.native_press(desktop, 'one')
                self.addCleanup(desktop._composer_helper_dir.cleanup)
                self.assertEqual(result.exception.reason, reason)
                output.assert_any_call('电脑端输入框操作结果：', __import__('messages').reason_text(reason), flush=True)
                self.assertEqual(output.call_count, 2)
                timing = output.call_args_list[1].args
                self.assertEqual(timing[:2], ('电脑端输入框操作耗时：', '发送'))
                self.assertEqual(timing[2::2], ('导航毫秒：', '目录查询毫秒：', '原生操作毫秒：'))
                self.assertTrue(all(type(value) is int and value >= 0 for value in timing[3::2]))
                self.assertEqual(run.call_count, 3)

    def test_non_macos_cannot_press_or_fall_back_to_ipc(self):
        from interaction import Desktop as ActualDesktop
        desktop = ActualDesktop()
        with patch('interaction.sys.platform', 'linux'), patch.object(desktop, '_ipc_socket') as request:
            with self.assertRaises(RuntimeError): self.native_press(desktop, 'one')
        self.press.assert_not_called(); request.assert_not_called()

    def test_ui_owns_rich_mentions_attachments_and_empty_input_validation(self):
        from interaction import Desktop as ActualDesktop
        malformed = (None, [], {'document': {'type': 'doc', 'content': None}},
                     {'document': {'type': 'doc', 'content': [{'type': 'mention'}]}}, '')
        with tempfile.TemporaryDirectory() as directory:
            desktop = ActualDesktop(directory)
            for value in malformed:
                with self.subTest(value=value):
                    self.write_draft(directory, value)
                    self.assertTrue(desktop.send('one'))
            self.assertEqual(self.press.call_count, len(malformed))

    def test_project_catalog_deduplicates_migration_and_preserves_equal_names(self):
        from interaction import Desktop as ActualDesktop
        import json
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(str(Path(directory)/'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.executemany('INSERT INTO projects VALUES(?,?)', [('server','Old name'),('other','Same name')])
                db.commit()
            (Path(directory)/'.codex-global-state.json').write_text(json.dumps({
                'local-projects':{'legacy':{'name':'Same name'},'empty':{'name':'Empty project'}},
                'app-server-project-id-by-legacy-project-id-by-host':{'local':{'legacy':'server'}}}))
            projects = ActualDesktop(directory).projects()
            self.assertEqual({p['id']: p['name'] for p in projects},
                             {'server':'Same name','other':'Same name','empty':'Empty project'})

    def test_catalog_includes_unloaded_chats_without_owner_discovery(self):
        from interaction import Desktop as ActualDesktop
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(str(Path(directory)/'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE threads(id TEXT,title TEXT,name TEXT,project_id TEXT,cwd TEXT,archived INTEGER,agent_path TEXT,updated_at INTEGER)')
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.execute("INSERT INTO projects VALUES('p','Project name')")
                db.executemany('INSERT INTO threads VALUES(?,\'First user prompt\',?,\'p\',\'/repo\',0,NULL,?)', [('closed','Old',2),('live','Current',1)])
                db.commit()
            desktop=ActualDesktop(directory)
            with patch.object(desktop,'activity_snapshot',side_effect=EOFError('连接已关闭')) as owner:
                self.assertEqual(desktop._scan_sessions(),[
                    {'id':'closed','title':'Old','project':'Project name','project_id':'p'},
                    {'id':'live','title':'Current','project':'Project name','project_id':'p'}])
                owner.assert_not_called()

    def test_legacy_project_assignment_and_renamed_titles(self):
        from interaction import Desktop as ActualDesktop
        import json
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(str(Path(directory)/'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE threads(id TEXT,title TEXT,name TEXT,project_id TEXT,cwd TEXT,archived INTEGER,agent_path TEXT,updated_at INTEGER)')
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.executemany('INSERT INTO threads VALUES(?,\'First prompt\',?,NULL,?,0,NULL,1)',
                               [('assigned','Actual title','/worktree/a'),('nested',None,'/repo/sub/path'),('loose',None,'/repo'),('unnamed',None,'/elsewhere')])
                db.commit()
            (Path(directory)/'.codex-global-state.json').write_text(json.dumps({
                'local-projects':{'p':{'name':'Renamed project','rootPaths':['/repo']},
                                  'sub':{'name':'Nested project','rootPaths':['/repo/sub']}},
                'thread-project-assignments':{'assigned':{'projectKind':'local','projectId':'p'}},
                'thread-titles':{'titles':{'nested':'Saved title'}},
                'projectless-thread-ids':['loose']}))
            desktop=ActualDesktop(directory)
            with patch.object(desktop,'activity_snapshot',return_value='activity_snapshot'):
                found={s['id']:s for s in desktop._scan_sessions()}
                self.assertEqual(found['assigned']['project'],'Renamed project')
                self.assertEqual(found['assigned']['project_id'],'p')
                self.assertEqual(found['nested']['project'],'Nested project')
                self.assertEqual(found['nested']['project_id'],'sub')
                self.assertEqual(found['nested']['title'],'Saved title')
                self.assertEqual(found['loose']['project'],'无项目')
                self.assertEqual(found['loose']['project_id'],'__projectless__')
                self.assertEqual(found['unnamed']['title'],'未命名会话')

    def test_project_lists_all_saved_chats_beyond_recent_80_with_host_migration(self):
        from interaction import Desktop as ActualDesktop
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with closing(sqlite3.connect(str(root / 'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE threads(id TEXT,name TEXT,project_id TEXT,cwd TEXT,archived INTEGER,agent_path TEXT,updated_at INTEGER)')
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.executemany('INSERT INTO projects VALUES(?,?)', [('server','Saved project'),('other','Recent project')])
                db.executemany('INSERT INTO threads VALUES(?,?,?,NULL,0,NULL,?)',
                               [(f'recent-{i}',f'Recent {i}','other',100+i) for i in range(90)] +
                               [('old-one','First saved chat',None,2),('old-two','Second saved chat',None,1)])
                db.execute("INSERT INTO threads VALUES('archived','Archived','server',NULL,1,NULL,0)")
                db.execute("INSERT INTO threads VALUES('child','Subagent','server',NULL,0,'/root/child',0)")
                db.commit()
            (root / '.codex-global-state.json').write_text(json.dumps({
                'local-projects': {'legacy': {'name':'Saved project','rootPaths':['/repo']}},
                'thread-project-assignments': {thread: {'projectKind':'local','projectId':'legacy'}
                                               for thread in ('old-one','old-two')},
                'app-server-project-id-by-legacy-project-id-by-host': {
                    'local:' + str(root.resolve()): {'legacy':'server'},
                    'local:/different/account': {'legacy':'wrong-server'}}}))
            desktop = ActualDesktop(directory)
            with patch.object(desktop, 'activity_snapshot', side_effect=TimeoutError()) as owner:
                desktop._sessions = desktop._scan_sessions()
                desktop._refreshed = time.monotonic()
                self.assertEqual(len(desktop.sessions()), 92)
                self.assertEqual({p['id'] for p in desktop.projects()}, {'server','other'})
                review = Review(desktop, Broker(), Renderer())
                review.project = 'server'
                review.screen()
                self.assertIn('Saved project', review.renderer.last)
                self.assertNotIn('sessions', review.renderer.last)
                self.assertTrue(review.action('ok', review.token))
                review.screen()
                self.assertIn('First saved chat', review.renderer.last)
                self.assertIn('Second saved chat', review.renderer.last)
                self.assertNotIn('No sessions', review.renderer.last)
                self.assertNotIn('Recent ', review.renderer.last)
                self.assertEqual(review.target, 'old-one')
                self.assertTrue(review.action('down', review.token))
                self.assertEqual(review.target, 'old-two')
                owner.assert_not_called()

    def test_refresh_recovers_after_desktop_restart(self):
        from interaction import Desktop as ActualDesktop
        desktop=ActualDesktop()
        completed=threading.Event()
        def scan():
            completed.set()
            raise EOFError('连接已关闭')
        with patch.object(desktop,'_scan_sessions',side_effect=scan):
            self.assertEqual(desktop.sessions(),[])
            self.assertTrue(completed.wait(1))
            deadline=time.monotonic()+1
            while desktop._refreshing and time.monotonic()<deadline: time.sleep(0.001)
            self.assertFalse(desktop._refreshing)
        with desktop._lock:
            desktop._refreshed=0
            desktop._refresh_attempted=0
        with patch.object(desktop,'_scan_sessions',return_value=[{'id':'new','title':'Restored'}]):
            desktop.sessions()
            deadline=time.monotonic()+1
            while desktop._refreshing and time.monotonic()<deadline: time.sleep(0.001)
            self.assertEqual(desktop.sessions(),[{'id':'new','title':'Restored'}])

    def test_metadata_failure_keeps_titles_and_successful_empty_refresh_removes_them(self):
        from interaction import Desktop as ActualDesktop
        desktop = ActualDesktop()
        saved = [{'id': 'one', 'title': 'Saved title'}]
        desktop._sessions = list(saved)
        with patch.object(desktop, '_scan_sessions', side_effect=sqlite3.OperationalError('busy')):
            desktop.sessions()
            deadline = time.monotonic() + 1
            while desktop._refreshing and time.monotonic() < deadline:
                time.sleep(0.001)
            self.assertEqual(desktop.sessions(), saved)
        desktop._refresh_attempted = 0
        with patch.object(desktop, '_scan_sessions', return_value=[]):
            desktop.sessions()
            deadline = time.monotonic() + 1
            while desktop._refreshing and time.monotonic() < deadline:
                time.sleep(0.001)
            self.assertEqual(desktop.sessions(), [])

    def test_missing_identity_refreshes_fresh_cache_without_blocking_or_duplicate_worker(self):
        from interaction import Desktop as ActualDesktop
        desktop = ActualDesktop()
        desktop._refreshed = time.monotonic()
        entered, release = threading.Event(), threading.Event()
        def scan():
            entered.set()
            release.wait(2)
            return [{'id': 'new', 'title': 'New title'}]
        import hashlib
        required = [hashlib.sha256(b'new').hexdigest()[:32]]
        with patch.object(desktop, '_scan_sessions', side_effect=scan) as read:
            try:
                self.assertEqual(desktop.sessions(required=required), [])
                self.assertTrue(entered.wait(1))
                for _ in range(5):
                    self.assertEqual(desktop.sessions(required=required), [])
                self.assertEqual(read.call_count, 1)
            finally:
                release.set()
            deadline = time.monotonic() + 1
            while desktop._refreshing and time.monotonic() < deadline:
                time.sleep(0.001)
            self.assertEqual(desktop.sessions(required=required), [{'id': 'new', 'title': 'New title'}])

    def test_source_filter_and_missing_title_preserve_user_chat_without_internal_rows(self):
        from interaction import Desktop as ActualDesktop
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(str(Path(directory) / 'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE threads(id TEXT,name TEXT,project_id TEXT,cwd TEXT,archived INTEGER,agent_path TEXT,updated_at INTEGER,source TEXT)')
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.executemany('INSERT INTO threads VALUES(?,?,NULL,NULL,0,NULL,1,?)', [
                    ('one', None, 'vscode'), ('new', None, 'vscode'),
                    ('guardian', 'Internal', '{"subagent":{"other":"guardian"}}'),
                    ('child', 'Child', '{"subagent":{"thread_spawn":{"parent_thread_id":"one"}}}')])
                db.commit()
            desktop = ActualDesktop(directory)
            desktop._sessions = [{'id': 'one', 'title': 'Last valid title'}]
            found = {session['id']: session for session in desktop._scan_sessions()}
            self.assertEqual(set(found), {'one', 'new'})
            self.assertEqual(found['one']['title'], 'Last valid title')
            self.assertEqual(found['new']['title'], '未命名会话')
            self.assertEqual(set(desktop.activity_threads()), {'one', 'new'})

if __name__ == '__main__': unittest.main()
