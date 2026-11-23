"""Exercise the privileged boundary with fake commands; never manage real units."""
import importlib.util
from pathlib import Path
import threading
import http.client
import socketserver
import pytest

path = Path(__file__).resolve().parents[2] / 'deploy/droplet/tool_supervisor.py'
spec = importlib.util.spec_from_file_location('tool_supervisor', path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def test_unknown_units_and_actions_never_execute(monkeypatch):
    calls=[]
    monkeypatch.setattr(helper, 'command', lambda *args: 'LoadState=loaded\nActiveState=active\nSubState=running\n')
    monkeypatch.setattr(helper.subprocess, 'run', lambda args, **kwargs: calls.append(args))
    class Server(socketserver.TCPServer): allow_reuse_address=True
    with Server(('127.0.0.1',0), helper.Handler) as server:
        thread=threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        def request(path):
            conn=http.client.HTTPConnection(*server.server_address)
            conn.request('POST',path); response=conn.getresponse();response.read();conn.close();return response.status
        try:
            assert request('/services/osii-api/restart')==404
            assert request('/services/extractor/delete')==404
            assert request('/services/extractor/restart?unit=ssh')==404
            assert not calls
            assert request('/services/ocr-regions/restart')==200
            assert calls==[['/usr/bin/systemctl','--no-block','restart','osii-ocr-regions.service']]
        finally: server.shutdown();thread.join()


def test_log_redaction_and_output_bound():
    result=helper.scrub('Authorization: Bearer secret-token\napi_key="secret-key" password=hidden https://user:pass@example.test sk-or-v1-testsecret')
    for secret in ['secret-token','secret-key','hidden','user:pass','sk-or-v1-testsecret']:
        assert secret not in result
    output=helper.command('/usr/bin/yes','a'*1000)
    assert len(output.encode())<=65536


def test_missing_optional_tool_has_no_controls(monkeypatch):
    monkeypatch.setattr(helper,'command',lambda *args:'LoadState=not-found\nActiveState=inactive\n')
    state=helper.status('ocr-page')
    assert state['status']=='not_installed'
    assert not any(state[k] for k in ['can_start','can_stop','can_restart','can_logs'])


def test_unix_transport_enforces_controller_errors(monkeypatch):
    import tempfile
    from osii.server import service_routes
    from fastapi import HTTPException
    monkeypatch.setattr(helper, 'command', lambda *args: 'LoadState=loaded\nActiveState=active\n')
    with tempfile.TemporaryDirectory(prefix='osii-', dir='/tmp') as directory:
        address=directory+'/control.sock'
        with socketserver.UnixStreamServer(address, helper.Handler) as server:
            thread=threading.Thread(target=server.serve_forever, daemon=True);thread.start()
            monkeypatch.setenv('OSII_TOOL_CONTROL_SOCKET',address)
            try:
                rows=service_routes.controller('GET','/services')['services']
                assert len(rows)==3 and all(row['can_restart'] for row in rows)
                with pytest.raises(HTTPException) as error:
                    service_routes.controller('POST','/services/ssh/restart')
                assert error.value.status_code==404
            finally: server.shutdown();thread.join()
    with pytest.raises(HTTPException) as error:
        service_routes.controller('GET','/services')
    assert error.value.status_code==503
