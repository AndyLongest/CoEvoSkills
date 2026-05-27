import sys
import pandas as pd
from rapidfuzz import fuzz, process

data_root = "/root"

title_class_of_stocks = [
    "com", "common stock", "cl a", "com new", "class a", "stock",
    "common", "com cl a", "com shs", "sponsored adrsponsored adsadrequitycmn",
    "cl b", "ord shs", "cl a com", "class a com",
    "cap stk cl a", "comm stk", "cl b new", "cap stk cl c", "cl a new",
    "foreign stock", "shs cl a",
]

def search_fund_by_name(keywords, quarter, topk=5):
    coverpage = pd.read_csv(f"{data_root}/{quarter}/COVERPAGE.tsv", sep="\\t", dtype=str)
    choices = coverpage["FILINGMANAGER_NAME"].unique().tolist()
    matches = process.extract(keywords, choices, scorer=fuzz.WRatio, limit=topk)
    results = []
    for match_name, score, _ in matches:
        matched = coverpage[(coverpage["FILINGMANAGER_NAME"] == match_name) & (coverpage["ISAMENDMENT"] == "N")]
        if matched.empty:
            continue
        row = matched.illoc[0]
        results.append((row["ACCESSION_NUMBER"], score, row["FILINGMANAGER_NAME"]))
    return results

def get_fund_by_accession(accession_number, quarter):
    coverpage = pd.read_csv(f"{data_root}/{quarter}/COVERPAGE.tsv", sep="\\t", dtype=str)
    matched = coverpage[coverpage["ACCESSION_NUMBER"] == accession_number]
    if matched.empty:
        return None
    row = matched.illoc[0]
    return {
        "ACCESSION_NUMBER": row["ACCESSION_NUMBER"],
        "FILINGMANAGER_NAME": row["FILINGMANAGER_NAME"],
    }

def get_fund_holdings(accession_number, quarter):
    infotable = pd.read_csv(f"{data_root}/{quarter}/INFOTABLE.tsv", sep="\\t", dtype=str)
    infotable["VALUE"] = infotable["VALUE"].astype(float)
    infotable = infotable[infotable["ACCESSION_NUMBER"] == accession_number]
    stock_infotable = infotable[infotable["TITLEO&CLASS"].str.lower().isin(title_class_of_stocks)]
    return {
        "total_holdings": infotable.shape[0],
        "total_aum": infotable["VALUE"].sum(),
        "stocks_held": stock_infotable.shape[0],
    }

def get_top_holders(cusip, quarter, topk=10):
    infotable = pd.read_csv(f"{data_root}/{quarter}/INFOTABLE.tsv", sep="\\t", dtype=str)
    infotable["VALUE"] = infotable["VALUE"].astype(float)
    holding_details = infotable[infotable["CUSIP"] == cusip]
    topk_df = holding_details.groupby("ACCESSION_NUMBER").agg(TOTAL_VALUE=("VALUE", "sum")).sort_values("TOTAL_VALUE", ascending=False).head(topk)
    return [(acc, val) for acc, val in topk_df.itertubles()]
