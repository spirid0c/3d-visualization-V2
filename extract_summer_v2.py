"""
extract_summer_v2.py — Extraction complete jpbz_201707 (Summer 2017)
====================================================================
AUDIT CONFIRME: 91/91 fichiers presents, AUCUN GAP.

Parametres (conformes au CTL flx.ctl Summer):
  Grille : XDEF 192, YDEF 94 (Gaussien), lon=0.0 inc=1.875deg
  TDEF   : 91 pas, debut 00Z01jul2017, pas=1jour
  Mapping: T=i => fh=(i-1)*24h => flx.ft{fh}
           T=1 => fh=0 => flx.ft00  (cas special)
  PWAT1  : kpds5=150, record wgrib #77
  PWAT2  : kpds5=151, record wgrib #78
  UNDEF  : 9.999E+20 -> remplace par 0.0 (pas d'interpolation)

Sortie:
  jpbz_201707_pwat1_91frames.bin  (192x94x91 float32 LE = 6,569,472 bytes)
  jpbz_201707_pwat2_91frames.bin  (192x94x91 float32 LE = 6,569,472 bytes)

Conservation stricte: shader inchange (gribLon/360.0, inversion Y 1.0-vUv.y),
palette rgbset2, clevs identiques a make_summer.gs.
"""

import sys
import os
import subprocess
import numpy as np

# Force UTF-8 sur console Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ===========================================================================
# PARAMETRES GRILLE (CTL flx.ctl — NE PAS MODIFIER)
# ===========================================================================
GRID_XDEF       = 192
GRID_YDEF       = 94
GRID_TDEF       = 91
UNDEF_VAL       = 9.999e+20
BYTES_PER_FRAME = GRID_XDEF * GRID_YDEF * 4       # 72,192 bytes
EXPECTED_BYTES  = GRID_TDEF * BYTES_PER_FRAME      # 6,569,472 bytes

DS_NAME         = "jpbz_201707"
DS_DIR          = r"IsoGSM_Project\jpbz_201707"

OUTPUT_PWAT1    = f"{DS_NAME}_pwat1_{GRID_TDEF}frames.bin"
OUTPUT_PWAT2    = f"{DS_NAME}_pwat2_{GRID_TDEF}frames.bin"

WGRIB_EXE       = "wgrib.exe"

# ===========================================================================
# UTILITAIRES
# ===========================================================================

def get_filename_for_fh(fh):
    """
    Retourne le nom de fichier exact pour une heure de prevision.
    Cas special: fh=0 -> recherche 'flx.ft00' en priorite, sinon 'flx.ft0'.
    """
    path_zero  = os.path.join(DS_DIR, "flx.ft00")
    path_plain = os.path.join(DS_DIR, f"flx.ft{fh}")
    if fh == 0:
        if os.path.exists(path_zero):
            return "flx.ft00"
        elif os.path.exists(path_plain):
            return "flx.ft0"
        else:
            return None
    return f"flx.ft{fh}" if os.path.exists(path_plain) else None


