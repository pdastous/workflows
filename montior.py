import os
import json
from datetime import datetime, date
import requests
import yfinance as yf

# Récupération du topic ntfy
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "rbc_options_dgc_7841")

def send_ntfy(titre: str, message: str, priorite: str = "high", tags: str = "warning"):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    # Dans requests, les headers doivent être des chaînes str (pas de .encode())
    headers = {
        "Title": titre,
        "Priority": priorite,
        "Tags": tags
    }
    resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=15)
    resp.raise_for_status()

def get_cours_actuel(ticker_symbol: str):
    """Récupère le dernier cours de manière robuste sur yfinance."""
    stock = yf.Ticker(ticker_symbol)
    try:
        # 1. Tentative via fast_info (accès par attribut)
        cours = getattr(stock.fast_info, "last_price", None)
        if cours is not None:
            return float(cours)
    except Exception:
        pass

    try:
        # 2. Repli via l'historique du jour
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass

    return None

def analyser_positions():
    if not os.path.exists("positions.json"):
        raise FileNotFoundError("Le fichier positions.json est introuvable à la racine du dépôt.")

    with open("positions.json", "r", encoding="utf-8") as f:
        positions = json.load(f)

    today = date.today()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Début de l'analyse ({len(positions)} positions)...")

    for pos in positions:
        ticker_symbol = pos["ticker"]
        strike = float(pos["strike"])
        contracts = pos["contracts"]
        expiry_date = datetime.strptime(pos["expiry"], "%Y-%m-%d").date()
        jours_restants = (expiry_date - today).days

        cours = get_cours_actuel(ticker_symbol)
        if cours is None:
            print(f"⚠️ Impossible de récupérer le cours pour {ticker_symbol}")
            continue

        ratio = cours / strike
        is_expiry_day = (jours_restants == 0)
        print(f"• {ticker_symbol} : Cours = {cours:.2f} $ | Strike = {strike:.2f} $ (Ratio : {ratio:.1%})")

        # 1. Option dans le cours (ITM) -> Actions menacées
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

    print("Analyse terminée avec succès.")

if __name__ == "__main__":
    analyser_positions()
