from app.services.rates.rates_crypto import CryptoRatesClient
import asyncio

def test_crypto_update_contains_btc():
    client = CryptoRatesClient()
    asyncio.run(client.update())
    rates = client.rates_usd

    assert isinstance(rates, dict)
    assert "BTC" in rates
    assert rates["BTC"] > 0