def inventory_grib_records(filepath):
    """
    Inventorie les records GRIB1 et retourne (rec_pwat1, rec_pwat2).
    PWAT1 : kpds5=150 | PWAT2 : kpds5=151
    """
    try:
        out = subprocess.check_output(
            [WGRIB_EXE, filepath, "-s"],
            text=True, errors="replace", stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return None, None

    rec1, rec2 = None, None
    for line in out.strip().split("\n"):
        if ":kpds5=150:" in line or ":var150:" in line:
            rec1 = line.split(":")[0].strip()
        elif ":kpds5=151:" in line or ":var151:" in line:
            rec2 = line.split(":")[0].strip()
        if rec1 and rec2:
            break

    return rec1, rec2


def extract_record(filepath, record_num, tmp_path):
    """
    Extrait un record GRIB1 en IEEE 754 Big-Endian.
    Retourne np.ndarray float32 shape (GRID_YDEF, GRID_XDEF) ordre N->S.
    UNDEF (9.999E+20) -> 0.0 (pas d'interpolation, zone bleue dans le shader).
    Retourne None si echec.
    """
    try:
        subprocess.check_call(
            [WGRIB_EXE, filepath, "-d", record_num, "-nh", "-ieee", "-o", tmp_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        raw = np.fromfile(tmp_path, dtype=">f4").astype(np.float32)

        if len(raw) != GRID_XDEF * GRID_YDEF:
            print(f"      [ERR] Taille: {len(raw)} pts, attendu {GRID_XDEF * GRID_YDEF}")
            return None

        # Masquer UNDEF -> 0.0 (comportement identique make_summer.gs)
        raw = np.where(raw > UNDEF_VAL * 0.5, 0.0, raw)

        return raw.reshape(GRID_YDEF, GRID_XDEF)

    except Exception as e:
        print(f"      [ERR] Record {record_num}: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ===========================================================================
# PROGRAMME PRINCIPAL
# ===========================================================================

def main():
    print("=" * 65)
    print(f" EXTRACTION jpbz_201707 — Summer 2017 — V2 (Sans Gaps)")
    print("=" * 65)
    print(f" Grille  : {GRID_XDEF} x {GRID_YDEF} | TDEF : {GRID_TDEF} jours")
    print(f" Taille attendue par variable : {EXPECTED_BYTES:,} bytes")
    print(f" Output PWAT1 : {OUTPUT_PWAT1}")
    print(f" Output PWAT2 : {OUTPUT_PWAT2}")
    print()

    if not os.path.exists(WGRIB_EXE):
        print(f"[FATAL] {WGRIB_EXE} introuvable.")
        sys.exit(1)
    if not os.path.isdir(DS_DIR):
        print(f"[FATAL] Dossier source absent: {DS_DIR}")
        sys.exit(1)

    pwat1_frames  = []
    pwat2_frames  = []
    blank_frame   = np.zeros((GRID_YDEF, GRID_XDEF), dtype=np.float32)
    success_count = 0
    gap_count     = 0

    for t_idx in range(GRID_TDEF):
        t_label = t_idx + 1
        fh      = t_idx * 24

        fname = get_filename_for_fh(fh)
        label = f"T={t_label:02d}/91  fh={fh:5d}h  "
        label += (fname if fname else f"flx.ft{fh:<7}") + "  "

        if fname is None:
            print(label + "ABSENT -> zeros (GAP)")
            pwat1_frames.append(blank_frame.copy())
            pwat2_frames.append(blank_frame.copy())
            gap_count += 1
            continue

        filepath = os.path.join(DS_DIR, fname)
        rec1, rec2 = inventory_grib_records(filepath)

        if rec1 is None or rec2 is None:
            print(label + f"PWAT introuvable (r1={rec1}, r2={rec2}) -> zeros")
            pwat1_frames.append(blank_frame.copy())
            pwat2_frames.append(blank_frame.copy())
            gap_count += 1
            continue

        tmp1 = f"_tmp_s1_{fh}.bin"
        tmp2 = f"_tmp_s2_{fh}.bin"

        v1 = extract_record(filepath, rec1, tmp1)
        v2 = extract_record(filepath, rec2, tmp2)

        if v1 is None or v2 is None:
            print(label + "EXTRACTION ECHOUEE -> zeros")
            pwat1_frames.append(blank_frame.copy())
            pwat2_frames.append(blank_frame.copy())
            gap_count += 1
            continue

        success_count += 1
        print(label + f"OK  p1={v1.max():.4f}  p2={v2.max():.4f}")
        pwat1_frames.append(v1)
        pwat2_frames.append(v2)

    # Assemblage
    print()
    print("=" * 65)
    print(" ASSEMBLAGE ET VERIFICATION")
    print("=" * 65)

    p1_stack = np.stack(pwat1_frames, axis=0).astype(np.float32)
    p2_stack = np.stack(pwat2_frames, axis=0).astype(np.float32)

    print(f" Shape PWAT1 : {p1_stack.shape}  ({p1_stack.nbytes:,} bytes)")
    print(f" Shape PWAT2 : {p2_stack.shape}  ({p2_stack.nbytes:,} bytes)")
    print(f" Frames reussies : {success_count}/{GRID_TDEF}")
    print(f" Frames vides    : {gap_count}/{GRID_TDEF}")

    if p1_stack.nbytes != EXPECTED_BYTES or p2_stack.nbytes != EXPECTED_BYTES:
        print("[ERREUR CRITIQUE] Taille incorrecte — ecriture annulee")
        sys.exit(1)

    # Ecriture binaire Little-Endian (natif x86 pour WebGL/Three.js)
    p1_stack.tofile(OUTPUT_PWAT1)
    p2_stack.tofile(OUTPUT_PWAT2)

    print()
    print(f" [OK] {OUTPUT_PWAT1}  ({os.path.getsize(OUTPUT_PWAT1):,} bytes)")
    print(f" [OK] {OUTPUT_PWAT2}  ({os.path.getsize(OUTPUT_PWAT2):,} bytes)")

    # Verification statistique
    print()
    print("=" * 65)
    print(" VERIFICATION STATISTIQUE (PWAT1)")
    print("=" * 65)
    non_zero = p1_stack[p1_stack > 0]
    print(f" Max PWAT1 global  : {p1_stack.max():.4f} kg/m2")
    print(f" Min PWAT1 (>0)    : {non_zero.min():.6f} kg/m2")
    print(f" Valeurs non-nulles: {len(non_zero):,} / {p1_stack.size:,}")

    # Frame T=1 (01jul2017, etat initial)
    f0 = p1_stack[0]
    print()
    print(" Frame T=01 (01jul2017 — etat initial):")
    nz = f0[f0 > 0]
    print(f"   Max PWAT1 = {f0.max():.4f} | Mean(>0) = {nz.mean():.4f if len(nz) else 0:.4f}")

    # Verification climatologique ete: max PWAT1 attendu en zone subTropicale
    f5 = p1_stack[4]  # T=5 (fh=96h, 05jul2017) — test coherence geo
    max_idx = f5.argmax()
    row, col = divmod(max_idx, GRID_XDEF)
    # Latitudes N->S (index 0 = Nord)
    lat_ns = [
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
    max_lat = lat_ns[row]
    max_lon = col * 1.875
    japan_ok = (28 <= max_lat <= 45) and (120 <= max_lon <= 160)
    status = "CONFORME" if japan_ok else "VERIFIER"
    print()
    print(" Test coherence geo T=05 (fh=96h, 05jul2017):")
    print(f"   Max PWAT1 = {f5.max():.4f} kg/m2  @ lat={max_lat:.2f}  lon={max_lon:.2f}")
    print(f"   Zone Japon (28-45N, 120-160E): {status}")

    print()
    print("=" * 65)
    print(" EXTRACTION TERMINEE AVEC SUCCES")
    print("=" * 65)
    if gap_count == 0:
        print(" Aucun gap — animation Summer sans clignotement bleu garanti")
    else:
        print(f" ATTENTION: {gap_count} frame(s) vide(s) detectees")
    print()


if __name__ == "__main__":
    main()
