import pytest

from pracownie import cli


def test_github_error_annotation(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(cli.parser().__class__, "parse_args", lambda self: None)
    def fail(_):
        raise RuntimeError("Przerwano\nzapis 50%")
    monkeypatch.setattr(cli, "execute", fail)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    assert "::error title=Pracownie Monitor::Przerwano%0Azapis 50%25" in capsys.readouterr().err
