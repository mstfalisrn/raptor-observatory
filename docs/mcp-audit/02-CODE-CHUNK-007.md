# RAPTOR — Code Chunk 007

> GPT sırayla okuyup birleştirsin (MCP 100KB limit).

## `tests/unit/test_connectors.py`

```py
# RAPTOR — AŞAMA 12 connector testleri (http_json, internal_health, github)
import json

import httpx
import pytest

from connectors.github import GithubRepoConnector
from connectors.http_json import HttpJsonConnector
from connectors.internal_health import InternalHealthConnector


class _FakeResp:
    def __init__(self, status_code=200, headers=None, body=b"", chunks=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self._chunks = chunks

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    async def aiter_bytes(self, chunk_size=8192):
        if self._chunks is not None:
            for c in self._chunks:
                yield c
        elif self._body:
            yield self._body


class _FakeStream:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        pass


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    def stream(self, method, url, **kw):
        return _FakeStream(self._resp)

    async def get(self, url, **kw):
        return self._resp

    async def aclose(self):
        pass


@pytest.fixture(autouse=True)
def _no_ssrf(monkeypatch):
    # SSRF kontrolü ayrı test edilir (test_ssrf); connector testinde no-op
    monkeypatch.setattr("connectors.http_json.validate_url", lambda *a, **k: None)
    monkeypatch.setattr("connectors.http_json.resolve_redirect_url", lambda *a, **k: a[1])
    monkeypatch.setattr("connectors.github.validate_host", lambda *a, **k: None)


# ---------- http_json ----------
@pytest.mark.asyncio
async def test_http_json_success():
    c = HttpJsonConnector(allowed_hosts={"example.com"})
    c._client = _FakeClient(_FakeResp(200, {"content-type": "application/json"},
                                      body=json.dumps({"a": 1}).encode()))
    assert await c.get_json("https://example.com/x") == {"a": 1}


@pytest.mark.asyncio
async def test_http_json_content_length_limit():
    c = HttpJsonConnector(allowed_hosts={"example.com"}, max_bytes=10)
    c._client = _FakeClient(_FakeResp(200, {"content-type": "application/json",
                                            "content-length": "999999"}))
    with pytest.raises(RuntimeError):
        await c.get_json("https://example.com/x")


@pytest.mark.asyncio
async def test_http_json_content_type_rejected():
    c = HttpJsonConnector(allowed_hosts={"example.com"})
    c._client = _FakeClient(_FakeResp(200, {"content-type": "text/html"}, body=b"<html>"))
    with pytest.raises(RuntimeError):
        await c.get_json("https://example.com/x")


@pytest.mark.asyncio
async def test_http_json_parse_error():
    c = HttpJsonConnector(allowed_hosts={"example.com"})
    c._client = _FakeClient(_FakeResp(200, {"content-type": "application/json"}, body=b"not json"))
    with pytest.raises(RuntimeError):
        await c.get_json("https://example.com/x")


@pytest.mark.asyncio
async def test_http_json_empty_body():
    c = HttpJsonConnector(allowed_hosts={"example.com"})
    c._client = _FakeClient(_FakeResp(200, {"content-type": "application/json"}, body=b""))
    assert await c.get_json("https://example.com/x") == {}


# ---------- internal_health ----------
@pytest.mark.asyncio
async def test_internal_health_check():
    c = InternalHealthConnector()
    c._client = _FakeClient(_FakeResp(200))
    r = await c.check()
    assert r["api"]["reachable"] is True
    assert r["postgres"]["reachable"] is False  # None url → api üzerinden


@pytest.mark.asyncio
async def test_internal_health_check_failure():
    class _Boom:
        async def get(self, url, **kw):
            raise RuntimeError("down")

        async def aclose(self):
            pass

    c = InternalHealthConnector()
    c._client = _Boom()
    r = await c.check()
    assert r["api"]["reachable"] is False
    assert r["api"]["error"] == "RuntimeError"


@pytest.mark.asyncio
async def test_internal_health_check_local():
    c = InternalHealthConnector()
    c._client = _FakeClient(_FakeResp(200))
    r = await c.check_local()
    assert r["self"]["reachable"] is True


# ---------- github ----------
@pytest.mark.asyncio
async def test_github_repo_activity():
    c = GithubRepoConnector()
    c._client = _FakeClient(_FakeResp(200, {"content-type": "application/vnd.github+json"},
                                      body=json.dumps({"full_name": "o/r", "pushed_at": "x",
                                                       "default_branch": "main"}).encode()))
    r = await c.repo_activity("o/r")
    assert r["full_name"] == "o/r"
    assert r["default_branch"] == "main"


@pytest.mark.asyncio
async def test_github_repo_activity_invalid():
    c = GithubRepoConnector()
    with pytest.raises(ValueError):
        await c.repo_activity("tekparca")


@pytest.mark.asyncio
async def test_github_recent_releases():
    c = GithubRepoConnector()
    c._client = _FakeClient(_FakeResp(200, {"content-type": "application/vnd.github+json"},
                                      body=json.dumps([{"tag_name": "v1", "published_at": "x"}]).encode()))
    r = await c.recent_releases("o/r")
    assert r[0]["tag_name"] == "v1"


class _SequenceClient:
    """Sıralı yanıt döndüren client (retry/429 testleri için)."""

    def __init__(self, responses):
        self._responses = list(responses)

    def stream(self, method, url, **kw):
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return _FakeStream(resp)

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_github_rate_limit_429_retry(monkeypatch):
    async def _nosleep(_):
        return None

    monkeypatch.setattr("connectors.github.asyncio.sleep", _nosleep)
    c = GithubRepoConnector()
    r429 = _FakeResp(429, {"retry-after": "2", "x-ratelimit-remaining": "0"}, body=b"")
    rok = _FakeResp(200, {"content-type": "application/vnd.github+json"},
                    body=json.dumps({"full_name": "o/r", "default_branch": "main"}).encode())
    c._client = _SequenceClient([r429, rok])
    r = await c.repo_activity("o/r")
    assert r["full_name"] == "o/r"


@pytest.mark.asyncio
async def test_github_transport_error_retry(monkeypatch):
    async def _nosleep(_):
        return None

    monkeypatch.setattr("connectors.github.asyncio.sleep", _nosleep)
    c = GithubRepoConnector()
    err = httpx.TransportError("connection reset")
    rok = _FakeResp(200, {"content-type": "application/vnd.github+json"},
                    body=json.dumps({"full_name": "o/r", "default_branch": "main"}).encode())
    c._client = _SequenceClient([err, rok])
    r = await c.repo_activity("o/r")
    assert r["full_name"] == "o/r"


@pytest.mark.asyncio
async def test_github_streaming_size_limit():
    c = GithubRepoConnector(max_bytes=10)
    c._client = _FakeClient(_FakeResp(200, {"content-type": "application/vnd.github+json"},
                                      chunks=[b"12345678901234567890"]))
    with pytest.raises(RuntimeError):
        await c.repo_activity("o/r")


@pytest.mark.asyncio
async def test_github_close_idempotent():
    c = GithubRepoConnector()
    c._client = _FakeClient(_FakeResp(200))
    await c.aclose()
    await c.aclose()  # idempotent
    await c.close()
    async with c as _c:
        assert _c is c

```

