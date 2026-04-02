import aiohttp
import time
import math
from utils.log import get_logger

logger = get_logger("utils.currency")

_CACHE = {}
_CACHE_TIMEOUT = 86400  # 1 day

async def get_exchange_rate(base_currency: str, target_currency: str = "USD") -> float:
    """Fetches the exchange rate from a public API, with caching."""
    base_currency = base_currency.upper()
    target_currency = target_currency.upper()

    if base_currency == target_currency:
        return 1.0

    cache_key = f"{base_currency}_{target_currency}"
    now = time.time()
    if cache_key in _CACHE and now - _CACHE[cache_key]["time"] < _CACHE_TIMEOUT:
        return _CACHE[cache_key]["rate"]

    try:
        url = f"https://open.er-api.com/v6/latest/{base_currency}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rates = data.get("rates", {})
                    rate = rates.get(target_currency)
                    if rate:
                        _CACHE[cache_key] = {"rate": rate, "time": now}
                        return rate
    except Exception as e:
        logger.error(f"Failed to fetch exchange rate for {base_currency} to {target_currency}: {e}")

    # Fallback to older cached value if available
    if cache_key in _CACHE:
        return _CACHE[cache_key]["rate"]

    # Fallback to 1.0 if completely failed
    logger.warning(f"Using fallback exchange rate 1.0 for {base_currency} to {target_currency}")
    return 1.0

def format_fiat(amount: float, currency: str) -> str:
    """Formats fiat currency based on 'strength' (e.g. strong currencies get decimals, weak get rounded)."""
    strong_currencies = ["USD", "EUR", "GBP", "AUD", "CAD", "CHF"]
    currency = currency.upper()

    # Map common currencies to their symbols
    symbols = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "RUB": "₽", "BRL": "R$"
    }
    sym = symbols.get(currency, f"{currency} ")

    if currency in strong_currencies:
        # Round to nearest 10 cents and keep 2 decimal places
        val = round(amount * 10) / 10.0
        return f"{sym}{val:.2f}".replace(" $", "$").replace(" €", "€").replace(" £", "£")
    else:
        # For weak currencies, round to nearest whole number
        val = int(round(amount))
        return f"{val} {sym}".strip()

async def convert_to_usd_str(price_string: str) -> str:
    """Converts a price string to a dual display: Local Fiat / USD."""
    price_string = price_string.strip().upper()
    if not price_string:
        return ""

    try:
        import re
        match = re.search(r"([\d\.]+)\s*([A-Z]+|\$|€|£|₹|₽)?", price_string)
        if not match:
            return price_string

        amount_str = match.group(1)
        currency_sym = match.group(2)

        amount = float(amount_str)
        currency = "USD"

        if currency_sym:
            if currency_sym == "$": currency = "USD"
            elif currency_sym == "€": currency = "EUR"
            elif currency_sym == "£": currency = "GBP"
            elif currency_sym == "₹": currency = "INR"
            elif currency_sym == "₽": currency = "RUB"
            else: currency = currency_sym

        local_formatted = format_fiat(amount, currency)

        if currency == "USD":
            return local_formatted

        rate = await get_exchange_rate(currency, "USD")
        usd_amount = amount * rate
        usd_formatted = format_fiat(usd_amount, "USD")

        return f"{local_formatted} / {usd_formatted}"
    except Exception as e:
        logger.error(f"Error converting price '{price_string}': {e}")
        return price_string
