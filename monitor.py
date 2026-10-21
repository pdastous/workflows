import os
import json
from datetime import datetime, date
import requests
import yfinance as yf

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "Surveillance des options couvertes")

def send_ntfy(titre: str, message: str, priorite: str = "high", tags: str = "warning"):
    url = "https://ntfy.sh/Cov_Opt_PDA303/"
    
    # Conversion des priorités textuelles en niveaux numériques ntfy (1 à 5)
    priority_map = {
        "urgent": 5,
        "high": 4,
        "default": 3,
        "low": 2,
        "min": 1
    }
    
    payload = {
        "topic": NTFY_TOPIC,
        "title": titre,
        "message": message,
        "priority": priority_map.get(priorite, 3),
        "tags": [t.strip() for t in tags.split(",") if t.strip()]
    }
    
    # requests encode automatiquement le JSON en UTF-8 sans restriction de caractères
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()

def get_cours_actuel(ticker_symbol: str):
    stock = yf.Ticker(ticker_symbol)
    try:
        cours = getattr(stock.fast_info, "last_price", None)
        if cours is not None:
            return float(cours)
    except Exception:
        pass

    try:
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
    heure_actuelle = datetime.now().strftime("%H:%M")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Démarrage de l'analyse ({len(positions)} positions)...")

    alertes_declenchees = 0
    resume_lignes = []

    for pos in positions:
        ticker_symbol = pos["ticker"]
        strike = float(pos["strike"])
        contracts = pos["contracts"]
        expiry_date = datetime.strptime(pos["expiry"], "%Y-%m-%d").date()
        jours_restants = (expiry_date - today).days

        cours = get_cours_actuel(ticker_symbol)
        if cours is None:
            print(f"⚠️ Impossible de récupérer le cours pour {ticker_symbol}")
            resume_lignes.append(f"• {ticker_symbol} : Erreur cours")
            continue

        ratio = cours / strike
        is_expiry_day = (jours_restants == 0)
        symbole_court = ticker_symbol.replace(".TO", "")
        resume_lignes.append(f"• {symbole_court} : {cours:.2f} $ / {strike:.2f} $ ({ratio:.0%})")
        print(f"• {ticker_symbol} : Cours = {cours:.2f} $ | Strike = {strike:.2f} $")

        # -----------------------------------------------------------------
        # 1. SURVEILLANCE EX-DIVIDENDE (J-2 à J-1)
        # -----------------------------------------------------------------
        if "ex_div" in pos and pos["ex_div"]:
            ex_div_date = datetime.strptime(pos["ex_div"], "%Y-%m-%d").date()
            jours_avant_ex_div = (ex_div_date - today).days
            div_montant = float(pos.get("div_amount", 0.0))

            if 0 < jours_avant_ex_div <= 2 and cours >= strike:
                alertes_declenchees += 1
                valeur_intrinseque = cours - strike
                send_ntfy(
                    titre=f"🚨 RISQUE ASSIGNATION ANTICIPÉE : {ticker_symbol}",
                    message=(
                        f"Date ex-dividende dans {jours_avant_ex_div} j ({pos['ex_div']}) !\n"
                        f"Dividende : {div_montant:.2f} $ | Cours : {cours:.2f} $ | Strike : {strike:.2f} $\n\n"
                        f"Vérifiez le call sur RBC DI. Si sa valeur temps est < {div_montant:.2f} $, "
                        f"exécutez un Roll Out avant 15h30 pour conserver titres et dividendes."
                    ),
                    priorite="urgent",
                    tags="moneybag,rotating_light"
                )

        # -----------------------------------------------------------------
        # 2. DANS LE COURS (ITM)
        # -----------------------------------------------------------------
        if cours >= strike:
            alertes_declenchees += 1
            if is_expiry_day:
                send_ntfy(
                    titre=f"URGENCE ABSOLUE : {ticker_symbol} ITM",
                    message=(
                        f"3e Vendredi d'échéance !\n"
                        f"Cours : {cours:.2f} $ | Strike : {strike:.2f} $\n"
                        f"Contrats : {contracts}\n"
                        f"Action requise avant 15h15 : Roll Out obligatoire sur RBC DI."
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
                        f"Échéance dans {jours_restants} j ({pos['expiry']}).\n"
                        f"Préparez un roulement (Roll Out) à crédit net."
                    ),
                    priorite="high",
                    tags="warning,chart_with_upwards_trend"
                )

        # -----------------------------------------------------------------
        # 3. PROXIMITÉ DU STRIKE (98 % à 99.9 %)
        # -----------------------------------------------------------------
        elif ratio >= 0.98:
            alertes_declenchees += 1
            if is_expiry_day:
                send_ntfy(
                    titre=f"PIN RISK (3e Vendredi) : {ticker_symbol}",
                    message=(
                        f"Cours ({cours:.2f} $) tangent au strike ({strike:.2f} $).\n"
                        f"Annulez l'ordre GTC et rachetez (BTC) avant 15h30."
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

    # -----------------------------------------------------------------
    # 4. ACCUSÉ DE RÉCEPTION : AUCUNE MENACE DÉTECTÉE
    # -----------------------------------------------------------------
    if alertes_declenchees == 0:
        details_marche = "\n".join(resume_lignes)
        send_ntfy(
            titre="🟢 Statut RBC : 100 % Sécurisé",
            message=(
                f"Exécution réussie ({heure_actuelle}).\n"
                f"Aucune menace d'assignation détectée.\n\n"
                f"Cours / Strike actuel :\n"
                f"{details_marche}"
            ),
            priorite="low",
            tags="white_check_mark,shield"
        )
        print("Aucune menace détectée. Notification de confirmation envoyée.")

    print("Analyse terminée avec succès.")

if __name__ == "__main__":
    analyser_positions()
