# Horaire HEH — MA1 Ingé ind., PASS Info IA & Big Data

Horaire HEH Planning filtré sur une option, lisible sur téléphone.
Rafraîchi chaque nuit par GitHub Actions, servi par GitHub Pages.

- `index.html` : la page (générée)
- `horaire.ics` : abonnement calendrier (Google Agenda > Autres agendas > À partir de l'URL)
- `fetch.py` : récupération (Hyperplanning, espace invités) — protocole repris d'[EzHoraire](https://github.com/Frybex/EzHoraire)

Changer d'option : modifier `OPTION` dans `fetch.py`. À chaque rentrée : modifier `BASE`.

Local :

```bash
pip install -r requirements.txt
python fetch.py
```
