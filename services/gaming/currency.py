USD_TO_INR = 87.50

def format_inr(amount: float | str) -> str:
    """Formats numeric or string amount into Indian Rupee representation (e.g. ₹ 1,499)."""
    if isinstance(amount, str):
        if amount.strip().lower() in ("free", "free to play", "n/a", "none", ""):
            return amount
        try:
            val = float(amount.replace("$", "").replace("₹", "").replace(",", "").strip())
            return f"₹ {round(val):,}"
        except Exception:
            return amount
    try:
        return f"₹ {round(amount):,}"
    except Exception:
        return str(amount)

def convert_usd_to_inr_str(usd_amount: float | str) -> str:
    """Converts USD amount to INR representation."""
    if isinstance(usd_amount, str):
        if usd_amount.strip().lower() in ("free", "free to play", "n/a", "none", ""):
            return usd_amount
        try:
            val = float(usd_amount.replace("$", "").replace(",", "").strip())
            return f"₹ {round(val * USD_TO_INR):,}"
        except Exception:
            return usd_amount
    try:
        return f"₹ {round(usd_amount * USD_TO_INR):,}"
    except Exception:
        return str(usd_amount)