## `tests/unit/test_llm.py`

```py
# RAPTOR — AŞAMA 12 LLM provider testleri (mock + openai-compatible + embedding)
import pytest

from agent_core.llm import (
    LLMMessage,
    LLMResult,
    MockProvider,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleProvider,
    build_embedding_provider,
    build_provider,
)


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, *a, **k):
        self._data = k.get("_data") if "_data" in k else a[0] if a else None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def post(self, url, json=None, headers=None):
        return _FakeResp(self._data)


@pytest.mark.asyncio
async def test_mock_provider_chat_and_check():
    p = MockProvider()
    r = await p.chat([LLMMessage("user", "merhaba")])
    assert isinstance(r, LLMResult)
    assert r.finish_reason == "stop"
    assert await p.check() is True


@pytest.mark.asyncio
async def test_openai_compatible_chat_text():
    p = OpenAICompatibleProvider("https://x.ai/v1", "m", "k")
    p._client = _FakeClient({
        "choices": [{"message": {"content": "selam", "tool_calls": []}, "finish_reason": "stop"}],
        "usage": {"total_tokens": 5},
    })
    r = await p.chat([LLMMessage("user", "hi")])
    assert r.text == "selam"
    assert r.finish_reason == "stop"
    assert r.usage.get("total_tokens") == 5


@pytest.mark.asyncio
async def test_openai_compatible_chat_tool_calls():
    p = OpenAICompatibleProvider("https://x.ai/v1", "m", "k")
    p._client = _FakeClient({
        "choices": [{"message": {
            "content": "",
            "tool_calls": [{"id": "t1", "function": {"name": "github_repo_read", "arguments": '{"owner": "a", "repo": "b"}'}}],
        }, "finish_reason": "tool_calls"}],
    })
    r = await p.chat([LLMMessage("user", "hi")], tools=[{"name": "github_repo_read"}])
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0].name == "github_repo_read"
    assert r.tool_calls[0].arguments == {"owner": "a", "repo": "b"}


@pytest.mark.asyncio
async def test_openai_compatible_check_true():
    p = OpenAICompatibleProvider("https://x.ai/v1", "m", "k")
    p._client = _FakeClient({
        "choices": [{"message": {"content": "pong", "tool_calls": []}, "finish_reason": "stop"}],
    })
    assert await p.check() is True


@pytest.mark.asyncio
async def test_openai_compatible_check_false():
    class _Boom:
        async def post(self, url, json=None, headers=None):
            raise RuntimeError("kapalı")

    p = OpenAICompatibleProvider("https://x.ai/v1", "m", "k")
    p._client = _Boom()
    assert await p.check() is False


def test_build_provider_mock(monkeypatch):
    monkeypatch.setattr("agent_core.llm.settings.LLM_PROVIDER", "mock")
    assert isinstance(build_provider(), MockProvider)


def test_build_provider_openai(monkeypatch):
    monkeypatch.setattr("agent_core.llm.settings.LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr("agent_core.llm.settings.LLM_BASE_URL", "https://x.ai/v1")
    monkeypatch.setattr("agent_core.llm.settings.LLM_MODEL", "m")
    monkeypatch.setattr("agent_core.llm.settings.LLM_API_KEY", "k")
    p = build_provider()
    assert isinstance(p, OpenAICompatibleProvider)


def test_build_embedding_provider_none(monkeypatch):
    monkeypatch.setattr("agent_core.llm.settings.EMBEDDING_MODEL", "")
    monkeypatch.setattr("agent_core.llm.settings.LLM_MODEL", "")
    assert build_embedding_provider() is None


@pytest.mark.asyncio
async def test_embedding_provider_embed(monkeypatch):
    monkeypatch.setattr(
        "agent_core.llm.httpx.AsyncClient",
        lambda *a, **k: _FakeClient({"data": [{"embedding": [0.1, 0.2, 0.3]}]}),
    )
    p = OpenAICompatibleEmbeddingProvider("https://x.ai/v1", "m", "k")
    v = await p.embed("test")
    assert v == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_embedding_provider_bad_shape(monkeypatch):
    monkeypatch.setattr(
        "agent_core.llm.httpx.AsyncClient",
        lambda *a, **k: _FakeClient({"data": [{"embedding": "not-a-list"}]}),
    )
    p = OpenAICompatibleEmbeddingProvider("https://x.ai/v1", "m", "k")
    with pytest.raises(ValueError):
        await p.embed("test")

```

## `tests/unit/test_memory.py`

