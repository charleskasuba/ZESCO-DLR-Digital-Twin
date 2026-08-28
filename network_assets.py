"""
ZESCO DLR Digital Twin - Real Network Asset Registry
=====================================================
Reflects real ZESCO transmission assets so the digital twin operates
on actual conductors and line segments rather than a generic lab rig.

Data sources:
    - Conductor specs (ACSR Bison / Wolf / Lynx / Dog) from BS 215 pt 2
      data sheets: overall diameter, DC resistance @20C, rated ampacity.
    - Line-segment registry derived from ZESCO 330 kV & 66 kV line
      inventories (length, conductor, tower count, commissioning year).
"""

import math

# ----------------------------------------------------------------------
# Conductor specifications
# ----------------------------------------------------------------------
# Fields: code, area_mm2, dia_mm, R20_per_m (ohm/km), ampacity_A (rated),
#         max_temp_C (IEEE-typical thermal limit for the asset class)
CONDUCTORS = {
    # Code name: (nominal area mm2, overall dia mm, R DC @20C ohm/km, rated ampacity A, max temp C)
    "Bison": {"area_mm2": 431.3, "dia_mm": 27.00, "r_per_km": 0.07571, "ampacity": 595, "max_temp": 75.0},
    "Wolf":  {"area_mm2": 194.9, "dia_mm": 18.13, "r_per_km": 0.18280, "ampacity": 355, "max_temp": 75.0},
    "Lynx":  {"area_mm2": 226.2, "dia_mm": 19.53, "r_per_km": 0.15760, "ampacity": 386, "max_temp": 75.0},
    "Dog":   {"area_mm2": 118.5, "dia_mm": 14.15, "r_per_km": 0.27330, "ampacity": 280, "max_temp": 75.0},
}


def conductor(name: str) -> dict:
    """Return a copy of the conductor specification by code name."""
    if name not in CONDUCTORS:
        raise KeyError(f"Unknown conductor: {name}")
    return dict(CONDUCTORS[name])


def conductor_names() -> list:
    """Alphabetical list of available conductor code names."""
    return sorted(CONDUCTORS.keys())


