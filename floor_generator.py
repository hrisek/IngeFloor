# SPDX-License-Identifier: GPL-3.0-or-later
"""Floor & Decking Generator for IngeTrazo (Generator podłogi deskowanej).

Bilingual (English default, Polish switchable):
- Parametric wood flooring, decking, and parquet generator for any room outline.
- Rebuilding / Editing in-place of previously generated floors (remembers geometry & params).
- Automatic detection of internal openings / holes (face.hole_loops) and coplanar user selections (columns / cutouts).
- Perimeter mitered border (Friz) for both room boundaries and internal holes/columns.
- Multiple floor patterns:
    * 1/2 Running bond / Staggered (Cegiełka)
    * 1/3 Staggered step (Schodkowy)
    * Random stagger (Losowy)
    * Stack bond / Straight grid (Szeregowy)
    * Continuous (Wall to wall)
    * Classic Herringbone 1x (Jodełka klasyczna pojedyncza 90°)
    * Double Herringbone 2x (Jodełka podwójna 90°)
    * Triple Herringbone 3x (Jodełka potrójna 90°)
    * French Chevron 45° (Jodełka francuska)
    * Basketweave / Parquet squares (Koszykowy / Szachownica)
    * Versailles Parquet (Kasetony wersalskie / pałacowe)
    * Mixed / Random Widths (Szerokości mieszane - styl rustykalny)
- Skirting boards generator (Listwy przypodłogowe cięte na miter wzdłuż ścian i wokół słupów).
- Material & Cutting Calculator (Kalkulator cięć, zapotrzebowania, otworów i eksport do CSV).
- High-performance component instances for uncut planks (zero UI freezing on selection).
- Strictly outward face normals (CCW) ensuring front wood materials/colors are immediately visible.
- BIM IFC tagging (IfcCovering), undoable history (Undo/Redo with Ctrl+Z).
"""
from __future__ import annotations

import copy
import csv
import math
import os
import random
from pathlib import Path
from typing import Any, List, Tuple, Union

from PySide6.QtCore import QByteArray, QBuffer, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImageReader, QMatrix4x4, QPixmap, QVector3D, QVector4D
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from core.group import Group
from core.history import SnapshotImport
from core.mesh import Face, Mesh
from tools.base import Tool

try:  # Bazowa klasa komend historii (Undo/Redo) – obecna w każdej współczesnej wersji.
    from core.history import Command as _HistCommand
except Exception:  # pragma: no cover - bardzo stare wersje
    _HistCommand = object

KEY = "floor_generator"

# ---------------------------------------------------------------------------
# Silnik booleanów 2D (przycinanie desek do obrysu, bordiura, otwory)
# ---------------------------------------------------------------------------
# 1. manifold3d – zależność samego IngeTrazo (Solid Tools), Clipper2 w C++: najszybszy.
# 2. shapely    – jeśli użytkownik ma go zainstalowanego (NIE jest zależnością IngeTrazo).
# 3. czysty Python – tryb awaryjny (bez otworów; bordiura przez prosty inset).
# Zmienna środowiskowa FLOOR_GEN_BACKEND=manifold3d|shapely|python wymusza wybór (testy).
_mf = None
_SPolygon = None
_s_prep = None
_BACKEND = "python"
_forced = os.environ.get("FLOOR_GEN_BACKEND", "").strip().lower()
if _forced in ("", "manifold3d"):
    try:
        import manifold3d as _mf  # noqa: F811
        if hasattr(_mf, "CrossSection"):
            _BACKEND = "manifold3d"
        else:
            _mf = None
    except Exception:
        _mf = None
if _BACKEND == "python" and _forced in ("", "manifold3d", "shapely"):
    try:
        from shapely.geometry import Polygon as _SPolygon  # noqa: F811
        from shapely.prepared import prep as _s_prep  # noqa: F811
        _BACKEND = "shapely"
    except Exception:
        _SPolygon = None
        _s_prep = None
del _forced

# ===========================================================================
# Słownik wielojęzyczny (i18n: English default / Polski)
# ===========================================================================

TRANSLATIONS = {
    "en": {
        "title": "Floor & Decking Generator",
        "title_edit": "Edit Floor Layout – {name}",
        "pattern_group": "Pattern & Layout Angle",
        "pattern_label": "Floor pattern:",
        "angle_label": "Layout angle:",
        "dim_group": "Plank & Joint Dimensions",
        "width_label": "Plank width:",
        "length_label": "Plank length:",
        "continuous_text": "Continuous (wall to wall)",
        "thickness_label": "Thickness (height):",
        "gap_label": "Gap / joint:",
        "border_group": "Perimeter Border (Mitered)",
        "border_chk": "Add perimeter border (mitered corners)",
        "border_hole_chk": "Add border around internal holes/columns",
        "border_planks_label": "Plank count in border:",
        "border_planks_suffix": " planks",
        "border_width_label": "Border plank width:",
        "skirting_group": "Skirting Boards (Baseboards)",
        "skirting_chk": "Add skirting boards along walls",
        "skirting_holes_chk": "Add skirting around holes/columns",
        "skirting_h_label": "Height:",
        "skirting_th_label": "Thickness:",
        "skirting_col_label": "Finish / Color:",
        "skirting_col_wood": "Match floor wood",
        "skirting_col_white": "White painted (RAL 9003)",
        "material_group": "Material & Color",
        "wood_label": "Wood species:",
        "var_label": "Shade variation:",
        "opt_group": "Performance Optimization",
        "opt_chk": "Create planks as components (recommended: smooth UI)",
        "opt_tip": "Uncut planks share component instances, dramatically reducing memory and eliminating UI freeze on selection.",
        "lang_label": "Language / Język:",
        "btn_report_preview": "Material & Cut Report...",
        "flash_select": "Select a floor face (Face) to create, or a generated floor (Group) to edit.",
        "flash_rebuilt": "Rebuilt floor layout: {name}",
        "flash_done": "Generated floor: {total_planks} planks in {count} outline(s).",
        "flash_holes_detected": "Detected {n} internal opening(s)/column(s).",
        "flash_empty": "No planks generated (check outline size).",
        "err_title": "Floor Generator Error",
        "menu_floor": "Floor & Decking",
        "menu_action": "Generate / Edit Floor...",
        "context_edit": "Edit Floor ({name})...",
        "context_gen": "Generate Floor...",
        "context_report": "Material Report ({name})...",
        "tool_name": "Floor & Decking Generator",
        "tool_desc": "Generates or edits parametric plank flooring, decking, or parquet with borders and skirting boards.",
        "group_name": "Plank Floor",
        "item_plank_comp": "Plank {n} (component)",
        "item_plank_cut": "Plank {n} (cut)",
        "item_border": "Border {b} (wall {w})",
        "item_hole_border": "Hole Border {b} (hole {h} seg {w})",
        "item_herringbone": "Herringbone {n}",
        "item_chevron": "Chevron {n}",
        "item_square": "Square {n}",
        "item_versailles": "Versailles {n}",
        "item_skirting": "Skirting (wall {w})",
        "item_hole_skirting": "Hole Skirting (hole {h} seg {w})",
        "pat_half": "1/2 (staggered / running bond)",
        "pat_third": "1/3 (staggered step)",
        "pat_random": "Random stagger",
        "pat_straight": "Stack bond (straight grid)",
        "pat_herringbone": "Classic Herringbone (1x Single)",
        "pat_herringbone_double": "Double Herringbone (2x Double)",
        "pat_herringbone_triple": "Triple Herringbone (3x Triple)",
        "pat_chevron": "French Chevron (45°)",
        "pat_basket": "Basketweave / Parquet squares",
        "pat_versailles": "Versailles Parquet (Palace panels)",
        "pat_mixed_widths": "Mixed Widths (Rustic random)",
        "wood_oak": "Natural Oak",
        "wood_pine": "Light Pine",
        "wood_walnut": "Dark Walnut",
        "wood_ash": "Bleached Ash",
        "wood_teak": "Gray Teak",
        # Report strings
        "rep_title": "Floor Material & Cut Calculator",
        "rep_header_general": "Project & Geometry Summary",
        "rep_header_holes": "Internal Openings & Columns",
        "rep_header_planks": "Plank Counts & Dimensions",
        "rep_header_skirting": "Skirting Boards",
        "rep_header_order": "Material Order Recommendation",
        "rep_room_area": "Room Net Area:",
        "rep_fl_area": "Flooring Covered Area:",
        "rep_hole_count": "Openings / Holes Count:",
        "rep_hole_area": "Deducted Openings Area:",
        "rep_pattern": "Layout Pattern:",
        "rep_wood": "Wood Species:",
        "rep_dims": "Plank Dimensions:",
        "rep_full": "Full Planks (Uncut instances):",
        "rep_cut": "Cut / Trimmed Planks:",
        "rep_border": "Border Planks (Outer walls):",
        "rep_hole_border": "Border Planks (Around holes):",
        "rep_total_planks": "Total Plank Count:",
        "rep_linear_m": "Total Plank Linear Length:",
        "rep_skirt_count": "Skirting Segments:",
        "rep_skirt_linear": "Skirting Total Length:",
        "rep_waste": "Recommended Waste Buffer (+{pct}%):",
        "rep_order_area": "Recommended Purchase Area:",
        "rep_export_csv": "Export to CSV...",
        "rep_close": "Close",
        "rep_csv_saved_title": "Export Successful",
        "rep_csv_saved_msg": "Report saved successfully to:\n{path}",
        "rep_comp": "Components (instances / definitions):",
        "rep_comp_val": "{inst} / {defs}",
        # Element kinds & names (component definitions share one name)
        "kind_plank": "Plank",
        "kind_border": "Border",
        "kind_skirting": "Skirting",
        "kind_herringbone": "Herringbone",
        "kind_chevron": "Chevron",
        "kind_square": "Basket",
        "kind_versailles": "Versailles",
        "item_comp_def": "{kind} {l}×{w} cm",
        "item_single": "{kind} {n} (unique)",
    },
    "pl": {
        "title": "Generator podłogi deskowanej",
        "title_edit": "Edycja podłogi deskowanej – {name}",
        "pattern_group": "Wzór ułożenia i kąt",
        "pattern_label": "Wzór podłogi:",
        "angle_label": "Kąt ułożenia:",
        "dim_group": "Wymiary desek i szczelin",
        "width_label": "Szerokość deski:",
        "length_label": "Długość deski:",
        "continuous_text": "Ciągła (od ściany do ściany)",
        "thickness_label": "Grubość (wysokość):",
        "gap_label": "Fuga / odstęp:",
        "border_group": "Bordiura obwodowa (Friz)",
        "border_chk": "Dodaj bordiurę dookoła (cięta na miter)",
        "border_hole_chk": "Dodaj bordiurę wokół otworów/słupów",
        "border_planks_label": "Liczba desek w bordiurze:",
        "border_planks_suffix": " desek",
        "border_width_label": "Szerokość deski bordiury:",
        "skirting_group": "Listwy przypodłogowe (Cokoły)",
        "skirting_chk": "Dodaj listwy przypodłogowe wzdłuż ścian",
        "skirting_holes_chk": "Dodaj listwy wokół otworów/słupów",
        "skirting_h_label": "Wysokość listwy:",
        "skirting_th_label": "Grubość listwy:",
        "skirting_col_label": "Wykończenie / Kolor:",
        "skirting_col_wood": "W kolorze drewna podłogi",
        "skirting_col_white": "Biała lakierowana (RAL 9003)",
        "material_group": "Materiał i kolorystyka",
        "wood_label": "Rodzaj drewna:",
        "var_label": "Zróżnicowanie odcieni:",
        "opt_group": "Optymalizacja wydajności",
        "opt_chk": "Twórz deski jako komponenty (zalecane: brak zacinania)",
        "opt_tip": "Deski pełne korzystają ze współdzielonych instancji komponentu, co drastycznie zmniejsza pamięć i eliminuje zawieszanie programu przy zaznaczaniu podłogi.",
        "lang_label": "Język / Language:",
        "btn_report_preview": "Raport materiałowy i kalkulator...",
        "flash_select": "Zaznacz płaszczyznę podłogi (Face) do utworzenia, lub wygenerowaną podłogę (Group) do edycji.",
        "flash_rebuilt": "Przebudowano układ podłogi: {name}",
        "flash_done": "Wygenerowano podłogę: {total_planks} desek w {count} obrysie/ach.",
        "flash_holes_detected": "Wykryto {n} otwór(ów)/słup(ów) wewnętrznych.",
        "flash_empty": "Nie wygenerowano desek (sprawdź rozmiar obrysu).",
        "err_title": "Błąd generatora podłogi",
        "menu_floor": "Podłoga deskowana",
        "menu_action": "Generuj / Edytuj podłogę...",
        "context_edit": "Edytuj podłogę ({name})...",
        "context_gen": "Generuj podłogę deskowaną...",
        "context_report": "Raport materiałowy ({name})...",
        "tool_name": "Generator podłogi deskowanej",
        "tool_desc": "Generuje lub przebudowuje parametryczną podłogę deskowaną / parkiet z bordiurą i listwami przypodłogowymi.",
        "group_name": "Podłoga deskowana",
        "item_plank_comp": "Deska {n} (komponent)",
        "item_plank_cut": "Deska {n} (docięta)",
        "item_border": "Bordiura {b} (ściana {w})",
        "item_hole_border": "Bordiura otworu {b} (otwór {h} seg {w})",
        "item_herringbone": "Jodełka {n}",
        "item_chevron": "Chevron {n}",
        "item_square": "Kwadrat {n}",
        "item_versailles": "Kaseton {n}",
        "item_skirting": "Listwa (ściana {w})",
        "item_hole_skirting": "Listwa otworu (otwór {h} seg {w})",
        "pat_half": "1/2 (cegiełka)",
        "pat_third": "1/3 (schodkowy)",
        "pat_random": "Losowe przesunięcie",
        "pat_straight": "Brak (szeregowy)",
        "pat_herringbone": "Jodełka klasyczna (1x pojedyncza)",
        "pat_herringbone_double": "Jodełka podwójna (2x podwójna)",
        "pat_herringbone_triple": "Jodełka potrójna (3x potrójna)",
        "pat_chevron": "Jodełka francuska (Chevron 45°)",
        "pat_basket": "Koszykowy / Szachownica",
        "pat_versailles": "Kasetony wersalskie / pałacowe",
        "pat_mixed_widths": "Szerokości mieszane (styl rustykalny)",
        "wood_oak": "Dąb naturalny (Oak)",
        "wood_pine": "Sosna jasna (Pine)",
        "wood_walnut": "Ciemny orzech (Walnut)",
        "wood_ash": "Bielony jesion (Ash)",
        "wood_teak": "Szary tek (Teak)",
        # Raport strings
        "rep_title": "Raport materiałowy i kalkulator cięć",
        "rep_header_general": "Podsumowanie geometrii i wzoru",
        "rep_header_holes": "Otwory wewnętrzne i słupy",
        "rep_header_planks": "Liczba elementów i wymiary",
        "rep_header_skirting": "Listwy przypodłogowe",
        "rep_header_order": "Zalecane zamówienie materiału",
        "rep_room_area": "Powierzchnia netto pomieszczenia:",
        "rep_fl_area": "Powierzchnia pokrycia deskami:",
        "rep_hole_count": "Liczba otworów / słupów:",
        "rep_hole_area": "Odliczona powierzchnia otworów:",
        "rep_pattern": "Wzór ułożenia:",
        "rep_wood": "Rodzaj drewna:",
        "rep_dims": "Wymiary deski:",
        "rep_full": "Deski pełne (niecięte komponenty):",
        "rep_cut": "Deski docięte (odpad / brzeg):",
        "rep_border": "Deski bordiury obwodowej (ściany):",
        "rep_hole_border": "Deski bordiury wokół otworów:",
        "rep_total_planks": "Łączna liczba desek:",
        "rep_linear_m": "Łączna długość bieżąca desek:",
        "rep_skirt_count": "Liczba odcinków listew:",
        "rep_skirt_linear": "Łączna długość listew przypodłogowych:",
        "rep_waste": "Zalecany naddatek na odpady (+{pct}%):",
        "rep_order_area": "Zalecana ilość do zakupu:",
        "rep_export_csv": "Eksportuj do CSV...",
        "rep_close": "Zamknij",
        "rep_csv_saved_title": "Eksport zakończony sukcesem",
        "rep_csv_saved_msg": "Raport został pomyślnie zapisany do pliku:\n{path}",
        "rep_comp": "Komponenty (instancje / definicje):",
        "rep_comp_val": "{inst} / {defs}",
        "kind_plank": "Deska",
        "kind_border": "Bordiura",
        "kind_skirting": "Listwa",
        "kind_herringbone": "Jodełka",
        "kind_chevron": "Chevron",
        "kind_square": "Koszyk",
        "kind_versailles": "Kaseton",
        "item_comp_def": "{kind} {l}×{w} cm",
        "item_single": "{kind} {n} (unikalna)",
    },
}


