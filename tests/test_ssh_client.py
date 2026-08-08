from unittest import mock
from pathlib import Path

import pytest

from src.ssh_client import SSHClient


class _FakeChannel:
    def __init__(self, exit_code=0, out="", err=""):
        self._code = exit_code
        self._out = out.encode("utf-8")
        self._err = err.encode("utf-8")
        self._pos = 0

    def recv(self, n):
        chunk = self._out[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def recv_exit_status(self):
        return self._code


class _FakeStdout:
    def __init__(self, code, text):
        self.channel = _FakeChannel(code)
        self._text = text.encode("utf-8")

    def read(self):
        return self._text


class _FakeStderr:
    def __init__(self, text):
        self._text = text.encode("utf-8")

    def read(self):
        return self._text


class _FakeSessionChannel:
    def __init__(self, exec_map):
        self._exec_map = exec_map
        self._stream = b""
        self._code = 0
        self._pos = 0

    def settimeout(self, t):
        pass

    def exec_command(self, command):
        code, out, _ = self._exec_map.get(command, (0, "", ""))
        self._code = code
        self._stream = out.encode("utf-8")

    def recv(self, n):
        chunk = self._stream[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def recv_exit_status(self):
        return self._code


class _FakeClient:
    def __init__(self, exec_map=None):
        self.exec_map = exec_map or {}
        self.transport = _FakeTransport(self.exec_map)

    def get_transport(self):
        return self.transport

    def exec_command(self, command, timeout=60):
        code, out, err = self.exec_map.get(command, (0, "", ""))
        return None, _FakeStdout(code, out), _FakeStderr(err)


class _FakeTransport:
    def __init__(self, exec_map):
        self._exec_map = exec_map

    def open_session(self):
        return _FakeSessionChannel(self._exec_map)


def _make_client(exec_map=None):
    c = SSHClient("10.0.0.1", 22, "root", "pw")
    c._client = _FakeClient(exec_map)
    return c


def test_exec_stdout_returns_code_out_err():
    c = _make_client({"kubectl get ns": (0, "ns1\nns2\n", "")})
    code, out, err = c.exec_stdout("kubectl get ns")
    assert code == 0
    assert out == "ns1\nns2\n"
    assert err == ""


def test_stream_to_file_writes_bytes(tmp_path):
    payload = "A" * 1000
    c = _make_client({"cmd": (0, payload, "")})
    target = tmp_path / "out.bin"
    code = c.stream_to_file("cmd", str(target))
    assert code == 0
    assert target.read_text() == payload


@mock.patch("src.ssh_client.paramiko.SSHClient")
def test_connect_success(mock_cls):
    mock_client = mock.MagicMock()
    mock_cls.return_value = mock_client
    c = SSHClient("10.0.0.1", 22, "root", "pw").connect()
    mock_client.connect.assert_called_once()
    assert c._client is mock_client


@mock.patch("src.ssh_client.paramiko.SSHClient")
def test_connect_failure_raises(mock_cls):
    mock_client = mock.MagicMock()
    mock_client.connect.side_effect = Exception("auth failed")
    mock_cls.return_value = mock_client
    with pytest.raises(Exception):
        SSHClient("10.0.0.1", 22, "root", "pw").connect()


def test_close_closes_underlying_client_and_resets():
    c = SSHClient("10.0.0.1", 22, "root", "pw")
    fake = mock.MagicMock()
    c._client = fake
    c.close()
    fake.close.assert_called_once()
    assert c._client is None
    c.close()  # 幂等：重复 close 不报错
