from funding_tool.core.exchanges._binance_sign import sign_query


def test_sign_query_matches_known_vector():
    # Vector from Binance documentation:
    secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
    query = "symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1&recvWindow=5000&timestamp=1499827319559"
    expected = "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"
    assert sign_query(secret, query) == expected


def test_sign_query_handles_unicode_safely():
    # Should not raise for any UTF-8 secret/query
    sig = sign_query("ümlaut", "symbol=BTCUSDT")
    assert isinstance(sig, str)
    assert len(sig) == 64  # hex sha256
