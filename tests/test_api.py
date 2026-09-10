import urllib.error
from unittest import mock

from bulario.api import Client


def _http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, None)


def test_retries_on_5xx_then_succeeds():
    ok = mock.MagicMock()
    ok.__enter__.return_value.read.return_value = b'{"a": 1}'
    with (
        mock.patch("urllib.request.urlopen", side_effect=[_http_error(500), _http_error(502), ok]) as m,
        mock.patch("time.sleep"),
    ):
        assert Client(delay=0).get_json("bulario/1") == {"a": 1}
        assert m.call_count == 3


def test_no_retry_on_4xx():
    with mock.patch("urllib.request.urlopen", side_effect=_http_error(404)) as m, mock.patch("time.sleep"):
        try:
            Client(delay=0).get_json("bulario/1")
        except urllib.error.HTTPError as e:
            assert e.code == 404
        assert m.call_count == 1


def test_gives_up_after_retries():
    with mock.patch("urllib.request.urlopen", side_effect=_http_error(500)) as m, mock.patch("time.sleep"):
        try:
            Client(delay=0, retries=2).get_json("bulario/1")
            raise AssertionError("deveria falhar")
        except urllib.error.HTTPError:
            pass
        assert m.call_count == 3


def test_retries_on_429_with_retry_after():
    ok = mock.MagicMock()
    ok.__enter__.return_value.read.return_value = b'{"a": 1}'
    err = urllib.error.HTTPError("http://x", 429, "slow down", {"Retry-After": "3"}, None)
    with (
        mock.patch("urllib.request.urlopen", side_effect=[err, ok]) as m,
        mock.patch("time.sleep") as sleep,
    ):
        assert Client(delay=0).get_json("bulario/1") == {"a": 1}
        assert m.call_count == 2
        assert 10 in [c.args[0] for c in sleep.call_args_list]  # mínimo de 10 s mesmo com Retry-After menor


def test_retries_on_truncated_response():
    import http.client

    ok = mock.MagicMock()
    ok.__enter__.return_value.read.return_value = b"%PDF"
    truncated = mock.MagicMock()
    truncated.__enter__.return_value.read.side_effect = http.client.IncompleteRead(b"")
    with mock.patch("urllib.request.urlopen", side_effect=[truncated, ok]) as m, mock.patch("time.sleep"):
        assert Client(delay=0).download_bula("id") == b"%PDF"
        assert m.call_count == 2