```py
# RAPTOR — AŞAMA 8 memory testleri (lifecycle, DLP, verified/active retrieval)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from memory.service import MemoryService
from observability.models import Base, MemoryStatus


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
class TestLifecycle:
    async def test_candidate_to_active(self, session):
        svc = MemoryService(session)
        item = await svc.create_candidate(content="önemli bir gerçek", source="test", confidence=0.8)
        assert item.status == MemoryStatus.CANDIDATE.value
        await svc.approve(item.id)
        assert item.status == MemoryStatus.APPROVED.value
        await svc.mark_active(item.id)
        assert item.status == MemoryStatus.ACTIVE.value

    async def test_approve_guard_requires_candidate(self, session):
        svc = MemoryService(session)
        item = await svc.create_candidate(content="x", source="test")
        await svc.mark_active(item.id)  # CANDIDATE -> mark_active guard: yalnız APPROVED/AUTO
        assert item.status == MemoryStatus.CANDIDATE.value  # değişmedi

    async def test_reject(self, session):
        svc = MemoryService(session)
        item = await svc.create_candidate(content="x", source="test")
        await svc.reject(item.id)
        assert item.status == MemoryStatus.REJECTED.value


@pytest.mark.asyncio
class TestDLP:
    async def test_secret_redacted_on_create(self, session):
        svc = MemoryService(session)
        secret = "8820797359:AAGJ18u8OZgrHUxDlhYHy9dW5bXrmHyvA2o"
        item = await svc.create_candidate(content=f"token {secret} kaydedildi", source="test")
        assert secret not in item.content, "secret memory'ye yazılmamalı"


@pytest.mark.asyncio
class TestRetrieval:
    async def test_only_verified_active_returned(self, session):
        svc = MemoryService(session)
        # unverified candidate
        c = await svc.create_candidate(content="taslak veri", source="test")
        res = await svc.retrieve_for_context("taslak", limit=10)
        assert all(m.id != c.id for m in res), "unverified candidate context'e girmemeli"

        # approve + active
        await svc.approve(c.id)
        await svc.mark_active(c.id)
        res2 = await svc.retrieve_for_context("taslak", limit=10)
        assert any(m.id == c.id for m in res2), "verified active context'e girmeli"

```

## `tests/unit/test_memory_service.py`

```py
# RAPTOR — AŞAMA 12 memory service ek testleri (approve/reject/supersede/sweep/search/vector)
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from memory.service import MemoryService
from observability.models import Base, MemoryStatus


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    S = async_sessionmaker(engine, expire_on_commit=False)
    async with S() as s:
        yield s
    await engine.dispose()


async def _candidate(session, content="hafıza içeriği", **kw):
    svc = MemoryService(session)
    return await svc.create_candidate(content=content, source=kw.get("source", "test"),
                                      confidence=kw.get("confidence", 0.8),
                                      ttl_seconds=kw.get("ttl_seconds"), category=kw.get("category"))


@pytest.mark.asyncio
async def test_approve_auto(session):
    svc = MemoryService(session)
    item = await _candidate(session)
    r = await svc.approve(item.id, auto=True)
    assert r.status == MemoryStatus.AUTO_APPROVED.value
    assert r.verification_status == "verified"


@pytest.mark.asyncio
async def test_approve_wrong_status_returns_none(session):
    svc = MemoryService(session)
    item = await _candidate(session)
    await svc.approve(item.id)
    # ikinci approve (zaten APPROVED) → None
    assert await svc.approve(item.id) is None


@pytest.mark.asyncio
async def test_reject(session):
    svc = MemoryService(session)
    item = await _candidate(session)
    await svc.reject(item.id)
    got = await session.get(type(item), item.id)
    assert got.status == MemoryStatus.REJECTED.value


@pytest.mark.asyncio
async def test_mark_active(session):
    svc = MemoryService(session)
    item = await _candidate(session)
    await svc.approve(item.id)
    await svc.mark_active(item.id)
    got = await session.get(type(item), item.id)
    assert got.status == MemoryStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_supersede(session):
    svc = MemoryService(session)
    old = await _candidate(session, content="eski bilgi")
    new = await _candidate(session, content="yeni bilgi")
    await svc.approve(old.id)
    await svc.approve(new.id)
    await svc.mark_active(old.id)
    await svc.mark_active(new.id)
    await svc.supersede(old.id, new.id)
    got = await session.get(type(old), old.id)
    assert got.status == MemoryStatus.SUPERSEDED.value


@pytest.mark.asyncio
async def test_supersede_invalid_new(session):
    svc = MemoryService(session)
    old = await _candidate(session)
    # new_id yok → no-op
    await svc.supersede(old.id, uuid.uuid4())


@pytest.mark.asyncio
async def test_search_status_filter(session):
    svc = MemoryService(session)
    item = await _candidate(session, content="benzersiz-kelime-xyz")
    await svc.approve(item.id)
    await svc.mark_active(item.id)
    await session.commit()
    res = await svc.search("benzersiz-kelime", status=MemoryStatus.ACTIVE.value)
    assert any(str(i.id) == str(item.id) for i in res)


@pytest.mark.asyncio
async def test_search_wildcard_escaped(session):
    svc = MemoryService(session)
    # '%' içeren sorgu wildcard olarak davranmamalı
    await _candidate(session, content="yuzde-50")
    await session.commit()
    res = await svc.search("yuzde%", verified_only=False)
    assert len(res) == 0


@pytest.mark.asyncio
async def test_expire_sweep(session):
    svc = MemoryService(session)
    await _candidate(session, content="geçmiş", ttl_seconds=-1)  # zaten expired
    await session.commit()
    n = await svc.expire_sweep()
    assert n >= 1


@pytest.mark.asyncio
async def test_list_status_invalid(session):
    svc = MemoryService(session)
    assert await svc.list_status("BOGUS") == []


@pytest.mark.asyncio
async def test_vector_search_fallback(session):
    svc = MemoryService(session)
    # SQLite'ta vector operatörü yok → fallback boş liste (exception yakalanır)
    res = await svc.vector_search([0.1, 0.2, 0.3])
    assert res == []


@pytest.mark.asyncio
async def test_create_candidate_dlp_redact(session):
    svc = MemoryService(session)
    # TG bot token pattern'i (bilinen DLP kalıbı) redakte edilmeli
    item = await svc.create_candidate(content="token: 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij", source="test")
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij" not in item.content
    assert "<TG_TOKEN_REDACTED>" in item.content

```

