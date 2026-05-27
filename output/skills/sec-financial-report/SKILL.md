---
name: evo-13f-analysis
---

---
name: evo-13f-analysis
description: Evolved skill for analyzing SEC 13-F filings across quarters. Provides utilities for fuzzy fund search, AUM retrieval, stock count, holding change comparison, and top holder identification.
---

## Overview
Provides utility functions for analyzing hedge fund 13F filings from COVERPAGE.tsv, INFOTABLE.tsv, SUMMARYPAGE.tsv in /root/{quarter}/.

## Usage
Import functions from scripts/utils.py: sys.path.insert(0, "/app/environment/skills/evo-13f-analysis/scripts"); from utils import *

## Functions
- search_fund_by_name(keywords, quarter): fuzzy search fund
- get_fund_by_accession(acc, quarter): get fund details
- get_fund_holdings(acc, quarter): get AUM and stock count
- compare_holdings(acc_q2, acc_q3): compare Q2 vs Q3
- search_stock_cusip_by_name(keywords): find stock CUSIP
- get_top_holders(cusip, quarter): top fund holders