def tr(key: str, lang: str = "en", **kwargs) -> str:
    """Zwraca zlokalizowany ciąg znaków."""
    table = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    text = table.get(key, TRANSLATIONS["en"].get(key, key))
    return text.format(**kwargs) if kwargs else text


PATTERN_KEYS = [
    "pat_half",
    "pat_third",
    "pat_random",
    "pat_straight",
    "pat_herringbone",
    "pat_herringbone_double",
    "pat_herringbone_triple",
    "pat_chevron",
    "pat_basket",
    "pat_versailles",
    "pat_mixed_widths",
]

WOOD_KEYS = [
    "wood_oak",
    "wood_pine",
    "wood_walnut",
    "wood_ash",
    "wood_teak",
]

WOOD_COLORS = {
    "wood_oak": (0.76, 0.58, 0.40),
    "wood_pine": (0.86, 0.72, 0.52),
    "wood_walnut": (0.42, 0.28, 0.18),
    "wood_ash": (0.88, 0.84, 0.78),
    "wood_teak": (0.55, 0.50, 0.45),
}


def normalize_pattern(val: str) -> str:
    """Normalizuje nazwę wzoru do stabilnego klucza wewnętrznego."""
    if not val or val in PATTERN_KEYS:
        return val or "pat_half"
    val_l = val.lower()
    if "triple" in val_l or "potrójn" in val_l or "3x" in val_l:
        return "pat_herringbone_triple"
    if "double" in val_l or "podwójn" in val_l or "2x" in val_l:
        return "pat_herringbone_double"
    if "herringbone" in val_l or "jodełka klasyczna" in val_l or "jodełka" in val_l:
        return "pat_herringbone"
    if "chevron" in val_l or "francuska" in val_l:
        return "pat_chevron"
    if "versailles" in val_l or "wersal" in val_l or "kaseton" in val_l:
        return "pat_versailles"
    if "mixed" in val_l or "mieszan" in val_l or "rustic" in val_l:
        return "pat_mixed_widths"
    if "1/3" in val_l or "third" in val_l:
        return "pat_third"
    if "losow" in val_l or "random" in val_l:
        return "pat_random"
    if "brak" in val_l or "szereg" in val_l or "stack" in val_l or "straight" in val_l:
        return "pat_straight"
    if "koszyk" in val_l or "szachownica" in val_l or "basket" in val_l:
        return "pat_basket"
    return "pat_half"


def normalize_wood(val: str) -> str:
    """Normalizuje nazwę drewna do stabilnego klucza wewnętrznego."""
    if not val or val in WOOD_KEYS:
        return val or "wood_oak"
    val_l = val.lower()
    if "sosna" in val_l or "pine" in val_l:
        return "wood_pine"
    if "orzech" in val_l or "walnut" in val_l:
        return "wood_walnut"
    if "jesion" in val_l or "ash" in val_l:
        return "wood_ash"
    if "tek" in val_l or "teak" in val_l:
        return "wood_teak"
    return "wood_oak"


DEFAULT_PARAMS = {
    "lang": "en",              # Default: English (ENG), switchable to Polish (PL)
    "pattern": "pat_half",
    "plank_w_cm": 14.0,        # Plank width in cm
    "plank_l_cm": 120.0,       # Plank length in cm (0 = continuous)
    "thickness_mm": 20.0,      # Thickness in mm
    "gap_mm": 3.0,             # Gap in mm
    "angle_deg": 0.0,          # Layout angle in degrees
    "wood_type": "wood_oak",
    "color_var_pct": 6.0,      # Random shade variation +/- %
    "use_components": True,    # Performance: component instances for uncut planks
    "use_border": False,       # Perimeter border toggle
    "border_planks": 1,        # Number of planks in border
    "border_plank_w_cm": 14.0, # Border plank width in cm
    "use_hole_border": True,   # Border around internal openings/columns
    "use_skirting": False,     # Skirting boards toggle
    "skirting_holes": True,    # Skirting around internal openings/columns
    "skirting_h_cm": 8.0,      # Skirting board height in cm
    "skirting_th_mm": 15.0,    # Skirting board thickness in mm
    "skirting_color": "wood",  # "wood" or "white"
}


def _merged_params(params: dict | None) -> dict:
    """Parametry zapisane (np. przez starszą wersję) nałożone na domyślne – brakujący
    klucz nigdy nie wywoła KeyError w oknie dialogowym ani w generatorze."""
    out = dict(DEFAULT_PARAMS)
    if params:
        out.update(params)
    return out


# ===========================================================================
# Ikona narzędzia (górny pasek narzędzi / menu)
# ===========================================================================

#: Ikona osadzona w skrypcie (plugin działa jako pojedynczy plik .py). Jeśli obok
#: pluginu leży ``floor_generator.svg`` lub ``floor_generator.png``, ma pierwszeństwo.
_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64"><polygon points="1.5,27.0 32.0,9.5 62.5,27.0 62.5,36.0 32.0,53.5 1.5,36.0" fill="#4A2E16" stroke="#2E1A0B" stroke-width="1.6" stroke-linejoin="round"/><polygon points="1.5,27.0 14.1,19.77 19.92,23.12 7.33,30.34" fill="#E2AD72"/><line x1="4.93" y1="27.57" x2="13.26" y2="22.79" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="9.24" y1="27.24" x2="16.65" y2="22.99" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="14.52,19.53 32.0,9.5 37.83,12.84 20.35,22.87" fill="#CB8E52"/><line x1="17.96" y1="20.1" x2="31.16" y2="12.52" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="22.26" y1="19.77" x2="34.55" y2="12.71" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="1.5,27.0 7.33,30.34 7.33,39.34 1.5,36.0" fill="#9A6331"/><polygon points="7.87,30.66 13.15,27.63 18.7,30.82 13.43,33.84" fill="#EDC08C"/><line x1="11.2" y1="31.17" x2="12.21" y2="30.59" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="15.42" y1="30.79" x2="15.51" y2="30.73" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="13.58,27.38 29.01,18.53 34.56,21.71 19.13,30.57" fill="#BE8048"/><line x1="16.91" y1="27.9" x2="28.07" y2="21.49" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="21.12" y1="27.51" x2="31.37" y2="21.63" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="29.44,18.29 38.37,13.16 43.93,16.34 34.99,21.47" fill="#D89C5F"/><line x1="32.77" y1="18.8" x2="37.43" y2="16.12" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="36.98" y1="18.41" x2="40.74" y2="16.26" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="7.87,30.66 13.43,33.84 13.43,42.84 7.87,39.66" fill="#87562A"/><polygon points="13.97,34.16 30.54,24.66 36.09,27.84 19.53,37.34" fill="#C6894E"/><line x1="17.3" y1="34.67" x2="29.6" y2="27.62" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="21.52" y1="34.29" x2="32.9" y2="27.76" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="30.96,24.41 44.47,16.66 50.03,19.84 36.51,27.59" fill="#E6B47D"/><line x1="34.29" y1="24.92" x2="43.53" y2="19.62" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="38.51" y1="24.54" x2="46.84" y2="19.76" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="13.97,34.16 19.53,37.34 19.53,46.34 13.97,43.16" fill="#A46B37"/><polygon points="20.07,37.66 29.01,32.53 34.56,35.72 25.63,40.84" fill="#E2AD72"/><line x1="23.4" y1="38.17" x2="28.07" y2="35.49" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="27.62" y1="37.79" x2="31.37" y2="35.63" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="29.44,32.28 46.09,22.73 51.64,25.91 34.99,35.47" fill="#CB8E52"/><line x1="32.77" y1="32.8" x2="45.15" y2="25.69" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="36.98" y1="32.41" x2="48.45" y2="25.83" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="46.52,22.48 50.57,20.16 56.13,23.34 52.07,25.67" fill="#EDC08C"/><line x1="49.85" y1="23.0" x2="49.63" y2="23.12" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="54.06" y1="22.61" x2="52.94" y2="23.26" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="20.07,37.66 25.63,40.84 25.63,49.84 20.07,46.66" fill="#7E4F26"/><polygon points="26.17,41.16 44.87,30.43 50.7,33.77 32.0,44.5" fill="#BE8048"/><line x1="29.61" y1="41.73" x2="44.03" y2="33.45" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="33.91" y1="41.4" x2="47.42" y2="33.64" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="45.3,30.19 56.67,23.66 62.5,27.0 51.12,33.53" fill="#D89C5F"/><line x1="48.73" y1="30.76" x2="55.84" y2="26.68" stroke="#FFF3DF" stroke-opacity="0.45" stroke-width="0.7" stroke-linecap="round"/><line x1="53.04" y1="30.42" x2="59.23" y2="26.87" stroke="#6B421F" stroke-opacity="0.30" stroke-width="0.6" stroke-linecap="round"/><polygon points="26.17,41.16 32.0,44.5 32.0,53.5 26.17,50.16" fill="#93602F"/><polygon points="32.0,44.5 50.7,33.77 50.7,42.77 32.0,53.5" fill="#B07440"/><polygon points="51.12,33.53 62.5,27.0 62.5,36.0 51.12,42.53" fill="#A56C3B"/><polyline points="1.5,27.0 32.0,9.5 62.5,27.0" fill="none" stroke="#FFE2B8" stroke-opacity="0.55" stroke-width="1.1" stroke-linejoin="round"/><polygon points="1.5,27.0 32.0,9.5 62.5,27.0 62.5,36.0 32.0,53.5 1.5,36.0" fill="none" stroke="#2E1A0B" stroke-width="1.6" stroke-linejoin="round"/><line x1="32.0" y1="44.5" x2="32.0" y2="53.5" stroke="#2E1A0B" stroke-width="1.0"/><circle cx="51.5" cy="51.5" r="10.5" fill="#2E9E5B" stroke="#FFFFFF" stroke-width="2.2"/><path d="M51.5 45.6v11.8M45.6 51.5h11.8" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round"/></svg>"""

_ICON_CACHE: list = []


def _plugin_icon() -> QIcon:
    """QIcon generatora: plik obok pluginu, a w razie braku – SVG osadzone w kodzie,
    rasteryzowane w kilku rozmiarach (ostre przy 20/24/32/48 px i HiDPI)."""
    if _ICON_CACHE:
        return _ICON_CACHE[0]
    icon = QIcon()
    try:
        here = Path(__file__).resolve()
        for ext in (".svg", ".png"):
            cand = here.with_suffix(ext)
            if cand.is_file():
                icon = QIcon(str(cand))
                if not icon.isNull():
                    break
    except Exception:
        icon = QIcon()
    if icon.isNull():
        data = QByteArray(_ICON_SVG.encode("utf-8"))
        for size in (16, 20, 24, 32, 40, 48, 64, 96, 128):
            buf = QBuffer(data)
            reader = QImageReader(buf, QByteArray(b"svg"))
            reader.setScaledSize(QSize(size, size))
            img = reader.read()
            if not img.isNull():
                icon.addPixmap(QPixmap.fromImage(img))
    _ICON_CACHE.append(icon)
    return icon


# ===========================================================================
# Algorytmy geometryczne 2D
# ===========================================================================

def _signed_area_2d(pts: List[Tuple[float, float]]) -> float:
    """Pole ze znakiem wielokąta 2D. Wartość > 0 oznacza orientację CCW."""
    n = len(pts)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        a += pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
    return 0.5 * a


def _polygon_area_2d(pts: List[Tuple[float, float]]) -> float:
    """Pole bezwzględne wielokąta 2D metodą Gaussa."""
    return abs(_signed_area_2d(pts))


