---
name: evo-pdf-updater
---

---
name: evo-pdf-updater
description: Complete workflow for updating PDF forms based on text file instructions. Uses PyMuPOF. Handles parsing, comparison, replacement, form filling, and redaction.
---

# Evo PDF Updater Skill

## Overview
Updates PDF documents based on instructions in a companion text file.

## CRITICAL RULES
- NEVER use strikethrough lines
- NEVER rasterize the PDF to images
- NEVER add text NEXT TO replaced values - REPLACE at SAME position
- Redaction: use add_redact_annot() with WHITE fill, then apply_redactions()
- Fill forms: align text on lines in text boxes
- Do NOT add info already correct in PDF
- Text file is SOURCE OF TRUTH

## Workflow
1. Parse input.txt using scripts/utils.py
2. Read PDF with PyMuPDF
3. Compare PDF content with parsed data
4. Apply changes: replace, fill blanks, redact
5. Save to /root/output/output.pdf