## `tests/unit/test_queue.py`

```py
# RAPTOR — AŞAMA 6 queue testleri (DLQ, stream publish, group)

from observability.queue import (
    DLQ_STREAM,
    GROUP,
    STREAM,
    ack,
    ensure_stream_group,
    publish_to_dlq,
    publish_to_stream,
)


class _FakeRedis:
    def __init__(self):
        self.streams = {}
        self.groups = {}
        self.xacks = []
        self._counter = 0

    def xgroup_create(self, stream, group, **kw):
        if group in self.groups.get(stream, set()):
            raise Exception("BUSYGROUP Consumer Group name already exists")
        self.groups.setdefault(stream, set()).add(group)
        return True

    def xadd(self, stream, fields, **kw):
        self._counter += 1
        eid = f"{self._counter}-0"
        self.streams.setdefault(stream, []).append((eid, fields))
        return eid

    def xack(self, stream, group, entry_id):
        self.xacks.append((stream, entry_id))
        return 1


class TestPublishToStream:
    def test_adds_data_field(self):
        r = _FakeRedis()
        publish_to_stream(r, {"run_id": "abc"}, idempotency_key="k1")
        assert r.streams[STREAM][0][1]["data"] == '{"run_id": "abc"}'
        assert r.streams[STREAM][0][1]["idempotency_key"] == "k1"

    def test_no_idempotency_key(self):
        r = _FakeRedis()
        publish_to_stream(r, {"run_id": "abc"})
        assert "idempotency_key" not in r.streams[STREAM][0][1]


class TestDLQ:
    def test_publish_to_dlq(self):
        r = _FakeRedis()
        publish_to_dlq(r, {"run_id": "abc"}, reason="max_retries_exceeded")
        entry = r.streams[DLQ_STREAM][0][1]
        assert entry["reason"] == "max_retries_exceeded"
        assert entry["data"] == '{"run_id": "abc"}'


class TestStreamGroup:
    def test_ensure_group_idempotent(self):
        r = _FakeRedis()
        ensure_stream_group(r)  # ilk kez
        ensure_stream_group(r)  # ikinci kez BUSYGROUP yakalanır, hata fırlatmaz
        assert GROUP in r.groups.get(STREAM, set())


class TestAck:
    def test_ack(self):
        r = _FakeRedis()
        ack(r, "123-0")
        assert ("123-0") in [x[1] for x in r.xacks]

```

## `tests/unit/test_queue_streams.py`

```py
# RAPTOR — AŞAMA 12 queue stream fonksiyon testleri (fake sync Redis)
import json

import pytest

from observability.queue import (
    DLQ_STREAM,
    STREAM,
    ack,
    claim_pending,
    ensure_stream_group,
    publish_to_dlq,
    publish_to_stream,
    read_group,
)


class FakeRedis:
    def __init__(self):
        self.calls = []
        self.xadd_result = "1-0"
        self.xautoclaim_result = ("0-0", [("1-1", {"data": "{}"})])
        self.xautoclaim_raises = False
        self.xpending_result: list | None = [{"message_id": "1-1", "time_since_delivered": 40000}]
        self.xclaim_result = [("1-1", {})]
        self.xgroup_error: Exception | None = None

    def xgroup_create(self, *a, **k):
        if self.xgroup_error:
            raise self.xgroup_error
        self.calls.append(("xgroup_create", a))

    def xadd(self, *a, **k):
        self.calls.append(("xadd", a, k))
        return self.xadd_result

    def xreadgroup(self, *a, **k):
        self.calls.append(("xreadgroup", a, k))
        return [("stream", [("1-1", {"data": "{}"})])]

    def xack(self, *a, **k):
        self.calls.append(("xack", a))

    def xautoclaim(self, *a, **k):
        self.calls.append(("xautoclaim", a, k))
        if self.xautoclaim_raises:
            raise RuntimeError("no xautoclaim")
        return self.xautoclaim_result

    def xpending_range(self, *a, **k):
        self.calls.append(("xpending_range", a, k))
        return self.xpending_result

    def xclaim(self, *a, **k):
        self.calls.append(("xclaim", a))
        return self.xclaim_result


def test_publish_to_stream():
    r = FakeRedis()
    eid = publish_to_stream(r, {"run_id": "abc"})
    assert eid == "1-0"
    assert r.calls[0][0] == "xadd"
    assert r.calls[0][1][0] == STREAM
    assert json.loads(r.calls[0][1][1]["data"]) == {"run_id": "abc"}


def test_publish_to_stream_idempotency():
    r = FakeRedis()
    publish_to_stream(r, {"x": 1}, idempotency_key="ik-1")
    assert r.calls[0][1][1]["idempotency_key"] == "ik-1"


def test_publish_to_dlq():
    r = FakeRedis()
    publish_to_dlq(r, {"run_id": "x"}, "max retry")
    assert r.calls[0][1][0] == DLQ_STREAM
    assert r.calls[0][1][1]["reason"] == "max retry"


def test_ensure_stream_group_busygroup():
    r = FakeRedis()
    r.xgroup_error = RuntimeError("BUSYGROUP Consumer Group name already exists")
    ensure_stream_group(r)  # raise etmemeli


def test_ensure_stream_group_real_error():
    r = FakeRedis()
    r.xgroup_error = RuntimeError("connection refused")
    with pytest.raises(RuntimeError):
        ensure_stream_group(r)


def test_read_group_and_ack():
    r = FakeRedis()
    res = read_group(r, "worker-1")
    assert res[0][0] == "stream"
    ack(r, "1-1")
    assert r.calls[-1][0] == "xack"


def test_claim_pending_xautoclaim():
    r = FakeRedis()
    entries = claim_pending(r, "worker-1")
    assert entries == [("1-1", {"data": "{}"})]


def test_claim_pending_fallback():
    r = FakeRedis()
    r.xautoclaim_raises = True
    entries = claim_pending(r, "worker-1")
    assert entries == [("1-1", {})]
    assert any(c[0] == "xpending_range" for c in r.calls)
    assert any(c[0] == "xclaim" for c in r.calls)


def test_claim_pending_total_failure():
    r = FakeRedis()
    r.xautoclaim_raises = True
    r.xpending_result = None  # fallback da patlasın
    assert claim_pending(r, "worker-1") == []

```