def _ensure_ccw(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Gwarantuje kolejność wierzchołków CCW (wymusza normale skierowane na zewnątrz)."""
    if _signed_area_2d(pts) < 0:
        return list(reversed(pts))
    return pts


def _clip_polygon_against_halfplane(
    poly: List[Tuple[float, float]], nx: float, ny: float, c: float
) -> List[Tuple[float, float]]:
    out = []
    if not poly:
        return out
    n = len(poly)
    for i in range(n):
        cur = poly[i]
        prev = poly[(i - 1) % n]
        cur_in = (nx * cur[0] + ny * cur[1]) >= c - 1e-9
        prev_in = (nx * prev[0] + ny * prev[1]) >= c - 1e-9
        if cur_in:
            if not prev_in:
                dprev = nx * prev[0] + ny * prev[1] - c
                dcur = nx * cur[0] + ny * cur[1] - c
                denom = dcur - dprev
                t = -dprev / denom if abs(denom) > 1e-12 else 0.0
                out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
            out.append(cur)
        elif prev_in:
            dprev = nx * prev[0] + ny * prev[1] - c
            dcur = nx * cur[0] + ny * cur[1] - c
            denom = dcur - dprev
            t = -dprev / denom if abs(denom) > 1e-12 else 0.0
            out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
    return out


def _clip_by_convex(subject: List[Tuple[float, float]], window: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Sutherland–Hodgman: przycina dowolny wielokąt ``subject`` wypukłym oknem ``window`` (CCW)."""
    out = subject
    n = len(window)
    for i in range(n):
        ax, ay = window[i]
        bx, by = window[(i + 1) % n]
        nx, ny = -(by - ay), (bx - ax)           # normalna do wnętrza dla CCW
        out = _clip_polygon_against_halfplane(out, nx, ny, nx * ax + ny * ay)
        if not out:
            break
    return out


def _inset_polygon_simple(poly: List[Tuple[float, float]], d: float) -> List[Tuple[float, float]]:
    """Prosty odsunięty do wewnątrz obrys (miter) – tylko dla trybu awaryjnego bez bibliotek."""
    n = len(poly)
    out = []
    for i in range(n):
        px, py = poly[i]
        ax, ay = poly[i - 1]
        bx, by = poly[(i + 1) % n]
        d1x, d1y = px - ax, py - ay
        d2x, d2y = bx - px, by - py
        l1 = math.hypot(d1x, d1y) or 1.0
        l2 = math.hypot(d2x, d2y) or 1.0
        n1 = (-d1y / l1, d1x / l1)
        n2 = (-d2y / l2, d2x / l2)
        mx, my = n1[0] + n2[0], n1[1] + n2[1]
        lm = math.hypot(mx, my)
        if lm < 1e-9:
            mx, my, lm = n1[0], n1[1], 1.0
        mx, my = mx / lm, my / lm
        cos_a = max(0.2, mx * n1[0] + my * n1[1])
        out.append((px + mx * d / cos_a, py + my * d / cos_a))
    return out if _signed_area_2d(out) > 1e-6 else []


def _point_in_poly(x: float, y: float, poly: List[Tuple[float, float]]) -> bool:
    """Test parzystości (ray casting) punktu w wielokącie."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-300) + xi:
            inside = not inside
        j = i
    return inside


def _dist_point_seg(px: float, py: float, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll < 1e-18 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _poly_inside_poly(inner, outer, tol: float = 1e-5) -> bool:
    """Czy wielokąt ``inner`` leży w ``outer`` (wierzchołki wewnątrz lub na brzegu,
    środek ciężkości ściśle wewnątrz) – słup dosunięty do ściany też się liczy."""
    n = len(inner)
    if n < 3 or _polygon_area_2d(inner) >= _polygon_area_2d(outer):
        return False
    m = len(outer)
    for x, y in inner:
        if _point_in_poly(x, y, outer):
            continue
        if min(_dist_point_seg(x, y, outer[k], outer[(k + 1) % m]) for k in range(m)) > tol:
            return False
    a6 = 0.0
    cx = cy = 0.0
    for i in range(n):
        x0, y0 = inner[i]
        x1, y1 = inner[(i + 1) % n]
        c = x0 * y1 - x1 * y0
        a6 += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if abs(a6) < 1e-12:
        return False
    return _point_in_poly(cx / (3.0 * a6), cy / (3.0 * a6), outer)


def _clean_to_simple_polys(geom: Any) -> List[Any]:
    """[shapely] Dzieli wielokąty z otworami na proste wielokąty bez otworów za pomocą linii cięcia."""
    if geom is None or geom.is_empty:
        return []
    from shapely.geometry import Polygon as SPolygon, LineString as SLineString
    from shapely.ops import split as s_split

    poly_list = []
    if geom.geom_type == 'Polygon':
        poly_list = [geom]
    elif geom.geom_type == 'MultiPolygon':
        poly_list = list(geom.geoms)
    elif hasattr(geom, 'geoms'):
        poly_list = [g for g in geom.geoms if g.geom_type == 'Polygon']

    result = []
    for g in poly_list:
        if not g.interiors:
            result.append(g)
        else:
            curr_pieces = [g]
            for hole in g.interiors:
                h_poly = SPolygon(hole)
                cx = h_poly.centroid.x
                miny, maxy = g.bounds[1] - 1.0, g.bounds[3] + 1.0
                knife = SLineString([(cx, miny), (cx, maxy)])
                next_pieces = []
                for piece in curr_pieces:
                    if piece.intersects(knife):
                        sp = s_split(piece, knife)
                        sub_polys = [p for p in getattr(sp, 'geoms', [sp]) if p.geom_type == 'Polygon']
                        next_pieces.extend(sub_polys)
                    else:
                        next_pieces.append(piece)
                curr_pieces = next_pieces
            for piece in curr_pieces:
                if piece.geom_type == 'Polygon' and piece.area > 1e-5:
                    result.append(piece)
    return result


def _mf_simple_pieces(cs: Any, depth: int = 0) -> List[List[Tuple[float, float]]]:
    """[manifold3d] Rozkłada wynik boolean na proste wielokąty CCW bez otworów
    (otwór wewnątrz deski – np. rura – jest rozcinany pionową linią przez otwór)."""
    out: List[List[Tuple[float, float]]] = []
    for sub in cs.decompose():
        polys = [[(float(x), float(y)) for x, y in c] for c in sub.to_polygons()]
        polys = [p for p in polys if len(p) >= 3]
        if not polys:
            continue
        outers = [p for p in polys if _signed_area_2d(p) > 0]
        holes = [p for p in polys if _signed_area_2d(p) < 0]
        if not holes or depth > 6:
            for p in outers:
                if _signed_area_2d(p) > 1e-5:
                    out.append(p)
            continue
        hx = sum(p[0] for p in holes[0]) / len(holes[0])
        x0, y0, x1, y1 = sub.bounds()
        left = sub ^ _mf.CrossSection([[(x0 - 1.0, y0 - 1.0), (hx, y0 - 1.0), (hx, y1 + 1.0), (x0 - 1.0, y1 + 1.0)]])
        right = sub ^ _mf.CrossSection([[(hx, y0 - 1.0), (x1 + 1.0, y0 - 1.0), (x1 + 1.0, y1 + 1.0), (hx, y1 + 1.0)]])
        out.extend(_mf_simple_pieces(left, depth + 1))
        out.extend(_mf_simple_pieces(right, depth + 1))
    return out


class _ClipTarget:
    """Jedna spójna część pola wypełnienia z szybkim przycinaniem elementów.

    ``clip(pts)`` zwraca (lista_kawałków_CCW, czy_element_jest_nieprzycięty).
    Element nieprzycięty wraca z DOKŁADNYMI współrzędnymi wejściowymi – dzięki temu
    wszystkie pełne deski mają bit-w-bit ten sam kształt i trafiają do jednego komponentu.
    """

    __slots__ = ("_cs", "_sp", "_prep", "_pts", "bounds")

    def __init__(self, bounds, cs=None, sp=None, pts=None) -> None:
        self.bounds = tuple(float(b) for b in bounds)
        self._cs = cs
        self._sp = sp
        self._prep = _s_prep(sp) if sp is not None else None
        self._pts = pts

    def clip(self, pts) -> Tuple[List[List[Tuple[float, float]]], bool]:
        bx0, by0, bx1, by1 = self.bounds
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if min(xs) > bx1 or max(xs) < bx0 or min(ys) > by1 or max(ys) < by0:
            return [], False          # szybkie odrzucenie – większość kandydatów jodełki
        pts = _ensure_ccw(pts)

        if self._cs is not None:      # manifold3d (Clipper2, C++)
            q = _mf.CrossSection([pts])
            a_q = q.area()
            if a_q <= 1e-12:
                return [], False
            res = q ^ self._cs
            if res.is_empty():
                return [], False
            a = res.area()
            if a >= a_q * (1.0 - 1e-6):
                return [list(pts)], True
            if a < 1e-5:
                return [], False
            return _mf_simple_pieces(res), False

        if self._sp is not None:      # shapely (prepared geometry)
            q = _SPolygon(pts)
            if self._prep.contains(q):
                return [list(pts)], True
            if not self._prep.intersects(q):
                return [], False
            pieces = []
            for sp in _clean_to_simple_polys(q.intersection(self._sp)):
                coords = list(sp.exterior.coords)[:-1]
                if len(coords) >= 3 and _polygon_area_2d(coords) > 1e-5:
                    pieces.append(_ensure_ccw(coords))
            return pieces, False

        # Tryb awaryjny (czysty Python): element wypukły jako okno przycięcia obrysu.
        res = _clip_by_convex(self._pts, pts)
        if len(res) < 3:
            return [], False
        a = _polygon_area_2d(res)
        if a >= _polygon_area_2d(pts) * (1.0 - 1e-6):
            return [list(pts)], True
        if a < 1e-5:
            return [], False
        return [_ensure_ccw(res)], False


def _infill_parts(
    room: List[Tuple[float, float]],
    holes: List[List[Tuple[float, float]]],
    border_depth: float,
    hole_depth: float,
) -> List[_ClipTarget]:
    """Pole wypełnienia wzorem = obrys (pomniejszony o bordiurę) − otwory (powiększone
    o bordiurę wokół otworów), rozbite na spójne części."""
    if _BACKEND == "manifold3d":
        C = _mf.CrossSection
        miter = _mf.JoinType.Miter
        reg = C([room])
        if border_depth > 0:
            reg = reg.offset(-border_depth, miter, 2.0)
        for h in holes:
            hc = C([h])
            if hole_depth > 0:
                hc = hc.offset(hole_depth, miter, 2.0)
            reg = reg - hc
        return [_ClipTarget(sub.bounds(), cs=sub) for sub in reg.decompose() if sub.area() > 1e-6]

    if _BACKEND == "shapely":
        reg = _SPolygon(room)
        if not reg.is_valid:
            reg = reg.buffer(0)
        if border_depth > 0:
            reg = reg.buffer(-border_depth, join_style=2, mitre_limit=2.0)
        for h in holes:
            hp = _SPolygon(h)
            if hole_depth > 0:
                hp = hp.buffer(hole_depth, join_style=2, mitre_limit=2.0)
            reg = reg.difference(hp)
        if reg.is_empty:
            return []
        geoms = [reg] if reg.geom_type == "Polygon" else [g for g in getattr(reg, "geoms", []) if g.geom_type == "Polygon"]
        return [_ClipTarget(g.bounds, sp=g) for g in geoms if g.area > 1e-6]

    # Czysty Python: bez otworów, bordiura przez prosty inset.
    pts = _inset_polygon_simple(room, border_depth) if border_depth > 0 else list(room)
    if len(pts) < 3:
        return []
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [_ClipTarget((min(xs), min(ys), max(xs), max(ys)), pts=pts)]


def _ray_intersection_2d(
    p1: Tuple[float, float],
    m1: Tuple[float, float],
    p2: Tuple[float, float],
    m2: Tuple[float, float],
) -> Tuple[float | None, float | None]:
    """Oblicza punkt przecięcia dwóch promieni 2D: p1 + t*m1 oraz p2 + u*m2."""
    det = m1[0] * (-m2[1]) - m1[1] * (-m2[0])
    if abs(det) < 1e-9:
        return None, None
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    t = (dx * (-m2[1]) - dy * (-m2[0])) / det
    u = (m1[0] * dy - m1[1] * dx) / det
    return t, u


def _safe_miter_polygon(
    poly: List[Tuple[float, float]],
    i: int,
    d_out: float,
    d_in: float,
) -> List[Tuple[float, float]]:
    """Generuje wielokąt deski bordiury lub cokołu dla ściany zewnętrznej i, w 100% chroniony przed samo-przecięciem."""
    n = len(poly)
    prev_i = (i - 1) % n
    nxt_i = (i + 1) % n
    nxt2_i = (i + 2) % n

    p_prev = poly[prev_i]
    p1 = poly[i]
    p2 = poly[nxt_i]
    p_next = poly[nxt2_i]

    v = (p2[0] - p1[0], p2[1] - p1[1])
    L = math.hypot(*v)
    if L < 1e-6:
        return []
    d_wall = (v[0] / L, v[1] / L)
    n_wall = (-d_wall[1], d_wall[0])

    # Dwusieczna w wierzchołku p1
    v_prev = (p1[0] - p_prev[0], p1[1] - p_prev[1])
    L_prev = math.hypot(*v_prev)
    d_prev = (v_prev[0] / L_prev, v_prev[1] / L_prev) if L_prev > 1e-6 else d_wall
    n_prev = (-d_prev[1], d_prev[0])
    nb1 = (n_prev[0] + n_wall[0], n_prev[1] + n_wall[1])
    lb1 = math.hypot(*nb1)
    m1 = (nb1[0] / lb1, nb1[1] / lb1) if lb1 > 1e-6 else n_wall

    # Dwusieczna w wierzchołku p2
    v_next = (p_next[0] - p2[0], p_next[1] - p2[1])
    L_next = math.hypot(*v_next)
    d_next = (v_next[0] / L_next, v_next[1] / L_next) if L_next > 1e-6 else d_wall
    n_next = (-d_next[1], d_next[0])
    nb2 = (n_wall[0] + n_next[0], n_wall[1] + n_next[1])
    lb2 = math.hypot(*nb2)
    m2 = (nb2[0] / lb2, nb2[1] / lb2) if lb2 > 1e-6 else n_wall

    cos1 = n_wall[0] * m1[0] + n_wall[1] * m1[1]
    cos2 = n_wall[0] * m2[0] + n_wall[1] * m2[1]
    # Ochrona przed nieskończonymi szpicami przy ostrych kątach (Miter Limit)
    if abs(cos1) < 0.2:
        cos1 = 0.2 if cos1 >= 0 else -0.2
    if abs(cos2) < 0.2:
        cos2 = 0.2 if cos2 >= 0 else -0.2

    # Wykrywanie zbieżności promieni dwusiecznych (wygaszanie krótkiej krawędzi)
    t1, u2 = _ray_intersection_2d(p1, m1, p2, m2)
    d_max = 999999.0
    X = None
    if t1 is not None and t1 > 1e-6 and u2 > 1e-6:
        cand_X = (p1[0] + t1 * m1[0], p1[1] + t1 * m1[1])
        cand_depth = (cand_X[0] - p1[0]) * n_wall[0] + (cand_X[1] - p1[1]) * n_wall[1]
        if cand_depth > 1e-6:
            d_max = cand_depth
            X = cand_X

    # Jeśli krawędź wygasła już przed rozpoczęciem tego pasa:
    if d_out >= d_max - 1e-6:
        return []

    dist1_out = d_out / cos1
    dist2_out = d_out / cos2
    c1_out = (p1[0] + m1[0] * dist1_out, p1[1] + m1[1] * dist1_out)
    c2_out = (p2[0] + m2[0] * dist2_out, p2[1] + m2[1] * dist2_out)

    if d_in >= d_max and X is not None:
        poly_pts = [c1_out, c2_out, X]
    else:
        dist1_in = d_in / cos1
        dist2_in = d_in / cos2
        c1_in = (p1[0] + m1[0] * dist1_in, p1[1] + m1[1] * dist1_in)
        c2_in = (p2[0] + m2[0] * dist2_in, p2[1] + m2[1] * dist2_in)
        poly_pts = [c1_out, c2_out, c2_in, c1_in]

    return _ensure_ccw(poly_pts)


def _safe_miter_hole_polygon(
    poly: List[Tuple[float, float]],
    i: int,
    d_out: float,
    d_in: float,
) -> List[Tuple[float, float]]:
    """Generuje wielokąt bordiury lub cokołu wokół wewnętrznego otworu (kolumny/kominka).
    
    Wielokąt otworu ma orientację CCW. Wnętrze otworu znajduje się po lewej stronie,
    a podłoga (pokój) po prawej stronie. Normalna rozszerzająca się na zewnątrz
    otworu w stronę pokoju wynosi (dy/L, -dx/L).
    """
    n = len(poly)
    prev_i = (i - 1) % n
    nxt_i = (i + 1) % n
    nxt2_i = (i + 2) % n

    p_prev = poly[prev_i]
    p1 = poly[i]
    p2 = poly[nxt_i]
    p_next = poly[nxt2_i]

    v = (p2[0] - p1[0], p2[1] - p1[1])
    L = math.hypot(*v)
    if L < 1e-6:
        return []
    d_wall = (v[0] / L, v[1] / L)
    # Wektor normalny na zewnątrz otworu (w stronę pokoju) dla pętli CCW:
    n_wall = (d_wall[1], -d_wall[0])

    # Dwusieczna w wierzchołku p1
    v_prev = (p1[0] - p_prev[0], p1[1] - p_prev[1])
    L_prev = math.hypot(*v_prev)
    d_prev = (v_prev[0] / L_prev, v_prev[1] / L_prev) if L_prev > 1e-6 else d_wall
    n_prev = (d_prev[1], -d_prev[0])
    nb1 = (n_prev[0] + n_wall[0], n_prev[1] + n_wall[1])
    lb1 = math.hypot(*nb1)
    m1 = (nb1[0] / lb1, nb1[1] / lb1) if lb1 > 1e-6 else n_wall

    # Dwusieczna w wierzchołku p2
    v_next = (p_next[0] - p2[0], p_next[1] - p2[1])
    L_next = math.hypot(*v_next)
    d_next = (v_next[0] / L_next, v_next[1] / L_next) if L_next > 1e-6 else d_wall
    n_next = (d_next[1], -d_next[0])
    nb2 = (n_wall[0] + n_next[0], n_wall[1] + n_next[1])
    lb2 = math.hypot(*nb2)
    m2 = (nb2[0] / lb2, nb2[1] / lb2) if lb2 > 1e-6 else n_wall

    cos1 = n_wall[0] * m1[0] + n_wall[1] * m1[1]
    cos2 = n_wall[0] * m2[0] + n_wall[1] * m2[1]
    # Ochrona przed nieskończonymi szpicami przy ostrych kątach (Miter Limit)
    if abs(cos1) < 0.2:
        cos1 = 0.2 if cos1 >= 0 else -0.2
    if abs(cos2) < 0.2:
        cos2 = 0.2 if cos2 >= 0 else -0.2

    # Wykrywanie zbieżności promieni dwusiecznych (wygaszanie krawędzi)
    t1, u2 = _ray_intersection_2d(p1, m1, p2, m2)
    d_max = 999999.0
    X = None
    if t1 is not None and t1 > 1e-6 and u2 > 1e-6:
        cand_X = (p1[0] + t1 * m1[0], p1[1] + t1 * m1[1])
        cand_depth = (cand_X[0] - p1[0]) * n_wall[0] + (cand_X[1] - p1[1]) * n_wall[1]
        if cand_depth > 1e-6:
            d_max = cand_depth
            X = cand_X

    if d_out >= d_max - 1e-6:
        return []

    dist1_out = d_out / cos1
    dist2_out = d_out / cos2
    c1_out = (p1[0] + m1[0] * dist1_out, p1[1] + m1[1] * dist1_out)
    c2_out = (p2[0] + m2[0] * dist2_out, p2[1] + m2[1] * dist2_out)

    if d_in >= d_max and X is not None:
        poly_pts = [c1_out, c2_out, X]
    else:
        dist1_in = d_in / cos1
        dist2_in = d_in / cos2
        c1_in = (p1[0] + m1[0] * dist1_in, p1[1] + m1[1] * dist1_in)
        c2_in = (p2[0] + m2[0] * dist2_in, p2[1] + m2[1] * dist2_in)
        poly_pts = [c1_out, c2_out, c2_in, c1_in]

    return _ensure_ccw(poly_pts)


def _row_spans(
    u_min: float, u_max: float, col_pitch: float, plank_l: float, u_offset: float, continuous: bool
) -> List[Tuple[float, float]]:
    """Zakresy [u0, u1] desek w jednym rzędzie (wzory wzdłużne i szerokości mieszane)."""
    if continuous:
        return [(u_min - 0.1, u_max + 0.1)]
    spans = []
    u_start = u_min - col_pitch + u_offset
    col_idx = 0
    while True:
        u0 = u_start + col_idx * col_pitch
        u1 = u0 + plank_l
        col_idx += 1
        if u0 > u_max + 0.1:
            break
        if u1 < u_min - 0.1:
            continue
        spans.append((u0, u1))
    return spans


# ===========================================================================
# Konstrukcja brył 3D (Solid Mesh) i Komponentów
# ===========================================================================

def _polygon_normal_3d(pts: List[QVector3D]) -> QVector3D:
    """Oblicza jednostkowy wektor normalny wielokąta 3D metodą Newella."""
    n = len(pts)
    nx, ny, nz = 0.0, 0.0, 0.0
    for i in range(n):
        cur = pts[i]
        nxt = pts[(i + 1) % n]
        nx += (cur.y() - nxt.y()) * (cur.z() + nxt.z())
        ny += (cur.z() - nxt.z()) * (cur.x() + nxt.x())
        nz += (cur.x() - nxt.x()) * (cur.y() + nxt.y())
    vec = QVector3D(nx, ny, nz)
    if vec.length() > 1e-6:
        return vec.normalized()
    return QVector3D(0.0, 0.0, 1.0)


def _derive_plane_basis(normal: QVector3D, angle_deg: float) -> Tuple[QVector3D, QVector3D, QVector3D]:
    """Oblicza ortonormalną bazę (U, V, N) na płaszczyźnie, obróconą o angle_deg."""
    n = normal.normalized()
    ref = QVector3D(1.0, 0.0, 0.0)
    if abs(QVector3D.dotProduct(ref, n)) > 0.95:
        ref = QVector3D(0.0, 1.0, 0.0)

    u0 = (ref - n * QVector3D.dotProduct(ref, n)).normalized()
    v0 = QVector3D.crossProduct(n, u0).normalized()

    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    u = (u0 * cos_a + v0 * sin_a).normalized()
    v = (v0 * cos_a - u0 * sin_a).normalized()

    return u, v, n


def _add_prism(mesh: Mesh, bot: List[QVector3D], top: List[QVector3D], color) -> None:
    """Dokłada do siatki zamknięty graniastosłup (normalne na zewnątrz).

    ``color`` = None → ściany bez własnego koloru (prototyp komponentu, kolor
    przychodzi z ``Group.material`` instancji). Każda ściana dostaje WŁASNY słownik
    ``attrs`` (malowanie pojedynczej ściany nie może przemalować sąsiednich).
    """
    col = list(color[:3]) if color is not None else None

    def mk(loop):
        f = mesh.add_face(loop)
        if col is not None:
            f.attrs = {"color": list(col)}

    mk(top)                       # góra (+N)
    mk(list(reversed(bot)))       # dół (-N)
    m = len(bot)
    for i in range(m):            # boki
        nxt = (i + 1) % m
        mk([bot[i], bot[nxt], top[nxt], top[i]])


def _add_plank_solid_to_mesh(
    mesh: Mesh,
    poly_2d: List[Tuple[float, float]],
    origin: QVector3D,
    u_axis: QVector3D,
    v_axis: QVector3D,
    n_axis: QVector3D,
    thickness: float,
    color_rgb,
) -> None:
    """Tworzy zamkniętą, szczelną bryłę 3D (współrzędne świata) dla pojedynczej deski."""
    poly_2d = _ensure_ccw(poly_2d)
    bot_pts = [origin + u_axis * u + v_axis * v for u, v in poly_2d]
    off = n_axis * thickness
    top_pts = [pt + off for pt in bot_pts]
    _add_prism(mesh, bot_pts, top_pts, color_rgb)


def _make_cut_plank_group(
    piece: List[Tuple[float, float]],
    origin: QVector3D,
    u_axis: QVector3D,
    v_axis: QVector3D,
    n_axis: QVector3D,
    thickness: float,
    color_rgb,
    name: str = "Plank (cut)",
) -> Group:
    """Tworzy podgrupę (siatka w układzie świata) dla unikalnego elementu."""
    mesh = Mesh()
    _add_plank_solid_to_mesh(mesh, piece, origin, u_axis, v_axis, n_axis, thickness, color_rgb)
    grp = Group(mesh=mesh, name=name)
    grp.component = False
    return grp


# ---------------------------------------------------------------------------
# Komponenty: rozpoznawanie identycznych kształtów niezależnie od położenia/obrotu
# ---------------------------------------------------------------------------

#: Kwantyzacja przy porównywaniu kształtów: 0.1 mm (tolerancja spawania IngeTrazo)
#: i ~0.006° – różnice poniżej tego progu są niewidoczne, a łapią szum numeryczny.
_Q_LEN = 1e-4
_Q_ANG = 1e-4
#: Liczba dyskretnych odcieni drewna. Renderer IngeTrazo „wypieka” prototyp raz
#: na parę (siatka, materiał instancji), więc ciągły losowy odcień = osobny wypiek
#: dla KAŻDEJ deski. 7 poziomów wygląda naturalnie i ogranicza koszt do 7 wypieków.
_N_SHADES = 7


def _group_supports_material() -> bool:
    """Czy ta wersja IngeTrazo ma ``Group.material`` (malowanie instancji, issue #47)."""
    if "material" in getattr(Group, "__slots__", ()):
        return True
    try:
        return hasattr(Group(), "material")
    except Exception:
        return False


_HAS_GROUP_MATERIAL = _group_supports_material()


def _shade_palette(base, var_pct: float, n: int = _N_SHADES) -> List[List[float]]:
    """Dyskretna paleta odcieni wokół koloru bazowego (±var_pct)."""
    if var_pct <= 1e-4 or n < 2:
        return [[round(c, 4) for c in base]]
    out = []
    for i in range(n):
        d = -var_pct + (2.0 * var_pct * i) / (n - 1)
        out.append([round(min(1.0, max(0.0, c * (1.0 + d))), 4) for c in base])
    return out


def _clean_poly(pts, eps: float = 1e-7) -> List[Tuple[float, float]]:
    """Usuwa zdublowane i współliniowe wierzchołki (boolean 2D potrafi je zostawić,
    a rozbiłyby rozpoznawanie identycznych kształtów)."""
    out: List[Tuple[float, float]] = []
    for p in pts:
        x, y = float(p[0]), float(p[1])
        if not out or abs(x - out[-1][0]) > eps or abs(y - out[-1][1]) > eps:
            out.append((x, y))
    while len(out) > 1 and abs(out[0][0] - out[-1][0]) <= eps and abs(out[0][1] - out[-1][1]) <= eps:
        out.pop()
    i = 0
    while len(out) > 3 and i < len(out):
        a = out[i - 1]
        b = out[i]
        c = out[(i + 1) % len(out)]
        abx, aby = b[0] - a[0], b[1] - a[1]
        bcx, bcy = c[0] - b[0], c[1] - b[1]
        la = math.hypot(abx, aby)
        lb = math.hypot(bcx, bcy)
        if la < eps or lb < eps or abs(abx * bcy - aby * bcx) <= 1e-6 * la * lb:
            del out[i]
            i = max(i - 1, 0)
        else:
            i += 1
    return out


def _shape_signature(pts: List[Tuple[float, float]]):
    """Kanoniczny podpis wielokąta niezmienniczy względem przesunięcia, obrotu
    i wierzchołka startowego: ciąg (długość krawędzi, kąt skrętu) w minimalnej
    leksykograficznie rotacji. Zwraca (klucz, indeks_startu, kierunek_1_krawędzi)."""
    n = len(pts)
    dirs = []
    lens = []
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        ln = math.hypot(ex, ey)
        lens.append(ln)
        dirs.append((ex / ln, ey / ln))
    seq = []
    for i in range(n):
        ax, ay = dirs[i]
        bx, by = dirs[(i + 1) % n]
        turn = math.atan2(ax * by - ay * bx, ax * bx + ay * by)
        seq.append((int(round(lens[i] / _Q_LEN)), int(round(turn / _Q_ANG))))
    best = min(range(n), key=lambda s: seq[s:] + seq[:s])
    return tuple(seq[best:] + seq[:best]), best, dirs[best]


def _to_local(pts, start: int, dx: float, dy: float) -> List[Tuple[float, float]]:
    """Współrzędne wielokąta w ramce: początek = pts[start], oś X = (dx, dy)."""
    ox, oy = pts[start]
    n = len(pts)
    out = []
    for j in range(n):
        px, py = pts[(start + j) % n]
        rx, ry = px - ox, py - oy
        out.append((rx * dx + ry * dy, -rx * dy + ry * dx))
    return out


def _placement_matrix(o, dx, dy, z_off, origin, u_axis, v_axis, n_axis) -> QMatrix4x4:
    """Macierz lokalne → świat dla instancji (obrót w płaszczyźnie + przesunięcie)."""
    x_ax = u_axis * dx + v_axis * dy
    y_ax = u_axis * (-dy) + v_axis * dx
    pos = origin + u_axis * o[0] + v_axis * o[1] + n_axis * z_off
    mat = QMatrix4x4()
    mat.setColumn(0, QVector4D(x_ax.x(), x_ax.y(), x_ax.z(), 0.0))
    mat.setColumn(1, QVector4D(y_ax.x(), y_ax.y(), y_ax.z(), 0.0))
    mat.setColumn(2, QVector4D(n_axis.x(), n_axis.y(), n_axis.z(), 0.0))
    mat.setColumn(3, QVector4D(pos.x(), pos.y(), pos.z(), 1.0))
    return mat


class _PlankAssembler:
    """Zbiera elementy 2D i buduje z nich grupy / komponenty.

    KAŻDY element (deska pełna, docięta, bordiura, listwa, klepka jodełki…), którego
    kształt i grubość powtarzają się co najmniej dwa razy, staje się instancją
    komponentu ze WSPÓLNYM prototypem siatki – również gdy różni się kolorem
    (odcień ląduje w ``Group.material`` instancji) i obrotem (jodełka, wersal).
    Elementy jednorazowe zostają zwykłymi podgrupami.
    """

    def __init__(self) -> None:
        self._items: list = []

    def add(self, pts, thickness: float, color, kind: str, z_off: float = 0.0) -> None:
        self._items.append((pts, thickness, list(color[:3]), kind, z_off))

    def __len__(self) -> int:
        return len(self._items)

    def build(self, origin, u_axis, v_axis, n_axis, use_components: bool, lang: str):
        """Zwraca (children, single_mesh, liczba_definicji, liczba_instancji)."""
        if not use_components:
            mesh = Mesh()
            for pts, th, col, _kind, z in self._items:
                _add_plank_solid_to_mesh(mesh, pts, origin + n_axis * z, u_axis, v_axis, n_axis, th, col)
            return [], mesh, 0, 0

        buckets: dict = {}
        order: list = []
        for pts, th, col, kind, z in self._items:
            pts = _clean_poly(_ensure_ccw(list(pts)))
            if len(pts) < 3:
                continue
            shape_key, start, (dx, dy) = _shape_signature(pts)
            key = (kind, int(round(th / _Q_LEN)), shape_key)
            if not _HAS_GROUP_MATERIAL:
                key += (tuple(col),)   # stara wersja: kolor musi siedzieć w prototypie
            lst = buckets.get(key)
            if lst is None:
                lst = buckets[key] = []
                order.append(key)
            lst.append((pts, start, dx, dy, th, col, z))

        children: list = []
        n_defs = 0
        n_inst = 0
        single_idx: dict = {}
        for key in order:
            entries = buckets[key]
            kind = key[0]
            kind_name = tr(kind, lang)
            if len(entries) >= 2:
                pts0, s0, dx0, dy0, th0, col0, _z0 = entries[0]
                local = _to_local(pts0, s0, dx0, dy0)
                proto = Mesh()
                bot = [QVector3D(u, v, 0.0) for u, v in local]
                top = [QVector3D(u, v, th0) for u, v in local]
                _add_prism(proto, bot, top, None if _HAS_GROUP_MATERIAL else col0)
                ext_a = max(p[0] for p in local) - min(p[0] for p in local)
                ext_b = max(p[1] for p in local) - min(p[1] for p in local)
                name = tr("item_comp_def", lang, kind=kind_name,
                          l=f"{max(ext_a, ext_b) * 100:.1f}", w=f"{min(ext_a, ext_b) * 100:.1f}")
                n_defs += 1
                for pts, start, dx, dy, _th, col, z in entries:
                    g = Group(mesh=proto, name=name)
                    g.component = True
                    g.xform = _placement_matrix(pts[start], dx, dy, z, origin, u_axis, v_axis, n_axis)
                    if _HAS_GROUP_MATERIAL:
                        g.material = {"color": list(col)}
                    children.append(g)
                    n_inst += 1
            else:
                pts, _s, _dx, _dy, th, col, z = entries[0]
                idx = single_idx[kind] = single_idx.get(kind, 0) + 1
                name = tr("item_single", lang, kind=kind_name, n=idx)
                children.append(_make_cut_plank_group(
                    pts, origin + n_axis * z, u_axis, v_axis, n_axis, th, col, name=name))
        return children, None, n_defs, n_inst


# ===========================================================================
# Generator Wzorów Specjalnych (Versailles & Helpers)
# ===========================================================================

def _make_slat_quad(p1: Tuple[float, float], p2: Tuple[float, float], width: float) -> List[Tuple[float, float]]:
    """Tworzy prostokątną listewkę 2D między punktami p1 i p2 o zadanej szerokości (CCW)."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return []
    nx = -dy / dist * (width / 2.0)
    ny = dx / dist * (width / 2.0)
    return _ensure_ccw([
        (p1[0] - nx, p1[1] - ny),
        (p2[0] - nx, p2[1] - ny),
        (p2[0] + nx, p2[1] + ny),
        (p1[0] + nx, p1[1] + ny),
    ])


def _generate_versailles_tile(u0: float, v0: float, S: float, gap: float) -> List[List[Tuple[float, float]]]:
    """Generuje listę wielokątów tworzących klasyczny kaseton wersalski w module S x S."""
    Wf = S / 8.0
    pieces = []

    # 1. Zewnętrzna miterowana ramka (4 deski)
    pieces.append(_ensure_ccw([(u0, v0), (u0 + S, v0), (u0 + S - Wf, v0 + Wf), (u0 + Wf, v0 + Wf)]))
    pieces.append(_ensure_ccw([(u0, v0 + S), (u0 + Wf, v0 + S - Wf), (u0 + S - Wf, v0 + S - Wf), (u0 + S, v0 + S)]))
    pieces.append(_ensure_ccw([(u0, v0), (u0 + Wf, v0 + Wf), (u0 + Wf, v0 + S - Wf), (u0, v0 + S)]))
    pieces.append(_ensure_ccw([(u0 + S, v0), (u0 + S, v0 + S), (u0 + S - Wf, v0 + S - Wf), (u0 + S - Wf, v0 + Wf)]))

    # 2. Wewnętrzne ukośne listwy tworzące romb
    iu0, iv0 = u0 + Wf, v0 + Wf
    Sin = S - 2.0 * Wf
    Mb = (iu0 + Sin / 2.0, iv0)
    Mr = (iu0 + Sin, iv0 + Sin / 2.0)
    Mt = (iu0 + Sin / 2.0, iv0 + Sin)
    Ml = (iu0, iv0 + Sin / 2.0)
    Wd = Wf * 0.70

    pieces.append(_make_slat_quad(Mb, Mr, Wd))
    pieces.append(_make_slat_quad(Mr, Mt, Wd))
    pieces.append(_make_slat_quad(Mt, Ml, Wd))
    pieces.append(_make_slat_quad(Ml, Mb, Wd))

    # 3. Środkowa plecionka (4 kwadraty wewnątrz rombu)
    cu = iu0 + Sin / 2.0
    cv = iv0 + Sin / 2.0
    half_c = Sin / 4.0
    slat_w = (half_c - gap) / 2.0

    # Ćwiartka TL: poziome
    pieces.append(_ensure_ccw([(cu - half_c, cv), (cu, cv), (cu, cv + slat_w), (cu - half_c, cv + slat_w)]))
    pieces.append(_ensure_ccw([(cu - half_c, cv + slat_w + gap), (cu, cv + slat_w + gap), (cu, cv + 2*slat_w + gap), (cu - half_c, cv + 2*slat_w + gap)]))
    # Ćwiartka TR: pionowe
    pieces.append(_ensure_ccw([(cu, cv), (cu + slat_w, cv), (cu + slat_w, cv + half_c), (cu, cv + half_c)]))
    pieces.append(_ensure_ccw([(cu + slat_w + gap, cv), (cu + 2*slat_w + gap, cv), (cu + 2*slat_w + gap, cv + half_c), (cu + slat_w + gap, cv + half_c)]))
    # Ćwiartka BL: pionowe
    pieces.append(_ensure_ccw([(cu - half_c, cv - half_c), (cu - half_c + slat_w, cv - half_c), (cu - half_c + slat_w, cv), (cu - half_c, cv)]))
    pieces.append(_ensure_ccw([(cu - half_c + slat_w + gap, cv - half_c), (cu, cv - half_c), (cu, cv), (cu - half_c + slat_w + gap, cv)]))
    # Ćwiartka BR: poziome
    pieces.append(_ensure_ccw([(cu, cv - half_c), (cu + half_c, cv - half_c), (cu + half_c, cv - half_c + slat_w), (cu, cv - half_c + slat_w)]))
    pieces.append(_ensure_ccw([(cu, cv - half_c + slat_w + gap), (cu + half_c, cv - half_c + slat_w + gap), (cu + half_c, cv), (cu, cv)]))

    return [p for p in pieces if len(p) >= 3 and _polygon_area_2d(p) > 1e-5]


# ===========================================================================
# Generator Geometrii Podłogi & Zestawienia Materiałowego
# ===========================================================================

def _generate_floor_geometry(
    verts_3d: List[QVector3D],
    normal: QVector3D,
    params: dict,
    holes_3d: List[List[QVector3D]] | None = None,
) -> Tuple[Group, int, dict]:
    """Główny silnik geometryczny generujący podłogę z bordiurą, otworami, wzorem, listwami i kalkulatorem cięć.

    Przebieg (zoptymalizowany):
      1. Wszystkie elementy (deski, bordiura, listwy) są najpierw zbierane jako
         wielokąty 2D w układzie (U, V) płaszczyzny podłogi – bez budowania siatek.
      2. Przycinanie do obrysu: szybkie odrzucanie po bbox + boolean 2D w C++
         (manifold3d/Clipper2 dostarczany z IngeTrazo, ewentualnie shapely).
      3. ``_PlankAssembler`` rozpoznaje elementy o IDENTYCZNYM kształcie i grubości
         (niezależnie od położenia i obrotu) i buduje dla nich JEDEN prototyp siatki
         współdzielony przez instancje komponentu; odcień drewna idzie w
         ``Group.material`` instancji, więc różny kolor nie rozbija komponentu.
    """
    lang = params.get("lang", "en")
    params = _merged_params(params)
    origin = verts_3d[0]
    u_axis, v_axis, n_axis = _derive_plane_basis(normal, params["angle_deg"])

    # 1. Zewnętrzny obrys w układzie 2D (U, V)
    room_poly_2d = []
    for pt in verts_3d:
        diff = pt - origin
        room_poly_2d.append((QVector3D.dotProduct(diff, u_axis), QVector3D.dotProduct(diff, v_axis)))
    room_poly_2d = _clean_poly(_ensure_ccw(room_poly_2d))
    if len(room_poly_2d) < 3:
        raise ValueError("Obrys podłogi jest zdegenerowany (mniej niż 3 niezależne wierzchołki).")

    # 2. Otwory wewnętrzne (słupy, kominki, wycięcia) w układzie 2D (U, V)
    holes_2d = []
    for h_loop in (holes_3d or []):
        h_pts = []
        for pt in h_loop:
            diff = pt - origin
            h_pts.append((QVector3D.dotProduct(diff, u_axis), QVector3D.dotProduct(diff, v_axis)))
        h_pts = _clean_poly(_ensure_ccw(h_pts))
        if len(h_pts) >= 3 and _polygon_area_2d(h_pts) > 1e-5:
            holes_2d.append(h_pts)

    plank_w = params["plank_w_cm"] / 100.0
    plank_l = params["plank_l_cm"] / 100.0 if params["plank_l_cm"] > 0 else 0.0
    thickness = params["thickness_mm"] / 1000.0
    gap = params["gap_mm"] / 1000.0
    pattern_key = normalize_pattern(params.get("pattern", params.get("stagger_mode", "pat_half")))
    wood_key = normalize_wood(params.get("wood_type", "wood_oak"))
    base_color = WOOD_COLORS.get(wood_key, (0.76, 0.58, 0.40))
    var_pct = params["color_var_pct"] / 100.0
    use_components = params.get("use_components", True)

    use_border = params.get("use_border", False)
    use_hole_border = params.get("use_hole_border", True)
    border_planks = int(params.get("border_planks", 1))
    border_plank_w = params.get("border_plank_w_cm", params["plank_w_cm"]) / 100.0

    rng = random.Random(42)
    palette = _shade_palette(base_color, var_pct)
    asm = _PlankAssembler()

    def shade():
        return palette[rng.randrange(len(palette))] if len(palette) > 1 else palette[0]

    # Statystyki do kalkulatora cięć i raportu BOM
    full_planks_count = 0
    cut_planks_count = 0
    border_planks_count = 0
    hole_border_planks_count = 0
    total_plank_len_m = 0.0
    skirting_count = 0
    skirting_total_len_m = 0.0

    # 3. Bordiura zewnętrzna (wzdłuż ścian obwodowych)
    if use_border and border_planks > 0:
        n_pts = len(room_poly_2d)
        for b in range(border_planks):
            d_out = b * (border_plank_w + gap)
            d_in = d_out + border_plank_w
            for i in range(n_pts):
                p1 = room_poly_2d[i]
                p2 = room_poly_2d[(i + 1) % n_pts]
                b_poly = _safe_miter_polygon(room_poly_2d, i, d_out, d_in)
                if len(b_poly) >= 3 and _polygon_area_2d(b_poly) > 1e-5:
                    asm.add(b_poly, thickness, shade(), "kind_border")
                    border_planks_count += 1
                    total_plank_len_m += math.hypot(p2[0] - p1[0], p2[1] - p1[1])

    # 4. Bordiura wewnętrzna (wokół słupów i otworów)
    if use_border and use_hole_border and border_planks > 0 and holes_2d:
        for hole_poly in holes_2d:
            n_h = len(hole_poly)
            for b in range(border_planks):
                d_out = b * (border_plank_w + gap)
                d_in = d_out + border_plank_w
                for i in range(n_h):
                    p1 = hole_poly[i]
                    p2 = hole_poly[(i + 1) % n_h]
                    b_poly = _safe_miter_hole_polygon(hole_poly, i, d_out, d_in)
                    if len(b_poly) >= 3 and _polygon_area_2d(b_poly) > 1e-5:
                        asm.add(b_poly, thickness, shade(), "kind_border")
                        border_planks_count += 1
                        hole_border_planks_count += 1
                        total_plank_len_m += math.hypot(p2[0] - p1[0], p2[1] - p1[1])

    # 5. Pole wypełnienia wzorem (obrys - bordiura - otwory) jako rozłączne części
    border_depth = border_planks * (border_plank_w + gap) if (use_border and border_planks > 0) else 0.0
    hole_depth = border_depth if use_hole_border else 0.0
    infill_parts = _infill_parts(room_poly_2d, holes_2d, border_depth, hole_depth)

    continuous = (plank_l <= 0.0)

    def emit(target: "_ClipTarget", pts, kind: str, length_m: float) -> None:
        """Przycina element do obrysu i dodaje kawałki do montażu."""
        nonlocal full_planks_count, cut_planks_count, total_plank_len_m
        pieces, uncut = target.clip(pts)
        for piece in pieces:
            asm.add(piece, thickness, shade(), kind)
            if uncut:
                full_planks_count += 1
            else:
                cut_planks_count += 1
            total_plank_len_m += length_m

    # 6. Generowanie wzoru podłogi
    for target in infill_parts:
        u_min, v_min, u_max, v_max = target.bounds

        # A) JODEŁKA KLASYCZNA (1x Single), PODWÓJNA (2x Double) i POTRÓJNA (3x Triple)
        if pattern_key in ("pat_herringbone", "pat_herringbone_double", "pat_herringbone_triple"):
            k_pack = {"pat_herringbone_double": 2, "pat_herringbone_triple": 3}.get(pattern_key, 1)

            eff_w = plank_w
            eff_l = plank_l if plank_l > 0 else (eff_w * 4.0 * k_pack)
            w_arm = k_pack * eff_w + (k_pack - 1) * gap
            l_arm = eff_l

            sx = w_arm + gap
            sy = l_arm + gap
            cos45 = math.cos(math.radians(45))
            sin45 = math.sin(math.radians(45))

            corners = [(u_min, v_min), (u_max, v_min), (u_max, v_max), (u_min, v_max)]
            rot_pts = [(u * cos45 + v * sin45, -u * sin45 + v * cos45) for u, v in corners]
            rx_min, rx_max = min(p[0] for p in rot_pts), max(p[0] for p in rot_pts)
            ry_min, ry_max = min(p[1] for p in rot_pts), max(p[1] for p in rot_pts)

            i_min = int(math.floor((rx_min + ry_min) / (2.0 * sx))) - 2
            i_max = int(math.ceil((rx_max + ry_max) / (2.0 * sx))) + 2
            j_min = int(math.floor((rx_min - ry_max) / (2.0 * sy))) - 2
            j_max = int(math.ceil((rx_max - ry_min) / (2.0 * sy))) + 2

            def rot(pts):
                return [(px * cos45 - py * sin45, px * sin45 + py * cos45) for px, py in pts]

            for i in range(i_min, i_max + 1):
                for j in range(j_min, j_max + 1):
                    dx = i * sx + j * sy
                    dy = i * sx - j * sy
                    # Ramię 1 (poziome w układzie 45°)
                    for m in range(k_pack):
                        ya = dy + m * (eff_w + gap)
                        yb = ya + eff_w
                        emit(target, rot([(dx, ya), (dx + l_arm, ya), (dx + l_arm, yb), (dx, yb)]),
                             "kind_herringbone", eff_l)
                    # Ramię 2 (pionowe w układzie 45°)
                    for m in range(k_pack):
                        xa = dx + m * (eff_w + gap)
                        xb = xa + eff_w
                        ya = dy + w_arm + gap
                        yb = ya + l_arm
                        emit(target, rot([(xa, ya), (xb, ya), (xb, yb), (xa, yb)]),
                             "kind_herringbone", eff_l)

        # B) JODEŁKA FRANCUSKA (Chevron 45°)
        elif pattern_key == "pat_chevron":
            eff_l = plank_l if plank_l > 0 else 0.50
            eff_w = plank_w
            c45 = math.cos(math.radians(45))
            s45 = math.sin(math.radians(45))
            wx = eff_l * c45
            hy = eff_l * s45
            v_plank = eff_w / c45

            col_step = 2.0 * wx + gap
            row_step = v_plank + gap

            c_min = int(math.floor(u_min / col_step)) - 1
            c_max = int(math.ceil(u_max / col_step)) + 1
            r_min = int(math.floor((v_min - hy) / row_step)) - 1
            r_max = int(math.ceil((v_max + hy) / row_step)) + 1

            for c_idx in range(c_min, c_max + 1):
                u_col = c_idx * col_step
                for r_idx in range(r_min, r_max + 1):
                    v_row = r_idx * row_step
                    emit(target, [
                        (u_col, v_row),
                        (u_col + wx, v_row + hy),
                        (u_col + wx, v_row + hy + v_plank),
                        (u_col, v_row + v_plank),
                    ], "kind_chevron", eff_l)
                    emit(target, [
                        (u_col + wx + gap, v_row + hy),
                        (u_col + 2.0 * wx + gap, v_row),
                        (u_col + 2.0 * wx + gap, v_row + v_plank),
                        (u_col + wx + gap, v_row + hy + v_plank),
                    ], "kind_chevron", eff_l)

        # C) KASETONY WERSALSKIE (Versailles Parquet)
        elif pattern_key == "pat_versailles":
            tile_s = plank_l if plank_l >= 0.40 else 0.80
            c_min = int(math.floor(u_min / (tile_s + gap))) - 1
            c_max = int(math.ceil(u_max / (tile_s + gap))) + 1
            r_min = int(math.floor(v_min / (tile_s + gap))) - 1
            r_max = int(math.ceil(v_max / (tile_s + gap))) + 1

            for c_idx in range(c_min, c_max + 1):
                u0 = c_idx * (tile_s + gap)
                for r_idx in range(r_min, r_max + 1):
                    v0 = r_idx * (tile_s + gap)
                    # Szybkie odrzucenie całego kasetonu poza obrysem
                    if u0 > u_max or u0 + tile_s < u_min or v0 > v_max or v0 + tile_s < v_min:
                        continue
                    for slat_poly in _generate_versailles_tile(u0, v0, tile_s, gap):
                        emit(target, slat_poly, "kind_versailles", tile_s * 0.4)

        # D) SZEROKOŚCI MIESZANE (Mixed / Random Widths)
        elif pattern_key == "pat_mixed_widths":
            w_cycle = [plank_w * 0.75, plank_w * 1.35, plank_w * 1.0, plank_w * 0.80, plank_w * 1.25]
            col_pitch = (plank_l + gap) if not continuous else (u_max - u_min + 1.0)
            v_curr = v_min
            row_idx = 0

            while v_curr <= v_max:
                row_w = w_cycle[row_idx % len(w_cycle)]
                v0 = v_curr
                v1 = v0 + row_w
                v_curr = v1 + gap
                row_idx += 1

                u_offset = rng.uniform(0.0, col_pitch)
                for u0, u1 in _row_spans(u_min, u_max, col_pitch, plank_l, u_offset, continuous):
                    emit(target, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], "kind_plank", u1 - u0)

        # E) KOSZYKOWY / SZACHOWNICA (Basketweave)
        elif pattern_key == "pat_basket":
            eff_l = plank_l if plank_l > 0 else (plank_w * 4)
            nb = max(2, int(round(eff_l / plank_w)))
            mod_s = nb * plank_w + (nb - 1) * gap

            c_min = int(math.floor(u_min / (mod_s + gap))) - 1
            c_max = int(math.ceil(u_max / (mod_s + gap))) + 1
            r_min = int(math.floor(v_min / (mod_s + gap))) - 1
            r_max = int(math.ceil(v_max / (mod_s + gap))) + 1

            for c_idx in range(c_min, c_max + 1):
                u0 = c_idx * (mod_s + gap)
                for r_idx in range(r_min, r_max + 1):
                    v0 = r_idx * (mod_s + gap)
                    is_horiz = (c_idx + r_idx) % 2 == 0
                    for k in range(nb):
                        if is_horiz:
                            ua, ub = u0, u0 + mod_s
                            va = v0 + k * (plank_w + gap)
                            vb = va + plank_w
                        else:
                            ua = u0 + k * (plank_w + gap)
                            ub = ua + plank_w
                            va, vb = v0, v0 + mod_s
                        emit(target, [(ua, va), (ub, va), (ub, vb), (ua, vb)], "kind_square", mod_s)

        # F) WZORY WZDŁUŻNE (1/2, 1/3, Random, Straight, Continuous)
        else:
            row_pitch = plank_w + gap
            col_pitch = (plank_l + gap) if not continuous else (u_max - u_min + 1.0)
            n_rows = math.ceil((v_max - v_min) / row_pitch) + 1

            for row_idx in range(n_rows):
                v0 = v_min + row_idx * row_pitch
                v1 = v0 + plank_w
                if v0 > v_max:
                    break

                if continuous or pattern_key == "pat_straight":
                    u_offset = 0.0
                elif pattern_key == "pat_half":
                    u_offset = (row_idx * (col_pitch * 0.5)) % col_pitch
                elif pattern_key == "pat_third":
                    u_offset = (row_idx * (col_pitch / 3.0)) % col_pitch
                elif pattern_key == "pat_random":
                    u_offset = rng.uniform(0.0, col_pitch)
                else:
                    u_offset = 0.0

                for u0, u1 in _row_spans(u_min, u_max, col_pitch, plank_l, u_offset, continuous):
                    emit(target, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], "kind_plank", u1 - u0)

    # 7. Listwy przypodłogowe (Skirting boards wzdłuż ścian i wokół słupów)
    if params.get("use_skirting", False):
        skirting_h = params.get("skirting_h_cm", 8.0) / 100.0
        skirting_th = params.get("skirting_th_mm", 15.0) / 1000.0
        skirting_col = [0.95, 0.95, 0.95] if params.get("skirting_color", "wood") == "white" else list(base_color)

        n_pts = len(room_poly_2d)
        for i in range(n_pts):
            p1 = room_poly_2d[i]
            p2 = room_poly_2d[(i + 1) % n_pts]
            seg_len = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if seg_len < 1e-4:
                continue
            skirt_poly = _safe_miter_polygon(room_poly_2d, i, d_out=0.0, d_in=skirting_th)
            if len(skirt_poly) >= 3 and _polygon_area_2d(skirt_poly) > 1e-5:
                asm.add(skirt_poly, skirting_h, skirting_col, "kind_skirting", z_off=thickness)
                skirting_count += 1
                skirting_total_len_m += seg_len

        if params.get("skirting_holes", True) and holes_2d:
            for hole_poly in holes_2d:
                n_h = len(hole_poly)
                for i in range(n_h):
                    p1 = hole_poly[i]
                    p2 = hole_poly[(i + 1) % n_h]
                    seg_len = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                    if seg_len < 1e-4:
                        continue
                    skirt_poly = _safe_miter_hole_polygon(hole_poly, i, d_out=0.0, d_in=skirting_th)
                    if len(skirt_poly) >= 3 and _polygon_area_2d(skirt_poly) > 1e-5:
                        asm.add(skirt_poly, skirting_h, skirting_col, "kind_skirting", z_off=thickness)
                        skirting_count += 1
                        skirting_total_len_m += seg_len

    # 8. Budowa grup / komponentów
    grp_name = tr("group_name", lang)
    children, single_mesh, comp_defs, comp_inst = asm.build(
        origin, u_axis, v_axis, n_axis, use_components, lang
    )
    if use_components:
        floor_group = Group(name=grp_name)
        floor_group.adopt(children)
    else:
        floor_group = Group(single_mesh, name=grp_name)
    # Zawsze macierz położenia (także dla trybu jednej siatki): Move/Rotate całej
    # podłogi trafia w xform, więc późniejsza przebudowa zostaje tam, gdzie podłoga stoi.
    if floor_group.xform is None:
        floor_group.xform = QMatrix4x4()
    floor_group.component = False
    floor_group.ifc = {"class": "IfcCovering", "name": grp_name}

    # 9. Obliczenie pełnego raportu materiałowego (BOM) z uwzględnieniem otworów
    raw_room_area = _polygon_area_2d(room_poly_2d)
    total_holes_area = sum(_polygon_area_2d(h) for h in holes_2d)
    room_area = max(0.0, raw_room_area - total_holes_area)

    if pattern_key in ("pat_straight", "pat_half", "pat_third"):
        waste_pct = 7.0
    elif pattern_key in ("pat_random", "pat_mixed_widths"):
        waste_pct = 8.0
    elif pattern_key in ("pat_herringbone", "pat_herringbone_double", "pat_herringbone_triple"):
        waste_pct = 12.0
    elif pattern_key == "pat_chevron":
        waste_pct = 15.0
    elif pattern_key == "pat_versailles":
        waste_pct = 10.0
    else:
        waste_pct = 7.0

    if abs(params.get("angle_deg", 0.0)) > 0.01:
        waste_pct += 3.0

    order_area = room_area * (1.0 + waste_pct / 100.0)
    pw = params.get("plank_w_cm", 14.0)
    pl = params.get("plank_l_cm", 120.0)
    pth = params.get("thickness_mm", 20.0)
    dims_str = f"{pw:.1f} x {pl:.1f} x {pth/10.0:.1f} cm"
    total_planks = full_planks_count + cut_planks_count + border_planks_count

    report_data = {
        "room_area_m2": room_area,
        "raw_room_area_m2": raw_room_area,
        "flooring_area_m2": room_area,
        "holes_count": len(holes_2d),
        "holes_area_m2": total_holes_area,
        "pattern_key": pattern_key,
        "pattern_name": tr(pattern_key, lang),
        "wood_key": wood_key,
        "wood_name": tr(wood_key, lang),
        "plank_dims_str": dims_str,
        "full_planks_count": full_planks_count,
        "cut_planks_count": cut_planks_count,
        "border_planks_count": border_planks_count,
        "hole_border_planks_count": hole_border_planks_count,
        "total_planks_count": total_planks,
        "total_linear_m": total_plank_len_m,
        "skirting_count": skirting_count,
        "skirting_linear_m": skirting_total_len_m,
        "waste_pct": waste_pct,
        "recommended_order_m2": order_area,
        "component_defs": comp_defs,
        "component_instances": comp_inst,
        "geometry_backend": _BACKEND,
    }

    return floor_group, total_planks, report_data


# ===========================================================================
# Ekstrakcja otworów ze ścian i grupowanie płaszczyzn współpłaszczyznowych
# ===========================================================================

def _to_qvector3d(pt: Any) -> QVector3D:
    """Konwertuje obiekt punktu (QVector3D, Vertex z .position, tuple/list) do czystego QVector3D."""
    if hasattr(pt, "position"):
        pt = pt.position
    if hasattr(pt, "x") and callable(pt.x):
        return QVector3D(float(pt.x()), float(pt.y()), float(pt.z()))
    elif hasattr(pt, "x"):
        return QVector3D(float(pt.x), float(pt.y), float(pt.z))
    elif isinstance(pt, (tuple, list)) and len(pt) >= 3:
        return QVector3D(float(pt[0]), float(pt[1]), float(pt[2]))
    return QVector3D(0.0, 0.0, 0.0)


def _extract_face_outer_and_holes(face: Face) -> Tuple[List[QVector3D], List[List[QVector3D]]]:
    """Ekstrahuje zewnętrzny obrys oraz wewnętrzne otwory ze ściany IngeTrazo."""
    outer: List[QVector3D] = []
    if hasattr(face, "vertices") and face.vertices:
        outer = [_to_qvector3d(p) for p in face.vertices]
    elif hasattr(face, "loop") and face.loop:
        outer = [_to_qvector3d(p) for p in face.loop]

    holes: List[List[QVector3D]] = []
    h_sources = []
    if hasattr(face, "holes") and face.holes:
        h_sources.extend(face.holes)
    if hasattr(face, "hole_loops") and face.hole_loops:
        h_sources.extend(face.hole_loops)

    for h in h_sources:
        if h and len(h) >= 3:
            holes.append([_to_qvector3d(p) for p in h])

    return outer, holes


def _resolve_rooms_and_holes(faces: List[Face]) -> List[Tuple[List[QVector3D], QVector3D, List[List[QVector3D]]]]:
    """Grupując zaznaczone płaszczyzny współpłaszczyznowe, automatycznie rozpoznaje mniejsze płaszczyzny wewnątrz jako otwory/słupy.
    
    Zwraca listę krotek: (room_verts_3d, room_normal, room_holes_3d)
    """
    if not faces:
        return []

    if len(faces) == 1:
        outer, native_holes = _extract_face_outer_and_holes(faces[0])
        if len(outer) < 3:
            return []
        return [(outer, faces[0].normal(), native_holes)]

    # 1. Klastrowanie według równania płaszczyzny: n * x - d = 0
    clusters: List[dict] = []
    for f in faces:
        outer, native_holes = _extract_face_outer_and_holes(f)
        if len(outer) < 3:
            continue
        n = f.normal().normalized()
        d = QVector3D.dotProduct(outer[0], n)
        placed = False
        for cl in clusters:
            if abs(QVector3D.dotProduct(n, cl['normal'])) > 0.99 and abs(d - cl['d']) < 0.005:
                cl['faces'].append(f)
                placed = True
                break
        if not placed:
            clusters.append({'normal': n, 'd': d, 'faces': [f]})

    resolved: List[Tuple[List[QVector3D], QVector3D, List[List[QVector3D]]]] = []

    # 2. Dla każdego klastra płaszczyzn sprawdzamy relację zawierania (pokój vs otwór)
    for cl in clusters:
        cl_faces = cl['faces']
        normal = cl['normal']
        first_outer, _ = _extract_face_outer_and_holes(cl_faces[0])
        if not first_outer:
            continue
        origin = first_outer[0]
        u_axis, v_axis, _ = _derive_plane_basis(normal, 0.0)

        face_infos = []
        for f in cl_faces:
            outer, native_holes = _extract_face_outer_and_holes(f)
            pts_2d = []
            for p in outer:
                diff = p - origin
                pts_2d.append((QVector3D.dotProduct(diff, u_axis), QVector3D.dotProduct(diff, v_axis)))
            pts_2d = _ensure_ccw(pts_2d)

            face_infos.append({
                'outer_3d': outer,
                'native_holes_3d': native_holes,
                'pts': pts_2d,
                'area': _polygon_area_2d(pts_2d),
            })

        # Sortujemy od największej powierzchni (potencjalne obrysy pokoju) do najmniejszej (słupy/otwory)
        face_infos.sort(key=lambda item: item['area'], reverse=True)

        rooms: List[dict] = []
        for info in face_infos:
            is_hole = False
            for r in rooms:
                if _poly_inside_poly(info['pts'], r['pts']):
                    r['holes_3d'].append(info['outer_3d'])
                    r['holes_3d'].extend(info['native_holes_3d'])
                    is_hole = True
                    break
            if not is_hole:
                rooms.append({
                    'outer_3d': info['outer_3d'],
                    'normal': normal,
                    'holes_3d': list(info['native_holes_3d']),
                    'pts': info['pts'],
                })

        for r in rooms:
            resolved.append((r['outer_3d'], r['normal'], r['holes_3d']))

    return resolved


def generate_floor_for_face(
    face_or_verts: Face | List[QVector3D],
    params: dict,
    normal: QVector3D | None = None,
    holes_3d: List[List[QVector3D]] | None = None,
) -> Tuple[Group, int, dict]:
    """Generuje nową podłogę na płaszczyźnie lub liście wierzchołków z obsługą otworów wewnętrznych."""
    if isinstance(face_or_verts, Face):
        verts_3d, native_holes = _extract_face_outer_and_holes(face_or_verts)
        face_normal = normal or face_or_verts.normal()
        all_holes = list(native_holes)
        if holes_3d:
            all_holes.extend(holes_3d)
    else:
        verts_3d = list(face_or_verts)
        face_normal = normal or _polygon_normal_3d(verts_3d)
        all_holes = list(holes_3d or [])

    if len(verts_3d) < 3:
        raise ValueError("Zaznaczona powierzchnia ma mniej niż 3 wierzchołki.")

    floor_group, count, report = _generate_floor_geometry(verts_3d, face_normal, params, holes_3d=all_holes)

    floor_group.ext = {
        KEY: {
            "params": dict(params),
            "outline_3d": [[float(p.x()), float(p.y()), float(p.z())] for p in verts_3d],
            "normal_3d": [float(face_normal.x()), float(face_normal.y()), float(face_normal.z())],
            "holes_3d": [
                [[float(p.x()), float(p.y()), float(p.z())] for p in h]
                for h in all_holes
            ],
            "report": dict(report),
        }
    }
    return floor_group, count, report


def _rebuild_geometry(floor_group: Group, params: dict) -> Tuple[Group, int, dict]:
    """Liczy nową geometrię dla istniejącej podłogi (bez modyfikowania sceny)."""
    data = (getattr(floor_group, "ext", None) or {}).get(KEY)
    if not data or "outline_3d" not in data or "normal_3d" not in data:
        raise ValueError("Ta grupa nie zawiera wymaganych danych geometrii do przebudowy.")

    outline_3d = [QVector3D(*p) for p in data["outline_3d"]]
    normal_3d = QVector3D(*data["normal_3d"])
    holes_3d = [[QVector3D(*p) for p in h] for h in data.get("holes_3d", [])]
    return _generate_floor_geometry(outline_3d, normal_3d, params, holes_3d=holes_3d)


def _apply_rebuild(floor_group: Group, new_group: Group, params: dict, report: dict) -> None:
    """Podmienia zawartość podłogi w miejscu – tożsamość, nazwa, warstwa i macierz
    położenia (przesunięcie/obrót całej podłogi) zostają zachowane."""
    data = (getattr(floor_group, "ext", None) or {}).get(KEY) or {}
    xform = floor_group.xform if floor_group.xform is not None else QMatrix4x4()
    floor_group.children = list(new_group.children)
    floor_group.mesh = new_group.mesh if not new_group.children else Mesh()
    floor_group.xform = xform

    ext = dict(floor_group.ext or {})
    ext[KEY] = dict(data, params=dict(params), report=dict(report), holes_3d=data.get("holes_3d", []))
    floor_group.ext = ext


def rebuild_floor(scene, floor_group: Group, params: dict) -> Tuple[int, dict]:
    """Przebudowuje istniejącą grupę podłogi w miejscu z zachowaniem tożsamości obiektu i otworów."""
    new_group, count, report = _rebuild_geometry(floor_group, params)
    _apply_rebuild(floor_group, new_group, params, report)
    return count, report


# ===========================================================================
# Okno Raportu Materiałowego (BOM & CSV Export Dialog)
# ===========================================================================

class FloorReportDialog(QDialog):
    """Zestawienie materiałowe, kalkulator cięć, otworów i naddatków z eksportem do CSV."""

    def __init__(self, parent=None, report: dict = None, lang: str = "en"):
        super().__init__(parent)
        self.report = report or {}
        self.lang = lang
        self.setWindowTitle(tr("rep_title", lang))
        self.resize(480, 640)

        layout = QVBoxLayout(self)

        # 1. Podsumowanie ogólne
        grp_gen = QGroupBox(tr("rep_header_general", lang))
        form_gen = QFormLayout(grp_gen)
        form_gen.addRow(tr("rep_room_area", lang), QLabel(f"<b>{self.report.get('room_area_m2', 0.0):.2f} m²</b>"))
        form_gen.addRow(tr("rep_pattern", lang), QLabel(f"{self.report.get('pattern_name', '-') }"))
        form_gen.addRow(tr("rep_wood", lang), QLabel(f"{self.report.get('wood_name', '-') }"))
        form_gen.addRow(tr("rep_dims", lang), QLabel(f"{self.report.get('plank_dims_str', '-') }"))
        layout.addWidget(grp_gen)

        # 2. Otwory wewnętrzne i słupy (jeśli występują)
        if self.report.get("holes_count", 0) > 0:
            grp_holes = QGroupBox(tr("rep_header_holes", lang))
            form_holes = QFormLayout(grp_holes)
            form_holes.addRow(tr("rep_hole_count", lang), QLabel(f"<b>{self.report.get('holes_count', 0)}</b>"))
            form_holes.addRow(tr("rep_hole_area", lang), QLabel(f"<b>-{self.report.get('holes_area_m2', 0.0):.2f} m²</b>"))
            layout.addWidget(grp_holes)

        # 3. Liczba elementów podłogi
        grp_plk = QGroupBox(tr("rep_header_planks", lang))
        form_plk = QFormLayout(grp_plk)
        form_plk.addRow(tr("rep_full", lang), QLabel(f"{self.report.get('full_planks_count', 0)}"))
        form_plk.addRow(tr("rep_cut", lang), QLabel(f"{self.report.get('cut_planks_count', 0)}"))
        if self.report.get('border_planks_count', 0) > 0:
            form_plk.addRow(tr("rep_border", lang), QLabel(f"{self.report.get('border_planks_count', 0) - self.report.get('hole_border_planks_count', 0)}"))
        if self.report.get('hole_border_planks_count', 0) > 0:
            form_plk.addRow(tr("rep_hole_border", lang), QLabel(f"{self.report.get('hole_border_planks_count', 0)}"))
        form_plk.addRow(tr("rep_total_planks", lang), QLabel(f"<b>{self.report.get('total_planks_count', 0)} szt.</b>"))
        form_plk.addRow(tr("rep_linear_m", lang), QLabel(f"{self.report.get('total_linear_m', 0.0):.2f} mb"))
        if self.report.get('component_instances', 0) > 0:
            form_plk.addRow(
                tr("rep_comp", lang),
                QLabel(tr("rep_comp_val", lang,
                          inst=self.report.get('component_instances', 0),
                          defs=self.report.get('component_defs', 0))),
            )
        layout.addWidget(grp_plk)

        # 4. Listwy przypodłogowe
        if self.report.get('skirting_count', 0) > 0:
            grp_sk = QGroupBox(tr("rep_header_skirting", lang))
            form_sk = QFormLayout(grp_sk)
            form_sk.addRow(tr("rep_skirt_count", lang), QLabel(f"{self.report.get('skirting_count', 0)}"))
            form_sk.addRow(tr("rep_skirt_linear", lang), QLabel(f"<b>{self.report.get('skirting_linear_m', 0.0):.2f} mb</b>"))
            layout.addWidget(grp_sk)

        # 5. Rekomendowane zamówienie
        grp_ord = QGroupBox(tr("rep_header_order", lang))
        form_ord = QFormLayout(grp_ord)
        wpct = self.report.get('waste_pct', 10.0)
        form_ord.addRow(tr("rep_waste", lang, pct=f"{wpct:.1f}"), QLabel(f"+{wpct:.1f}%"))
        form_ord.addRow(
            tr("rep_order_area", lang),
            QLabel(f"<span style='font-size: 15px; color: #1e7e34;'><b>{self.report.get('recommended_order_m2', 0.0):.2f} m²</b></span>"),
        )
        layout.addWidget(grp_ord)

        # Przyciski
        btn_layout = QHBoxLayout()
        self.btn_export = QPushButton(tr("rep_export_csv", lang))
        self.btn_export.clicked.connect(self._on_export_csv)
        self.btn_close = QPushButton(tr("rep_close", lang))
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_export)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _on_export_csv(self):
        default_name = "floor_material_report.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("rep_export_csv", self.lang),
            default_name,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Parameter", "Value", "Unit"])
                writer.writerow(["Room Net Area", f"{self.report.get('room_area_m2', 0.0):.2f}", "m2"])
                if self.report.get("holes_count", 0) > 0:
                    writer.writerow(["Internal Holes Count", self.report.get('holes_count', 0), "pcs"])
                    writer.writerow(["Deducted Holes Area", f"{self.report.get('holes_area_m2', 0.0):.2f}", "m2"])
                writer.writerow(["Flooring Covered Area", f"{self.report.get('flooring_area_m2', 0.0):.2f}", "m2"])
                writer.writerow(["Layout Pattern", self.report.get('pattern_name', '-'), ""])
                writer.writerow(["Wood Species", self.report.get('wood_name', '-'), ""])
                writer.writerow(["Plank Dimensions", self.report.get('plank_dims_str', '-'), "cm"])
                writer.writerow(["Full Planks (Uncut instances)", self.report.get('full_planks_count', 0), "pcs"])
                writer.writerow(["Cut / Trimmed Planks", self.report.get('cut_planks_count', 0), "pcs"])
                writer.writerow(["Border Planks (Outer walls)", self.report.get('border_planks_count', 0) - self.report.get('hole_border_planks_count', 0), "pcs"])
                if self.report.get('hole_border_planks_count', 0) > 0:
                    writer.writerow(["Border Planks (Around holes)", self.report.get('hole_border_planks_count', 0), "pcs"])
                writer.writerow(["Total Planks Count", self.report.get('total_planks_count', 0), "pcs"])
                writer.writerow(["Total Plank Linear Length", f"{self.report.get('total_linear_m', 0.0):.2f}", "m"])
                writer.writerow(["Component Definitions", self.report.get('component_defs', 0), "pcs"])
                writer.writerow(["Component Instances", self.report.get('component_instances', 0), "pcs"])
                writer.writerow(["Skirting Segments", self.report.get('skirting_count', 0), "pcs"])
                writer.writerow(["Skirting Linear Length", f"{self.report.get('skirting_linear_m', 0.0):.2f}", "m"])
                writer.writerow(["Estimated Waste Buffer", f"{self.report.get('waste_pct', 0.0):.1f}", "%"])
                writer.writerow(["Recommended Purchase Area", f"{self.report.get('recommended_order_m2', 0.0):.2f}", "m2"])

            QMessageBox.information(
                self,
                tr("rep_csv_saved_title", self.lang),
                tr("rep_csv_saved_msg", self.lang, path=path),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))


# ===========================================================================
# Interfejs Użytkownika (Qt Dialog z pełnymi ustawieniami)
# ===========================================================================

class FloorGeneratorDialog(QDialog):
    """Główne okno dialogowe z przełącznikiem języka, wzorami, bordiurą, otworami, listwami i kalkulatorem."""

    def __init__(self, parent=None, initial_params=None, title=None, is_edit=False):
        super().__init__(parent)
        self.params = _merged_params(initial_params)
        self.is_edit = is_edit
        self.custom_title = title
        self.resize(450, 720)

        main_layout = QVBoxLayout(self)

        # 0. Przełącznik języka (u samej góry)
        lang_layout = QHBoxLayout()
        self.lbl_lang = QLabel()
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("English (EN)", "en")
        self.combo_lang.addItem("Polski (PL)", "pl")

        curr_lang = self.params.get("lang", "en")
        self.combo_lang.setCurrentIndex(0 if curr_lang == "en" else 1)
        self.combo_lang.currentIndexChanged.connect(self._on_lang_changed)
        lang_layout.addWidget(self.lbl_lang)
        lang_layout.addWidget(self.combo_lang)
        lang_layout.addStretch()
        main_layout.addLayout(lang_layout)

        # 1. Wzór i orientacja
        self.pat_group = QGroupBox()
        pat_layout = QFormLayout(self.pat_group)

        self.lbl_pattern = QLabel()
        self.combo_pattern = QComboBox()
        pat_layout.addRow(self.lbl_pattern, self.combo_pattern)

        self.lbl_angle = QLabel()
        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setRange(0.0, 360.0)
        self.spin_angle.setValue(self.params["angle_deg"])
        self.spin_angle.setSuffix("°")
        pat_layout.addRow(self.lbl_angle, self.spin_angle)
        main_layout.addWidget(self.pat_group)

        # 2. Wymiary desek
        self.dim_group = QGroupBox()
        dim_layout = QFormLayout(self.dim_group)

        self.lbl_w = QLabel()
        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(3.0, 100.0)
        self.spin_w.setValue(self.params["plank_w_cm"])
        self.spin_w.setSuffix(" cm")
        dim_layout.addRow(self.lbl_w, self.spin_w)

        self.lbl_l = QLabel()
        self.spin_l = QDoubleSpinBox()
        self.spin_l.setRange(0.0, 1000.0)
        self.spin_l.setValue(self.params["plank_l_cm"])
        self.spin_l.setSuffix(" cm")
        dim_layout.addRow(self.lbl_l, self.spin_l)

        self.lbl_th = QLabel()
        self.spin_th = QDoubleSpinBox()
        self.spin_th.setRange(2.0, 100.0)
        self.spin_th.setValue(self.params["thickness_mm"])
        self.spin_th.setSuffix(" mm")
        dim_layout.addRow(self.lbl_th, self.spin_th)

        self.lbl_gap = QLabel()
        self.spin_gap = QDoubleSpinBox()
        self.spin_gap.setRange(0.0, 20.0)
        self.spin_gap.setValue(self.params["gap_mm"])
        self.spin_gap.setSuffix(" mm")
        dim_layout.addRow(self.lbl_gap, self.spin_gap)
        main_layout.addWidget(self.dim_group)

        # 3. Bordiura obwodowa (Friz wzdłuż ścian i wokół otworów)
        self.border_group = QGroupBox()
        border_layout = QFormLayout(self.border_group)

        self.chk_border = QCheckBox()
        self.chk_border.setChecked(self.params.get("use_border", False))
        self.chk_border.toggled.connect(self._toggle_border_inputs)
        border_layout.addRow(self.chk_border)

        self.chk_hole_border = QCheckBox()
        self.chk_hole_border.setChecked(self.params.get("use_hole_border", True))
        border_layout.addRow(self.chk_hole_border)

        self.lbl_border_planks = QLabel()
        self.spin_border_planks = QSpinBox()
        self.spin_border_planks.setRange(1, 10)
        self.spin_border_planks.setValue(self.params.get("border_planks", 1))
        border_layout.addRow(self.lbl_border_planks, self.spin_border_planks)

        self.lbl_border_w = QLabel()
        self.spin_border_w = QDoubleSpinBox()
        self.spin_border_w.setRange(3.0, 100.0)
        self.spin_border_w.setValue(self.params.get("border_plank_w_cm", self.params["plank_w_cm"]))
        self.spin_border_w.setSuffix(" cm")
        border_layout.addRow(self.lbl_border_w, self.spin_border_w)

        self._toggle_border_inputs(self.chk_border.isChecked())
        main_layout.addWidget(self.border_group)

        # 4. Listwy przypodłogowe (Skirting boards)
        self.skirting_group = QGroupBox()
        skirting_layout = QFormLayout(self.skirting_group)

        self.chk_skirting = QCheckBox()
        self.chk_skirting.setChecked(self.params.get("use_skirting", False))
        self.chk_skirting.toggled.connect(self._toggle_skirting_inputs)
        skirting_layout.addRow(self.chk_skirting)

        self.chk_skirting_holes = QCheckBox()
        self.chk_skirting_holes.setChecked(self.params.get("skirting_holes", True))
        skirting_layout.addRow(self.chk_skirting_holes)

        self.lbl_skirt_h = QLabel()
        self.spin_skirt_h = QDoubleSpinBox()
        self.spin_skirt_h.setRange(3.0, 25.0)
        self.spin_skirt_h.setValue(self.params.get("skirting_h_cm", 8.0))
        self.spin_skirt_h.setSuffix(" cm")
        skirting_layout.addRow(self.lbl_skirt_h, self.spin_skirt_h)

        self.lbl_skirt_th = QLabel()
        self.spin_skirt_th = QDoubleSpinBox()
        self.spin_skirt_th.setRange(5.0, 35.0)
        self.spin_skirt_th.setValue(self.params.get("skirting_th_mm", 15.0))
        self.spin_skirt_th.setSuffix(" mm")
        skirting_layout.addRow(self.lbl_skirt_th, self.spin_skirt_th)

        self.lbl_skirt_col = QLabel()
        self.combo_skirt_col = QComboBox()
        self.combo_skirt_col.addItem("Match floor wood", "wood")
        self.combo_skirt_col.addItem("White painted (RAL 9003)", "white")
        curr_sk_col = self.params.get("skirting_color", "wood")
        self.combo_skirt_col.setCurrentIndex(1 if curr_sk_col == "white" else 0)
        skirting_layout.addRow(self.lbl_skirt_col, self.combo_skirt_col)

        self._toggle_skirting_inputs(self.chk_skirting.isChecked())
        main_layout.addWidget(self.skirting_group)

        # 5. Wykończenie i materiał
        self.app_group = QGroupBox()
        app_layout = QFormLayout(self.app_group)

        self.lbl_wood = QLabel()
        self.combo_wood = QComboBox()
        app_layout.addRow(self.lbl_wood, self.combo_wood)

        self.lbl_var = QLabel()
        self.spin_var = QDoubleSpinBox()
        self.spin_var.setRange(0.0, 25.0)
        self.spin_var.setValue(self.params["color_var_pct"])
        self.spin_var.setSuffix(" %")
        app_layout.addRow(self.lbl_var, self.spin_var)
        main_layout.addWidget(self.app_group)

        # 6. Optymalizacja
        self.opt_group = QGroupBox()
        opt_layout = QVBoxLayout(self.opt_group)
        self.chk_components = QCheckBox()
        self.chk_components.setChecked(self.params.get("use_components", True))
        opt_layout.addWidget(self.chk_components)
        main_layout.addWidget(self.opt_group)

        # Przyciski
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        main_layout.addWidget(self.buttons)

        # Wczytujemy teksty w wybranym języku
        self._refresh_ui_texts()

    def _on_lang_changed(self):
        self.params["lang"] = self.combo_lang.currentData()
        self._refresh_ui_texts()

    def _refresh_ui_texts(self):
        """Aktualizuje wszystkie etykiety, tytuły i listy w oknie dialogowym."""
        lang = self.params.get("lang", "en")

        # Tytuł okna
        if self.custom_title:
            self.setWindowTitle(self.custom_title)
        elif self.is_edit:
            self.setWindowTitle(tr("title_edit", lang, name=""))
        else:
            self.setWindowTitle(tr("title", lang))

        # Etykieta języka
        self.lbl_lang.setText(tr("lang_label", lang))

        # Sekcja 1
        self.pat_group.setTitle(tr("pattern_group", lang))
        self.lbl_pattern.setText(tr("pattern_label", lang))
        self.lbl_angle.setText(tr("angle_label", lang))

        cur_pat_key = normalize_pattern(self.params.get("pattern", "pat_half"))
        self.combo_pattern.blockSignals(True)
        self.combo_pattern.clear()
        selected_idx = 0
        for idx, k in enumerate(PATTERN_KEYS):
            self.combo_pattern.addItem(tr(k, lang), k)
            if k == cur_pat_key:
                selected_idx = idx
        self.combo_pattern.setCurrentIndex(selected_idx)
        self.combo_pattern.blockSignals(False)

        # Sekcja 2
        self.dim_group.setTitle(tr("dim_group", lang))
        self.lbl_w.setText(tr("width_label", lang))
        self.lbl_l.setText(tr("length_label", lang))
        self.spin_l.setSpecialValueText(tr("continuous_text", lang))
        self.lbl_th.setText(tr("thickness_label", lang))
        self.lbl_gap.setText(tr("gap_label", lang))

        # Sekcja 3
        self.border_group.setTitle(tr("border_group", lang))
        self.chk_border.setText(tr("border_chk", lang))
        self.chk_hole_border.setText(tr("border_hole_chk", lang))
        self.lbl_border_planks.setText(tr("border_planks_label", lang))
        self.spin_border_planks.setSuffix(tr("border_planks_suffix", lang))
        self.lbl_border_w.setText(tr("border_width_label", lang))

        # Sekcja 4
        self.skirting_group.setTitle(tr("skirting_group", lang))
        self.chk_skirting.setText(tr("skirting_chk", lang))
        self.chk_skirting_holes.setText(tr("skirting_holes_chk", lang))
        self.lbl_skirt_h.setText(tr("skirting_h_label", lang))
        self.lbl_skirt_th.setText(tr("skirting_th_label", lang))
        self.lbl_skirt_col.setText(tr("skirting_col_label", lang))
        cur_sk_col = self.combo_skirt_col.currentData()
        self.combo_skirt_col.blockSignals(True)
        self.combo_skirt_col.clear()
        self.combo_skirt_col.addItem(tr("skirting_col_wood", lang), "wood")
        self.combo_skirt_col.addItem(tr("skirting_col_white", lang), "white")
        self.combo_skirt_col.setCurrentIndex(1 if cur_sk_col == "white" else 0)
        self.combo_skirt_col.blockSignals(False)

        # Sekcja 5
        self.app_group.setTitle(tr("material_group", lang))
        self.lbl_wood.setText(tr("wood_label", lang))
        self.lbl_var.setText(tr("var_label", lang))

        cur_wood_key = normalize_wood(self.params.get("wood_type", "wood_oak"))
        self.combo_wood.blockSignals(True)
        self.combo_wood.clear()
        selected_wood_idx = 0
        for idx, wk in enumerate(WOOD_KEYS):
            self.combo_wood.addItem(tr(wk, lang), wk)
            if wk == cur_wood_key:
                selected_wood_idx = idx
        self.combo_wood.setCurrentIndex(selected_wood_idx)
        self.combo_wood.blockSignals(False)

        # Sekcja 6
        self.opt_group.setTitle(tr("opt_group", lang))
        self.chk_components.setText(tr("opt_chk", lang))
        self.chk_components.setToolTip(tr("opt_tip", lang))

    def _toggle_border_inputs(self, enabled: bool) -> None:
        self.chk_hole_border.setEnabled(enabled)
        self.spin_border_planks.setEnabled(enabled)
        self.spin_border_w.setEnabled(enabled)

    def _toggle_skirting_inputs(self, enabled: bool) -> None:
        self.chk_skirting_holes.setEnabled(enabled)
        self.spin_skirt_h.setEnabled(enabled)
        self.spin_skirt_th.setEnabled(enabled)
        self.combo_skirt_col.setEnabled(enabled)

    def _on_accept(self):
        self.params["lang"] = self.combo_lang.currentData()
        self.params["pattern"] = self.combo_pattern.currentData()
        self.params["stagger_mode"] = self.combo_pattern.currentData()
        self.params["plank_w_cm"] = self.spin_w.value()
        self.params["plank_l_cm"] = self.spin_l.value()
        self.params["thickness_mm"] = self.spin_th.value()
        self.params["gap_mm"] = self.spin_gap.value()
        self.params["angle_deg"] = self.spin_angle.value()
        self.params["wood_type"] = self.combo_wood.currentData()
        self.params["color_var_pct"] = self.spin_var.value()
        self.params["use_components"] = self.chk_components.isChecked()
        self.params["use_border"] = self.chk_border.isChecked()
        self.params["use_hole_border"] = self.chk_hole_border.isChecked()
        self.params["border_planks"] = self.spin_border_planks.value()
        self.params["border_plank_w_cm"] = self.spin_border_w.value()
        self.params["use_skirting"] = self.chk_skirting.isChecked()
        self.params["skirting_holes"] = self.chk_skirting_holes.isChecked()
        self.params["skirting_h_cm"] = self.spin_skirt_h.value()
        self.params["skirting_th_mm"] = self.spin_skirt_th.value()
        self.params["skirting_color"] = self.combo_skirt_col.currentData()
        self.accept()

    @classmethod
    def ask(cls, parent=None, initial_params=None, title=None, is_edit=False):
        dlg = cls(parent, initial_params, title, is_edit)
        if dlg.exec() == QDialog.Accepted:
            return dlg.params
        return None


# ===========================================================================
# Logika wykonawcza (Command Execution & Selection)
# ===========================================================================

def _selected_floors(scene) -> List[Group]:
    """Zwraca zaznaczone grupy podłóg utworzone przez to rozszerzenie."""
    out = []
    for g in getattr(scene, "selection", []):
        if isinstance(g, Group) and getattr(g, "ext", None) and KEY in g.ext:
            out.append(g)
    return out


def _selected_faces(scene) -> List[Face]:
    """Zwraca zaznaczone płaszczyzny w modelu."""
    return [e for e in getattr(scene, "selection", []) if isinstance(e, Face)]


def show_material_report(viewport) -> None:
    """Wyświetla okno raportu materiałowego dla zaznaczonej podłogi."""
    try:
        floors = _selected_floors(viewport.scene)
        if not floors:
            QMessageBox.information(
                viewport.window(),
                "Material Report / Raport materiałowy",
                "Select a generated floor (Group) to view its material report.\n\nZaznacz wygenerowaną podłogę (Group), aby wyświetlić jej raport materiałowy.",
            )
            return
        floor_grp = floors[0]
        data = (getattr(floor_grp, "ext", None) or {}).get(KEY, {})
        report = data.get("report")
        lang = data.get("params", {}).get("lang", "en")
        if not report:
            QMessageBox.information(
                viewport.window(),
                "Material Report / Raport materiałowy",
                "No material report found for this floor.\n\nBrak zapisanego raportu materiałowego dla tej podłogi.",
            )
            return

        dlg = FloorReportDialog(viewport.window(), report=report, lang=lang)
        dlg.exec()
    except Exception as exc:
        import traceback
        QMessageBox.critical(viewport.window(), "Report Error", f"{exc}\n\n{traceback.format_exc()}")


class FloorCommand(_HistCommand):
    """Jeden krok Undo/Redo dla tworzenia LUB przebudowy podłogi.

    ``SnapshotImport`` zapamiętuje tylko luźną siatkę i *dodane* grupy – przebudowa
    istniejącej podłogi (podmiana ``children``/``mesh``/``ext``) nie dawała się więc
    cofnąć. Ta komenda zapamiętuje listę grup sceny, stan edytowanych podłóg oraz
    dane dokumentu pluginu – i nic więcej (żadnych kosztownych snapshotów siatki).
    """

    def __init__(self, mutate, targets=()) -> None:
        self.mutate = mutate
        self.targets = list(targets)
        self.before = None
        self.after = None

    def _capture(self, scene) -> dict:
        pdata = getattr(scene, "plugin_data", None) or {}
        return {
            "groups": list(scene.groups),
            "targets": [
                (g, list(g.children or ()), g.mesh, g.xform,
                 copy.deepcopy(getattr(g, "ext", None)), g.ifc and dict(g.ifc))
                for g in self.targets
            ],
            "data": copy.deepcopy(pdata.get(KEY)),
        }

    def _restore(self, scene, s) -> None:
        scene.groups[:] = s["groups"]
        for g, kids, mesh, xform, ext, ifc in s["targets"]:
            g.children = list(kids)
            g.mesh = mesh
            g.xform = xform
            g.ext = copy.deepcopy(ext)
            g.ifc = ifc and dict(ifc)
        pdata = getattr(scene, "plugin_data", None)
        if pdata is not None:
            if s["data"] is None:
                pdata.pop(KEY, None)
            else:
                pdata[KEY] = copy.deepcopy(s["data"])
        sel = getattr(scene, "selection", None)
        if sel is not None:
            alive = set(scene.groups)
            for item in list(sel):
                if isinstance(item, Group) and item not in alive:
                    try:
                        sel.discard(item)
                    except Exception:
                        pass

    def do(self, scene) -> None:
        if self.after is None:
            self.before = self._capture(scene)
            try:
                self.mutate(scene)
            except BaseException:
                self._restore(scene, self.before)
                raise
            self.after = self._capture(scene)
        else:
            self._restore(scene, self.after)
        scene.version += 1

    def undo(self, scene) -> None:
        self._restore(scene, self.before)
        scene.version += 1


def _execute(viewport, mutate, targets=()) -> bool:
    """Wykonuje mutację jako jeden krok historii; zwraca False przy błędzie."""
    hist = viewport.history
    if _HistCommand is object:  # bardzo stara wersja IngeTrazo – brak core.history.Command
        hist.execute(SnapshotImport(mutate))
    else:
        hist.execute(FloorCommand(mutate, targets))
    err = getattr(hist, "last_error", None)
    if err:
        QMessageBox.critical(viewport.window(), tr("err_title", "en"), str(err))
        return False
    notify = getattr(viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    viewport.update()
    return True


class _BusyCursor:
    """Kursor oczekiwania na czas generowania geometrii."""

    def __enter__(self):
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self._on = True
        except Exception:
            self._on = False
        return self

    def __exit__(self, *exc):
        if self._on:
            from PySide6.QtWidgets import QApplication
            QApplication.restoreOverrideCursor()
        return False


def _ask_report(viewport, message: str, report: dict, lang: str) -> None:
    reply = QMessageBox.question(
        viewport.window(),
        tr("rep_title", lang),
        f"{message}\n\nDo you want to view the Material & Cut Report? / Czy chcesz zobaczyć raport materiałowy?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if reply == QMessageBox.Yes:
        FloorReportDialog(viewport.window(), report=report, lang=lang).exec()


def run_floor_generator(viewport) -> None:
    """Główna procedura (obsługuje automatycznie edycję lub tworzenie w wybranym języku)."""
    try:
        scene = viewport.scene
        floors = _selected_floors(scene)
        faces = _selected_faces(scene)

        doc_data = getattr(scene, "plugin_data", {}) or {}
        global_lang = (doc_data.get(KEY) or {}).get("lang", DEFAULT_PARAMS["lang"])

        # 1. TRYB EDYCJI / PRZEBUDOWY (Gdy zaznaczono istniejącą grupę podłogi)
        if floors:
            target_floor = floors[0]
            data = target_floor.ext[KEY]
            saved_params = _merged_params(data.get("params"))
            lang = saved_params.get("lang", global_lang)

            edit_title = tr("title_edit", lang, name=target_floor.name)
            params = FloorGeneratorDialog.ask(
                viewport.window(),
                saved_params,
                title=edit_title,
                is_edit=True,
            )
            if params is None:
                return
            lang = params.get("lang", "en")

            # Geometria liczona POZA historią: błąd nie zostawia półproduktu.
            with _BusyCursor():
                new_group, _count, report = _rebuild_geometry(target_floor, params)

            def mutate_edit(sc):
                _apply_rebuild(target_floor, new_group, params, report)

            if not _execute(viewport, mutate_edit, targets=[target_floor]):
                return
            msg = tr("flash_rebuilt", lang, name=target_floor.name)
            viewport.flash_status(msg, 4000)
            if report:
                _ask_report(viewport, msg, report, lang)
            return

        # 2. Brak zaznaczenia - wyświetlamy czytelne okno informujące użytkownika
        if not faces:
            viewport.flash_status(tr("flash_select", global_lang), 5000)
            QMessageBox.information(
                viewport.window(),
                tr("title", global_lang),
                tr("flash_select", global_lang),
            )
            return

        # 3. TRYB TWORZENIA NOWEJ PODŁOGI (Z automatycznym rozpoznawaniem otworów)
        rooms_data = _resolve_rooms_and_holes(faces)
        if not rooms_data:
            viewport.flash_status(tr("flash_empty", global_lang), 4000)
            QMessageBox.warning(
                viewport.window(),
                tr("title", global_lang),
                tr("flash_empty", global_lang),
            )
            return

        total_holes = sum(len(r[2]) for r in rooms_data)
        last_params = _merged_params(doc_data.get(KEY))
        params = FloorGeneratorDialog.ask(
            viewport.window(),
            last_params,
            title=tr("title", last_params.get("lang", "en")),
            is_edit=False,
        )
        if params is None:
            return

        active_lang = params.get("lang", "en")
        total_planks = 0
        groups_to_add = []
        latest_report = {}

        with _BusyCursor():
            for room_verts_3d, room_normal, room_holes_3d in rooms_data:
                floor_group, count, rep = generate_floor_for_face(
                    room_verts_3d, params, normal=room_normal, holes_3d=room_holes_3d
                )
                if count > 0:
                    groups_to_add.append(floor_group)
                    total_planks += count
                    latest_report = rep

        if not groups_to_add:
            viewport.flash_status(tr("flash_empty", active_lang), 4000)
            return

        def mutate_add(sc):
            if getattr(sc, "plugin_data", None) is None:
                sc.plugin_data = {}
            sc.plugin_data[KEY] = dict(params)   # ostatnie ustawienia – też cofane Ctrl+Z
            for g in groups_to_add:
                sc.groups.append(g)

        if not _execute(viewport, mutate_add):
            return

        status_msg = tr("flash_done", active_lang, total_planks=total_planks, count=len(groups_to_add))
        if total_holes > 0:
            status_msg += " " + tr("flash_holes_detected", active_lang, n=total_holes)
        viewport.flash_status(status_msg, 5000)

        # Propozycja otwarcia raportu materiałowego
        if latest_report:
            _ask_report(viewport, status_msg, latest_report, active_lang)

    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            QMessageBox.critical(
                viewport.window(),
                "Floor Generator Error",
                f"An error occurred in Floor Generator:\n\n{exc}\n\n{traceback.format_exc()}"
            )
        except Exception:
            pass


# ===========================================================================
# Rejestracja wtyczki (Tool & setup)
# ===========================================================================

class FloorGeneratorTool(Tool):
    """Narzędzie one-shot w menu Extensions."""

    name = "Floor & Decking Generator"
    shortcut = "Ctrl+Shift+F"
    description = "Generates or edits parametric plank flooring, decking, or parquet with borders and skirting boards."
    uses_snap = False

    def on_activate(self, viewport) -> None:
        QTimer.singleShot(0, lambda: run_floor_generator(viewport))

    def on_deactivate(self, viewport) -> None:
        pass


def _install_toolbar(app, viewport_of) -> None:
    """Górny pasek narzędzi z ikoną generatora (klik = generuj/edytuj, strzałka = raport).

    Extension API (v2) nie ma własnego wywołania „dodaj przycisk do toolbara”,
    więc korzystamy z okna głównego: preferowany jest ``MainWindow._new_toolbar``
    (ten sam styl, przesuwanie/odpinanie, rozmiar ikon z Preferencji i zapamiętana
    pozycja dzięki ``objectName``); w starszych wersjach budujemy QToolBar sami.
    """
    from PySide6.QtWidgets import QMenu, QToolBar, QToolButton
    from PySide6.QtGui import QAction

    win = getattr(app, "window", None)
    if win is None or not hasattr(win, "addToolBar"):
        return
    obj_name = f"extension_{KEY}_toolbar"
    if win.findChild(QToolBar, obj_name) is not None:
        return  # już zainstalowany (np. ponowne wywołanie setup)

    title = "Floor & Decking"
    maker = getattr(win, "_new_toolbar", None)
    tb = None
    if callable(maker):
        try:
            tb = maker(title, obj_name)
        except Exception:
            tb = None
    if tb is None:
        tb = QToolBar(title, win)
        tb.setObjectName(obj_name)
        tb.setMovable(True)
        tb.setFloatable(True)
        px = 24
        try:
            from views.icons import toolbar_icon_px
            px = toolbar_icon_px()
        except Exception:
            pass
        tb.setIconSize(QSize(px, px))
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        win.addToolBar(Qt.TopToolBarArea, tb)

    icon = _plugin_icon()
    act_gen = QAction(icon, "Floor & Decking Generator", win)
    act_gen.setToolTip(
        "Floor & Decking Generator – generate / edit floor (Ctrl+Shift+F)\n"
        "Generator podłogi deskowanej – generuj / edytuj podłogę"
    )
    act_gen.setStatusTip(tr("tool_desc", "en"))
    act_gen.triggered.connect(
        lambda _c=False: QTimer.singleShot(0, lambda: run_floor_generator(viewport_of()))
    )

    menu = QMenu(win)
    m_gen = menu.addAction(icon, "Generate / Edit Floor...  (Generuj / Edytuj)")
    m_gen.triggered.connect(act_gen.trigger)
    m_rep = menu.addAction("Material & Cut Report...  (Raport materiałowy)")
    m_rep.triggered.connect(
        lambda _c=False: QTimer.singleShot(0, lambda: show_material_report(viewport_of()))
    )
    act_gen.setMenu(menu)
    tb.addAction(act_gen)
    btn = tb.widgetForAction(act_gen)
    if isinstance(btn, QToolButton):
        btn.setPopupMode(QToolButton.MenuButtonPopup)
    # Referencje trzymamy przy pasku, aby GC nie zebrał akcji/menu.
    tb._floor_gen_refs = (act_gen, menu)


def setup(app) -> None:
    """Punkt wejścia rozszerzenia (Extension API v2)."""
    viewport_of = lambda: app.viewport  # noqa: E731

    # 0. Przycisk z ikoną na górnym pasku narzędzi
    try:
        _install_toolbar(app, viewport_of)
    except Exception:
        import logging
        logging.getLogger("ingetrazo.plugins").exception("floor_generator: toolbar install failed")

    # 1. Menu Extensions
    sub_menu = app.add_menu("Floor & Decking (Podłoga)")
    if sub_menu is not None:
        act_gen = sub_menu.addAction(_plugin_icon(), "Generate / Edit Floor...")
        act_gen.triggered.connect(
            lambda _c=False: QTimer.singleShot(0, lambda: run_floor_generator(viewport_of()))
        )
        act_rep = sub_menu.addAction("Material & Cut Report...")
        act_rep.triggered.connect(
            lambda _c=False: QTimer.singleShot(0, lambda: show_material_report(viewport_of()))
        )

    # 2. Menu kontekstowe (PPM) z dynamicznym rozpoznaniem
    def context_menu_hook(menu, selection):
        doc_data = getattr(app.viewport.scene, "plugin_data", {}) or {}
        lang = doc_data.get(KEY, {}).get("lang", "en")

        floors = [g for g in selection if isinstance(g, Group) and getattr(g, "ext", None) and KEY in g.ext]
        if floors:
            menu.addSeparator()
            action_edit_text = tr("context_edit", lang, name=floors[0].name)
            act_edit = menu.addAction(action_edit_text)
            act_edit.triggered.connect(
                lambda _c=False: QTimer.singleShot(0, lambda: run_floor_generator(viewport_of()))
            )
            action_rep_text = tr("context_report", lang, name=floors[0].name)
            act_rep = menu.addAction(action_rep_text)
            act_rep.triggered.connect(
                lambda _c=False: QTimer.singleShot(0, lambda: show_material_report(viewport_of()))
            )
            return

        faces = [f for f in selection if isinstance(f, Face)]
        if faces:
            menu.addSeparator()
            action_text = tr("context_gen", lang)
            action = menu.addAction(action_text)
            action.triggered.connect(
                lambda _c=False: QTimer.singleShot(0, lambda: run_floor_generator(viewport_of()))
            )

    app.add_context_menu(context_menu_hook)
