import os
import json
from datetime import datetime, date
import requests
import yfinance as yf

NTFY_TOPIC = os.environ.get("NTFY_COV", "rbc_options_dgc_7841")

def send_ntfy(titre: str, message: str, priorite: str = "high", tags: str = "warning"):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {
        "Title": titre.encode("utf-8"),
        "Priority": priorite,
        "Tags": tags
    }
    resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
    resp.raise_for_status()

def analyser_positions():
    with open("positions.json", "r", encoding="utf-8") as f:
        positions = json.load(f)

    today = date.today()

    for pos in positions:
        ticker_symbol = pos["ticker"]
        strike = float(pos["strike"])
        contracts = pos["contracts"]
        expiry_date = datetime.strptime(pos["expiry"], "%Y-%m-%d").date()
        jours_restants = (expiry_date - today).days

        stock = yf.Ticker(ticker_symbol)
        cours = stock.fast_info.get("last_price")
        if not cours:
            continue

        ratio = cours / strike
        is_expiry_day = (jours_restants == 0)

        # 1. Option dans le cours (ITM) -> Risque d'assignation
        if cours >= strike:
            if is_expiry_day:
                send_ntfy(
                    titre=f"URGENCE ABSOLUE : {ticker_symbol} ITM",
                    message=(
                        f"3e Vendredi d'échéance !\n"
                        f"Cours : {cours:.2f} $ | Strike : {strike:.2f} $\n"
                        f"Contrats : {contracts}\n"
                        f"Action requise avant 15h15 : Exécuter un Roll Out sur RBC DI "
                        f"pour conserver vos actions."
                    ),
                    priorite="urgent",
                    tags="rotating_light,fire"
                )
            else:
                send_ntfy(
                    titre=f"ALERTE ITM : {ticker_symbol}",
                    message=(
                        f"Le titre a franchi le strike.\n"
                        f"Cours : {cours:.2f} $ | Strike : {strike:.2f} $\n"
                        f"Échéance dans {jours_restants} jours ({pos['expiry']}).\n"
                        f"Préparez un roulement (Roll Out) à crédit net."
                    ),
                    priorite="high",
                    tags="warning,chart_with_upwards_trend"
                )

        # 2. Vigilance proximité du strike (98% à 99.9%)
        elif ratio >= 0.98:
            if is_expiry_day:
                send_ntfy(
                    titre=f"PIN RISK (3e Vendredi) : {ticker_symbol}",
                    message=(
                        f"Cours ({cours:.2f} $) très proche du strike ({strike:.2f} $).\n"
                        f"Annulez l'ordre GTC et clôturez manuellement (BTC) "
                        f"pour éliminer tout risque d'assignation."
                    ),
                    priorite="high",
                    tags="warning"
                )
            else:
                send_ntfy(
                    titre=f"Vigilance Strike : {ticker_symbol}",
                    message=(
                        f"Cours : {cours:.2f} $ s'approche du strike {strike:.2f} $.\n"
                        f"Échéance : {pos['expiry']} ({jours_restants} j)."
                    ),
                    priorite="default",
                    tags="eyes"
                )

if __name__ == "__main__":
    analyser_positions()
