"""Récupère l'horaire HEH Planning (Hyperplanning, espace invités) d'une option
et génère une page mobile (index.html) + un calendrier (horaire.ics).

Protocole de l'espace invités repris du projet EzHoraire
(https://github.com/Frybex/EzHoraire, api/_moteurs/hyperplanning.py).

Usage : python fetch.py            (dépendances : requirements.txt)
        python fetch.py --page     (régénère index.html sans rappeler l'école)
"""
import base64
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone

import requests
from zoneinfo import ZoneInfo
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

BASE = "https://hehplanning2026.umons.ac.be"   # change chaque année
FORMATION = "MA1 Ingénieur industriel"
OPTION = "MA1 TL - PASS Info IA et Big Data"    # tag (genre 15) de l'option
GARDER_SANS_TAG = True                           # cours sans option = communs (St Eloi...)
ONGLET = "DIPLOME.EDT.EDT_GRILLE"
ICI = os.path.dirname(os.path.abspath(__file__))


class HP:
    """Mini-client pour l'API 'appelfonction' de l'espace invités."""

    def __init__(self, base):
        self.base = base
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
            "Content-Type": "application/json",
            "Referer": base + "/invite?fd=1", "Origin": base})
        html = self.s.get(base + "/invite?fd=1", timeout=20).text
        m = re.search(r"""Start \(\{\s*["']?a["']?\s*:\s*(\d+)\s*,\s*["']?b["']?\s*:\s*(\d+)\s*,"""
                      r"""\s*["']?c["']?\s*:\s*["']([^"']+)["']\s*,\s*["']?i["']?\s*:\s*["']?(\d+)""", html)
        if not m:
            raise RuntimeError("page d'accueil inattendue (Start introuvable)")
        self.genre, self.sess = int(m.group(1)), int(m.group(4))
        self.key, self.iv = b"", os.urandom(16)
        self.params = self.call("FonctionParametres", ordre=1, raw_iv=True,
                                charge={"ModeJeton": False, "identifiantNav": "",
                                        "Uuid": base64.b64encode(self.iv).decode()})
        self.ordre = 3
        self.dpu = self.call("DemandeParametreUtilisateur", charge={})

    def _no(self, n, raw_iv):
        iv = b"" if raw_iv else self.iv
        k = hashlib.md5(self.key).digest()
        v = hashlib.md5(iv).digest() if iv else bytes(16)
        return AES.new(k, AES.MODE_CBC, v).encrypt(pad(str(n).encode(), 16)).hex()

    def call(self, fid, charge=None, signature=None, ordre=None, raw_iv=False):
        no = self._no(self.ordre if ordre is None else ordre, raw_iv)
        env = {}
        if signature is not None:
            env["Signature"] = signature
        if charge is not None:
            env["data"] = charge
        r = self.s.post(f"{self.base}/appelfonction/{self.genre}/{self.sess}/{no}",
                        json={"session": self.sess, "no": no, "id": fid, "dataSec": env},
                        timeout=20)
        r.raise_for_status()
        j = r.json()
        sig = (j.get("dataSec") or {}).get("Signature") or {}
        if sig.get("Erreur"):
            raise RuntimeError(f"{fid} : {sig.get('MessageErreur')}")
        if ordre is None:
            self.ordre += 2
        return (j.get("dataSec") or {}).get("data") or {}

    def chercher(self, cle, obj=None):
        obj = self.params if obj is None else obj
        if isinstance(obj, dict):
            if cle in obj:
                return obj[cle]
            obj = list(obj.values())
        if isinstance(obj, list):
            for v in obj:
                t = self.chercher(cle, v)
                if t is not None:
                    return t
        return None

    def formation(self, nom):
        r = self.call("FonctionRenvoyerListeDeRessource", signature={"Onglet": ONGLET},
                      charge={"GenreRessource": 1, "GenreRecherche": 1,
                              "AvecPublicationForcee": False, "NomRessource": "*",
                              "PourEmail": False, "PourRessource": False,
                              "filtresRessource": []})
        return next(f for f in r["ListeRessources"]["Liste"] if f["L"] == nom)

    def periode(self, ress):
        r = self.call("FonctionDomaineDePresence",
                      signature={"Onglet": ONGLET, "listeRecherche": [ress]},
                      charge={"FiltreRessources": {"_T": 26, "V": "[0,6..7]"},
                              "AvecCalendrier": False})
        return ensemble(r["PeriodeConsultation"]["V"])

    def semaine(self, ress, w):
        return self.call("FonctionEmploiDuTemps",
                         signature={"Onglet": ONGLET, "listeRecherche": [ress]},
                         charge={"GenrePeriodeEDT": 2, "GenreAffichageEDT": 0,
                                 "FiltreRessources": {"_T": 26, "V": "[0,2,6..8]"},
                                 "AvecIndisponibilites": True, "AvecDomaineCours": True,
                                 "AvecDomainePere": False, "filterPlagesHoraires": False,
                                 "ignorerCoursAnnules": False, "avecInfosAppel": False,
                                 "Domaine": {"_T": 8, "V": f"[{w}]"}})["ListeCours"]


