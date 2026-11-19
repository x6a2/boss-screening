"""极简 Chrome DevTools Protocol 客户端（纯标准库）。

为什么自己写：CDP 只提供 WebSocket，标准库没有 ws 客户端；引入第三方库会
让"零依赖"这个卖点失效。这里只实现最小可用子集：
握手、发送文本帧、接收文本帧、处理 ping/close。

不做的事：压缩扩展、二进制帧、分片重组之外的任何高级特性。
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
from typing import Any
from urllib.parse import urlparse


class CDPError(RuntimeError):
    pass


class WebSocket:
    """够用就行的 WebSocket 客户端。"""

    def __init__(self, url: str, timeout: float = 10.0) -> None:
        u = urlparse(url)
        if u.scheme != "ws":
            raise CDPError(f"只支持 ws:// ，收到 {url}")
        self.host = u.hostname or "127.0.0.1"
        self.port = u.port or 80
        self.path = u.path or "/"
        if u.query:
            self.path += "?" + u.query
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = b""
        self._handshake()

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        while b"\r\n\r\n" not in self._buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("握手时连接被关闭")
            self._buf += chunk
        head, self._buf = self._buf.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0]
        if b"101" not in status:
            raise CDPError(f"WebSocket 握手失败：{status.decode(errors='replace')}")

    # --- 帧 -----------------------------------------------------------
    def send(self, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", n)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _read_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise CDPError("连接已关闭")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv(self) -> str:
        """返回一条完整文本消息；自动忽略 ping/pong。"""
        parts: list[bytes] = []
        while True:
            b1, b2 = self._read_exact(2)
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            data = self._read_exact(length)
            if masked:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))

            if opcode == 0x8:
                raise CDPError("对端关闭了 WebSocket")
            if opcode == 0x9:  # ping
                self._pong(data)
                continue
            if opcode == 0xA:  # pong
                continue
            parts.append(data)
            if fin:
                return b"".join(parts).decode("utf-8", errors="replace")

    def _pong(self, data: bytes) -> None:
        header = bytearray([0x8A])
        n = len(data)
        header.append(0x80 | n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class CDPSession:
    """对某个 target 的一次会话。只暴露 call()。"""

    def __init__(self, ws_url: str, timeout: float = 20.0) -> None:
        self.ws = WebSocket(ws_url, timeout=timeout)
        self._id = 0

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._id += 1
        msg_id = self._id
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = self.ws.recv()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("id") != msg_id:
                continue  # 事件或别的响应，忽略
            if "error" in data:
                raise CDPError(f"{method} 失败：{data['error']}")
            return data.get("result", {})

    def eval(self, expression: str, await_promise: bool = False) -> Any:
        res = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
                "userGesture": False,
            },
        )
        if "exceptionDetails" in res:
            det = res["exceptionDetails"]
            detail = (
                det.get("exception", {}).get("description")
                or det.get("exception", {}).get("value")
                or det.get("text")
            )
            raise CDPError(f"JS 异常：{detail}")
        return res.get("result", {}).get("value")

    def close(self) -> None:
        self.ws.close()