## `tests/unit/test_reporter.py`

```py
# RAPTOR — AŞAMA 12 Reporter testleri
from agent_core.reporter import Reporter, build_public_report


def test_human_summary_completed():
    r = Reporter()
    assert "Tamamlandı" in r.human_summary({"status": "COMPLETED", "id": "1234567890abcdef"})


def test_human_summary_failed():
    r = Reporter()
    assert "Başarısız" in r.human_summary({"status": "FAILED", "error": "zaman aşımı"})


def test_human_summary_unknown():
    r = Reporter()
    assert r.human_summary({"status": "GARIP"}) == "ℹ️ GARIP"


def test_machine_result_defaults():
    r = Reporter()
    m = r.machine_result(run_id="r1", status="COMPLETED")
    assert m["run_id"] == "r1"
    assert m["evidence"] == []
    assert m["reports"] == []
    assert m["confidence"] == 0.0
    assert "generated_at" in m


def test_machine_result_with_data():
    r = Reporter()
    m = r.machine_result(run_id="r1", status="FAILED", claim="c", evidence=["e1"],
                         confidence=0.9, reports=["rep"], error="err")
    assert m["claim"] == "c"
    assert m["evidence"] == ["e1"]
    assert m["confidence"] == 0.9
    assert m["error"] == "err"


def test_build_public_report():
    p = build_public_report(report_type="change", observed_at="2026-01-01", subject="s",
                            change="c", evidence="e", confidence=0.8)
    assert p["type"] == "change"
    assert p["schema_version"] == 1
    assert p["confidence"] == 0.8

```

## `tests/unit/test_security_redact.py`

```py
# RAPTOR — AŞAMA 12 security redact/DLP/env-secret testleri
from observability.security import (
    Redactor,
    contains_secret,
    load_secrets_from_env,
    redact,
    scrub_and_flag,
)


def test_redact_tg_token():
    out = redact("token: 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop")
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop" not in out
    assert "REDACT" in out


def test_redact_password_assignment():
    out = redact("config: password=supersecretvalue123")
    assert "supersecretvalue123" not in out


def test_redact_aws_key():
    out = redact("key AKIAIOSFODNN7EXAMPLE")
    assert "AKIAIOSFODNN7EXAMPLE" not in out


def test_redact_empty_and_none():
    assert redact("") == ""
    assert redact("temiz metin") == "temiz metin"


def test_contains_secret():
    assert contains_secret("token: 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop")
    assert not contains_secret("sıradan bir metin")


def test_scrub_and_flag():
    txt = "password=hunter2secret"
    scrubbed, had = scrub_and_flag(txt)
    assert had is True
    assert "hunter2secret" not in scrubbed
    clean, clean_had = scrub_and_flag("merhaba dünya")
    assert clean_had is False
    assert clean == "merhaba dünya"


def test_load_secrets_from_env_redacts_literal():
    env = {"LLM_API_KEY": "sk-test-0123456789abcdef", "UNRELATED": "merhaba dünya"}
    added = load_secrets_from_env(environ=env)
    assert added >= 1
    # literal değer artık redakte edilmeli
    assert "sk-test-0123456789abcdef" not in redact("anahtar sk-test-0123456789abcdef burada")


def test_load_secrets_from_env_skips():
    env = {
        "LLM_API_KEY": "CHANGE_ME",
        "SHORT": "kisa",
        "PATH_LIKE": "/usr/bin/python",
        "USERNAME": "bu-bir-uzun-deger-ama-key-ismi-gizli-degil",
    }
    assert load_secrets_from_env(environ=env) == 0


def test_redactor_class():
    r = Redactor()
    r.add_literal("gizlibirdeger123")
    out = r.scrub("parola gizlibirdeger123 burada")
    assert "gizlibirdeger123" not in out
    assert r.contains_secret("gizlibirdeger123") is True
    scrubbed, had = r.scrub_and_flag("x gizlibirdeger123 y")
    assert had is True and "gizlibirdeger123" not in scrubbed

```

## `tests/unit/test_ssrf.py`

```py
# RAPTOR — SSRF birim testleri
import pytest

from connectors.ssrf import SSRFError, validate_host, validate_url


class TestSSRF:
    @pytest.mark.parametrize("host", [
        "127.0.0.1", "127.0.0.2", "localhost", "10.0.0.1", "172.20.0.2",
        "192.168.1.5", "169.254.169.254", "0.0.0.0",
    ])
    def test_blocked_hosts(self, host):
        with pytest.raises(SSRFError):
            validate_host(host)

    def test_public_host_allowed_when_allowedlist_empty(self):
        # internet'e açık public host (DNS çözülüyorsa) — loopback değil
        validate_host("8.8.8.8")

    def test_allowlist_restricts(self):
        with pytest.raises(SSRFError):
            validate_host("example.com", allowed_hosts={"github.com"})

    def test_unix_socket_blocked(self):
        with pytest.raises(SSRFError):
            validate_url("http://localhost:9999/trigger?x=unix:/tmp/x")

    def test_bad_scheme(self):
        with pytest.raises(SSRFError):
            validate_url("file:///etc/passwd")
```

## `tests/unit/test_technocore_contract.py`

