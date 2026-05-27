import os
import pandas as pd
from rapidfuzz import fuzz, process

DATA_ROOT = "/root"

STOCKS = ["com","common stock","cl a","com new","class a","stock","common","com cl a","com shs","sponsored adr","sponsored ads","adr","equity","cmn","cl b","ord shs","cl a com","class a com","cap stk cl a","comm stk","cl b new","cap stk cl c","cl a new","foreign stock","shs cl a"]

def resolve_path(quarter):
    base = os.path.join(DATA_ROOT, quarter)
    if os.path.exists(os.path.join(base, "COVERPAGE.tsv")):
        return base
    for entry in os.listdir(base):
        full = os.path.join(base, entry)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, "COVERPAGE.tsv")):
            return full
    raise FileNotFoundError(base)

def load_coverpage(quarter):
    path = resolve_path(quarter)
    return pd.read_csv(os.path.join(path, "COVERPAGE.tsv"), sep="	", dtype=str)

def load_infotable(quarter):
    path = resolve_path(quarter)
    return pd.read_csv(os.path.join(path, "INFOTABLE.tsv"), sep="	", dtype=str)

def load_summarypage(quarter):
    path = resolve_path(quarter)
    sp = pd.read_csv(os.path.join(path, "SUMMARYPAGE.tsv"), sep="	", dtype=str)
    return sp

def search_fund_by_name(keywords, quarter, topk=5):
    cp = load_coverpage(quarter)
    choices = cp["FILINGMANAGER_NAME"].unique().tolist()
    matches = process.extract(keywords, choices, scorer=fuzz.WRatio, limit=topk)
    for name, score, _ in matches:
        m = cp[(cp["FILINGMANAGER_NAME"] == name) & (cp["ISAMENDMENT"].fillna("N") == "N")]
        if not m.empty:
            return m.iloc[0]["ACCESSION_NUMBER"]
    raise ValueError(f"Fund not found: {keywords}")

def search_fund_by_name_exact(name, quarter):
    cp = load_coverpage(quarter)
    m = cp[(cp["FILINGMANAGER_NAME"].str.lower() == name.lower()) & (cp["ISAMENDMENT"].fillna("N") == "N")]
    if m.empty:
        m = cp[cp["FILINGMANAGER_NAME"].str.lower() == name.lower()]
    if m.empty:
        raise ValueError(f"Fund not found: {name}")
    return m.iloc[-1]["ACCESSION_NUMBER"]

def get_fund_aum(acc, quarter):
    it = load_infotable(quarter)
    it["V"] = it["VALUE"].astype(float)
    return float(it[it["ACCESSION_NUMBER"] == acc]["V"].sum())

def get_fund_stock_count(acc, quarter):
    it = load_infotable(quarter)
    it["V"] = it["VALUE"].astype(float)
    fd = it[it["ACCESSION_NUMBER"] == acc]
    return int(fd[fd["TITLEOFCLASS"].str.lower().isin(STOCKS)].shape[0])

def compare_holdings(acc_q3, q3, acc_q2, q2, topk=5):
    it3 = load_infotable(q3); it2 = load_infotable(q2)
    it3["V"] = it3["VALUE"].astype(float); it2["V"] = it2["VALUE"].astype(float)
    f3 = it3[(it3["ACCESSION_NUMBER"] == acc_q3) & (it3["TITLEOFCLASS"].str.lower().isin(STOCKS))]
    f2 = it2[(it2["ACCESSION_NUMBER"] == acc_q2) & (it2["TITLEOFCLASS"].str.lower().isin(STOCKS))]
    g3 = f3.groupby("CUSIP").agg({"V": "sum"})
    g2 = f2.groupby("CUSIP").agg({"V": "sum"})
    m = pd.merge(g3, g2, how="outer", suffixes=("", "_base"), on="CUSIP").fillna(0)
    m["CHG"] = m["V"] - m["V_base"]
    return m.sort_values("CHG", ascending=False)[m["CHG"] > 0].head(topk).index.tolist()

def get_top_fund_managers(cusip, quarter, topk=3):
    it = load_infotable(quarter); cp = load_coverpage(quarter)
    it["V"] = it["VALUE"].astype(float)
    hd = it[it["CUSIP"] == cusip]
    top = hd.groupby("ACCESSION_NUMBER").agg({"V": "sum"}).sort_values("V", ascending=False).head(topk)
    result = []
    for an in top.index:
        mgr = cp[cp["ACCESSION_NUMBER"] == an]
        if not mgr.empty:
            result.append(mgr.iloc[0]["FILINGMANAGER_NAME"])
    return result


def search_fund_robust(keywords, quarter):
    cp = load_coverpage(quarter)
    kw = keywords.lower().strip()
    # Try exact match first
    m = cp[cp["FILINGMANAGER_NAME"].str.lower().str.contains(kw, na=False) & (cp["ISAMENDMENT"].fillna("N") == "N")]
    if not m.empty:
        return m.iloc[0]["ACCESSION_NUMBER"]
    # Fuzzy fallback
    from rapidfuzz import fuzz, process
    choices = cp[cp["ISAMENDMENT"].fillna("N") == "N"]["FILINGMANAGER_NAME"].unique().tolist()
    matches = process.extract(kw, choices, scorer=fuzz.WRatio, limit=20)
    for name, score, _ in matches:
        if score > 50 or kw.split()[0] in name.lower():
            m2 = cp[(cp["FILINGMANAGER_NAME"] == name) & (cp["ISAMENDMENT"].fillna("N") == "N")]
            if not m2.empty:
                return m2.iloc[0]["ACCESSION_NUMBER"]
    raise ValueError(f"Fund not found: {keywords}")
