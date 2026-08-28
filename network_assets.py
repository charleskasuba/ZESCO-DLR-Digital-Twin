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

# Substation coordinates (lat, lon) for key ZESCO nodes. Used to render
# each line segment's real corridor on the map. Approximate WGS84 points
# for the main 330 kV / 66 kV substations in Zambia.
SUBSTATIONS = {
    "Kabwe":        (-14.4440, 28.4450),
    "Kabwe Step":   (-14.4300, 28.4600),
    "Kabwe Stepdown": (-14.4300, 28.4600),
    "Kitwe":        (-12.8024, 28.2132),
    "Luano":        (-12.9000, 28.2500),
    "Pensulo":      (-13.1700, 30.0700),
    "Serenje":      (-13.2300, 30.2300),
    "Kasama":       (-10.1860, 31.1840),
    "Mpika":        (-11.0610, 31.4460),
    "Mbala":        (-8.8390, 31.4460),
    "Mansa":        (-11.1990, 28.8930),
    "Kasama":       (-10.1860, 31.1840),
    "Chinsali":     (-10.5420, 32.0750),
    "Isoka":        (-10.1600, 32.6320),
    "Nakonde":      (-9.3210, 32.7620),
    "Kawambwa":     (-9.7860, 29.0790),
    "Mporokoso":    (-9.3790, 30.1320),
    "Luwingu":      (-10.2400, 29.9060),
    "Lunzua":       (-9.0000, 31.5000),
    "Nkamba":       (-8.7000, 31.1500),
    "Sumbawanga":   (-8.5500, 30.5500),
    "Chambasitu":   (-10.5500, 29.6500),
    "Musonda":      (-11.0000, 29.5000),
    "Chishimba":    (-10.1500, 30.8500),
    "Mfuwe":        (-13.0000, 32.0500),
    "Chipata":      (-13.6400, 32.6500),
    "Chipata West": (-13.6200, 32.6100),
    "Msoro":        (-13.1000, 32.0000),
    "Azele":        (-13.3000, 32.3000),
    "Mkushi":       (-13.6200, 29.4000),
    "Kanona":       (-13.3500, 30.7000),
    "Lusiwasi":     (-13.3000, 30.0000),
    "Mupepetwe":    (-13.5000, 29.8000),
    "Solwezi":      (-12.1800, 26.4000),
    "Kasempa":      (-13.4600, 25.8400),
    "Lumwana":      (-12.2600, 25.8000),
    "Kalumbila":    (-12.3500, 25.5000),
    "Kansanshi":    (-12.1200, 26.4200),
    "Nambala":      (-12.3000, 27.5000),
    "Leopards":     (-15.4800, 28.1900),
    "Leopard":      (-15.4800, 28.1900),
    "Leopard's":    (-15.4800, 28.1900),
    "Lusaka":       (-15.3875, 28.3228),
    "Kafue":        (-15.7690, 28.1810),
    "Muzuma":       (-15.2000, 27.9000),
    "Kariba":       (-16.5220, 28.7610),
    "Kafue Gorge":  (-15.8100, 28.4000),
    "Victoria":     (-17.9250, 25.8560),
    "Maamba":       (-17.3700, 27.1400),
    "Chambishi":    (-12.6300, 28.0700),
    "Chambeshi":    (-12.6300, 28.0700),
    "Muzuma":       (-15.2000, 27.9000),
    "Kafue Town":   (-15.7690, 28.1810),
    "Ndeke":        (-12.9000, 28.1000),
    "Mwambashi":    (-12.8500, 28.0500),
    "New Scaw":     (-12.8800, 28.1200),
    "Nkana":        (-12.8100, 28.2100),
    "Luangwa":      (-13.5000, 30.0000),
    "Maposa":       (-12.7800, 28.2300),
    "Bwana":        (-12.8000, 28.2400),
    "Mushili":      (-12.7900, 28.2200),
    "Kazungula":    (-17.7920, 25.2670),
    "Sesheke":      (-17.5050, 24.2980),
    "Senanga":      (-16.1320, 23.2660),
    "Mongu":        (-15.2540, 23.1280),
    "Kaoma":        (-14.8000, 24.8000),
    "Kasane":       (-17.8000, 25.1500),
    "Chilanga":     (-15.5300, 28.2500),
    "Chinsali":     (-10.5420, 32.0750),
    "Mwinilunga":   (-11.7360, 24.4280),
}


