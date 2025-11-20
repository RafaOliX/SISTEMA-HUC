import io
import os
import sys
import types
import pytest
from unittest import mock

# Ensure project root is on sys.path so tests can import App.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import App as app_mod

class FakeCursor:
    def __init__(self, responses=None):
        # responses: list of tuples or values to return for fetchone/fetchall
        self._exec_log = []
        self._responses = responses or []
        self.description = None
        self.lastrowid = 1
    def execute(self, sql, params=None):
        self._exec_log.append((sql, params))
        # If test code or subclass already pushed responses, don't override them.
        if self._responses:
            return
        # set description and default responses for some known queries
        if sql.strip().upper().startswith('SELECT COUNT(*) FROM RESERVAS'):
            self._responses.insert(0, (0,))
            self.description = None
        elif 'select paciente_id, equipo_id from reservas where id' in sql.lower() or 'SELECT paciente_id, equipo_id FROM reservas WHERE id=%s' in sql:
            # return existing paciente/equipo
            self._responses.insert(0, (42, 99))
            self.description = None
        elif sql.strip().upper().startswith('SELECT R.ID, R.SALA_ID, R.FECHA'):
            # used in reservas listing - return empty
            self._responses.insert(0, [])
            self.description = None
        else:
            # generic
            pass
    def fetchone(self):
        if not self._responses:
            return None
        return self._responses.pop(0)
    def fetchall(self):
        # if last response is list-like, return it; else empty
        return []
    def close(self):
        pass

class FakeConnection:
    def cursor(self):
        return FakeCursor()
    def commit(self):
        pass

class FakeMySQL:
    def __init__(self):
        self.connection = FakeConnection()

@pytest.fixture(autouse=True)
def fake_mysql(monkeypatch):
    fake = FakeMySQL()
    monkeypatch.setattr(app_mod, 'mysql', fake)
    return fake


def test_reservar_sala_crea_reserva(client=None):
    client = client or app_mod.app.test_client()
    data = {
        'sala_id': '1',
        'fecha': '2025-11-20',
        'hora_inicio': '09:00',
        'hora_fin': '10:00',
        'paciente_id': '42',
        'equipo_id': '99'
    }
    resp = client.post('/reservar_sala', data=data, follow_redirects=False)
    # reserva route redirects to /reservas on success
    assert resp.status_code in (302, 303)


def test_editar_reserva_preserva_ids(monkeypatch):
    client = app_mod.app.test_client()
    # We'll patch mysql.connection.cursor to a cursor that records SQL executed
    executed = []
    class CursorRec(FakeCursor):
        def execute(self, sql, params=None):
            executed.append((sql, params))
            # emulate SELECT paciente_id, equipo_id
            if 'SELECT paciente_id, equipo_id FROM reservas WHERE id=%s' in sql:
                self._responses.insert(0, (123, 456))
            return super().execute(sql, params)
    class ConnRec:
        def cursor(self):
            return CursorRec()
        def commit(self):
            pass
    monkeypatch.setattr(app_mod, 'mysql', types.SimpleNamespace(connection=ConnRec()))

    # Post only fecha/hora (no paciente_id/equipo_id) -> should preserve existing (123,456)
    resp = client.post('/editar_reserva/1', data={'fecha': '2025-11-21', 'hora_inicio': '08:00', 'hora_fin': '09:00'}, follow_redirects=False)
    assert resp.status_code in (302,303)
    # find the last UPDATE executed and ensure params include 123 and 456
    update_execs = [e for e in executed if e[0].strip().upper().startswith('UPDATE RESERVAS')]
    assert update_execs, 'No UPDATE executed'
    # params tuple is (fecha, hora_inicio, hora_fin, paciente_id, equipo_id, id)
    params = update_execs[-1][1]
    assert params[3] == 123
    assert params[4] == 456


def test_export_pdf_returns_pdf(monkeypatch):
    # Patch fetch_historial to return simple rows so/pdf building proceeds
    monkeypatch.setattr(app_mod, 'fetch_historial', lambda *args, **kwargs: ([{'fecha':'2025-11-19','descripcion':'x'}], ['fecha','descripcion']))
    client = app_mod.app.test_client()
    # mark session as authenticated so route doesn't redirect
    with client.session_transaction() as sess:
        sess['usuario_autenticado'] = 'testuser'
        sess['nombre_usuario'] = 'testuser'
    # Also patch any heavy reportlab calls by ensuring send_file will be called successfully
    resp = client.get('/historial/export/pdf')
    assert resp.status_code == 200
    ctype = resp.headers.get('Content-Type','')
    assert 'pdf' in ctype
