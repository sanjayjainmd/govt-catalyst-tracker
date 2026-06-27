"""Live market caps via yfinance, with graceful fallback to the crosswalk statics.

Materiality (award ÷ market cap) drives every score, so stale caps skew everything.
This refreshes them at runtime; if a fetch fails the static crosswalk value stands in.
"""


def fetch_caps(tickers):
    """Return {ticker: market_cap_usd} for whatever resolves; missing ones are omitted."""
    caps = {}
    try:
        import yfinance as yf
    except Exception as e:
        print(f"market_cap: yfinance unavailable ({e}); using static caps")
        return caps
    for t in sorted(set(tickers)):
        try:
            mc = yf.Ticker(t).fast_info["market_cap"]
            if mc:
                caps[t] = float(mc)
        except Exception:
            pass
    return caps


def apply_live_caps(crosswalk):
    """Overwrite each crosswalk row's market_cap_musd with the live value when available."""
    caps = fetch_caps([c["ticker"] for c in crosswalk])
    for c in crosswalk:
        live = caps.get(c["ticker"])
        if live:
            c["market_cap_musd"] = live / 1e6
    print(f"market_cap: refreshed {len(caps)} of {len(crosswalk)} tickers live")
    return crosswalk
