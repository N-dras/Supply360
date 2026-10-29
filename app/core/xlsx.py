"""Écriture de classeurs Excel (.xlsx) mis en forme, avec la seule bibliothèque standard.

Remplace openpyxl / xlsxwriter, absents de Pyodide : l'app n'a plus rien à télécharger
depuis PyPI. Gère : plusieurs feuilles, en-têtes en gras blanc sur bleu marine, volets
figés, filtres automatiques, largeurs ajustées, dates JJ/MM/AAAA, surlignage de lignes.
"""

import io
import math
import zipfile
from datetime import date, datetime
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd

NAVY = "002157"
EPOCH = datetime(1899, 12, 30)


def _col(n: int) -> str:
    """1 → A, 27 → AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _xml_text(v) -> str:
    # Caractères de contrôle interdits en XML.
    return escape("".join(ch for ch in str(v) if ch in "\t\n\r" or ord(ch) >= 32))


class _Styles:
    """Index de styles (cellXfs) : (format, couleur de fond) → numéro."""

    FMT_DATE = 164

    def __init__(self):
        self.fills = ["none", "gray125", NAVY]
        self.xfs = [(0, 0, 0)]          # (numFmtId, fillId, fontId) ; 0 = défaut
        self.cache = {}
        self.header = self._xf(0, self._fill(NAVY), 1)

    def _fill(self, hexa):
        if hexa not in self.fills:
            self.fills.append(hexa)
        return self.fills.index(hexa)

    def _xf(self, fmt, fill, font=0):
        key = (fmt, fill, font)
        if key not in self.xfs:
            self.xfs.append(key)
        return self.xfs.index(key)

    def cellule(self, est_date: bool, fond: str | None):
        key = (est_date, fond)
        if key not in self.cache:
            self.cache[key] = self._xf(self.FMT_DATE if est_date else 0, self._fill(fond) if fond else 0)
        return self.cache[key]

    def xml(self) -> str:
        fills = []
        for f in self.fills:
            if f in ("none", "gray125"):
                fills.append(f'<fill><patternFill patternType="{f}"/></fill>')
            else:
                fills.append(f'<fill><patternFill patternType="solid"><fgColor rgb="FF{f}"/><bgColor indexed="64"/></patternFill></fill>')
        xfs = "".join(
            f'<xf numFmtId="{n}" fontId="{fo}" fillId="{fi}" borderId="0" xfId="0"'
            + (' applyNumberFormat="1"' if n else "") + (' applyFill="1"' if fi else "") + (' applyFont="1"' if fo else "")
            + (' applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>' if fo else "/>")
            for n, fi, fo in self.xfs)
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<numFmts count="1"><numFmt numFmtId="{self.FMT_DATE}" formatCode="dd/mm/yyyy"/></numFmts>'
                '<fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
                '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font></fonts>'
                f'<fills count="{len(fills)}">{"".join(fills)}</fills>'
                '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                f'<cellXfs count="{len(self.xfs)}">{xfs}</cellXfs>'
                '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                '</styleSheet>')


def _valeur(v):
    """(type, valeur XML) d'une cellule ou None si vide."""
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, (pd.Timestamp, datetime, date, np.datetime64)):
        ts = pd.Timestamp(v)
        if pd.isna(ts):
            return None
        ts = ts.tz_localize(None) if ts.tzinfo else ts
        return "d", (ts.to_pydatetime() - EPOCH).total_seconds() / 86400
    if isinstance(v, (bool, np.bool_)):
        return "b", "1" if v else "0"
    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return "n", repr(int(f)) if f.is_integer() and abs(f) < 1e15 else repr(f)
    s = str(v)
    return ("s", s) if s else None


