from printmaster.infra.logging_setup import setup_logging


def test_api_key_redacted(tmp_path):
    log = setup_logging(tmp_path)
    key = "AIza" + "x" * 35
    log.warning("conectando api_key=%s", key)
    log.warning("clave suelta %s", key)
    for h in log.handlers:
        h.flush()
    text = (tmp_path / "printmaster.log").read_text(encoding="utf-8")
    assert "***" in text
    assert "AIza" not in text
