"""Priority, stable order, selection isolation, glyph coverage and screen bounds."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest
import socket
import threading
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/codex_pet'))
from dashboard import overview, DashboardRenderer, HOME_PIXELS, EMPTY_LABELS, SUMMARY_SIZE, LIST_SIZE
from bridge import Tracker, compact_event


def identity(text):
    return hashlib.sha256(text.encode()).hexdigest()[:32]


class OverviewTests(unittest.TestCase):
    def test_all_projects_priority_counts_stable_across_metadata_reordering(self):
        activity = {identity(str(i)): {'status': 'waiting' if i == 3 else 'working'} for i in range(5)}
        sessions = [{'id': str(i), 'title': f'Chat {i}', 'project': f'Project {i % 2}'} for i in range(5)]
        first = overview(activity, sessions)
        self.assertEqual((first['active'], first['waiting'], first['remaining']), (5, 1, 2))
        self.assertEqual([r['title'] for r in first['rows']], ['Chat 3', 'Chat 0', 'Chat 1'])
        self.assertEqual(overview(activity, list(reversed(sessions))), first)

    def test_approval_without_hook_is_visible_and_deduplicated(self):
        activity = {identity('one'): {'status': 'working'}}
        model = overview(activity, [{'id': 'one'}, {'id': 'two'}], ['one', 'two'])
        self.assertEqual((model['active'], model['waiting']), (2, 2))
        self.assertTrue(all(r['status'] == 'waiting' for r in model['rows']))

    def test_expired_turns_are_unknown_not_ready_or_active(self):
        tracker = Tracker()
        tracker.accept(compact_event({'hook_event_name': 'UserPromptSubmit', 'session_id': 'one'}), 1)
        self.assertEqual(overview(tracker.activity(2), [{'id': 'one'}])['status'], 'working')
        self.assertEqual(overview(tracker.activity(1801), [])['status'], 'error')
        self.assertEqual(overview(tracker.activity(1801), [])['active'], 0)
        self.assertEqual(overview({}, [])['status'], 'idle')

    def test_empty_and_closed_sessions_are_idle_while_bridge_is_connected(self):
        tracker = Tracker()
        for event, now in (('SessionStart', 1), ('SessionEnd', 2)):
            tracker.accept(compact_event({'hook_event_name': event, 'session_id': 'one'}), now)
        model = overview(tracker.activity(3), [])
        self.assertEqual((model['status'], model['active'], model['rows']), ('idle', 0, []))

    def test_idle_does_not_expire_or_hide_an_unknown_active_turn(self):
        tracker = Tracker()
        tracker.accept(compact_event({'hook_event_name': 'SessionStart', 'session_id': 'one'}), 1)
        self.assertEqual(overview(tracker.activity(1801), [])['status'], 'idle')
        tracker.accept(compact_event({'hook_event_name': 'UserPromptSubmit', 'session_id': 'two'}), 2)
        self.assertEqual(overview(tracker.activity(1802), [])['status'], 'error')

    def test_idle_and_unknown_do_not_fill_rows(self):
        model = overview({identity('one'): {'status': 'idle'}}, [])
        self.assertEqual((model['status'], model['rows']), ('idle', []))

    def test_unknown_activity_does_not_occupy_rows_or_inflate_counts(self):
        activity = {identity('known'): {'status': 'working'}, identity('unknown'): {'status': 'waiting'}}
        model = overview(activity, [{'id': 'known', 'title': 'Real chat'}])
        self.assertEqual((model['active'], model['waiting'], model['remaining']), (1, 0, 0))
        self.assertEqual([row['title'] for row in model['rows']], ['Real chat'])
        model = overview(activity, [])
        self.assertEqual((model['status'], model['active'], model['rows']), ('syncing', 0, []))

    def test_confirmed_chat_without_metadata_remains_visible_for_approval(self):
        model = overview({identity('one'): {'status': 'waiting', 'confirmed': True}}, [])
        self.assertEqual((model['status'], model['active'], model['waiting']), ('waiting', 1, 1))
        self.assertEqual(model['rows'][0]['title'], '未命名会话')

    def test_turn_finished_animation_expires_without_claiming_success(self):
        tracker = Tracker()
        for event, now in (('UserPromptSubmit', 1), ('Stop', 2)):
            tracker.accept(compact_event({'hook_event_name': event, 'session_id': 'one'}), now)
        self.assertEqual(overview(tracker.activity(9), [])['status'], 'done')
        self.assertEqual(overview(tracker.activity(10), [])['status'], 'idle')


class BitmapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from interaction import Renderer
            cls.renderer = Renderer()
            cls.dashboard = DashboardRenderer(cls.renderer)
        except (ImportError, OSError):
            raise unittest.SkipTest('Requires local CJK font and bridge dependencies')

    def test_fixed_labels_coverage_and_negative_case(self):
        texts = '需要你处理正在工作运行中待处理还有个会话按键查看全部暂无活跃会话未命名会话'
        texts += ''.join(text for labels in EMPTY_LABELS.values() for text, _ in labels)
        self.assertTrue(all(ord(char) in self.renderer.coverage for char in texts))
        self.assertEqual(self.dashboard.supported('\U0010ffff', 'View on PC'), 'View on PC')

    def test_frames_for_zero_one_many_and_long_cjk_titles(self):
        for count in (0, 1, 3, 5, 999):
            activity = {identity(str(i)): {'status': 'waiting' if i < 2 else 'working', 'confirmed': True} for i in range(count)}
            sessions = [{'id': str(i), 'title': '优化电子宠物界面与多会话展示' * 15,
                         'project': '超长中文项目名称' * 12} for i in range(min(count, 3))]
            model = overview(activity, sessions)
            frame = self.dashboard.frame(model)
            self.assertEqual(len(frame), HOME_PIXELS + 8)
            kind, status, active, waiting, rows, mask = struct.unpack('!BBHHBB', frame[:8])
            self.assertEqual((kind, active, waiting, rows), (9, count, min(count, 2), min(count, 3)))
            self.assertEqual(mask, (1 << min(count, 2)) - 1)
            self.assertTrue(any(frame[8:]))

    def test_metadata_fits_each_line_and_unsupported_content_is_explicit(self):
        for text in ('中文标题' * 30, 'W' * 200, '👨‍👩‍👧‍👦'):
            for size, width, lines in ((11, 140, 1), (14, 200, 1), (16, 200, 3)):
                fitted = self.dashboard.fit(text, size, width, lines)
                self.assertLessEqual(len(fitted), lines)
                self.assertTrue(all(self.dashboard.fonts[size].getlength(line) <= width for line in fitted))
        self.assertEqual(self.dashboard.fit('\U0010ffff', 14, 200), ['请在电脑上查看文字'])

    def test_idle_disconnect_and_unknown_have_distinct_readable_empty_messages(self):
        from unittest.mock import patch
        frames = []
        for status in ('idle', 'offline', 'error', 'syncing'):
            dashboard = DashboardRenderer(self.renderer)
            with patch.object(dashboard, 'text', wraps=dashboard.text) as draw_text:
                frames.append(dashboard.frame({'status': status, 'active': 0, 'waiting': 0,
                                               'remaining': 0, 'rows': []}))
            texts = [call.args[2] for call in draw_text.call_args_list]
            for message, _ in EMPTY_LABELS[status]:
                self.assertIn(message, texts)
            self.assertNotIn('等待状态同步', texts)
            self.assertNotIn('正在连接电脑工作状态', texts)
        self.assertEqual(len(set(frames)), 4)

    def test_local_offline_bitmap_survives_without_bridge(self):
        from prepare_sprites import offline_bitmap
        model = {'status': 'offline', 'active': 0, 'waiting': 0, 'remaining': 0, 'rows': []}
        frame = self.dashboard.frame(model)
        start = 8 + SUMMARY_SIZE[0] * SUMMARY_SIZE[1] // 8
        size = LIST_SIZE[0] * LIST_SIZE[1] // 8
        self.assertEqual(offline_bitmap(self.renderer.source), frame[start:start + size])
        self.assertTrue(any(frame[start:start + size]))

    def test_syncing_bitmap_is_available_before_encrypted_overview(self):
        from prepare_sprites import status_bitmap
        model = {'status': 'syncing', 'active': 0, 'waiting': 0, 'remaining': 0, 'rows': []}
        frame = self.dashboard.frame(model)
        start = 8 + SUMMARY_SIZE[0] * SUMMARY_SIZE[1] // 8
        size = LIST_SIZE[0] * LIST_SIZE[1] // 8
        self.assertEqual(status_bitmap('syncing', self.renderer.source), frame[start:start + size])

    def test_empty_messages_fit_and_missing_offline_glyphs_stop_import(self):
        from prepare_sprites import offline_bitmap
        from unittest.mock import patch
        from types import SimpleNamespace
        for labels in EMPTY_LABELS.values():
            for (text, _), size in zip(labels, (16, 12)):
                self.assertEqual(self.dashboard.fit(text, size, 216), [text])
        with patch('interaction.Renderer', return_value=SimpleNamespace(coverage=set())):
            with self.assertRaisesRegex(ValueError, '支持中文的字体'):
                offline_bitmap()

    def test_encrypted_overview_is_opt_in_and_never_changes_selection(self):
        from interaction import InteractionServer, SecureChannel, SelectionMemory, Broker, PIXELS
        class Desktop:
            def sessions(self, required=()):
                return [{'id': 'one', 'title': 'First', 'project': 'Alpha', 'project_id': 'a'},
                        {'id': 'two', 'title': 'Second', 'project': 'Beta', 'project_id': 'b'}]
            def projects(self):
                return [{'id': 'a', 'name': 'Alpha'}, {'id': 'b', 'name': 'Beta'}]
        server = InteractionServer.__new__(InteractionServer)
        server.key, server.desktop = 'a' * 32, Desktop()
        server.broker, server.renderer = Broker(), self.renderer
        server.active, server.target = threading.Lock(), None
        server.selection = SelectionMemory()
        server.dashboard = self.dashboard
        server.tracker = Tracker()
        server.tracker.accept(compact_event({'hook_event_name': 'UserPromptSubmit', 'session_id': 'two'}), __import__('time').monotonic())
        a, b = socket.socketpair()
        worker = threading.Thread(target=server.handle, args=(b,))
        worker.start()
        with a:
            a.settimeout(3)
            wire = SecureChannel(a, 'a' * 32)
            wire.send(b'\x01' + json.dumps({'cmd': 'sync', 'home': True}).encode())
            view = wire.receive()
            home = wire.receive()
            self.assertEqual(len(view), 17 + PIXELS)
            self.assertEqual(struct.unpack('!BBHHBB', home[:8]), (9, 2, 1, 0, 1, 0))
            self.assertIsNone(server.target)
            self.assertIsNone(server.selection.target)
            # Clients without overview support still receive exactly one response per request.
            wire.send(b'\x01' + json.dumps({'cmd': 'sync'}).encode())
            self.assertEqual(len(wire.receive()), 17 + PIXELS)
            wire.send(b'\x01' + json.dumps({'cmd': 'sessions', 'home': True}).encode())
            self.assertEqual(wire.receive()[0], 1)
            self.assertEqual(wire.receive()[0], 9)
            self.assertEqual(server.target, 'one')
            self.assertEqual(server.selection.target, 'one')
        worker.join(3)
        self.assertFalse(worker.is_alive())


if __name__ == '__main__':
    unittest.main()