```py
# RAPTOR — Faz 7 Technocore contract testleri
# DID base58btc, canonical string, nonce monotonic, cursor DB, POST OpenAPI, 429 backoff
from __future__ import annotations

import json
import re
import tempfile

import httpx
import pytest

from connectors.technocore import (
    TechnocoreConnector,
    TechnocoreError,
    _did_to_pubkey,
    _parse_retry_after,
    _pubkey_to_did,
    canonical_string,
    sweep_text,
)

_DID_RE = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$")
_SIG_RE = re.compile(r"^[A-Za-z0-9_-]{86}$")
_NONCE_RE = re.compile(r"^[0-9]{1,19}$")


# ---------------------------------------------------------------------------
# DID base58btc
# ---------------------------------------------------------------------------
class TestDIDBase58btc:
    def test_did_format_and_length(self):
        with tempfile.TemporaryDirectory() as td:
            tc = TechnocoreConnector(ed25519_key_path=f"{td}/did.key")
            did, _ = tc.load_or_generate_key()
            assert _DID_RE.match(did), f"DID pattern hatası: {did}"
            assert len(did) == 56
            assert did.startswith("did:key:z6Mk")

    def test_did_roundtrip_pubkey(self):
        with tempfile.TemporaryDirectory() as td:
            tc = TechnocoreConnector(ed25519_key_path=f"{td}/did2.key")
            did, _ = tc.load_or_generate_key()
            pub = _did_to_pubkey(did)
            assert len(pub) == 32
            # tekrar DID'e dön
            did2 = _pubkey_to_did(pub)
            assert did == did2

    def test_did_not_hex(self):
        with tempfile.TemporaryDirectory() as td:
            tc = TechnocoreConnector(ed25519_key_path=f"{td}/did3.key")
            did, _ = tc.load_or_generate_key()
            # eski hatalı format hex idi (did:key: + 64 hex char) — artık olmamalı
            assert not re.match(r"^did:key:[0-9a-f]{64}$", did)
            assert "z6Mk" in did

    def test_pubkey_to_did_known_vector(self):
        # sabit 32 bayt pubkey için DID deterministik
        pub = bytes.fromhex("5ebfb8fcfbbe1fc500e9ab1234567890abcdef1234567890abcdef12345678")
        # truncated to 32? use full 32 bytes deterministic
        pub = bytes(range(32))
        did = _pubkey_to_did(pub)
        assert _DID_RE.match(did)
        assert _did_to_pubkey(did) == pub


# ---------------------------------------------------------------------------
# Canonical string + sweep
# ---------------------------------------------------------------------------
class TestCanonicalString:
    def test_canonical_exact(self):
        assert canonical_string("lobby", "123", "hello") == "lobby|123|hello"

    def test_sweep_newline_and_controls(self):
        assert sweep_text("a\nb\r\nc") == "a b  c"
        assert sweep_text("x\x00y\x1f z") == "x y  z"
        assert sweep_text("hi\u200bthere") == "hi there"
        assert sweep_text("a\u200c b\u200d c\ufeff") == "a  b  c "

    def test_canonical_uses_swept_text(self):
        # canonical, text sweep edilmiş hali imzalamalı
        raw = "hello\nworld"
        c = canonical_string("myroom", "999", raw)
        assert c == "myroom|999|hello world"
        assert "\n" not in c

    def test_canonical_invalid_room(self):
        with pytest.raises(ValueError):
            canonical_string("Invalid-Room!", "1", "hi")

    def test_canonical_invalid_nonce(self):
        with pytest.raises(ValueError):
            canonical_string("lobby", "abc", "hi")
        with pytest.raises(ValueError):
            canonical_string("lobby", "0" * 20, "hi")  # 20 digits >19


# ---------------------------------------------------------------------------
# Signature — base64url 86 chars, verify
# ---------------------------------------------------------------------------
class TestSignature:
    def test_sig_86_base64url(self):
        with tempfile.TemporaryDirectory() as td:
            tc = TechnocoreConnector(ed25519_key_path=f"{td}/sig.key")
            tc.load_or_generate_key()
            sig = tc.sign("lobby", "1234567890", "hello world")
            assert len(sig) == 86
            assert _SIG_RE.match(sig)
            assert "=" not in sig
            assert "+" not in sig and "/" not in sig

    def test_sig_covers_canonical(self):
        with tempfile.TemporaryDirectory() as td:
            tc = TechnocoreConnector(ed25519_key_path=f"{td}/sig2.key")
            did, _ = tc.load_or_generate_key()
            room, nonce, text = "test-room", "42", "payload here"
            sig = tc.sign(room, nonce, text)
            assert tc.verify(did, room, nonce, text, sig) is True
            # farklı text -> fail
            assert tc.verify(did, room, nonce, "other text", sig) is False
            # farklı nonce -> fail
            assert tc.verify(did, room, "43", text, sig) is False
            # sweep sonrası verify: \n -> space sweep ile aynı sig olmalı
            sig2 = tc.sign(room, nonce, "hello\nworld")
            assert tc.verify(did, room, nonce, "hello world", sig2) is True
            assert tc.verify(did, room, nonce, "hello\nworld", sig2) is True  # sweep nedeniyle

    def test_sig_sweep_consistency(self):
        with tempfile.TemporaryDirectory() as td:
            tc = TechnocoreConnector(ed25519_key_path=f"{td}/sig3.key")
            did, _ = tc.load_or_generate_key()
            # raw text with \n, but canonical sweeps to space — both should verify
            raw = "a\tb\nc\u200b"
            swept = sweep_text(raw)
            sig = tc.sign("lobby", "1", raw)
            # verify with raw or swept — both canonical same -> both ok
            assert tc.verify(did, "lobby", "1", raw, sig)
            assert tc.verify(did, "lobby", "1", swept, sig)


# ---------------------------------------------------------------------------
# Nonce monotonic
# ---------------------------------------------------------------------------
class TestNonceMonotonic:
    def test_next_nonce_increasing(self):
        tc = TechnocoreConnector()
        n1 = tc.next_nonce()
        n2 = tc.next_nonce()
        assert _NONCE_RE.match(n1)
        assert _NONCE_RE.match(n2)
        assert int(n2) > int(n1)

    def test_nonce_ensure_greater(self):
        tc = TechnocoreConnector()
        n1 = tc.next_nonce()
        # aynı değeri tekrar verirsek monotonic +1 yapmalı
        tc._global_nonce.ensure_greater(n1) if hasattr(tc, "_global_nonce") else None
        # _global_nonce is module-level; test via tc.next_nonce internals
        from connectors.technocore import _global_nonce

        forced = _global_nonce.ensure_greater(n1)
        assert int(forced) > int(n1)

    @pytest.mark.asyncio
    async def test_nonce_db_atomic(self):
        """In-memory SQLite ile DB nonce atomik increment."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from observability.models import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)

        with tempfile.TemporaryDirectory() as td:
            tc = TechnocoreConnector(ed25519_key_path=f"{td}/nonce.key")
            tc.load_or_generate_key()

            async with Session() as s:
                n1 = await tc.next_nonce_db("test-room", s)
                n2 = await tc.next_nonce_db("test-room", s)
                await s.commit()
                assert int(n2) > int(n1)
                assert _NONCE_RE.match(n1)
                # farklı room aynı DID -> bağımsız nonce sequence
                n3 = await tc.next_nonce_db("other-room", s)
                await s.commit()
                assert _NONCE_RE.match(n3)

            # persistence: yeni session'da devam
            async with Session() as s:
                n4 = await tc.next_nonce_db("test-room", s)
                await s.commit()
                assert int(n4) > int(n2)

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_nonce_db_requires_did(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from observability.models import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        tc = TechnocoreConnector()  # no key loaded
        async with Session() as s:
            with pytest.raises(TechnocoreError, match="DID yok"):
                await tc.next_nonce_db("room", s)
        await engine.dispose()


# ---------------------------------------------------------------------------
# Cursor DB persistence
# ---------------------------------------------------------------------------
class TestCursorDB:
    @pytest.mark.asyncio
    async def test_cursor_get_set(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from observability.models import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        tc = TechnocoreConnector()

        async with Session() as s:
            assert await tc.get_cursor("room-a", s) == 0
            await tc.set_cursor("room-a", 42, s)
            await s.commit()
            assert await tc.get_cursor("room-a", s) == 42
            # monotonic: küçük seq set edilmez
            await tc.set_cursor("room-a", 10, s)
            await s.commit()
            assert await tc.get_cursor("room-a", s) == 42
            # büyük seq ilerler
            await tc.set_cursor("room-a", 100, s)
            await s.commit()
            assert await tc.get_cursor("room-a", s) == 100

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_cursor_advance_from_response(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from observability.models import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        tc = TechnocoreConnector()
        async with Session() as s:
            data = {"last_seq": 77, "messages": []}
            await tc.advance_cursor_from_response("myroom", data, s)
            await s.commit()
            assert await tc.get_cursor("myroom", s) == 77
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_read_room_updates_cursor(self):
        """Mock HTTP + DB session ile read_room cursor'u günceller."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from observability.models import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)

        # mock transport: returns JSON with last_seq 55
        async def handler(request):
            return httpx.Response(
                200,
                json={"room": "myroom", "count": 1, "last_seq": 55, "messages": [], "first_seq": 1},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            tc = TechnocoreConnector(client=client)
            # validate_host'u bypass için base_url'i localhost yapma — mock için patch
            tc._validate_base_host = lambda: None
            async with Session() as s:
                data = await tc.read_room("myroom", since=0, wait=0, session=s)
                await s.commit()
                assert data["last_seq"] == 55
                assert data["_untrusted"] is True
                cur = await tc.get_cursor("myroom", s)
                assert cur == 55

        await engine.dispose()


# ---------------------------------------------------------------------------
# POST body OpenAPI uyumlu
# ---------------------------------------------------------------------------
class TestPostBodyOpenAPI:
    @pytest.mark.asyncio
    async def test_signed_post_body_shape(self):
        captured: dict = {}

        async def handler(request):
            captured["json"] = json.loads(request.content)
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"room": "myroom", "count": 1, "last_seq": 10, "messages": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with tempfile.TemporaryDirectory() as td:
                tc = TechnocoreConnector(client=client, ed25519_key_path=f"{td}/post.key")
                tc.load_or_generate_key()
                tc._validate_base_host = lambda: None

                # payload string
                await tc.signed_post("myroom", "hello world")
                body = captured["json"]
                # OpenAPI required: text, sig, did, nonce
                assert "text" in body
                assert body["text"] == "hello world"
                assert _DID_RE.match(body["did"]), f"did bad: {body['did']}"
                assert _SIG_RE.match(body["sig"]), f"sig bad: {body['sig']}"
                assert _NONCE_RE.match(body["nonce"])
                # yasaklar: eski alanlar olmamalı
                for forbidden in ("type", "observed_at", "subject", "change", "evidence", "confidence", "schema_version", "signature", "idempotency_key"):
                    assert forbidden not in body, f"forbidden field {forbidden} found"

    @pytest.mark.asyncio
    async def test_signed_post_dict_payload_to_text(self):
        captured: dict = {}

        async def handler(request):
            captured["json"] = json.loads(request.content)
            return httpx.Response(200, json={"room": "myroom", "count": 1, "last_seq": 1, "messages": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with tempfile.TemporaryDirectory() as td:
                tc = TechnocoreConnector(client=client, ed25519_key_path=f"{td}/post2.key")
                tc.load_or_generate_key()
                tc._validate_base_host = lambda: None
                # rapor dict payload -> text olarak JSON serialize
                await tc.signed_post("myroom", {"type": "report", "subject": "test"})
                body = captured["json"]
                assert "text" in body
                # text JSON parse edilebilir olmalı
                parsed = json.loads(body["text"])
                assert parsed["type"] == "report"

                # explicit text field override
                await tc.signed_post("myroom", {"text": "my explicit text", "extra": "ignored?"})
                body2 = captured["json"]
                assert body2["text"] == "my explicit text"

    @pytest.mark.asyncio
    async def test_signed_post_sweep_truncate(self):
        captured: dict = {}

        async def handler(request):
            captured["json"] = json.loads(request.content)
            return httpx.Response(200, json={"room": "myroom", "count": 1, "last_seq": 1, "messages": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with tempfile.TemporaryDirectory() as td:
                tc = TechnocoreConnector(client=client, ed25519_key_path=f"{td}/post3.key")
                tc.load_or_generate_key()
                tc._validate_base_host = lambda: None
                await tc.signed_post("myroom", "a\nb\x00c")
                assert captured["json"]["text"] == "a b c"
                # 4096 truncate
                long_text = "x" * 5000
                await tc.signed_post("myroom", long_text)
                assert len(captured["json"]["text"]) == 4096

    def test_build_signed_get_url(self):
        with tempfile.TemporaryDirectory() as td:
            tc = TechnocoreConnector(ed25519_key_path=f"{td}/get.key")
            tc.load_or_generate_key()
            url = tc.build_signed_get_url("myroom", "hello world")
            assert "/r/myroom/say-signed/" in url
            assert "hello%20world" in url or "hello world" not in url  # encoded


# ---------------------------------------------------------------------------
# 429 backoff — body parsing
# ---------------------------------------------------------------------------
class TestBackoff429:
    def test_parse_body_retry(self):
        req = httpx.Request("GET", "https://x.test/r/lobby")
        # body contains retry seconds
        resp = httpx.Response(429, text="Too many requests, retry in 2.5 seconds. bucket reads ...", request=req)
        assert _parse_retry_after(resp) == pytest.approx(2.5)
        # header fallback
        httpx.Response(429, headers={"Retry-After": "3"}, text="rate limited", request=req)
        # body has no number? but "rate limited" still has maybe no number -> header used? Actually body has no float match? Let's craft
        httpx.Response(429, headers={"Retry-After": "3"}, text="no numbers here!", request=req)
        # "no numbers here!" has no digits? but we clamp — should parse header
        # Our impl searches body first, finds none? Actually _RETRY_BODY_RE would not match "no numbers here!" -> header
        # Let's patch body to empty numeric to test header path directly
        resp3 = httpx.Response(429, headers={"Retry-After": "4.2"}, text="", request=req)
        assert _parse_retry_after(resp3) == pytest.approx(4.2)

    def test_parse_body_empty_defaults(self):
        req = httpx.Request("GET", "https://x.test/r/lobby")
        resp = httpx.Response(429, text="", headers={}, request=req)
        assert _parse_retry_after(resp) == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_read_room_429_retry_then_success(self):
        call_count = 0

        async def handler(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, text="retry in 0.01 seconds", headers={"Retry-After": "0.01"})
            return httpx.Response(200, json={"room": "myroom", "count": 0, "last_seq": 5, "messages": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            tc = TechnocoreConnector(client=client, max_retries=2)
            tc._validate_base_host = lambda: None
            data = await tc.read_room("myroom", since=0, wait=0)
            assert data["last_seq"] == 5
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_signed_post_429_retry(self):
        call_count = 0

        async def handler(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, text="Too many writes, retry in 0.01 seconds", headers={"Retry-After": "0.01"})
            return httpx.Response(200, json={"room": "myroom", "count": 1, "last_seq": 6, "messages": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with tempfile.TemporaryDirectory() as td:
                tc = TechnocoreConnector(client=client, ed25519_key_path=f"{td}/backoff.key", max_retries=2)
                tc.load_or_generate_key()
                tc._validate_base_host = lambda: None
                data = await tc.signed_post("myroom", "hello")
                assert data["last_seq"] == 6
                assert call_count == 2

    @pytest.mark.asyncio
    async def test_429_exhaust_raises(self):
        async def handler(request):
            return httpx.Response(429, text="retry in 0.01 seconds", headers={"Retry-After": "0.01"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            tc = TechnocoreConnector(client=client, max_retries=1)
            tc._validate_base_host = lambda: None
            with pytest.raises(TechnocoreError, match="429"):
                await tc.read_room("myroom", since=0, wait=0)

```

