"""paramiko SSH 封装：连接、一次性读小输出、流式写大输出到文件。"""
from pathlib import Path

import paramiko


class SSHClient:
    def __init__(self, host: str, port: int, username: str, password: str, timeout: int = 15):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self._client: paramiko.SSHClient | None = None

    def connect(self) -> "SSHClient":
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host, port=self.port,
            username=self.username, password=self.password,
            timeout=self.timeout, allow_agent=False, look_for_keys=False,
        )
        self._client = client
        return self

    def exec_stdout(self, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """执行命令，一次性读回 (退出码, stdout, stderr)。适合小输出。"""
        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return stdout.channel.recv_exit_status(), out, err

    def stream_to_file(self, command: str, filepath: Path, timeout: int = 600) -> int:
        """执行命令，把 stdout 流式写入文件，返回退出码。适合 tar 等大输出。"""
        channel = self._client.get_transport().open_session()
        channel.settimeout(timeout)
        channel.exec_command(command)
        with open(filepath, "wb") as fh:
            while True:
                chunk = channel.recv(65536)
                if not chunk:
                    break
                fh.write(chunk)
        return channel.recv_exit_status()

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
