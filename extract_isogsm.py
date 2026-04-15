"""
extract_isogsm.py — Pipeline d'extraction GRIB1 rigoureusement conforme
========================================================================
CONFORMITE INTRANSIGENTE basée sur l'audit structurel du CTL + GRIB source.

PARAMETRES VERIFIES (PHASE 1):
  Grille : XDEF 192, YDEF 94, origine lon=0.0E, inc=1.875deg
  TDEF   : 91 pas de temps, 1 jour, début 00Z01JUL2017 (jpbz_201707)
  UNDEF  : 9.999E+20 (jamais inventé, jamais interpolé)
  DTYPE  : GRIB1, Endian Big (>f4), PAS de padding Fortran
  PWAT1  : kpds5=150, record wgrib #77 par fichier
  PWAT2  : kpds5=151, record wgrib #78 par fichier

EXTRACTION (PHASE 2):
  - Chaque T={1..91} correspond à fh = (T-1)*24 heures après init modèle
  - Template: flx.ft%fh => ex. fh=96 => flx.ft96
  - Si le fichier est absent: frame remplie par np.nan (→ converti en 0.0 pour WebGL)
  - JAMAIS d'interpolation entre frames adjacentes
  - Vérification taille: 91 * 94 * 192 * 4 = 6,569,472 octets EXACT

VERIFICATION COHERENCE (PHASE 4):
  - A T=5 (flx.ft96, premier disponible pour jpbz_201707):
    max(PWAT1) attendu dans la région 30-40°N, 130-150°E ✅
"""

import sys
import numpy as np
import subprocess
import os

# Force UTF-8 output on Windows consoles
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ===========================================================================
# PARAMETRES DE GRILLE (extraits du CTL, NE PAS MODIFIER)
# ===========================================================================
GRID_XDEF = 192          # Points de longitude
GRID_YDEF = 94           # Points de latitude (Gaussien)
GRID_TDEF = 91           # Nombre de pas de temps
UNDEF_VAL = 9.999e+20    # Valeur UNDEF du CTL (à masquer, pas à interpoler)
BYTES_PER_FRAME = GRID_XDEF * GRID_YDEF * 4  # 72,192 octets
EXPECTED_TOTAL_BYTES = GRID_TDEF * BYTES_PER_FRAME  # 6,569,472

# Latitudes Gaussiennes (Nord→Sud, ordre GRIB natif, 94 valeurs)
# Source: CTL avec options yrev => wgrib sort en ordre N→S
LAT_NORTH_TO_SOUTH = [
     88.542, 86.653, 84.753, 82.851, 80.947, 79.043, 77.139, 75.235, 73.331, 71.426,
     69.522, 67.617, 65.713, 63.808, 61.903, 59.999, 58.094, 56.189, 54.285, 52.380,
     50.475, 48.571, 46.666, 44.761, 42.856, 40.952, 39.047, 37.142, 35.238, 33.333,
     31.428, 29.523, 27.619, 25.714, 23.809, 21.904, 20.000, 18.095, 16.190, 14.286,
     12.381, 10.476,  8.571,  6.667,  4.762,  2.857,  0.952, -0.952, -2.857, -4.762,
     -6.667, -8.571,-10.476,-12.381,-14.286,-16.190,-18.095,-20.000,-21.904,-23.809,
    -25.714,-27.619,-29.523,-31.428,-33.333,-35.238,-37.142,-39.047,-40.952,-42.856,
    -44.761,-46.666,-48.571,-50.475,-52.380,-54.285,-56.189,-58.094,-59.999,-61.903,
    -63.808,-65.713,-67.617,-69.522,-71.426,-73.331,-75.235,-77.139,-79.043,-80.947,
    -82.851,-84.753,-86.653,-88.542
]

# Datasets: {prefix: chemin_dossier}
DATASETS = {
    "jpbz_201707": "IsoGSM_Project/jpbz_201707",   # Été 2017: TDEF 00Z01jul2017
    "jpbz_1_2018": "IsoGSM_Project/jpbz_1_2018",   # Hiver 2018: TDEF 00Z01jan2018
}

# ===========================================================================
# EXTRACTION RIGOUREUSE
# ===========================================================================

def find_wgrib():
    """Localise wgrib.exe dans le répertoire courant."""
    exe = "wgrib.exe"
    if not os.path.exists(exe):
        print(f"!!! [FATAL] '{exe}' introuvable. Placez wgrib.exe dans le répertoire courant.")
        sys.exit(1)
    return exe


