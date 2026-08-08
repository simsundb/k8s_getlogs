"""paramiko SSH 封装：连接、一次性读小输出、流式写大输出到文件。"""
import os
import threading
from pathlib import Path

import paramiko


def _drain_stderr(channel, holder) -> None:
    """后台线程：持续排空 stderr，避免远端写满 stderr 管道导致死锁。"""
    while True:
        try:
            chunk = channel.recv_stderr(8192)
        except Exception:
            break
        if not chunk:
            break
        holder.add(chunk)


class _StderrCapture:
    """有界 stderr 收集器，只保留最后 max_bytes，供错误报告使用。"""

    def __init__(self, max_bytes: int = 2048):
        self._buf = bytearray()
        self._max = max_bytes

    def add(self, chunk: bytes) -> None:
        self._buf.extend(chunk)
        if len(self._buf) > self._max:
            self._buf = self._buf[-self._max:]

    def text(self) -> str:
        return self._buf.decode("utf-8", errors="replace")


class SSHClient:
    def __init__(self, host: str, port: int, username: str, password: str, timeout: int = 15):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self._client: paramiko.SSHClient | None = None
        self.last_stderr = ""

    def connect(self) -> "SSHClient":
        if self._client is not None:
            self._client.close()
            self._client = None
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host, port=self.port,
            username=self.username, password=self.password,
            timeout=self.timeout, allow_agent=False, look_for_keys=False,
        )
        self._client = client
        return self

    def _require_client(self) -> paramiko.SSHClient:
        if self._client is None:
            raise RuntimeError("未连接，请先 connect()")
        return self._client

    def exec_stdout(self, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """执行命令，一次性读回 (退出码, stdout, stderr)。适合小输出。"""
        client = self._require_client()
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return stdout.channel.recv_exit_status(), out, err

    def stream_to_file(self, command: str, filepath: Path | str, timeout: int = 600) -> int:
        """执行命令，把 stdout 流式写入文件，返回退出码。适合 tar 等大输出。

        后台线程排空 stderr 防死锁；写文件期间任何异常都会删除残留文件。
        排空到的 stderr（保留最后约 2KB）可通过 self.last_stderr 获取。
        """
        client = self._require_client()
        channel = client.get_transport().open_session()
        channel.settimeout(timeout)
        channel.exec_command(command)

        stderr = _StderrCapture()
        drainer = threading.Thread(
            target=_drain_stderr, args=(channel, stderr), daemon=True)
        drainer.start()
        try:
            with open(filepath, "wb") as fh:
                while True:
                    chunk = channel.recv(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
            code = channel.recv_exit_status()
        except BaseException:
            try:
                os.unlink(filepath)
            except OSError:
                pass
            try:
                channel.close()
            except Exception:
                pass
            raise
        finally:
            drainer.join(timeout=5)
            self.last_stderr = stderr.text()
        return code

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
