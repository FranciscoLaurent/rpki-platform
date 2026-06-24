"""TAL（Trust Anchor Locator）下载器。

负责从 5 个 RIR（APNIC、RIPE、ARIN、LACNIC、AFRINIC）官方地址下载 TAL 文件，
解析其中的 rsync URI、RRDP URI 与 Base64 编码的公钥信息。

TAL 文件格式（RFC 8630）：
    https://rpki.apnic.net/rpki/apnic-rpki-root-iana.cer
    rsync://rpki.apnic.net/repository/apnic-rpki-root-iana.cer

    MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...

下载策略：
- 使用 httpx.AsyncClient 异步下载
- 失败重试 max_retries 次，指数退避（1s, 2s, 4s, ...）
- HTTP 4xx 直接抛出 ValueError，不重试
- HTTP 5xx 与网络超时重试
- 单个 TAL 下载失败不影响其他 TAL
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.logging import get_logger

logger = get_logger("app.tal_downloader")


# 5 个 RIR 的官方 TAL 源
TAL_SOURCES: dict[str, dict[str, str]] = {
    "APNIC": {
        "url": "https://tal.apnic.net/apnic.tal",
        "rsync_uri": "rsync://rpki.apnic.net/repository/apnic-rpki-root-iana.cer",
        "rrdp_uri": "https://rpki.apnic.net/rrdp/notification.xml",
        "region": "亚太地区",
        "description": "Asia-Pacific Network Information Centre",
    },
    "RIPE": {
        "url": "https://tal.rpki.ripe.net/ripe-ncc.tal",
        "rsync_uri": "rsync://rpki.ripe.net/repository/ripe/root.cer",
        "rrdp_uri": "https://rpki.ripe.net/rrdp/notification.xml",
        "region": "欧洲、中东、中亚",
        "description": "Réseaux IP Européens Network Coordination Centre",
    },
    "ARIN": {
        "url": "https://www.arin.net/resources/manage/rpki/arin.tal",
        "rsync_uri": "rsync://rpki.arin.net/repository/arin-rpki-ta.cer",
        "rrdp_uri": "https://rpki.arin.net/rrdp/notification.xml",
        "region": "北美",
        "description": "American Registry for Internet Numbers",
    },
    "LACNIC": {
        "url": "https://www.lacnic.net/rpki/lacnic.tal",
        "rsync_uri": "rsync://repository.lacnic.net/rpki/lacnic/rta-lacnic-rpki.cer",
        "rrdp_uri": "https://rrdp.lacnic.net/ta/rta-lacnic-rpki.cer",
        "region": "拉丁美洲和加勒比",
        "description": "Latin American and Caribbean Internet Addresses Registry",
    },
    "AFRINIC": {
        "url": "https://rpki.afrinic.net/tal/afrinic.tal",
        "rsync_uri": "rsync://rpki.afrinic.net/repository/afrinic.cer",
        "rrdp_uri": "https://rpki.afrinic.net/rrdp/notification.xml",
        "region": "非洲",
        "description": "African Network Information Centre",
    },
}


@dataclass
class TALParsed:
    """解析后的 TAL 内容。"""

    rsync_uri: str
    rrdp_uri: str | None
    public_key_b64: str  # Base64 编码的公钥
    raw_content: str  # 原始 TAL 内容


@dataclass
class TALInfo:
    """TAL 信息。"""

    name: str  # "APNIC", "RIPE", "ARIN", "LACNIC", "AFRINIC"
    region: str
    description: str
    rsync_uri: str
    rrdp_uri: str
    raw_tal: str  # 下载的原始 TAL 文件内容
    parsed: TALParsed
    downloaded_at: datetime
    size_bytes: int


class TALDownloader:
    """TAL 文件下载器。

    从 5 个 RIR 官方地址下载 TAL 文件并解析。
    支持重试（指数退避）、容错（单个失败不影响其他）。

    Args:
        timeout: 单次请求超时秒数
        max_retries: 失败重试次数（针对 5xx 与网络错误）
    """

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def download_all_tals(self) -> list[TALInfo]:
        """下载所有 5 个 RIR 的 TAL 文件。

        单个 TAL 下载失败不影响其他 TAL，失败的会在结果中跳过并记录日志。

        Returns:
            成功下载的 TAL 信息列表
        """
        logger.info("开始下载全部 TAL", count=len(TAL_SOURCES))
        results: list[TALInfo] = []
        # 串行下载，避免对 RIR 站点造成并发压力
        for name in TAL_SOURCES:
            try:
                info = await self.download_tal(name)
                results.append(info)
            except Exception as e:
                logger.error(
                    "TAL 下载失败，跳过",
                    name=name,
                    error=str(e),
                    exc_info=True,
                )
        logger.info(
            "全部 TAL 下载完成",
            total=len(TAL_SOURCES),
            success=len(results),
            failed=len(TAL_SOURCES) - len(results),
        )
        return results

    async def download_tal(self, name: str) -> TALInfo:
        """下载单个 RIR 的 TAL 文件。

        Args:
            name: RIR 名称（APNIC/RIPE/ARIN/LACNIC/AFRINIC）

        Returns:
            TAL 信息

        Raises:
            ValueError: 未知 RIR 名称或 HTTP 4xx 错误
            RuntimeError: 重试耗尽仍失败
        """
        source = TAL_SOURCES.get(name)
        if source is None:
            raise ValueError(f"未知 RIR 名称: {name}")

        url = source["url"]
        logger.info("开始下载 TAL", name=name, url=url)

        content = await self._fetch_with_retry(url)
        parsed = self.parse_tal_content(content)

        info = TALInfo(
            name=name,
            region=source["region"],
            description=source["description"],
            rsync_uri=source["rsync_uri"],
            rrdp_uri=source["rrdp_uri"],
            raw_tal=content,
            parsed=parsed,
            downloaded_at=datetime.now(timezone.utc),
            size_bytes=len(content.encode("utf-8")),
        )
        logger.info(
            "TAL 下载成功",
            name=name,
            size_bytes=info.size_bytes,
            rsync_uri=info.rsync_uri,
        )
        return info

    async def _fetch_with_retry(self, url: str) -> str:
        """带重试与指数退避的 HTTP GET。

        Args:
            url: TAL 文件 URL

        Returns:
            TAL 文件文本内容

        Raises:
            ValueError: HTTP 4xx 错误（不重试）
            RuntimeError: 重试耗尽仍失败
        """
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, follow_redirects=True
                ) as client:
                    response = await client.get(url)
                if 200 <= response.status_code < 300:
                    return response.text
                if 400 <= response.status_code < 500:
                    # 客户端错误，不重试
                    raise ValueError(
                        f"HTTP {response.status_code}: {response.reason_phrase}"
                    )
                # 5xx 服务端错误，重试
                last_error = RuntimeError(
                    f"HTTP {response.status_code}: {response.reason_phrase}"
                )
                logger.warning(
                    "TAL 下载服务端错误，将重试",
                    url=url,
                    status_code=response.status_code,
                    attempt=attempt,
                )
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(
                    "TAL 下载超时，将重试",
                    url=url,
                    attempt=attempt,
                )
            except httpx.HTTPError as e:
                last_error = e
                logger.warning(
                    "TAL 下载网络错误，将重试",
                    url=url,
                    error=str(e),
                    attempt=attempt,
                )

            if attempt < self.max_retries:
                # 指数退避：1s, 2s, 4s, ...
                backoff = 2 ** (attempt - 1)
                await asyncio.sleep(backoff)

        raise RuntimeError(
            f"重试 {self.max_retries} 次后仍失败: {last_error}"
        )

    def parse_tal_content(self, content: str) -> TALParsed:
        """解析 TAL 文件内容。

        TAL 文件格式（RFC 8630）：
            # 注释行（可选，ARIN 使用）
            https://rpki.apnic.net/rpki/apnic-rpki-root-iana.cer  # RRDP URI（可选）
            rsync://rpki.apnic.net/repository/apnic-rpki-root-iana.cer

            MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...

        - 注释行以 # 开头（ARIN 特有）
        - HTTPS URI 行（RRDP）可能出现在 rsync URI 之前或之后
        - rsync URI 行以 rsync:// 开头
        - 空行后是 Base64 编码的公钥（可能多行）

        Args:
            content: TAL 文件原始内容

        Returns:
            解析后的 TALParsed 对象

        Raises:
            ValueError: 缺少 rsync URI 或公钥、公钥 Base64 解码失败
        """
        lines = content.replace("\r\n", "\n").split("\n")

        rrdp_uri: str | None = None
        rsync_uri: str | None = None
        key_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # 跳过注释行
            if stripped.startswith("#"):
                continue
            # URI 行
            if stripped.startswith("rsync://"):
                rsync_uri = stripped
                continue
            if stripped.startswith(("https://", "http://")):
                # RRDP URI（可能出现在 rsync 之前或之后）
                if rrdp_uri is None:
                    rrdp_uri = stripped
                continue
            # 其余非空行视为公钥的一部分
            key_lines.append(stripped)

        if rsync_uri is None:
            raise ValueError("TAL 内容缺少 rsync URI")

        if not key_lines:
            raise ValueError("TAL 内容缺少公钥信息")

        public_key_b64 = "".join(key_lines)

        # 校验 Base64 可解码
        try:
            base64.b64decode(public_key_b64)
        except Exception as e:
            raise ValueError(f"TAL 公钥 Base64 解码失败: {e}") from e

        return TALParsed(
            rsync_uri=rsync_uri,
            rrdp_uri=rrdp_uri,
            public_key_b64=public_key_b64,
            raw_content=content,
        )
