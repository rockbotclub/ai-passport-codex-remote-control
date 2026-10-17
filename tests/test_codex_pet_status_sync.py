"""Startup reconciliation, hook races, failure handling and IPC observer cleanup."""
from pathlib import Path
import hashlib
import socket
import sqlite3
import struct
import sys
import json
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/codex_pet'))
from bridge import Tracker, compact_event
from dashboard import overview
from interaction import Desktop, exact
from status_sync import StatusSync, compact_snapshot, thread_catalog


def identity(thread):
    return hashlib.sha256(thread.encode()).hexdigest()[:32]


def snapshot(status='active', flags=None, requests=None):
    return compact_snapshot({'threadRuntimeStatus': {'type': status, 'activeFlags': flags or []},
                             'requests': requests or [], 'title': 'private', 'turns': ['private']})


def hook(event, thread='one', turn='a'):
    return compact_event({'hook_event_name': event, 'session_id': thread, 'turn_id': turn})


class SyncTests(unittest.TestCase):
    def tracker(self):
        tracker = Tracker(sync=True)
        tracker.set_catalog({'one': 'one', 'cli': 'cli'})
        return tracker

    def test_initial_unknown_then_confirmed_empty(self):
        tracker = self.tracker()
        now = tracker.sync_started
        self.assertEqual(tracker.snapshot(now), b'CP1 syncing 0 0\n')
        self.assertEqual(overview(tracker.activity(now), [])['status'], 'syncing')
        tracker.reconcile({}, 0, now + 1, True)
        self.assertEqual(tracker.snapshot(now + 1), b'CP1 idle 0 0\n')

    def test_already_running_without_hooks_and_completion(self):
        tracker = self.tracker()
        now = tracker.sync_started
        tracker.reconcile({identity('one'): snapshot()}, 0, now, True)
        self.assertEqual(tracker.snapshot(now), b'CP1 working 1 0\n')
        tracker.accept(hook('Stop'), now + 1)
        self.assertEqual(tracker.snapshot(now + 1), b'CP1 done 0 0\n')
        self.assertEqual(tracker.snapshot(now + 9), b'CP1 idle 0 0\n')

    def test_snapshot_cannot_overwrite_newer_hook_or_resurrect_closed_chat(self):
        for event in ('Stop', 'SessionEnd', 'PermissionRequest'):
            with self.subTest(event=event):
                tracker = self.tracker()
                revision = tracker.revision()
                tracker.accept(hook(event), 10)
                tracker.reconcile({identity('one'): snapshot()}, revision, 11, True)
                expected = {'Stop': b'CP1 done 0 0\n', 'SessionEnd': b'CP1 idle 0 0\n',
                            'PermissionRequest': b'CP1 waiting 1 1\n'}[event]
                self.assertEqual(tracker.snapshot(11), expected)

    def test_failed_sync_never_means_idle_and_recovers(self):
        tracker = self.tracker()
        now = tracker.sync_started
        tracker.reconcile({}, 0, now + 1, False)
        self.assertEqual(tracker.snapshot(now + 1), b'CP1 syncing 0 0\n')
        self.assertEqual(tracker.snapshot(now + 15), b'CP1 error 0 0\n')
        tracker.reconcile({identity('one'): snapshot()}, 0, now + 16, True)
        self.assertEqual(tracker.snapshot(now + 16), b'CP1 working 1 0\n')
        tracker.reconcile({}, 0, now + 17, False)
        self.assertEqual(tracker.snapshot(now + 17), b'CP1 working 1 0\n')

    def test_partial_snapshot_shows_known_work_before_scan_finishes(self):
        tracker = self.tracker()
        tracker.reconcile({identity('one'): snapshot()}, 0, tracker.sync_started, False)
        self.assertEqual(tracker.snapshot(tracker.sync_started), b'CP1 working 1 0\n')

    def test_unloaded_removes_snapshot_only_and_preserves_cli_hooks(self):
        tracker = self.tracker()
        tracker.reconcile({identity('one'): snapshot()}, 0, 1, True)
        tracker.accept(hook('UserPromptSubmit', 'cli'), 2)
        tracker.reconcile({}, tracker.revision(), 3, True)
        self.assertEqual(tracker.snapshot(3), b'CP1 working 1 0\n')
        self.assertNotIn(identity('one'), tracker.sessions)

    def test_same_status_refresh_preserves_turn_and_waiting_tool(self):
        tracker = self.tracker()
        tracker.accept(hook('UserPromptSubmit'), 1)
        tracker.reconcile({identity('one'): snapshot()}, tracker.revision(), 2, True)
        tracker.accept(hook('Stop', turn='old'), 3)
        self.assertEqual(tracker.snapshot(3), b'CP1 working 1 0\n')

    def test_unloaded_desktop_hook_state_is_removed_without_waiting_for_expiry(self):
        tracker = self.tracker()
        tracker.accept(hook('UserPromptSubmit'), 1)
        tracker.reconcile({identity('one'): snapshot()}, tracker.revision(), 2, True)
        tracker.reconcile({}, tracker.revision(), 3, None, absent=(identity('one'),))
        self.assertEqual(tracker.snapshot(3), b'CP1 idle 0 0\n')

    def test_no_owner_does_not_remove_cli_or_a_hook_newer_than_the_read(self):
        tracker = self.tracker()
        tracker.accept(hook('UserPromptSubmit', 'cli'), 1)
        tracker.reconcile({}, tracker.revision(), 2, None, absent=(identity('cli'),))
        self.assertEqual(tracker.snapshot(2), b'CP1 working 1 0\n')
        tracker.reconcile({identity('one'): snapshot()}, tracker.revision(), 3, True)
        revision = tracker.revision()
        tracker.accept(hook('PermissionRequest'), 4)
        tracker.reconcile({}, revision, 5, None, absent=(identity('one'),))
        self.assertEqual(tracker.snapshot(5), b'CP1 waiting 2 1\n')

    def test_independent_visible_chats_stay_separate_and_internal_agents_are_excluded(self):
        tracker = self.tracker()
        tracker.set_catalog({'one': 'one', 'two': 'two', 'guardian': None, 'archived': None})
        tracker.reconcile({}, 0, 0, True)
        for thread in ('one', 'two', 'guardian', 'archived'):
            tracker.accept(hook('UserPromptSubmit', thread), 1)
        self.assertEqual(tracker.snapshot(2), b'CP1 working 2 0\n')
        activity = tracker.activity(2, ['two'])
        self.assertEqual(activity[identity('two')]['status'], 'waiting')
        self.assertEqual({key for key in activity if not key.startswith('@')}, {identity('one'), identity('two')})
        tracker.accept(hook('Stop', 'two'), 3)
        self.assertEqual(tracker.snapshot(3), b'CP1 working 1 0\n')
        tracker.accept(hook('Stop'), 4)
        self.assertEqual(tracker.snapshot(4), b'CP1 done 0 0\n')

    def test_unconfirmed_identity_is_global_sync_only_then_recovers(self):
        tracker = self.tracker()
        tracker.accept(hook('UserPromptSubmit', 'new'), 1)
        model = overview(tracker.activity(2), [])
        self.assertEqual((model['status'], model['active'], model['rows']), ('syncing', 0, []))
        self.assertEqual(tracker.snapshot(16), b'CP1 error 0 0\n')
        tracker.set_catalog({'new': 'new'})
        model = overview(tracker.activity(17), [])
        self.assertEqual((model['active'], model['rows'][0]['title']), (1, '未命名会话'))
        sync = StatusSync(Desktop(), tracker)
        sync.notify(identity('new'))
        self.assertFalse(sync.wake.is_set())
        sync.notify(identity('unknown'))
        self.assertTrue(sync.wake.is_set())

    def test_complete_sweep_clears_an_unloaded_hook_observed_on_desktop(self):
        tracker = self.tracker()
        tracker.accept(hook('UserPromptSubmit'), 1)
        tracker.reconcile({identity('one'): snapshot()}, tracker.revision(), 2, True)
        desktop = Desktop()
        sync = StatusSync(desktop, tracker)
        with patch.object(desktop, 'activity_index', return_value={'one': 'one'}), \
             patch.object(desktop, 'activity_snapshots', return_value=iter([('one', None)])), \
             patch.object(sync.stop, 'wait', return_value=True):
            sync.run()
        self.assertEqual(tracker.snapshot(3), b'CP1 idle 0 0\n')

    def test_idle_refresh_does_not_replay_finished_animation(self):
        tracker = self.tracker()
        tracker.accept(hook('Stop'), 1)
        tracker.reconcile({identity('one'): snapshot('idle')}, tracker.revision(), 20, True)
        self.assertEqual(tracker.snapshot(20), b'CP1 idle 0 0\n')
        tracker.reconcile({}, tracker.revision(), 21, False)
        self.assertEqual(tracker.snapshot(21), b'CP1 error 0 0\n')

    def test_compact_snapshot_privacy_and_waiting_states(self):
        for value in (snapshot(flags=['waitingOnApproval']), snapshot(flags=['waitingOnUserInput']),
                      snapshot(requests=[{'method': 'item/tool/requestUserInput', 'params': 'private'}])):
            self.assertEqual(value['status'], 'waiting')
            self.assertNotIn('private', json.dumps(value))
        self.assertEqual(snapshot('systemError')['status'], 'error')
        for state in ([], {}, {'threadRuntimeStatus': {'type': 'future'}}):
            with self.assertRaises(ValueError):
                compact_snapshot(state)

    def test_scan_database_failure_is_retryable(self):
        tracker = self.tracker()
        desktop = Desktop()
        sync = StatusSync(desktop, tracker)
        with patch.object(desktop, 'activity_index', side_effect=sqlite3.OperationalError('unavailable')), \
             patch.object(sync.stop, 'wait', return_value=True):
            sync.run()
        self.assertTrue(tracker.sync_failed)
        self.assertFalse(tracker.sync_ready)

    def test_workers_do_not_block_start_and_close(self):
        tracker = self.tracker()
        desktop = Desktop()
        sync = StatusSync(desktop, tracker)
        entered, release = threading.Event(), threading.Event()
        def read():
            entered.set()
            release.wait(2)
            return {}
        with patch.object(desktop, 'activity_index', side_effect=read), patch.object(desktop, 'activity_snapshots', return_value=iter([])):
            sync.start()
            self.assertTrue(entered.wait(1))
            self.assertEqual(tracker.snapshot(tracker.sync_started), b'CP1 syncing 0 0\n')
            release.set()
            sync.close()
            self.assertFalse(sync.worker.is_alive())