def ensemble(txt):
    """'[1..3,7]' -> [1, 2, 3, 7]"""
    out = []
    for p in str(txt).strip("[] ").split(","):
        if ".." in p:
            a, b = p.split("..")
            out += range(int(a), int(b) + 1)
        elif p.strip():
            out.append(int(p))
    return out


def items(brut, genre):
    out = []
    for cont in brut.get("listeC", []):
        if cont.get("G") == genre:
            c = cont.get("C")
            out += [i for i in (c if isinstance(c, list) else [c]) if isinstance(i, dict) and i]
    return out


def recuperer():
    hp = HP(BASE)
    heures = [h for h in hp.dpu["Horaire"]["ListeHeures"] if h.get("Debut")]
    ppj = int(hp.chercher("PlacesParJour") or 48)
    m = re.fullmatch(r"(\d\d)/(\d\d)/(\d{4})", str((hp.chercher("PremierLundi") or {}).get("V", "")))
    lundi1 = date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else date(2026, 9, 14)
    ress = hp.formation(FORMATION)
    cours = []
    for w in hp.periode(ress):
        for b in hp.semaine(ress, w):
            tags = [i["L"] for i in items(b, 15)]
            if OPTION not in tags and not (GARDER_SANS_TAG and not tags):
                continue
            jour, slot = divmod(b["p"], ppj)
            fin = min(slot + b["d"] - 1, len(heures) - 1)
            notes = [i.get("str", "") for i in items(b, 5)]
            cours.append({
                "date": (lundi1 + timedelta(weeks=w - 1, days=jour)).isoformat(),
                "debut": heures[slot]["Debut"].replace("h", ":"),
                "fin": (heures[fin].get("Fin") or heures[fin]["Debut"]).replace("h", ":"),
                "matiere": next((i["L"] for i in items(b, 0)), "") or next(iter(notes), ""),
                "type": next((i["L"] for i in items(b, 7)), ""),
                "profs": [i["L"] for i in items(b, 1)],
                "salles": [i["L"] for i in items(b, 3)],
                "note": ", ".join(n for n in notes if n and not re.fullmatch(r"\d\d-\d\d", n)),
                "couleur": b.get("co", "#888888"),
                # "pass" : réservé aux passerelles ; "sans" : aucune option indiquée
                "etiquette": "sans" if not tags else "pass" if all("PASS" in t for t in tags) else "",
                "annule": bool(b.get("estAnnule")),
            })
    cours.sort(key=lambda c: (c["date"], c["debut"]))
    return {"formation": FORMATION, "option": OPTION.replace("MA1 TL - ", ""),
            "maj": datetime.now(ZoneInfo("Europe/Brussels")).strftime("%d/%m/%Y %Hh%M"), "cours": cours}


def ics(data):
    def esc(t):
        return t.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    lignes = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//heh-horaire//FR",
              "X-WR-CALNAME:HEH " + esc(data["option"]), "X-WR-TIMEZONE:Europe/Brussels"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for c in data["cours"]:
        d = c["date"].replace("-", "")
        uid = hashlib.md5(f"{c['date']}{c['debut']}{c['matiere']}".encode()).hexdigest()
        desc = " · ".join(x for x in [c["type"], ", ".join(c["profs"]), c["note"]] if x)
        lignes += ["BEGIN:VEVENT", f"UID:{uid}@heh-horaire", f"DTSTAMP:{stamp}",
                   f"DTSTART;TZID=Europe/Brussels:{d}T{c['debut'].replace(':', '')}00",
                   f"DTEND;TZID=Europe/Brussels:{d}T{c['fin'].replace(':', '')}00",
                   f"SUMMARY:{esc(c['matiere'])}", f"LOCATION:{esc(', '.join(c['salles']))}",
                   f"DESCRIPTION:{esc(desc)}", "END:VEVENT"]
    lignes.append("END:VCALENDAR")
    return "\r\n".join(lignes) + "\r\n"


if __name__ == "__main__":
    import sys
    if "--page" in sys.argv:   # régénère juste la page depuis horaire.json (dev du template)
        data = json.load(open(os.path.join(ICI, "horaire.json"), encoding="utf-8"))
    else:
        data = recuperer()
    with open(os.path.join(ICI, "horaire.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(ICI, "horaire.ics"), "w", encoding="utf-8", newline="") as f:
        f.write(ics(data))
    gabarit = open(os.path.join(ICI, "template.html"), encoding="utf-8").read()
    page = gabarit.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
    with open(os.path.join(ICI, "index.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html>\n<html lang="fr">\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                + page + "\n</html>\n")
    print(f"{len(data['cours'])} cours -> index.html, horaire.ics, horaire.json")