# ----------------------------------------------------------------------
# Line-segment registry (330 kV)
# ----------------------------------------------------------------------
# Fields: id, name, voltage_kv, length_km, conductor, towers,
#         commissioned (year), builder, notes
LINES_330KV = [
    {"id": "kb_lh1",  "name": "Kariba - Leopard's Hill 1", "voltage_kv": 330, "length_km": 122.0, "conductor": "Bison", "towers": 286, "commissioned": 1960, "builder": "Power Lines", "notes": ""},
    {"id": "kb_lh2",  "name": "Kariba - Leopard's Hill 2", "voltage_kv": 330, "length_km": 122.0, "conductor": "Bison", "towers": 285, "commissioned": 1965, "builder": "Power Lines", "notes": ""},
    {"id": "kar_s1",  "name": "Kariba - Kariba South 1",  "voltage_kv": 330, "length_km": 3.0,   "conductor": "Bison", "towers": 5,   "commissioned": 1960, "builder": "Power Lines", "notes": ""},
    {"id": "kar_s2",  "name": "Kariba - Kariba South 2",  "voltage_kv": 330, "length_km": 3.0,   "conductor": "Bison", "towers": 5,   "commissioned": 1965, "builder": "Power Lines", "notes": ""},
    {"id": "kar_kfw", "name": "Kariba - Kafue West",      "voltage_kv": 330, "length_km": 130.0, "conductor": "Bison", "towers": 315, "commissioned": 2015, "builder": "Sinohydro", "notes": ""},
    {"id": "kfg_lh1", "name": "Kafue Gorge - Leopard's Hill 1", "voltage_kv": 330, "length_km": 47.0, "conductor": "Bison", "towers": 111, "commissioned": 1970, "builder": "Energoinvest", "notes": ""},
    {"id": "kfg_lh2", "name": "Kafue Gorge - Leopard's Hill 2", "voltage_kv": 330, "length_km": 47.0, "conductor": "Bison", "towers": 109, "commissioned": 1970, "builder": "Energoinvest", "notes": ""},
    {"id": "kfg_kfw", "name": "Kafue Gorge - Kafue West", "voltage_kv": 330, "length_km": 42.5, "conductor": "Bison", "towers": 84,  "commissioned": 1977, "builder": "Power Lines", "notes": "Steel lattice, Guyed"},
    {"id": "kfw_kt",   "name": "Kafue West - Kafue Town", "voltage_kv": 330, "length_km": 7.0,   "conductor": "Bison", "towers": 17,  "commissioned": None, "builder": "", "notes": "Steel lattice, Guyed"},
    {"id": "kfw_lh",   "name": "Kafue West - Leopard's Hill", "voltage_kv": 330, "length_km": 52.5, "conductor": "Bison", "towers": 123, "commissioned": 1974, "builder": "Power Lines", "notes": "Steel lattice, Guyed"},
    {"id": "leof_kit1", "name": "Leopard's Hill - Kabwe 1", "voltage_kv": 330, "length_km": 197.0, "conductor": "Bison", "towers": 217, "commissioned": 1960, "builder": "Power Lines", "notes": ""},
    {"id": "leof_kit2", "name": "Leopard's Hill - Kabwe 2", "voltage_kv": 330, "length_km": 197.0, "conductor": "Bison", "towers": 217, "commissioned": 1965, "builder": "Power Lines", "notes": ""},
    {"id": "leof_kit3", "name": "Leopard's Hill - Kabwe 3", "voltage_kv": 330, "length_km": 197.0, "conductor": "Bison", "towers": 217, "commissioned": 1972, "builder": "Power Lines", "notes": "Steel lattice, Guyed"},
    {"id": "lw_nam2",  "name": "Lusaka West - Nambala 2 (Pending Commissioning)", "voltage_kv": 330, "length_km": 145.0, "conductor": "Bison", "towers": 298, "commissioned": 2015, "builder": "KEC", "notes": "Double Circuit, Not Commissioned"},
    {"id": "lw_nam1",  "name": "Lusaka West - Nambala 1", "voltage_kv": 330, "length_km": 145.0, "conductor": "Bison", "towers": 298, "commissioned": 2015, "builder": "KEC", "notes": ""},
    {"id": "lw_kfw",   "name": "Lusaka West - Kafue West", "voltage_kv": 330, "length_km": 44.0, "conductor": "Bison", "towers": 98,  "commissioned": 2003, "builder": "ABB", "notes": "Steel lattice, Guyed"},
    {"id": "nam_kal2", "name": "Nambala - Kalumbila 2", "voltage_kv": 330, "length_km": 394.0, "conductor": "Bison", "towers": 894, "commissioned": 2016, "builder": "Kalpataru", "notes": "Double Circuit"},
    {"id": "nam_kal1", "name": "Nambala - Kalumbila 1", "voltage_kv": 330, "length_km": 394.0, "conductor": "Bison", "towers": 894, "commissioned": 2016, "builder": "Kalpataru", "notes": ""},
    {"id": "kabwe_kit2", "name": "Kabwe - Kitwe 2", "voltage_kv": 330, "length_km": 211.0, "conductor": "Bison", "towers": 520, "commissioned": 1972, "builder": "", "notes": ""},
    {"id": "kabwe_kit3", "name": "Kabwe - Kitwe 3", "voltage_kv": 330, "length_km": 211.0, "conductor": "Bison", "towers": 520, "commissioned": 1983, "builder": "", "notes": "Steel lattice, Guyed"},
    {"id": "kabwe_lua1", "name": "Kabwe - Luano 1", "voltage_kv": 330, "length_km": 251.0, "conductor": "Bison", "towers": 565, "commissioned": 1960, "builder": "", "notes": ""},
    {"id": "kabwe_lua2", "name": "Kabwe - Luano 2", "voltage_kv": 330, "length_km": 251.0, "conductor": "Bison", "towers": 565, "commissioned": 1960, "builder": "", "notes": "Steel lattice, Guyed"},
    {"id": "kabwe_pen", "name": "Kabwe - Pensulo", "voltage_kv": 330, "length_km": 298.0, "conductor": "Bison", "towers": 664, "commissioned": 1960, "builder": "", "notes": ""},
    {"id": "pen_kas",  "name": "Pensulo - Kasama", "voltage_kv": 330, "length_km": 382.0, "conductor": "Bison", "towers": 0,   "commissioned": 2015, "builder": "TBEA", "notes": ""},
    {"id": "pen_mso",  "name": "Pensulo - Msoro", "voltage_kv": 330, "length_km": 204.0, "conductor": "Bison", "towers": 0,   "commissioned": 2015, "builder": "TBEA", "notes": ""},
    {"id": "mso_chip", "name": "Msoro - Chipata West", "voltage_kv": 330, "length_km": 74.0, "conductor": "Bison", "towers": 0,   "commissioned": 2015, "builder": "TBEA", "notes": ""},
    {"id": "muz_mmb",  "name": "Muzuma - Maamba", "voltage_kv": 330, "length_km": 46.0, "conductor": "Bison", "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "kwt_cha",  "name": "Kitwe - Chambishi", "voltage_kv": 330, "length_km": 25.0, "conductor": "Bison", "towers": 59,  "commissioned": 1990, "builder": "", "notes": ""},
    {"id": "cha_lua",  "name": "Chambishi - Luano", "voltage_kv": 330, "length_km": 15.0, "conductor": "Bison", "towers": 39,  "commissioned": 1990, "builder": "", "notes": ""},
    {"id": "kan_lum",  "name": "Kansanshi - Lumwana", "voltage_kv": 330, "length_km": 72.0, "conductor": "Bison", "towers": 171, "commissioned": 2007, "builder": "Kalpataru/Spencon", "notes": ""},
    {"id": "lua_kan",  "name": "Luano - Kansanshi", "voltage_kv": 330, "length_km": 198.0, "conductor": "Bison", "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "kgg_kgl",  "name": "Kafue Gorge - Kafue Gorge Lower", "voltage_kv": 330, "length_km": 7.4, "conductor": "Bison", "towers": 17, "commissioned": 2017, "builder": "Sinohydro", "notes": ""},
    {"id": "muz_kt",   "name": "Muzuma - Kafue Town", "voltage_kv": 330, "length_km": 189.2, "conductor": "Bison", "towers": 769, "commissioned": 1968, "builder": "Babcock", "notes": "220 kV orig, upgraded to 330 kV 2017"},
    {"id": "vf_muz",   "name": "Victoria Falls - Muzuma (Charged at 220 kV)", "voltage_kv": 330, "length_km": 159.2, "conductor": "Bison", "towers": 370, "commissioned": 1968, "builder": "Babcock", "notes": "220 kV orig, upgraded to 330 kV 2017"},
    {"id": "lum_kal",  "name": "Lumwana - Kalumbila", "voltage_kv": 330, "length_km": 67.0, "conductor": "Bison", "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
]


# ----------------------------------------------------------------------
# Line-segment registry (66 kV)
# ----------------------------------------------------------------------
LINES_66KV = [
    {"id": "mpk_kas", "name": "Mpika - Kasama",       "voltage_kv": 66, "length_km": 210.0, "conductor": "Wolf",   "towers": 786, "commissioned": None, "builder": "", "notes": ""},
    {"id": "lua_mba", "name": "Luano - Mbala",        "voltage_kv": 66, "length_km": 161.0, "conductor": "Wolf",   "towers": 614, "commissioned": None, "builder": "", "notes": ""},
    {"id": "mba_sum", "name": "Mbala - Sumbawanga",   "voltage_kv": 66, "length_km": 120.0, "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": "Steel mono pole"},
    {"id": "mba_lun", "name": "Mbala - Lunzua",       "voltage_kv": 66, "length_km": 25.0,  "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "lun_nkb", "name": "Lunzua - Nkamba Bay",  "voltage_kv": 66, "length_km": 136.0, "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "kas_ll1", "name": "Kasama - Luano 1",     "voltage_kv": 66, "length_km": 1.5,   "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "kas_ll2", "name": "Kasama - Luano 2",     "voltage_kv": 66, "length_km": 1.5,   "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "kas_lwg", "name": "Kasama - Luwingu",     "voltage_kv": 66, "length_km": 170.0, "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "ll_chi",  "name": "Luano - Chishimba",    "voltage_kv": 66, "length_km": 30.0,  "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "mpk_chn", "name": "Mpika - Chinsali",     "voltage_kv": 66, "length_km": 179.0, "conductor": "Wolf",   "towers": 682, "commissioned": None, "builder": "", "notes": ""},
    {"id": "lwg_chb", "name": "Luwingu - Chambasitu", "voltage_kv": 66, "length_km": 123.0, "conductor": "Wolf",   "towers": 461, "commissioned": None, "builder": "", "notes": ""},
    {"id": "chb_mus", "name": "Chambasitu - Musonda T-Off", "voltage_kv": 66, "length_km": 40.0, "conductor": "Wolf", "towers": 0, "commissioned": None, "builder": "", "notes": ""},
    {"id": "mus_mns", "name": "Musonda T-Off - Mansa", "voltage_kv": 66, "length_km": 50.0, "conductor": "Wolf", "towers": 0, "commissioned": None, "builder": "", "notes": "Steel/Wood Poles"},
    {"id": "kaw_chb", "name": "Kawambwa - Chambasitu", "voltage_kv": 66, "length_km": 71.0, "conductor": "Wolf", "towers": 268, "commissioned": None, "builder": "", "notes": ""},
    {"id": "kaw_mbs", "name": "Kawambwa - Mbereshi",   "voltage_kv": 66, "length_km": 30.0, "conductor": "Wolf", "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "kaw_kt",   "name": "Kawambwa - Kawambwa Tea", "voltage_kv": 66, "length_km": 24.0, "conductor": "Wolf", "towers": 0, "commissioned": None, "builder": "", "notes": ""},
    {"id": "kt_mpr",   "name": "Kawambwa Tea - Mporokoso", "voltage_kv": 66, "length_km": 142.0, "conductor": "Wolf", "towers": 442, "commissioned": None, "builder": "", "notes": ""},
    {"id": "chn_iso",  "name": "Chinsali - Isoka",    "voltage_kv": 66, "length_km": 82.0,  "conductor": "Wolf",   "towers": 306, "commissioned": None, "builder": "", "notes": ""},
    {"id": "iso_nkn",  "name": "Isoka - Nakonde",     "voltage_kv": 66, "length_km": 107.0, "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "pen_mpk",  "name": "Pensulo - Mpika",     "voltage_kv": 66, "length_km": 197.0, "conductor": "Wolf",   "towers": 789, "commissioned": None, "builder": "", "notes": ""},
    {"id": "pen_lsw",  "name": "Pensulo - Lusiwasi",  "voltage_kv": 66, "length_km": 90.0,  "conductor": "Wolf",   "towers": 350, "commissioned": None, "builder": "", "notes": ""},
    {"id": "pen_srj",  "name": "Pensulo - Serenje",   "voltage_kv": 66, "length_km": 34.0,  "conductor": "Wolf",   "towers": 133, "commissioned": None, "builder": "", "notes": ""},
    {"id": "srj_mku",  "name": "Serenje - Mkushi",    "voltage_kv": 66, "length_km": 0.0,   "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": "Wood Poles"},
    {"id": "pen_kn",   "name": "Pensulo - Kanona",    "voltage_kv": 66, "length_km": 21.0,  "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "kn_lsw",   "name": "Kanona - Lusiwasi",   "voltage_kv": 66, "length_km": 69.0,  "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "kn_mpt",   "name": "Kanona - Mupepetwe",  "voltage_kv": 66, "length_km": 21.0,  "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": "Wood Poles"},
    {"id": "lsw_mso1", "name": "Lusiwasi - Msoro 1",  "voltage_kv": 66, "length_km": 115.0, "conductor": "Wolf",   "towers": 500, "commissioned": 1976, "builder": "Energoinvest", "notes": ""},
    {"id": "lsw_mso2", "name": "Lusiwasi - Msoro 2",  "voltage_kv": 66, "length_km": 115.0, "conductor": "Wolf",   "towers": 500, "commissioned": 1976, "builder": "Energoinvest", "notes": ""},
    {"id": "lua_slz",  "name": "Luano - Solwezi",     "voltage_kv": 66, "length_km": 189.0, "conductor": "Lynx",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "slz_ksp",  "name": "Solwezi - Kasempa",   "voltage_kv": 66, "length_km": 200.0, "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "cha_ndk",  "name": "Chambishi - Ndeke",   "voltage_kv": 66, "length_km": 25.0,  "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "cha_mwb",  "name": "Chambishi - Mwambashi", "voltage_kv": 66, "length_km": 13.0, "conductor": "Wolf", "towers": 0, "commissioned": None, "builder": "", "notes": ""},
    {"id": "mwb_sw",   "name": "Mwambashi - New Scaw", "voltage_kv": 66, "length_km": 25.0,  "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "nke_lng",  "name": "Nkana East - Luangwa", "voltage_kv": 66, "length_km": 11.0,  "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "mps_bm",   "name": "Maposa - Bwana Mkubwa", "voltage_kv": 66, "length_km": 42.0, "conductor": "Wolf", "towers": 0, "commissioned": None, "builder": "", "notes": "Steel Mono pole"},
    {"id": "mps_mul",  "name": "Maposa - Mushili",    "voltage_kv": 66, "length_km": 30.0,  "conductor": "Wolf",   "towers": 0,   "commissioned": None, "builder": "", "notes": "Steel Mono pole"},
    {"id": "mul_bm",   "name": "Mushili - Bwana Mkubwa", "voltage_kv": 66, "length_km": 9.0, "conductor": "Wolf", "towers": 0, "commissioned": None, "builder": "", "notes": "Steel Mono pole"},
    {"id": "mso_mfw",  "name": "Msoro - Mfuwe",       "voltage_kv": 66, "length_km": 65.0,  "conductor": "Dog",    "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "mso_azl",  "name": "Msoro - Azele",       "voltage_kv": 66, "length_km": 60.0,  "conductor": "Dog",    "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
    {"id": "vf_kzg",   "name": "Victoria Falls - Kazungula", "voltage_kv": 66, "length_km": 82.0, "conductor": "Dog", "towers": 372, "commissioned": 1973, "builder": "James Scoti", "notes": ""},
    {"id": "kzg_ses",  "name": "Kazungula - Sesheke",  "voltage_kv": 66, "length_km": 126.0, "conductor": "Dog", "towers": 638, "commissioned": 1973, "builder": "James Scoti", "notes": ""},
    {"id": "kzg_ksn",  "name": "Kazungula - Kasane",   "voltage_kv": 66, "length_km": 12.0,  "conductor": "Dog",    "towers": 10,  "commissioned": None, "builder": "", "notes": ""},
    {"id": "ses_sng",  "name": "Sesheke - Senanga",    "voltage_kv": 66, "length_km": 230.0, "conductor": "Dog", "towers": 840, "commissioned": 1973, "builder": "James Scoti", "notes": ""},
    {"id": "sng_mng",  "name": "Senanga - Mongu",      "voltage_kv": 66, "length_km": 105.0, "conductor": "Dog", "towers": 442, "commissioned": 1973, "builder": "James Scoti", "notes": ""},
    {"id": "mng_kma",  "name": "Mongu - Kaoma",        "voltage_kv": 66, "length_km": 190.0, "conductor": "Dog",    "towers": 0,   "commissioned": None, "builder": "", "notes": ""},
]


# ----------------------------------------------------------------------
# Accessors
# ----------------------------------------------------------------------

def all_lines() -> list:
    """All registered line segments (330 kV + 66 kV)."""
    return LINES_330KV + LINES_66KV


def lines_by_voltage(voltage_kv: int) -> list:
    """Lines at a given nominal voltage."""
    return [ln for ln in all_lines() if ln["voltage_kv"] == voltage_kv]


def line(line_id: str) -> dict:
    """Look up a single line segment by id."""
    for ln in all_lines():
        if ln["id"] == line_id:
            return dict(ln)
    raise KeyError(f"Unknown line: {line_id}")


def average_span_m(line_: dict) -> float:
    """Approximate average tower span (m) from length and tower count."""
    towers = line_.get("towers") or 0
    length_m = line_["length_km"] * 1000.0
    if towers >= 2:
        return length_m / max(towers - 1, 1)
    return 300.0  # sensible default


def builds_twin(line_: dict, engine=None, span_m: float = None):
    """Build a WireDigitalTwin calibrated to a real line segment.

    Returns (twin_instance, conductor_spec). If `engine` is provided it is
    not modified; otherwise a new WireDigitalTwin is returned sized to the
    real conductor resistance and rated ampacity.
    """
    spec = conductor(line_["conductor"])
    span = span_m or average_span_m(line_)
    # Engine uses resistance per unit length (ohm/m). Convert the published
    # ohm/km value to ohm/m.
    r_ref = spec["r_per_km"] / 1000.0
    twin_kw = dict(
        R_ref=r_ref,
        alpha=0.004,
        max_temp=spec["max_temp"],
        emissivity=0.5,
        static_rating=spec["ampacity"],
        span_length=span,
        diameter_m=spec["dia_mm"] / 1000.0,
    )
    return twin_kw, spec
