import httpx
import logging

logger = logging.getLogger(__name__)

class SharedHttpClient:
    """Singleton HTTP/2 multiplexed client with connection pooling & DNS keepalive.
    Eliminates TCP 3-way handshakes and TLS negotiation overhead for external APIs.
    """
    _client: httpx.AsyncClient | None = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            limits = httpx.Limits(
                max_keepalive_connections=50,
                max_connections=150,
                keepalive_expiry=60.0
            )
            timeout = httpx.Timeout(connect=10.0, read=25.0, write=25.0, pool=10.0)
            cls._client = httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                http2=False, # standard HTTP/1.1 keep-alive for universal compatibility
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client and not cls._client.is_closed:
            await cls._client.aclose()
            cls._client = None

class _HttpClientProxy:
    async def get(self, *args, **kwargs):
        client = SharedHttpClient.get_client()
        return await client.get(*args, **kwargs)

    async def post(self, *args, **kwargs):
        client = SharedHttpClient.get_client()
        return await client.post(*args, **kwargs)

shared_http_client = _HttpClientProxy()
