# RAPTOR — SSRF koruması
# Loopback, RFC1918, link-local, metadata IP, socket ve internal Docker hostname
# erişimi engeller. DNS çözümünden ve her redirect'ten sonra IP tekrar sınıflandırılır.
from __future__ import annotations

import ipaddress
import socket

# Arzu edilen engellenen her türlü IP
_BLOCKED_NETWORKS = [
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",   # link-local
    "0.0.0.0/8",
    "100.64.0.0/10",    # CGNAT — genelde engelle, üretim isteğe bağlı
    "::1/128",
    "fc00::/7",         # IPv6 unique-local
    "fe80::/10",        # link-local IPv6
]
# Cloud metadata serbest
_METADATA_HOSTS = {"169.254.169.254", "metadata.google.internal"}

_blocked = [ipaddress.ip_network(n) for n in _BLOCKED_NETWORKS]


class SSRFError(Exception):
    pass


def resolve_all(host: str) -> list[str]:
    """Tüm A/AAAA sonuçlarını döndürür (bir tanesi bile blokluysa düşman)."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise SSRFError(f"DNS çözümleme başarısız: {host}") from e
    ips: set[str] = set()
    for info in infos:
        ips.add(str(info[4][0]))
    return sorted(ips)


def ip_is_blocked(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    if ip_str in _METADATA_HOSTS:
        return True
    return any(ip in net for net in _blocked)


def validate_host(host: str, allowed_hosts: set[str] | None = None) -> None:
    """Host adını doğrular; DNS çözümünden sonra IP sınıfını kontrol eder.

    - allowed_hosts verilirse host bunlardan birine tam eşleşmek zorunda.
    - Hostname allowlist'e yoksa bile bloklu IP'ler reddedilir.
    """
    host = host.rstrip(".").lower()
    if not host:
        raise SSRFError("boş host")
    if host in _METADATA_HOSTS:
        raise SSRFError("metadata erişimi engellendi")
    if allowed_hosts and host not in {h.lower() for h in allowed_hosts}:
        raise SSRFError(f"host allowlist dışı: {host}")
    for ip in resolve_all(host):
        if ip_is_blocked(ip):
            raise SSRFError(f"bloklu IP (RFC1918/loopback/metadata): {ip}")


def validate_url(url: str, allowed_hosts: set[str] | None = None) -> str:
    """URL'yi ayrıştırır, host'u doğrular; port/scheme kontrolü yapar."""
    from urllib.parse import urlparse

    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        raise SSRFError(f"geçersiz scheme: {parts.scheme}")
    if not parts.hostname:
        raise SSRFError("host yok")
    # socket & dosya benzeri: urlparse hostname'de hacklenemez ama ayrıca control
    if "unix:" in url:
        raise SSRFError("unix socket erişimi engellendi")
    validate_host(parts.hostname, allowed_hosts)
    return url