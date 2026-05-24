#!/usr/bin/env bash
# Doppio click (Mac/Linux) o ./aggiorna_e_lancia.sh = aggiorna il codice dal
# git e rilancia lo script. Niente da imparare: 1 click e basta.
set -e
cd "$(dirname "$0")"
echo "=== Aggiorno il codice dal server git ==="
git pull origin main
echo
echo "=== Lancio lo scraper ==="
python3 run.py
echo
echo "=== Finito. Apri output/eventi.html nel browser e fai Ctrl+F5 ==="
