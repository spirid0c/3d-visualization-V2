"""
audit_winter.py — Audit de la sequence temporelle jpbz_1_2018 (Winter 2018)
============================================================================
Verifie la presence de tous les fichiers necessaires pour couvrir 91 jours.
CTL: tdef 366 linear 00Z01jan2018 1dy
Simulation: T=1..91 => fh=(T-1)*24h => flx.ft{fh}
Special: flx.ft0 = flx.ft00 (initial file)
"""

import os
import sys

ds_dir = r"IsoGSM_Project\jpbz_1_2018"

# Construire le set des fh disponibles
available_fh = set()
file_map = {}  # fh -> nom de fichier reel

for f in os.listdir(ds_dir):
    # Accepter flx.ft0, flx.ft00, flx.ft24, flx.ft48, etc.
    if f.startswith("flx.ft"):
        suffix = f[6:]
        if suffix.isdigit():
            fh = int(suffix)
            available_fh.add(fh)
            file_map[fh] = f

print("=" * 65)
print(" AUDIT jpbz_1_2018 (Winter 2018)")
print("=" * 65)
print(f" CTL: tdef 366 linear 00Z01jan2018 1dy")
print(f" Simulation: 91 jours => T=1..91 => fh=0..2160h (pas=24h)")
print()
print(f" Fichiers flx.ft* detectes: {len(available_fh)}")
if available_fh:
    sorted_fh = sorted(available_fh)
    print(f" Range: fh={sorted_fh[0]}h -> fh={sorted_fh[-1]}h")
print()

# Verifier les 91 frames
gaps = []
present = []
for t in range(1, 92):
    fh = (t - 1) * 24
    if fh in available_fh:
        fpath = os.path.join(ds_dir, file_map[fh])
        size = os.path.getsize(fpath)
        present.append((t, fh, file_map[fh], size))
    else:
        gaps.append((t, fh))

print("=" * 65)
print(" GAPS DETECTES")
print("=" * 65)
if not gaps:
    print(" ✅ AUCUN GAP — sequence completement couverte (91/91)!")
else:
    print(f" ⚠️  {len(gaps)} frames manquantes sur 91:")
    for t, fh in gaps:
        print(f"    MANQUANT: T={t:02d}  fh={fh:5d}h  flx.ft{fh}")

print()
print("=" * 65)
print(" SEQUENCE COMPLETE T=1..91")
print("=" * 65)
for t in range(1, 92):
    fh = (t - 1) * 24
    if fh in available_fh:
        fpath = os.path.join(ds_dir, file_map[fh])
        size = os.path.getsize(fpath)
        print(f"  T={t:02d}  fh={fh:5d}h  {file_map[fh]:<12}  OK  {size:>10} bytes")
    else:
        print(f"  T={t:02d}  fh={fh:5d}h  flx.ft{fh:<6}  ABSENT  <-- GAP")

print()
print("=" * 65)
print(f" BILAN: {len(present)}/91 frames presentes | {len(gaps)}/91 manquantes")
print("=" * 65)

# Verifier aussi les fichiers hors sequence (fh non multiples de 24)
expected_fh = set((t - 1) * 24 for t in range(1, 92))
extra_fh = available_fh - expected_fh
if extra_fh:
    print()
    print(f" INFO: {len(extra_fh)} fichiers hors-sequence (non utilises):")
    for fh in sorted(extra_fh)[:10]:
        print(f"    flx.ft{fh}")
    if len(extra_fh) > 10:
        print(f"    ... et {len(extra_fh)-10} autres")
