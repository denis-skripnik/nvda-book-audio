import importlib.util
from pathlib import Path
import tempfile
import unittest
from test_runtime import ROOT, PLUGIN, PYTHON, NVDA
import sys
sys.path.insert(0, str(PLUGIN))

class ClientTests(unittest.TestCase):
    def test_error_event_does_not_wait_for_driver_threads(self):
        import threading
        file = PLUGIN / 'client.py'
        spec = importlib.util.spec_from_file_location('book_client_error', file)
        client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(client)
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            client.HERE = Path(tmp)
            (Path(tmp) / 'worker.py').write_text('import json, threading\nthreading.Thread(target=lambda: threading.Event().wait(60)).start()\nprint(json.dumps({"type": "error", "message": "Ошибка драйвера"}), flush=True)\n', encoding='utf-8')
            runner = client.WorkerClient(python=PYTHON)
            done = threading.Event()
            errors = []
            def task():
                try:
                    runner.run({'action': 'voices'}, lambda event: None)
                except Exception as error:
                    errors.append(error)
                finally:
                    done.set()
            thread = threading.Thread(target=task)
            thread.start()
            finished = done.wait(3)
            if not finished:
                runner.cancel()
            thread.join(5)
            self.assertTrue(finished, 'A worker error must terminate orphaned driver threads promptly')
            self.assertIsInstance(errors[0], RuntimeError)
            self.assertIn('Ошибка драйвера', str(errors[0]))

    def test_cancel_stops_process_and_cleans_partial(self):
        import threading
        file = PLUGIN / 'client.py'
        spec = importlib.util.spec_from_file_location('book_client_cancel', file)
        client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(client)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'long.txt'
            source.write_text('Это длинная книга для проверки остановки. ' * 10000, encoding='utf-8')
            runner = client.WorkerClient(python=PYTHON)
            events = []
            def on_event(event):
                events.append(event)
                if event['type'] == 'chapter':
                    runner.cancel()
            with self.assertRaises(client.Cancelled):
                runner.run({'nvda': str(NVDA), 'addons': [], 'driver': 'sapi5', 'action': 'convert',
                            'files': [str(source)], 'output': tmp, 'separator': '', 'voice': '', 'rate': 50}, on_event)
            self.assertTrue(any(event['type'] == 'chapter' for event in events))
            self.assertFalse(list(Path(tmp).rglob('*.part')))
            self.assertIsNone(runner._process)

    def test_real_queue_of_txt_fb2_pdf_writes_four_mp3(self):
        file = PLUGIN / 'client.py'
        spec = importlib.util.spec_from_file_location('book_client_queue', file)
        client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(client)
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            txt = root / 'text.txt'
            txt.write_text('Глава 1\nПервая часть.\nГлава 2\nВторая часть.', encoding='utf-8')
            fb2 = root / 'fiction.fb2'
            fb2.write_text('<FictionBook><body><section><title><p>Глава 3</p></title><p>Третья часть.</p></section></body></FictionBook>', encoding='utf-8')
            pdf = root / 'paper.pdf'
            writer = PdfWriter()
            page = writer.add_blank_page(width=300, height=300)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(b'BT /F1 12 Tf 10 200 Td (An audio book test.) Tj ET')
            page[NameObject('/Contents')] = writer._add_object(stream)
            writer.write(pdf)
            runner = client.WorkerClient(python=PYTHON)
            events = []
            try:
                result = runner.run({'nvda': str(NVDA), 'addons': [], 'driver': 'sapi5', 'action': 'convert',
                                     'files': [str(txt), str(fb2), str(pdf)], 'output': tmp, 'separator': 'Глава', 'voice': '', 'rate': 50}, events.append)
            except RuntimeError:
                self.fail(str(events[-1]))
            self.assertEqual(result, {'type': 'done', 'count': 4})
            self.assertEqual(len(list(root.rglob('*.mp3'))), 4)
            self.assertEqual([Path(e['output']).parent.name for e in events if e['type'] == 'saved'], ['text', 'text', 'fiction', 'paper'])

    def test_runs_real_voice_enumeration_and_receives_events(self):
        file = PLUGIN / 'client.py'
        self.assertTrue(file.exists(), 'Worker client is not implemented')
        spec = importlib.util.spec_from_file_location('book_client', file)
        client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(client)
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            runner = client.WorkerClient(python=PYTHON)
            result = runner.run({'nvda': str(NVDA), 'addons': [], 'driver': 'sapi5', 'action': 'voices'}, events.append)
            self.assertEqual(result['type'], 'voices')
            self.assertTrue(result['voices'])
            self.assertEqual(events[-1], result)
