from pathlib import Path

from nls.router_ca import (
    create_root_ca,
    issue_router_certificate,
    verify_router_certificate,
)


def test_router_certificate_issued_and_verified(tmp_path: Path):
    ca_key, ca_cert = create_root_ca(tmp_path / "ca")
    router_key, router_cert = issue_router_certificate(
        ca_key, ca_cert, "router-01", tmp_path / "routers"
    )
    assert router_key.stat().st_mode & 0o777 == 0o600
    assert verify_router_certificate(router_cert, ca_cert, "router-01")
    assert not verify_router_certificate(router_cert, ca_cert, "router-02")


def test_ca_refuses_overwrite(tmp_path: Path):
    create_root_ca(tmp_path / "ca")
    try:
        create_root_ca(tmp_path / "ca")
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing CA material must not be overwritten")


def test_router_certificate_issuer_mismatch_rejected(tmp_path: Path):
    ca_key, ca_cert = create_root_ca(tmp_path / "ca1")
    _, router_cert = issue_router_certificate(ca_key, ca_cert, "router-01", tmp_path / "router")
    _, other_ca_cert = create_root_ca(tmp_path / "ca2")
    assert not verify_router_certificate(router_cert, other_ca_cert, "router-01")
