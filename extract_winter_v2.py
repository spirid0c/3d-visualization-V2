"""
extract_winter_v2.py — Extraction complete jpbz_1_2018 (Winter 2018)
=====================================================================
AUDIT CONFIRME: 91/91 fichiers presents, AUCUN GAP.

Parametres (conformes au CTL flx.ctl):
  Grille : XDEF 192, YDEF 94 (Gaussien), lon=0.0 inc=1.875deg
  TDEF   : 91 pas, debut 00Z01jan2018, pas=1jour
  Mapping: T=i => fh=(i-1)*24h => flx.ft{fh}
           T=1 => fh=0 => flx.ft00  (cas special: ft0 -> ft00)
  PWAT1  : kpds5=150, record wgrib #77
  PWAT2  : kpds5=151, record wgrib #78
  UNDEF  : 9.999E+20 -> remplace par 0.0 (pas d'interpolation)

Sortie:
  jpbz_1_2018_pwat1_91frames.bin  (192x94x91 float32 LE = 6,569,472 bytes)
  jpbz_1_2018_pwat2_91frames.bin  (192x94x91 float32 LE = 6,569,472 bytes)

Conservation stricte: shader inchange (offset +0.75, inversion Y), palette rgbset2.
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
# PARAMETRES (NE PAS MODIFIER — valides par nos tests precedents)
# ===========================================================================
GRID_XDEF         = 192          # Longitudes
GRID_YDEF         = 94           # Latitudes Gaussiennes
GRID_TDEF         = 91           # 91 jours de simulation
UNDEF_VAL         = 9.999e+20    # Valeur UNDEF du CTL
BYTES_PER_FRAME   = GRID_XDEF * GRID_YDEF * 4          # 72,192 octets
EXPECTED_BYTES    = GRID_TDEF * BYTES_PER_FRAME         # 6,569,472 octets

DS_NAME           = "jpbz_1_2018"
DS_DIR            = r"IsoGSM_Project\jpbz_1_2018"

OUTPUT_PWAT1      = f"{DS_NAME}_pwat1_{GRID_TDEF}frames.bin"
OUTPUT_PWAT2      = f"{DS_NAME}_pwat2_{GRID_TDEF}frames.bin"

WGRIB_EXE         = "wgrib.exe"

# ===========================================================================
# UTILITAIRES
# ===========================================================================

def get_filename_for_fh(fh):
    """
    Retourne le nom de fichier exact pour une heure de prevision.
    Cas special: fh=0 -> 'flx.ft00' (padding a 2 chiffres dans le CTL initial).
    Tous les autres: 'flx.ft{fh}' (ex: 'flx.ft24', 'flx.ft2160').
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
    Identification par kpds5=150 (PWAT1) et kpds5=151 (PWAT2).
    Retourne (None, None) en cas d'echec.
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
    Les valeurs UNDEF (9.999E+20) sont remplacees par 0.0.
    Retourne None si echec.
    """
    try:
        subprocess.check_call(
            [WGRIB_EXE, filepath, "-d", record_num, "-nh", "-ieee", "-o", tmp_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        raw = np.fromfile(tmp_path, dtype=">f4").astype(np.float32)

        if len(raw) != GRID_XDEF * GRID_YDEF:
            print(f"      [ERR] Taille incorrecte: {len(raw)} pts, attendu {GRID_XDEF * GRID_YDEF}")
            return None

        # Masquer UNDEF -> 0.0 (zone bleue fond dans le shader — comportement attendu)
        raw = np.where(raw > UNDEF_VAL * 0.5, 0.0, raw)

        return raw.reshape(GRID_YDEF, GRID_XDEF)

    except Exception as e:
        print(f"      [ERR] Extraction record {record_num}: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ===========================================================================
# PROGRAMME PRINCIPAL
# ===========================================================================

def main():
    print("=" * 65)
    print(f" EXTRACTION jpbz_1_2018 — Winter 2018 — V2 (Sans Gaps)")
    print("=" * 65)
    print(f" Grille : {GRID_XDEF} x {GRID_YDEF} | TDEF : {GRID_TDEF} jours")
    print(f" Taille attendue par variable : {EXPECTED_BYTES:,} bytes")
    print(f" Output PWAT1 : {OUTPUT_PWAT1}")
    print(f" Output PWAT2 : {OUTPUT_PWAT2}")
    print()

    # Verifier wgrib.exe
    if not os.path.exists(WGRIB_EXE):
        print(f"[FATAL] {WGRIB_EXE} introuvable. Execution depuis le bon repertoire?")
        sys.exit(1)

    # Verifier le dossier source
    if not os.path.isdir(DS_DIR):
        print(f"[FATAL] Dossier source absent: {DS_DIR}")
        sys.exit(1)

    pwat1_frames = []
    pwat2_frames = []
    blank_frame  = np.zeros((GRID_YDEF, GRID_XDEF), dtype=np.float32)
    success_count = 0
    gap_count     = 0

    for t_idx in range(GRID_TDEF):
        t_label = t_idx + 1                   # T GrADS (1-indexed)
        fh      = t_idx * 24                  # Forecast hour

        fname = get_filename_for_fh(fh)
        label = f"T={t_label:02d}/91  fh={fh:5d}h  "
        label += (fname if fname else f"flx.ft{fh:<6}") + "  "

        if fname is None:
            print(label + "ABSENT -> zeros (GAP)")
            pwat1_frames.append(blank_frame.copy())
            pwat2_frames.append(blank_frame.copy())
            gap_count += 1
            continue

        filepath = os.path.join(DS_DIR, fname)

        # Inventorier les records PWAT1 / PWAT2
        rec1, rec2 = inventory_grib_records(filepath)

        if rec1 is None or rec2 is None:
            print(label + f"PWAT introuvable (r1={rec1}, r2={rec2}) -> zeros")
            pwat1_frames.append(blank_frame.copy())
            pwat2_frames.append(blank_frame.copy())
            gap_count += 1
            continue

        # Extraction
        tmp1 = f"_tmp_w1_{fh}.bin"
        tmp2 = f"_tmp_w2_{fh}.bin"

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

    # Ecriture binary Little-Endian (natif x86 pour WebGL/Three.js)
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
    print(f" Max valeur PWAT1 : {p1_stack.max():.4f} kg/m2")
    print(f" Min valeur PWAT1 (>0) : {non_zero.min():.6f} kg/m2")
    print(f" Valeurs non-nulles : {len(non_zero):,} / {p1_stack.size:,}")

    # Verification frame T=1 (fh=0, debut hiver)
    f0 = p1_stack[0]
    print()
    print(" Frame T=01 (01jan2018):")
    print(f"   Max PWAT1 = {f0.max():.4f} | Mean (>0) = {f0[f0>0].mean():.4f}")

    print()
    print("=" * 65)
    print(" EXTRACTION TERMINEE AVEC SUCCES")
    print("=" * 65)
    if gap_count == 0:
        print(" Aucun gap — animation Winter sans clignotement bleu garanti")
    else:
        print(f" ATTENTION: {gap_count} frame(s) vide(s) — clignotements possibles")
    print()


if __name__ == "__main__":
    main()