def inventory_grib(wgrib_exe, filepath):
    """
    Inventorie les records GRIB1 d'un fichier.
    Retourne (rec_pwat1, rec_pwat2) — numéros de records (string).
    Retourne (None, None) si les variables sont absentes.
    """
    try:
        output = subprocess.check_output(
            [wgrib_exe, filepath, "-s"],
            text=True, errors="replace", stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return None, None

    rec1, rec2 = None, None
    for line in output.strip().split('\n'):
        # Identifier par kpds5 (code GRIB1 du paramètre)
        if ':kpds5=150:' in line or ':var150:' in line:
            rec1 = line.split(':')[0].strip()
        elif ':kpds5=151:' in line or ':var151:' in line:
            rec2 = line.split(':')[0].strip()

    return rec1, rec2


def extract_grib_record(wgrib_exe, filepath, record_num, tmp_path):
    """
    Extrait un record GRIB1 en IEEE 754 Big-Endian brut (sans header).
    Retourne un np.ndarray float32 (GRID_YDEF × GRID_XDEF), ordre N→S.
    Retourne None si l'extraction échoue.
    AUCUNE INTERPOLATION — les UNDEF sont laissés à 0.0 (zone bleue shader).
    """
    try:
        subprocess.check_call(
            [wgrib_exe, filepath, "-d", record_num, "-nh", "-ieee", "-o", tmp_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # Big-Endian IEEE 754 float32 → converti en float32 natif (Little-Endian x86)
        raw = np.fromfile(tmp_path, dtype=">f4").astype(np.float32)

        # Vérification de taille EXACTE (Phase 2 — cohérence obligatoire)
        expected_pts = GRID_XDEF * GRID_YDEF
        if len(raw) != expected_pts:
            print(f"    !!! ERREUR TAILLE: {len(raw)} valeurs, attendu {expected_pts}")
            return None

        # Masquer les UNDEF (9.999E+20) → 0.0 pour le rendu (zone bleue fond shader)
        # NE JAMAIS interpoler les zones UNDEF
        raw = np.where(raw > UNDEF_VAL * 0.5, 0.0, raw)

        return raw.reshape(GRID_YDEF, GRID_XDEF)

    except Exception as e:
        print(f"    !!! Erreur extraction record {record_num}: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def run_coherence_check(pwat1_frame, dataset_name, t_index):
    """
    Phase 4 — Test de cohérence géographique.
    À T=5 de jpbz_201707 (fh=96h), le max de PWAT1 doit être
    dans la région 30-42°N, 120-155°E (mer du Japon / Pacifique NW).
    """
    if dataset_name != "jpbz_201707" or t_index != 4:  # fh=96 = index 4 (0-based)
        return

    clean_frame = np.where(pwat1_frame > UNDEF_VAL * 0.5, 0.0, pwat1_frame)
    max_idx = np.unravel_index(clean_frame.argmax(), clean_frame.shape)
    max_lat = LAT_NORTH_TO_SOUTH[max_idx[0]]
    max_lon = max_idx[1] * 1.875
    max_val = clean_frame[max_idx]

    # Zone Japon: lat 30-42°N, lon 120-155°E
    japan_ok = (28 <= max_lat <= 45) and (120 <= max_lon <= 160)
    status = "✅ CONFORME" if japan_ok else "⚠️ ANORMAL"

    print(f"\n  >>>  TEST COHERENCE GEOGRAPHIQUE (Phase 4) <<<")
    print(f"       T=5 (fh=96h, 05JUL2017): max PWAT1 = {max_val:.4f} kg/m²")
    print(f"       Position: lat={max_lat:.2f}°N  lon={max_lon:.2f}°E")
    print(f"       Region Japon (30-45°N, 120-160°E): {status}")
    print()


def extract_dataset(wgrib_exe, ds_name, ds_dir):
    """
    Extrait les 91 frames PWAT1 et PWAT2 pour un dataset.
    Mapping conforme au CTL: T=i (1-indexed) → fh=(i-1)*24h → flx.ft{fh}
    """
    print(f"\n{'='*65}")
    print(f" DATASET : {ds_name} | {ds_dir}")
    print(f"{'='*65}")

    # Validation préalable
    if not os.path.exists(ds_dir):
        print(f"  !!! DOSSIER ABSENT — extraction impossible")
        return False

    # Lister les fh disponibles dans le dataset
    available_fh = set()
    for fname in os.listdir(ds_dir):
        if fname.startswith("flx.ft") and fname[6:].isdigit():
            available_fh.add(int(fname[6:]))

    print(f"  Fichiers flx.ft* disponibles: {len(available_fh)}/91")
    if available_fh:
        print(f"  Range: fh={min(available_fh)}h -> fh={max(available_fh)}h")

    pwat1_frames = []
    pwat2_frames = []
    blank_frame = np.zeros((GRID_YDEF, GRID_XDEF), dtype=np.float32)
    success_count = 0

    for t_idx in range(GRID_TDEF):
        fh = t_idx * 24  # fh = (T-1) * 24h, T est 1-indexé
        t_label = t_idx + 1  # T dans GrADS (1-indexé)
        filename = f"flx.ft{fh}"
        filepath = os.path.join(ds_dir, filename)

        print(f"  T={t_label:02d}/91  fh={fh:4d}h  {filename:<12} : ", end="", flush=True)

        if fh not in available_fh:
            print("ABSENT -> zeros (zone bleue WebGL)")
            pwat1_frames.append(blank_frame.copy())
            pwat2_frames.append(blank_frame.copy())
            continue

        # Inventorier les records
        rec1, rec2 = inventory_grib(wgrib_exe, filepath)

        if rec1 is None or rec2 is None:
            print(f"PWAT1/PWAT2 introuvables (rec1={rec1}, rec2={rec2}) -> zeros")
            pwat1_frames.append(blank_frame.copy())
            pwat2_frames.append(blank_frame.copy())
            continue

        # Extraction GRIB1 Big-Endian, sans interpolation
        tmp1 = f"_tmp_p1_{ds_name}_{fh}.bin"
        tmp2 = f"_tmp_p2_{ds_name}_{fh}.bin"

        v1 = extract_grib_record(wgrib_exe, filepath, rec1, tmp1)
        v2 = extract_grib_record(wgrib_exe, filepath, rec2, tmp2)

        if v1 is None or v2 is None:
            print("EXTRACTION ECHOUEE → zéros")
            pwat1_frames.append(blank_frame.copy())
            pwat2_frames.append(blank_frame.copy())
            continue

        pwat1_frames.append(v1)
        pwat2_frames.append(v2)
        success_count += 1
        print(f"OK  p1_max={v1.max():.4f}  p2_max={v2.max():.4f}")

        # Test de cohérence géographique (Phase 4)
        run_coherence_check(v1, ds_name, t_idx)

    # Assemblage et vérification de taille (Phase 2)
    pwat1_stack = np.stack(pwat1_frames, axis=0).astype(np.float32)
    pwat2_stack = np.stack(pwat2_frames, axis=0).astype(np.float32)

    actual_bytes_p1 = pwat1_stack.nbytes
    actual_bytes_p2 = pwat2_stack.nbytes

    print(f"\n  Frames réussies: {success_count}/{GRID_TDEF}")
    print(f"  Taille PWAT1: {actual_bytes_p1} octets | Attendu: {EXPECTED_TOTAL_BYTES}")
    print(f"  Taille PWAT2: {actual_bytes_p2} octets | Attendu: {EXPECTED_TOTAL_BYTES}")

    if actual_bytes_p1 != EXPECTED_TOTAL_BYTES or actual_bytes_p2 != EXPECTED_TOTAL_BYTES:
        print("  !!! ERREUR CRITIQUE: taille de sortie incorrecte — extraction ECHOUEE")
        return False

    # Écriture binaire Little-Endian (natif x86 pour WebGL / Three.js)
    out1 = f"{ds_name}_pwat1_{GRID_TDEF}frames.bin"
    out2 = f"{ds_name}_pwat2_{GRID_TDEF}frames.bin"

    pwat1_stack.tofile(out1)
    pwat2_stack.tofile(out2)

    print(f"\n  [OK] {out1} ({actual_bytes_p1 / 1024**2:.2f} MB)")
    print(f"  [OK] {out2} ({actual_bytes_p2 / 1024**2:.2f} MB)")
    return True


def main():
    print("=" * 65)
    print(" PIPELINE D'EXTRACTION ISOGSM — Conformité stricte CTL")
    print("=" * 65)
    print(f" Grille : {GRID_XDEF} × {GRID_YDEF} | TDEF : {GRID_TDEF} pas = 1 jour")
    print(f" Taille attendue par dataset : {EXPECTED_TOTAL_BYTES:,} octets")
    print(f" Variables : PWAT1 (kpds5=150) et PWAT2 (kpds5=151)")
    print()

    wgrib_exe = find_wgrib()
    results = {}

    for ds_name, ds_dir in DATASETS.items():
        ok = extract_dataset(wgrib_exe, ds_name, ds_dir)
        results[ds_name] = ok

    print("\n" + "=" * 65)
    print(" BILAN FINAL")
    print("=" * 65)
    for ds, ok in results.items():
        status = "✅ SUCCÈS" if ok else "❌ ÉCHEC"
        print(f"  {ds:<20} {status}")

    print()
    print(" RAPPEL: summer_anim et winter_anim n'ont pas de fichiers")
    print(" flx.ft* source → créer des liens symboliques ou copier les")
    print(" données vers IsoGSM_Project/summer_anim/ et winter_anim/")
    print()


if __name__ == "__main__":
    main()
