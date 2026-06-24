"""RPKI-RTR 协议（RFC 8210）服务端实现。

提供 RTR 协议 PDU 的编码与解码功能，支持协议版本 0（RFC 6810）
与版本 1（RFC 8210）。所有 PDU 采用网络字节序（大端）。

PDU 通用头部（8 字节）::

    0          8          16         24         32
    +----------+----------+----------+----------+
    | Protocol |  PDU     |                     |
    | Version  |   Type   |    Session ID       |
    +----------+----------+----------+----------+
    |                 Length                    |
    +----------+----------+----------+----------+
"""

from __future__ import annotations

import ipaddress
import struct
from typing import Any

from app.core.logging import get_logger

logger = get_logger("app.rtr_protocol")


# ──────────────────────────────────────────────
# 协议常量
# ──────────────────────────────────────────────


class RTRProtocol:
    """RPKI-RTR 协议编解码器。

    实现 RFC 8210（v1）与 RFC 6810（v0）的 PDU 编解码。
    所有方法均为静态方法，无状态，可在多线程/协程环境下安全使用。
    """

    # 协议版本
    VERSION_0: int = 0  # RFC 6810
    VERSION_1: int = 1  # RFC 8210

    # PDU 类型（RFC 8210 Section 5）
    PDU_SERIAL_NOTIFY: int = 0
    PDU_SERIAL_QUERY: int = 1
    PDU_RESET_QUERY: int = 2
    PDU_CACHE_RESPONSE: int = 3
    PDU_IPV4_PREFIX: int = 4
    PDU_IPV6_PREFIX: int = 6
    PDU_END_OF_DATA: int = 7
    PDU_CACHE_RESET: int = 8
    PDU_ROUTER_KEY: int = 9  # v1 only
    PDU_ERROR_REPORT: int = 10

    # 错误码（RFC 8210 Section 5.10）
    ERROR_CORRUPT_DATA: int = 0
    ERROR_INTERNAL_ERROR: int = 1
    ERROR_NO_DATA_AVAILABLE: int = 2
    ERROR_INVALID_REQUEST: int = 3
    ERROR_UNSUPPORTED_PROTOCOL_VERSION: int = 4
    ERROR_UNSUPPORTED_PDU_TYPE: int = 5
    ERROR_WITHDRAWAL_OF_UNKNOWN_RECORD: int = 6
    ERROR_DUPLICATE_ANNOUNCEMENT_RECORD: int = 7
    ERROR_UNEXPECTED_PROTOCOL_VERSION: int = 8

    # 头部长度
    HEADER_LENGTH: int = 8

    # 默认协议版本
    DEFAULT_VERSION: int = VERSION_1

    # 默认刷新/重试/过期间隔（秒）
    DEFAULT_REFRESH_INTERVAL: int = 3600
    DEFAULT_RETRY_INTERVAL: int = 600
    DEFAULT_EXPIRE_INTERVAL: int = 7200

    # ──────────────────────────────────────────────
    # 通用 PDU 编解码
    # ──────────────────────────────────────────────

    @staticmethod
    def encode_pdu(
        pdu_type: int,
        data: bytes = b"",
        session_id: int = 0,
        version: int = DEFAULT_VERSION,
    ) -> bytes:
        """编码通用 PDU。

        Args:
            pdu_type: PDU 类型
            data: PDU 负载（不含头部）
            session_id: 会话 ID
            version: 协议版本

        Returns:
            编码后的完整 PDU 字节流（含头部）
        """
        length = RTRProtocol.HEADER_LENGTH + len(data)
        header = struct.pack(
            "!BBHI",
            version & 0xFF,
            pdu_type & 0xFF,
            session_id & 0xFFFF,
            length,
        )
        return header + data

    @staticmethod
    def decode_pdu(data: bytes) -> dict[str, Any]:
        """解码通用 PDU。

        Args:
            data: 完整 PDU 字节流（至少包含头部）

        Returns:
            包含 version、pdu_type、session_id、length、payload 的字典

        Raises:
            ValueError: 数据长度不足或长度字段不一致
        """
        if len(data) < RTRProtocol.HEADER_LENGTH:
            raise ValueError(
                f"PDU 数据长度不足，至少需要 {RTRProtocol.HEADER_LENGTH} 字节，"
                f"实际 {len(data)} 字节"
            )
        version, pdu_type, session_id, length = struct.unpack(
            "!BBHI", data[: RTRProtocol.HEADER_LENGTH]
        )
        payload = data[RTRProtocol.HEADER_LENGTH : length]
        if len(payload) < length - RTRProtocol.HEADER_LENGTH:
            raise ValueError(f"PDU 长度字段声明 {length} 字节，但实际数据不足")
        return {
            "version": version,
            "pdu_type": pdu_type,
            "session_id": session_id,
            "length": length,
            "payload": payload,
        }

    # ──────────────────────────────────────────────
    # IPv4/IPv6 前缀 PDU
    # ──────────────────────────────────────────────

    @staticmethod
    def encode_ipv4_prefix(
        prefix: str,
        prefix_length: int,
        origin_as: int,
        max_length: int | None = None,
        flags: int = 0,
        session_id: int = 0,
        version: int = DEFAULT_VERSION,
    ) -> bytes:
        """编码 IPv4 前缀 PDU（PDU type 4）。

        PDU 结构（共 20 字节）::

            头部（8 字节）+ Flags(1) + Prefix Length(1) +
            Max Length(1) + Reserved(1) + IPv4 Prefix(4) + Origin AS(4)

        Args:
            prefix: IPv4 前缀字符串（如 ``192.168.0.0``）
            prefix_length: 前缀长度
            origin_as: 起源 AS 号
            max_length: 最大前缀长度，为 None 时等于 prefix_length
            flags: 标志位（0=announcement, 1=withdrawal）
            session_id: 会话 ID
            version: 协议版本

        Returns:
            编码后的 IPv4 前缀 PDU 字节流
        """
        if max_length is None:
            max_length = prefix_length
        if not (0 <= prefix_length <= 32):
            raise ValueError(f"IPv4 前缀长度应在 0-32 之间，实际 {prefix_length}")
        if not (0 <= max_length <= 32):
            raise ValueError(f"IPv4 maxLength 应在 0-32 之间，实际 {max_length}")
        if max_length < prefix_length:
            raise ValueError(f"maxLength ({max_length}) 不能小于 prefix_length ({prefix_length})")

        addr = ipaddress.IPv4Address(prefix)
        prefix_bytes = int(addr).to_bytes(4, byteorder="big")
        # PDU 负载：Flags(1) + Prefix Length(1) + Max Length(1) + Reserved(1) +
        #          IPv4 Prefix(4) + Origin AS(4) = 12 字节
        body = (
            struct.pack("!BBB", flags & 0xFF, prefix_length & 0xFF, max_length & 0xFF)
            + b"\x00"  # reserved
            + prefix_bytes
            + struct.pack("!I", origin_as & 0xFFFFFFFF)
        )
        return RTRProtocol.encode_pdu(
            RTRProtocol.PDU_IPV4_PREFIX,
            body,
            session_id=session_id,
            version=version,
        )

    @staticmethod
    def encode_ipv6_prefix(
        prefix: str,
        prefix_length: int,
        origin_as: int,
        max_length: int | None = None,
        flags: int = 0,
        session_id: int = 0,
        version: int = DEFAULT_VERSION,
    ) -> bytes:
        """编码 IPv6 前缀 PDU（PDU type 6）。

        PDU 结构（共 44 字节）::

            头部（8 字节）+ Flags(1) + Prefix Length(1) +
            Max Length(1) + Reserved(1) + IPv6 Prefix(16) + Origin AS(4)

        Args:
            prefix: IPv6 前缀字符串（如 ``2001:db8::``）
            prefix_length: 前缀长度
            origin_as: 起源 AS 号
            max_length: 最大前缀长度，为 None 时等于 prefix_length
            flags: 标志位（0=announcement, 1=withdrawal）
            session_id: 会话 ID
            version: 协议版本

        Returns:
            编码后的 IPv6 前缀 PDU 字节流
        """
        if max_length is None:
            max_length = prefix_length
        if not (0 <= prefix_length <= 128):
            raise ValueError(f"IPv6 前缀长度应在 0-128 之间，实际 {prefix_length}")
        if not (0 <= max_length <= 128):
            raise ValueError(f"IPv6 maxLength 应在 0-128 之间，实际 {max_length}")
        if max_length < prefix_length:
            raise ValueError(f"maxLength ({max_length}) 不能小于 prefix_length ({prefix_length})")

        addr = ipaddress.IPv6Address(prefix)
        prefix_bytes = int(addr).to_bytes(16, byteorder="big")
        body = (
            struct.pack("!BBB", flags & 0xFF, prefix_length & 0xFF, max_length & 0xFF)
            + b"\x00"  # reserved
            + prefix_bytes
            + struct.pack("!I", origin_as & 0xFFFFFFFF)
        )
        return RTRProtocol.encode_pdu(
            RTRProtocol.PDU_IPV6_PREFIX,
            body,
            session_id=session_id,
            version=version,
        )

    @staticmethod
    def decode_prefix_pdu(payload: bytes) -> dict[str, Any]:
        """解码 IPv4/IPv6 前缀 PDU 负载。

        Args:
            payload: PDU 负载（不含头部）

        Returns:
            包含 flags、prefix_length、max_length、prefix、origin_as、family 的字典
        """
        if len(payload) < 4:
            raise ValueError("前缀 PDU 负载长度不足")
        flags = payload[0]
        prefix_length = payload[1]
        max_length = payload[2]
        # payload[3] 是 reserved

        if len(payload) == 12:
            # IPv4: 4 字节前缀 + 4 字节 AS
            prefix_bytes = payload[4:8]
            origin_as = struct.unpack("!I", payload[8:12])[0]
            prefix = str(ipaddress.IPv4Address(int.from_bytes(prefix_bytes, "big")))
            family = 4
        elif len(payload) == 36:
            # IPv6: 16 字节前缀 + 4 字节 AS
            prefix_bytes = payload[4:20]
            origin_as = struct.unpack("!I", payload[20:24])[0]
            prefix = str(ipaddress.IPv6Address(int.from_bytes(prefix_bytes, "big")))
            family = 6
        else:
            raise ValueError(f"前缀 PDU 负载长度异常：{len(payload)}（应为 12 或 36）")

        return {
            "flags": flags,
            "prefix_length": prefix_length,
            "max_length": max_length,
            "prefix": prefix,
            "origin_as": origin_as,
            "family": family,
            "is_withdrawal": bool(flags & 0x01),
        }

    # ──────────────────────────────────────────────
    # 控制类 PDU
    # ──────────────────────────────────────────────

    @staticmethod
    def encode_serial_notify(
        serial_number: int,
        session_id: int,
        version: int = DEFAULT_VERSION,
    ) -> bytes:
        """编码 Serial Notify PDU（PDU type 0）。

        服务端主动通知客户端序列号已更新。

        Args:
            serial_number: 新的序列号
            session_id: 会话 ID
            version: 协议版本

        Returns:
            编码后的 Serial Notify PDU 字节流
        """
        body = struct.pack("!I", serial_number & 0xFFFFFFFF)
        return RTRProtocol.encode_pdu(
            RTRProtocol.PDU_SERIAL_NOTIFY,
            body,
            session_id=session_id,
            version=version,
        )

    @staticmethod
    def encode_serial_query(
        serial_number: int,
        session_id: int,
        version: int = DEFAULT_VERSION,
    ) -> bytes:
        """编码 Serial Query PDU（PDU type 1）。

        客户端请求指定序列号之后的增量更新。

        Args:
            serial_number: 客户端已知的最后序列号
            session_id: 会话 ID
            version: 协议版本

        Returns:
            编码后的 Serial Query PDU 字节流
        """
        body = struct.pack("!I", serial_number & 0xFFFFFFFF)
        return RTRProtocol.encode_pdu(
            RTRProtocol.PDU_SERIAL_QUERY,
            body,
            session_id=session_id,
            version=version,
        )

    @staticmethod
    def encode_reset_query(version: int = DEFAULT_VERSION) -> bytes:
        """编码 Reset Query PDU（PDU type 2）。

        客户端请求全量更新。

        Args:
            version: 协议版本

        Returns:
            编码后的 Reset Query PDU 字节流
        """
        return RTRProtocol.encode_pdu(
            RTRProtocol.PDU_RESET_QUERY,
            b"",
            session_id=0,
            version=version,
        )

    @staticmethod
    def encode_cache_response(session_id: int, version: int = DEFAULT_VERSION) -> bytes:
        """编码 Cache Response PDU（PDU type 3）。

        服务端响应 Serial Query 或 Reset Query，表示后续将发送 VRP 数据。

        Args:
            session_id: 会话 ID
            version: 协议版本

        Returns:
            编码后的 Cache Response PDU 字节流
        """
        return RTRProtocol.encode_pdu(
            RTRProtocol.PDU_CACHE_RESPONSE,
            b"",
            session_id=session_id,
            version=version,
        )

    @staticmethod
    def encode_end_of_data(
        serial_number: int,
        session_id: int,
        version: int = DEFAULT_VERSION,
        refresh_interval: int | None = None,
        retry_interval: int | None = None,
        expire_interval: int | None = None,
    ) -> bytes:
        """编码 End of Data PDU（PDU type 7）。

        服务端通知客户端本次数据发送结束。

        - v0：仅包含 serial_number（共 12 字节）
        - v1：包含 serial_number + refresh/retry/expire 间隔（共 24 字节）

        Args:
            serial_number: 当前序列号
            session_id: 会话 ID
            version: 协议版本
            refresh_interval: 刷新间隔（秒，仅 v1）
            retry_interval: 重试间隔（秒，仅 v1）
            expire_interval: 过期间隔（秒，仅 v1）

        Returns:
            编码后的 End of Data PDU 字节流
        """
        if version == RTRProtocol.VERSION_0:
            # v0: 仅 serial_number
            body = struct.pack("!I", serial_number & 0xFFFFFFFF)
        else:
            # v1: serial + refresh + retry + expire
            body = struct.pack(
                "!IIII",
                serial_number & 0xFFFFFFFF,
                refresh_interval or RTRProtocol.DEFAULT_REFRESH_INTERVAL,
                retry_interval or RTRProtocol.DEFAULT_RETRY_INTERVAL,
                expire_interval or RTRProtocol.DEFAULT_EXPIRE_INTERVAL,
            )
        return RTRProtocol.encode_pdu(
            RTRProtocol.PDU_END_OF_DATA,
            body,
            session_id=session_id,
            version=version,
        )

    @staticmethod
    def encode_cache_reset(version: int = DEFAULT_VERSION) -> bytes:
        """编码 Cache Reset PDU（PDU type 8）。

        服务端通知客户端缓存已失效，需重新发起 Reset Query。

        Args:
            version: 协议版本

        Returns:
            编码后的 Cache Reset PDU 字节流
        """
        return RTRProtocol.encode_pdu(
            RTRProtocol.PDU_CACHE_RESET,
            b"",
            session_id=0,
            version=version,
        )

    @staticmethod
    def encode_error_report(
        error_code: int,
        message: str,
        erroneous_pdu: bytes = b"",
        session_id: int = 0,
        version: int = DEFAULT_VERSION,
    ) -> bytes:
        """编码 Error Report PDU（PDU type 10）。

        PDU 结构::

            头部（8 字节）+ Error Code(4) +
            Erroneous PDU Length(4) + Erroneous PDU(N) +
            Error Text Length(4) + Error Text(M)

        Args:
            error_code: 错误码
            message: 错误描述文本
            erroneous_pdu: 引发错误的 PDU 原始字节流
            session_id: 会话 ID
            version: 协议版本

        Returns:
            编码后的 Error Report PDU 字节流
        """
        message_bytes = message.encode("utf-8")
        body = (
            struct.pack("!I", error_code & 0xFFFFFFFF)
            + struct.pack("!I", len(erroneous_pdu))
            + erroneous_pdu
            + struct.pack("!I", len(message_bytes))
            + message_bytes
        )
        return RTRProtocol.encode_pdu(
            RTRProtocol.PDU_ERROR_REPORT,
            body,
            session_id=session_id,
            version=version,
        )

    @staticmethod
    def decode_serial_pdu(payload: bytes) -> dict[str, Any]:
        """解码 Serial Notify/Serial Query PDU 负载。

        Args:
            payload: PDU 负载（不含头部）

        Returns:
            包含 serial_number 的字典
        """
        if len(payload) < 4:
            raise ValueError("Serial PDU 负载长度不足")
        serial_number = struct.unpack("!I", payload[:4])[0]
        return {"serial_number": serial_number}

    @staticmethod
    def decode_end_of_data_pdu(payload: bytes, version: int = VERSION_1) -> dict[str, Any]:
        """解码 End of Data PDU 负载。

        Args:
            payload: PDU 负载（不含头部）
            version: 协议版本

        Returns:
            包含 serial_number（v0）或 serial_number/refresh_interval/
            retry_interval/expire_interval（v1）的字典
        """
        if version == RTRProtocol.VERSION_0:
            if len(payload) < 4:
                raise ValueError("End of Data v0 负载长度不足")
            serial_number = struct.unpack("!I", payload[:4])[0]
            return {"serial_number": serial_number}
        else:
            if len(payload) < 16:
                raise ValueError("End of Data v1 负载长度不足")
            (
                serial_number,
                refresh_interval,
                retry_interval,
                expire_interval,
            ) = struct.unpack("!IIII", payload[:16])
            return {
                "serial_number": serial_number,
                "refresh_interval": refresh_interval,
                "retry_interval": retry_interval,
                "expire_interval": expire_interval,
            }

    @staticmethod
    def decode_error_report(payload: bytes) -> dict[str, Any]:
        """解码 Error Report PDU 负载。

        Args:
            payload: PDU 负载（不含头部）

        Returns:
            包含 error_code、erroneous_pdu、message 的字典
        """
        if len(payload) < 12:
            raise ValueError("Error Report PDU 负载长度不足")
        error_code = struct.unpack("!I", payload[:4])[0]
        erroneous_pdu_len = struct.unpack("!I", payload[4:8])[0]
        if len(payload) < 8 + erroneous_pdu_len + 4:
            raise ValueError("Error Report PDU 负载长度与字段声明不一致")
        erroneous_pdu = payload[8 : 8 + erroneous_pdu_len]
        text_len_offset = 8 + erroneous_pdu_len
        text_len = struct.unpack("!I", payload[text_len_offset : text_len_offset + 4])[0]
        text_start = text_len_offset + 4
        message_bytes = payload[text_start : text_start + text_len]
        return {
            "error_code": error_code,
            "erroneous_pdu": erroneous_pdu,
            "message": message_bytes.decode("utf-8", errors="replace"),
        }

    # ──────────────────────────────────────────────
    # VRP 批量编码
    # ──────────────────────────────────────────────

    @staticmethod
    def encode_vrp(
        prefix: str,
        prefix_length: int,
        origin_as: int,
        max_length: int | None = None,
        session_id: int = 0,
        version: int = DEFAULT_VERSION,
        is_withdrawal: bool = False,
    ) -> bytes:
        """根据前缀族自动选择 IPv4/IPv6 PDU 编码单个 VRP。

        Args:
            prefix: 前缀地址字符串
            prefix_length: 前缀长度
            origin_as: 起源 AS 号
            max_length: 最大前缀长度
            session_id: 会话 ID
            version: 协议版本
            is_withdrawal: 是否为撤销（True 时 flags=1）

        Returns:
            编码后的前缀 PDU 字节流

        Raises:
            ValueError: 前缀格式无效
        """
        flags = 1 if is_withdrawal else 0
        try:
            network = ipaddress.ip_network(f"{prefix}/{prefix_length}", strict=False)
        except ValueError as e:
            raise ValueError(f"无效的前缀 {prefix}/{prefix_length}: {e}") from e

        if network.version == 4:
            return RTRProtocol.encode_ipv4_prefix(
                str(network.network_address),
                prefix_length,
                origin_as,
                max_length=max_length,
                flags=flags,
                session_id=session_id,
                version=version,
            )
        else:
            return RTRProtocol.encode_ipv6_prefix(
                str(network.network_address),
                prefix_length,
                origin_as,
                max_length=max_length,
                flags=flags,
                session_id=session_id,
                version=version,
            )

    @staticmethod
    def encode_vrps(
        vrps: list[dict[str, Any]],
        session_id: int = 0,
        version: int = DEFAULT_VERSION,
    ) -> bytes:
        """批量编码 VRP 列表为连续的 PDU 字节流。

        每个 VRP 字典应包含：prefix、prefix_length、origin_as，
        可选：max_length、is_withdrawal。

        Args:
            vrps: VRP 字典列表
            session_id: 会话 ID
            version: 协议版本

        Returns:
            编码后的连续 PDU 字节流
        """
        chunks: list[bytes] = []
        for vrp in vrps:
            pdu = RTRProtocol.encode_vrp(
                prefix=vrp["prefix"],
                prefix_length=vrp["prefix_length"],
                origin_as=vrp["origin_as"],
                max_length=vrp.get("max_length"),
                session_id=session_id,
                version=version,
                is_withdrawal=vrp.get("is_withdrawal", False),
            )
            chunks.append(pdu)
        return b"".join(chunks)


__all__ = ["RTRProtocol"]