def substation_coords(name: str):
    """Return (lat, lon) for a substation name, or None if unknown."""
    if name in SUBSTATIONS:
        return SUBSTATIONS[name]
    # Tolerant match: try case-insensitive and partial prefix
    low = name.lower()
    for key, coords in SUBSTATIONS.items():
        if key.lower() in low or low in key.lower():
            return coords
    return None


def _route_endpoints(name: str):
    """Extract two endpoint names from a line's display name.

    The line names follow the form '<From> - <To>' with optional suffixes
    like '1', '2', '3', '(Charged at 220 kV)', 'Line', 'T-Off'.
    """
    base = name.split("(")[0].strip()
    parts = base.split("-")
    if len(parts) < 2:
        return None
    from_name = parts[0].strip()
    to_name = parts[-1].strip().split(" Line")[0].strip()
    # Strip trailing single digits (circuit numbers)
    import re
    to_name = re.sub(r"\s*\d+$", "", to_name).strip()
    from_name = re.sub(r"\s*\d+$", "", from_name).strip()
    from_c = substation_coords(from_name)
    to_c = substation_coords(to_name)
    if from_c and to_c:
        return from_c, to_c
    return None


def route_for(line_) -> list:
    """Build a [lat, lon] polyline for a line segment's real corridor.

    Uses the line's endpoint substation coordinates. For long lines
    (>120 km) an intermediate waypoint is inserted near the midpoint to
    suggest the geodetic path; short lines get a straight two-point line.
    """
    ep = _route_endpoints(line_["name"])
    if not ep:
        return None
    from_c, to_c = ep
    lat1, lon1 = from_c
    lat2, lon2 = to_c
    if line_.get("length_km", 0) >= 120:
        mid_lat = (lat1 + lat2) / 2.0
        mid_lon = (lon1 + lon2) / 2.0
        return [[lat1, lon1], [mid_lat, mid_lon], [lat2, lon2]]
    return [[lat1, lon1], [lat2, lon2]]


def endpoint_names(name: str):
    """Return (origin_substation, destination_substation) strings.

    Splits a line's display name '<From> - <To>' into its two endpoints,
    handling circuit-number suffixes, parenthetical status notes and
    hyphenated compound station names such as 'Musonda T-Off'.
    """
    import re

    base = name.split("(")[0].strip()
    base = base.replace("T-Off", "T__OFF")
    parts = base.split("-")
    if len(parts) < 2:
        return name, name
    origin = re.sub(r"\s*\d+$", "", parts[0].strip()).strip()
    destination = parts[-1].strip().split(" Line")[0].strip()
    destination = re.sub(r"\s*\d+$", "", destination).strip()
    origin = origin.replace("T__OFF", "T-Off")
    destination = destination.replace("T__OFF", "T-Off")
    return origin or name, destination or name


def status_for(line_) -> str:
    """Classify the operational status of a line from its notes / name.

    Returns one of: 'Commissioned', 'In Service', 'Pending / Under
    construction', 'Energised (lower voltage)'.
    """
    text = ((line_.get("notes") or "") + " " + line_["name"]).lower()
    if "pending commission" in text or "not commission" in text or "under construction" in text:
        return "Pending / Under construction"
    if "charged at" in text or "energised at" in text:
        return "Energised (lower voltage)"
    if line_.get("commissioned"):
        return "In Service"
    return "Commissioned"


def enrich(line_) -> dict:
    """Return an enriched copy of a line with origin, destination, status."""
    result = dict(line_)
    result["route"] = route_for(line_)
    origin, destination = endpoint_names(line_["name"])
    result["origin"] = origin
    result["destination"] = destination
    result["status"] = status_for(line_)
    return result


def all_lines() -> list:
    """All registered line segments (330 kV + 66 kV), enriched."""
    lines = [enrich(ln) for ln in (LINES_330KV + LINES_66KV)]
    return lines


def lines_by_voltage(voltage_kv: int) -> list:
    """Lines at a given nominal voltage."""
    return [ln for ln in all_lines() if ln["voltage_kv"] == voltage_kv]


def line(line_id: str) -> dict:
    """Look up a single line segment by id (enriched with route/status)."""
    for ln in LINES_330KV + LINES_66KV:
        if ln["id"] == line_id:
            return enrich(ln)
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