class DesktopSnapshotTests(unittest.TestCase):
    def test_saved_sources_distinguish_user_chats_from_internal_agents(self):
        def child(parent):
            return json.dumps({'subagent': {'thread_spawn': {'parent_thread_id': parent}}})
        roots = thread_catalog([
            ('one', 0, None, 'vscode'), ('child', 0, '/root/child', child('one')),
            ('nested', 0, '/root/child/nested', child('child')),
            ('guardian', 0, None, '{"subagent":{"other":"guardian"}}'),
            ('archived', 1, None, 'vscode'), ('orphan', 0, '/root/x', child('absent')),
            ('loop-a', 0, None, child('loop-b')), ('loop-b', 0, None, child('loop-a')),
            ('archived-child', 0, None, child('archived')), ('cli', 0, None, 'exec')])
        self.assertEqual({key: value for key, value in roots.items() if value is not None},
                         {'one': 'one', 'cli': 'cli'})

    def test_read_only_snapshot_and_observer_cleanup(self):
        for bad_version in (False, True):
            a, b = socket.socketpair()
            requests, errors = [], []
            def server():
                try:
                    with b:
                        b.settimeout(3)
                        def receive():
                            return json.loads(exact(b, struct.unpack('<I', exact(b, 4))[0]))
                        def send(value):
                            Desktop._ipc_send(b, value)
                        for result in ({'clientId': 'observer'}, {}):
                            req = receive(); requests.append(req)
                            send({'type': 'response', 'requestId': req['requestId'], 'resultType': 'success',
                                  'result': result, 'handledByClientId': 'owner'})
                        requests.append(receive())
                        send({'type': 'client-discovery-request', 'requestId': 'discovery', 'request': {}})
                        requests.append(receive())
                        send({'type': 'broadcast', 'method': 'thread-stream-state-changed',
                              'version': 12 if bad_version else 11, 'sourceClientId': 'owner',
                              'params': {'hostId': 'local', 'conversationId': 'one', 'change': {
                                  'type': 'snapshot', 'conversationState': {
                                      'threadRuntimeStatus': {'type': 'active', 'activeFlags': []}}}}})
                        if bad_version:
                            b.shutdown(socket.SHUT_WR)
                        requests.append(receive())
                except BaseException as error:
                    errors.append(error)
            worker = threading.Thread(target=server);worker.start()
            with patch.object(Desktop, '_ipc_socket', return_value=a):
                if bad_version:
                    self.assertIs(Desktop().activity_snapshot('one'), False)
                else:
                    self.assertEqual(Desktop().activity_snapshot('one')['status'], 'working')
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual([r.get('method') for r in requests if r['type']=='request'],
                             ['initialize', 'thread-owner-discovery'])
            self.assertEqual(requests[3]['response'], {'canHandle': False})
            self.assertTrue(requests[2]['params']['following'])
            self.assertFalse(requests[-1]['params']['following'])

    def test_no_owner_is_not_a_timeout(self):
        desktop = Desktop()
        for failure, expected in (('no-client-found', None), ('request-timeout', False), (None, False)):
            a, b = socket.socketpair()
            sent = []
            def receive(sock, deadline):
                if failure is None:
                    raise TimeoutError()
                return {'type': 'response', 'requestId': sent[-1]['requestId'],
                        'resultType': 'error', 'error': failure}
            with a, b, patch.object(desktop, '_ipc_socket', return_value=a), patch.object(
                    desktop, '_ipc_call', return_value={'result': {'clientId': 'observer'}}), patch.object(
                    desktop, '_ipc_send', side_effect=lambda sock, msg: sent.append(msg)), patch.object(
                    desktop, '_ipc_receive', side_effect=receive):
                self.assertIs(StatusSync(desktop, Tracker()).read('one'), expected)

    def test_batch_delivers_active_before_unloaded_history(self):
        desktop = Desktop()
        a, b = socket.socketpair()
        sent, reads = [], []
        def receive(sock, deadline):
            reads.append(True)
            if len(reads) == 1:
                self.assertEqual(len(sent), 2)  # Both discoveries are already in flight.
                return {'type': 'response', 'requestId': sent[0]['requestId'],
                        'resultType': 'success', 'handledByClientId': 'owner'}
            if len(reads) == 2:
                return {'type': 'broadcast', 'method': 'thread-stream-state-changed', 'version': 11,
                        'sourceClientId': 'owner', 'params': {'hostId': 'local', 'conversationId': 'running',
                        'change': {'type': 'snapshot', 'conversationState': {
                            'threadRuntimeStatus': {'type': 'active', 'activeFlags': []}}}}}
            return {'type': 'response', 'requestId': sent[1]['requestId'],
                    'resultType': 'error', 'error': 'no-client-found'}
        with a, b, patch.object(desktop, '_ipc_socket', return_value=a), patch.object(
                desktop, '_ipc_call', return_value={'result': {'clientId': 'observer'}}), patch.object(
                desktop, '_ipc_send', side_effect=lambda sock, msg: sent.append(msg)), patch.object(
                desktop, '_ipc_receive', side_effect=receive):
            results = desktop.activity_snapshots(['running', 'old'])
            thread, value = next(results)
            self.assertEqual((thread, value['status']), ('running', 'working'))
            self.assertEqual(len(reads), 2)
            self.assertEqual(list(results), [('old', None)])


if __name__ == '__main__':
    unittest.main()
