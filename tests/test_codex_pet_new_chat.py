"""Real local subprocesses exercise fresh-chat ownership without a model request."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/codex_pet'))
from new_chat import NewChatRunner, cli_path
from interaction import Desktop

THREAD = '0199a213-81c0-7800-8aa1-bbab2a035a53'


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.opened = []
        self.runner = NewChatRunner(self.opened.append)

    def tearDown(self):
        self.runner.close()
        self.temp.cleanup()

    def executable(self, body):
        path = self.root / 'fake-codex'
        path.write_text('#!' + sys.executable + '\n' + body)
        path.chmod(0o700)
        return str(path)

    def wait(self, predicate):
        end = time.monotonic() + 3
        while not predicate() and time.monotonic() < end:
            time.sleep(0.01)
        self.assertTrue(predicate())

    def test_prompt_is_stdin_project_is_cwd_and_handoff_waits_for_exit(self):
        executable = self.executable(f'''
import json, os, pathlib, sys, time
root=pathlib.Path(sys.argv[sys.argv.index('--cd')+1])
root.joinpath('input').write_text(sys.stdin.read())
root.joinpath('env').write_text(str('CODEX_THREAD_ID' in os.environ))
print(json.dumps({{'type':'thread.started','thread_id':{THREAD!r}}}),flush=True)
while not root.joinpath('release').exists(): time.sleep(.01)
print(json.dumps({{'type':'turn.completed'}}),flush=True)
''')
        voice = 'new voice $(do-not-execute); `literal` 中文。'
        with patch.dict(os.environ, {'CODEX_THREAD_ID':'existing-owner'}):
            job = self.runner.start(executable, self.root, 'selected-project', voice)
        self.wait(lambda: self.runner.status(job)['thread'] == THREAD)
        self.assertEqual((self.root / 'input').read_text(), voice)
        self.assertEqual((self.root / 'env').read_text(), 'False')
        self.assertTrue(self.runner.owns(THREAD))
        self.assertFalse(self.runner.owns('other'))
        self.assertEqual(self.opened, [])
        with self.assertRaises(RuntimeError): self.runner.start(executable, self.root, 'other', 'duplicate')
        (self.root / 'release').touch()
        self.wait(lambda: self.runner.status(job)['status'] == 'complete')
        self.assertEqual(self.opened, [THREAD])
        self.assertIsNotNone(self.runner.jobs[job]['process'].poll())
        self.assertFalse(self.runner.owns(THREAD))
        self.assertEqual(set(self.runner.status(job)), {'status','thread','project'})

    def test_failure_missing_identity_and_oversized_output_never_claim_success(self):
        for events, code in (([],0), ([{'type':'thread.started','thread_id':THREAD},
                                      {'type':'turn.failed'}],0),
                             ([{'type':'thread.started','thread_id':THREAD},
                               {'type':'turn.completed'}],1)):
            with self.subTest(events=events,code=code):
                executable = self.executable('import sys\nsys.stdin.read()\n' +
                    '\n'.join('print(' + repr(json.dumps(e)) + ',flush=True)' for e in events) +
                    '\nsys.exit(' + str(code) + ')\n')
                job = self.runner.start(executable, self.root, 'p', 'voice')
                self.wait(lambda: self.runner.status(job)['status'] == 'failed')
        executable = self.executable('import sys\nsys.stdin.read()\nprint("x"*200000)\n' +
            'print(' + repr(json.dumps({'type':'thread.started','thread_id':THREAD})) + ')\n' +
            'print(' + repr(json.dumps({'type':'turn.completed'})) + ')\n')
        job = self.runner.start(executable, self.root, 'p', 'voice')
        self.wait(lambda: self.runner.status(job)['status'] == 'complete')

    def test_close_stops_child_and_does_not_open_desktop(self):
        executable = self.executable('import time,sys\nsys.stdin.read()\ntime.sleep(30)\n')
        job = self.runner.start(executable, self.root, 'p', 'voice')
        self.runner.close()
        self.assertIsNotNone(self.runner.jobs[job]['process'].poll())
        self.assertEqual(self.opened, [])
        with self.assertRaises(RuntimeError): self.runner.start(executable, self.root, 'p', 'voice')

    def test_invalid_voice_does_not_launch(self):
        with patch('new_chat.subprocess.Popen') as launch:
            for text in ('', ' ', 'x' * 12001):
                with self.assertRaises(ValueError): self.runner.start('/codex', self.root, 'p', text)
            launch.assert_not_called()


class ProjectTests(unittest.TestCase):
    def test_inaccessible_project_and_ambiguous_shared_roots_fail_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            desktop = Desktop(directory)
            with patch.object(desktop, 'projects', return_value=[{'id':'a','name':'A'}]), patch.object(
                    desktop, 'project_state', return_value={}), patch.object(desktop, 'project_roots') as roots:
                for value in ({'a':[]}, {'a':['relative']}, {'a':[directory], 'b':[directory]}):
                    roots.return_value = value
                    with self.assertRaises(ValueError): desktop.project_directory('a')
                roots.return_value = {'a':[directory]}
                self.assertEqual(desktop.project_directory('a'), Path(directory).resolve())

    def test_modern_database_roots_map_cli_session_into_selected_project(self):
        import sqlite3
        from contextlib import closing
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(str(Path(directory)/'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE threads(id TEXT,name TEXT,cwd TEXT,project_id TEXT,archived INTEGER,agent_path TEXT,updated_at INTEGER)')
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.execute('CREATE TABLE project_roots(project_id TEXT,path TEXT,position INTEGER)')
                db.execute("INSERT INTO projects VALUES('p','Selected')")
                db.execute('INSERT INTO project_roots VALUES(?,?,0)', ('p',directory))
                db.execute('INSERT INTO threads VALUES(?,?,?,?,0,NULL,1)', (THREAD,'New',directory,None))
                db.commit()
            desktop = Desktop(directory)
            self.assertEqual(desktop._scan_sessions()[0]['project_id'], 'p')

    def test_migrated_database_root_survives_empty_legacy_paths_and_symlink(self):
        import sqlite3
        from contextlib import closing
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / 'work'; work.mkdir()
            alias = root / 'alias'; alias.symlink_to(work, target_is_directory=True)
            state = {'local-projects': {'legacy': {'name':'Selected', 'rootPaths':[]}},
                     'app-server-project-id-by-legacy-project-id-by-host': {'local': {'legacy':'p'}}}
            (root / '.codex-global-state.json').write_text(json.dumps(state))
            with closing(sqlite3.connect(str(root / 'state_5.sqlite'))) as db:
                db.execute('CREATE TABLE threads(id TEXT,name TEXT,cwd TEXT,project_id TEXT,archived INTEGER,agent_path TEXT,updated_at INTEGER)')
                db.execute('CREATE TABLE projects(id TEXT,name TEXT)')
                db.execute('CREATE TABLE project_roots(project_id TEXT,path TEXT,position INTEGER)')
                db.execute("INSERT INTO projects VALUES('p','Selected')")
                db.execute('INSERT INTO project_roots VALUES(?,?,0)', ('p',str(alias)))
                db.execute('INSERT INTO threads VALUES(?,?,?,?,0,NULL,1)', (THREAD,'New',str(work.resolve()),None))
                db.commit()
            desktop = Desktop(root)
            self.assertEqual(desktop.project_directory('p'), work.resolve())
            self.assertEqual(desktop._scan_sessions()[0]['project_id'], 'p')

    def test_cli_resolver_skips_broken_path_without_installing_or_changing_config(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory)/'codex'; executable.write_text(''); executable.chmod(0o700)
            with patch.dict(os.environ, {'CODEX_CLI_PATH':str(executable)}), patch(
                    'new_chat.subprocess.run', return_value=subprocess.CompletedProcess([],0,b'codex-cli 0.160.0\n')) as version:
                self.assertEqual(cli_path(), str(executable))
                self.assertEqual(version.call_args.args[0], [str(executable),'--version'])


if __name__ == '__main__':
    unittest.main()