## `tests/unit/test_telegram.py`

```py
# RAPTOR — AŞAMA 5 Telegram testleri (singleton, dedup helper, redact, allowlist)
from agent_core.telegram import TelegramService, get_service, webhook_opaque_path
from observability.security import redact


class TestSingleton:
    def test_get_service_returns_same_instance(self):
        a = get_service()
        b = get_service()
        assert a is b, "her çağrıda yeni instance oluşturulmamalı (singleton)"


class TestOpaquePath:
    def test_deterministic(self):
        p1 = webhook_opaque_path("my-secret")
        p2 = webhook_opaque_path("my-secret")
        assert p1 == p2
        assert len(p1) == 32  # sha256 hex ilk 32

    def test_different_secret_different_path(self):
        assert webhook_opaque_path("a") != webhook_opaque_path("b")

    def test_empty_secret_empty_path(self):
        assert webhook_opaque_path("") == ""


class TestRedactToken:
    def test_telegram_token_masked(self):
        token = "8820797359:AAGJ18u8OZgrHUxDlhYHy9dW5bXrmHyvA2o"
        out = redact(f"hata: {token} isteği başarısız")
        assert token not in out, "token log/metinde görünmemeli"
        assert "TG_TOKEN_REDACTED" in out

    def test_llm_key_masked(self):
        key = "sk-JgWZznvGKVXpsZRUBGHle8qXvXmWbeUiHbMToITn35WSvLAZ2dDOYnJCF61Nr4bf"
        out = redact(f"key={key}")
        assert key not in out
        assert "REDACTED" in out


class TestAllowlist:
    def test_empty_env_denies(self):
        svc = TelegramService.__new__(TelegramService)  # __init__'siz — settings token okumaz
        # env allowlist boşsa allowed() False döner (fail-closed)
        # Bu test yalnızca 'allowed' metodunun boş liste davranışını doğrular
        from observability.config import settings
        original = settings.allowed_user_ids
        settings.TELEGRAM_ALLOWED_USER_IDS = ""
        try:
            assert svc.allowed(123456789) is False
        finally:
            settings.TELEGRAM_ALLOWED_USER_IDS = ",".join(str(x) for x in original) if original else ""

```