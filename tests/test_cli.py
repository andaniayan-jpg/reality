from __future__ import annotations

from pytest import CaptureFixture

from reality.__main__ import main


def test_cli_prints_installation_greeting(capsys: CaptureFixture[str]) -> None:
    main()
    assert capsys.readouterr().out == "Andani is goat!!\n"
