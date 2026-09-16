#!/usr/bin/env python3
"""Install a temporary copy and test the actual preview at moz-extension://.
Requires FIREFOX_BINARY, Node.js and pdf-lib. Does not submit or sign anything.
Added test files are confined to a temporary copy, never the release extension.
Marionette's privileged access is used ONLY by this test driver, not the add-on.
"""
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
FIREFOX = os.environ['FIREFOX_BINARY']
DISABLE_SANDBOX = os.environ.get('PAPERLESS_TEST_DISABLE_BROWSER_SANDBOX') == '1'

with tempfile.TemporaryDirectory(prefix='paperless-native-test-') as directory:
    work = Path(directory)
    extension = work / 'extension'
    shutil.copytree(ROOT / 'extension', extension)
    subprocess.run(['node', str(ROOT / 'tests/make-preview-fixture.cjs'), str(extension / 'fixture.pdf')], check=True)
    (extension / 'native-test.html').write_text('''<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="app.css"><link rel="stylesheet" href="popup.css">
<link rel="stylesheet" href="pdf-preview.css">
<span class="job-thumbnail" id="trigger" tabindex="0" style="margin:80px">
<img src="icons/paperless-send-96.png" alt="Test PDF">
<span class="thumbnail-zoom"><img src="icons/paperless-send-96.png" alt=""></span></span>
<script src="pdf-preview.js"></script><script src="native-test.js"></script>''')
    (extension / 'native-test.js').write_text('''
const state = {config:{base:'https://fixture.invalid/'},unlocked:true,previewRevision:0};
window.reads = 0;
window.revoked = [];
const originalRevoke = URL.revokeObjectURL.bind(URL);
URL.revokeObjectURL = url => {window.revoked.push(url); originalRevoke(url);};
const P = {state:async()=>state,documentPageCount:async()=>3,
  documentPDF:async()=>{window.reads++;return (await fetch('fixture.pdf')).blob();}};
const preview = new PdfPreview(P), trigger = document.getElementById('trigger');
preview.sync(state);
preview.attach(trigger,trigger.querySelector('.thumbnail-zoom'),trigger.querySelector('.thumbnail-zoom img'),1,state.config.base);
window.lockPreview = () => {state.unlocked=false;state.previewRevision++;preview.sync(state);};
''')
    profile = work / 'profile'
    profile.mkdir()
    prefs = {'marionette.port': 2828, 'pdfjs.disabled': False,
             'browser.shell.checkDefaultBrowser': False,
             'browser.startup.homepage_override.mstone': 'ignore'}
    if DISABLE_SANDBOX:
        prefs['security.sandbox.content.level'] = 0
    (profile / 'user.js').write_text(''.join(f'user_pref({json.dumps(key)}, {json.dumps(value)});\n' for key, value in prefs.items()))
    env = os.environ.copy()
    if DISABLE_SANDBOX:
        env['MOZ_DISABLE_CONTENT_SANDBOX'] = '1'
    with (work / 'firefox.log').open('w') as log:
        process = subprocess.Popen([FIREFOX, '--headless', '--no-remote', '--profile', str(profile),
            '-marionette', '--remote-allow-system-access', 'about:blank'], stdout=log, stderr=log, env=env)
        connection = None
        try:
            for attempt in range(150):
                try:
                    connection = socket.create_connection(('127.0.0.1', 2828), timeout=1)
                    break
                except OSError:
                    time.sleep(.1)
            if not connection:
                raise RuntimeError('Firefox Marionette did not start')
            connection.settimeout(30)
            sequence = 0

            def receive():
                length = b''
                while not length.endswith(b':'):
                    part = connection.recv(1)
                    if not part:
                        raise EOFError('Firefox disconnected')
                    length += part
                data, size = b'', int(length[:-1])
                while len(data) < size:
                    part = connection.recv(size - len(data))
                    if not part:
                        raise EOFError('Firefox disconnected')
                    data += part
                return json.loads(data)

            def command(name, arguments=None):
                global sequence
                sequence += 1
                payload = json.dumps([0, sequence, name, arguments or {}]).encode()
                connection.sendall(str(len(payload)).encode() + b':' + payload)
                result = receive()
                if result[2]:
                    raise RuntimeError(result[2])
                return result[3]

            def evaluate(script):
                return command('WebDriver:ExecuteScript', {'script': script, 'args': []})['value']

            def until(script, timeout=15):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if evaluate(script):
                        return
                    time.sleep(.1)
                raise AssertionError('Timed out: ' + script)

            receive()
            session = command('WebDriver:NewSession', {'pageLoadStrategy': 'eager'})
            command('Addon:Install', {'path': str(extension), 'temporary': True})
            command('Marionette:SetContext', {'value': 'chrome'})
            # Automation builds default to downloading PDFs. Restore normal PDF
            # viewing in this disposable test profile, never the user's profile.
            evaluate("""Services.prefs.setBoolPref('pdfjs.disabled', false);
const mime=Components.classes['@mozilla.org/mime;1'].getService(Components.interfaces.nsIMIMEService).getFromTypeAndExtension('application/pdf','pdf');
mime.preferredAction=Components.interfaces.nsIHandlerInfo.handleInternally;mime.alwaysAskBeforeHandling=false;
Components.classes['@mozilla.org/uriloader/handler-service;1'].getService(Components.interfaces.nsIHandlerService).store(mime);""")
            url = evaluate("return WebExtensionPolicy.getByID('paperless-send@local').getURL('native-test.html');")
            command('Marionette:SetContext', {'value': 'content'})
            command('WebDriver:Navigate', {'url': url})
            assert evaluate('return window.reads;') == 0
            position = evaluate("const r=document.getElementById('trigger').getBoundingClientRect();return {x:Math.round(r.x+10),y:Math.round(r.y+10)};")
            command('WebDriver:PerformActions', {'actions': [{'type': 'pointer', 'id': 'mouse',
                'parameters': {'pointerType': 'mouse'}, 'actions': [{'type': 'pointerMove', 'duration': 0,
                    'origin': 'viewport', **position}]}]})
            until("return document.querySelector('.pdf-page-frame')?.hidden === false;")
            blob_url = evaluate("return document.querySelector('iframe').src.split('#')[0];")

            def page_is(number):
                command('WebDriver:SwitchToFrame', {'id': 0})
                until(f'return window.PDFViewerApplication?.page === {number} && window.PDFViewerApplication.pdfViewer.getPageView({number}-1)?.renderingState === 3;')
                assert evaluate('return window.PDFViewerApplication.pagesCount;') == 3
                command('WebDriver:SwitchToFrame', {'id': None})

            page_is(1)
            assert evaluate("return document.querySelector('iframe').contentDocument;") is None
            command('WebDriver:PerformActions', {'actions': [{'type': 'wheel', 'id': 'wheel',
                'actions': [{'type': 'scroll', 'x': position['x'], 'y': position['y'],
                             'deltaX': 0, 'deltaY': 120, 'duration': 0, 'origin': 'viewport'}]}]})
            page_is(2)
            command('WebDriver:PerformActions', {'actions': [{'type': 'key', 'id': 'keys',
                'actions': [{'type': 'keyDown', 'value': '\ue014'}, {'type': 'keyUp', 'value': '\ue014'}]}]})
            page_is(3)
            assert evaluate('return window.reads;') == 1
            screenshot = os.environ.get('PAPERLESS_TEST_SCREENSHOT')
            if screenshot:
                Path(screenshot).write_bytes(base64.b64decode(command('WebDriver:TakeScreenshot')['value']))
            evaluate('window.lockPreview();')
            assert evaluate("return document.querySelectorAll('iframe').length;") == 0
            assert blob_url in evaluate('return window.revoked;')
            # Hover must not silently download PDFs when the native viewer is disabled.
            command('Marionette:SetContext', {'value': 'chrome'})
            evaluate("Services.prefs.setBoolPref('pdfjs.disabled', true);")
            command('Marionette:SetContext', {'value': 'content'})
            command('WebDriver:Navigate', {'url': url})
            evaluate("document.getElementById('trigger').focus();")
            until("return document.querySelector('.pdf-page-footer').textContent.includes('aktivieren');")
            assert evaluate('return window.reads;') == 0
            assert evaluate("return document.querySelectorAll('iframe').length;") == 0
            # Also check the common 'Save File' application setting. Sandboxing
            # must prevent a download, and the original thumbnail must remain.
            command('Marionette:SetContext', {'value': 'chrome'})
            evaluate("""Services.prefs.setBoolPref('pdfjs.disabled', false);
const mime=Components.classes['@mozilla.org/mime;1'].getService(Components.interfaces.nsIMIMEService).getFromTypeAndExtension('application/pdf','pdf');
mime.preferredAction=Components.interfaces.nsIHandlerInfo.saveToDisk;mime.alwaysAskBeforeHandling=false;
Components.classes['@mozilla.org/uriloader/handler-service;1'].getService(Components.interfaces.nsIHandlerService).store(mime);""")
            command('Marionette:SetContext', {'value': 'content'})
            command('WebDriver:Navigate', {'url': url})
            evaluate("document.getElementById('trigger').focus();")
            until("return document.querySelector('.pdf-page-footer').textContent.includes('„In Firefox öffnen“');")
            assert evaluate("return document.querySelector('.pdf-page-frame').hidden;") is True
            assert evaluate("return document.querySelector('.pdf-page-body img').hidden;") is False
            command('Marionette:SetContext', {'value': 'chrome'})
            downloads = command('WebDriver:ExecuteAsyncScript', {'script': """const done=arguments[arguments.length-1];
const {Downloads}=ChromeUtils.importESModule('resource://gre/modules/Downloads.sys.mjs');
Downloads.getList(Downloads.ALL).then(list=>list.getAll()).then(items=>done(items.length));""", 'args': [], 'scriptTimeout': 10000})['value']
            assert downloads == 0, 'Hover must never cause an unsolicited PDF download'
            print('Installed Firefox extension PASS:', session['capabilities']['browserVersion'],
                  'native pages 1–3, mouse hover, wheel, arrow key, isolated frame, single read, lock/revoke, disabled viewer and no downloads')
        except Exception:
            print((work / 'firefox.log').read_text()[-5000:])
            raise
        finally:
            if connection:
                connection.close()
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