def _feuille(df: pd.DataFrame, styles: _Styles, fonds, fonds_cellules: dict | None = None) -> tuple[str, str | None]:
    """`fonds` : couleur par ligne ; `fonds_cellules` : {indice de colonne: couleur par ligne} (ex. cellule Statut)."""
    fonds_cellules = fonds_cellules or {}
    ncols, nrows = len(df.columns), len(df)
    largeurs = [len(str(c)) for c in df.columns]
    lignes = []
    entete = "".join(f'<c r="{_col(j + 1)}1" t="inlineStr" s="{styles.header}"><is><t>{_xml_text(c)}</t></is></c>'
                     for j, c in enumerate(df.columns))
    lignes.append(f'<row r="1">{entete}</row>')
    for i, rec in enumerate(df.itertuples(index=False, name=None), start=2):
        fond_ligne = fonds[i - 2] if fonds is not None else None
        cells = []
        for j, v in enumerate(rec):
            ref = f"{_col(j + 1)}{i}"
            fond = fonds_cellules[j][i - 2] if j in fonds_cellules and fonds_cellules[j][i - 2] else fond_ligne
            val = _valeur(v)
            if val is None:
                if fond:
                    cells.append(f'<c r="{ref}" s="{styles.cellule(False, fond)}"/>')
                continue
            t, x = val
            if t == "d":
                cells.append(f'<c r="{ref}" s="{styles.cellule(True, fond)}"><v>{x:.6f}</v></c>')
                largeurs[j] = max(largeurs[j], 10)
            elif t == "s":
                st = styles.cellule(False, fond)
                cells.append(f'<c r="{ref}" t="inlineStr"{f" s={chr(34)}{st}{chr(34)}" if st else ""}><is><t xml:space="preserve">'
                             f'{_xml_text(x)}</t></is></c>')
                if i < 502:
                    largeurs[j] = max(largeurs[j], len(x))
            else:
                st = styles.cellule(False, fond)
                cells.append(f'<c r="{ref}"{f" t={chr(34)}b{chr(34)}" if t == "b" else ""}'
                             f'{f" s={chr(34)}{st}{chr(34)}" if st else ""}><v>{x}</v></c>')
                if i < 502:
                    largeurs[j] = max(largeurs[j], len(x))
        lignes.append(f'<row r="{i}">{"".join(cells)}</row>')
    cols = "".join(f'<col min="{j + 1}" max="{j + 1}" width="{min(max(w + 2, 8), 60)}" customWidth="1"/>'
                   for j, w in enumerate(largeurs))
    ref_filtre = f"A1:{_col(ncols)}{nrows + 1}" if ncols and nrows else None
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
           '<sheetViews><sheetView workbookViewId="0">'
           '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
           '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView></sheetViews>'
           '<sheetFormatPr defaultRowHeight="15"/>'
           + (f"<cols>{cols}</cols>" if cols else "")
           + f'<sheetData>{"".join(lignes)}</sheetData>'
           + (f'<autoFilter ref="{ref_filtre}"/>' if ref_filtre else "")
           + '</worksheet>')
    return xml, ref_filtre


def classeur(feuilles: dict, couleurs_lignes: dict | None = None, couleurs_cellules: dict | None = None) -> bytes:
    """{nom_feuille: DataFrame} → octets d'un fichier .xlsx. `couleurs_lignes` : {nom: [hexa|None]} ;
    `couleurs_cellules` : {nom: {colonne: [hexa|None]}} (fond d'une seule colonne, ex. le statut)."""
    styles = _Styles()
    noms, xml_feuilles, filtres = [], [], []
    for nom, df in feuilles.items():
        nom31 = "".join(ch for ch in str(nom) if ch not in '[]:*?/\\')[:31] or "Feuille"
        df = df.reset_index(drop=True)
        cellules = {list(df.columns).index(c): list(v) for c, v in ((couleurs_cellules or {}).get(nom) or {}).items() if c in df.columns}
        xml, ref = _feuille(df, styles, (couleurs_lignes or {}).get(nom), cellules)
        noms.append(nom31)
        xml_feuilles.append(xml)
        filtres.append(ref)
    n = len(noms)
    sheets = "".join(f'<sheet name="{_xml_text(s)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, s in enumerate(noms))
    defs = "".join(f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
                   f"'{_xml_text(s)}'!{':'.join(_abs(p) for p in ref.split(':'))}</definedName>"
                   for i, (s, ref) in enumerate(zip(noms, filtres)) if ref)
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<bookViews><workbookView/></bookViews><sheets>{sheets}</sheets>'
                + (f"<definedNames>{defs}</definedNames>" if defs else "") + '</workbook>')
    rels = "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                   f'Target="worksheets/sheet{i + 1}.xml"/>' for i in range(n))
    rels += (f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
             'Target="styles.xml"/>')
    types = "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(n))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   f'{types}</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                   'Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        z.writestr("xl/styles.xml", styles.xml())
        for i, xml in enumerate(xml_feuilles):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", xml)
    return buf.getvalue()


def _abs(ref: str) -> str:
    """« Q15 » → « $Q$15 »."""
    lettres = "".join(c for c in ref if c.isalpha())
    return f"${lettres}${ref[len(lettres):]}"
