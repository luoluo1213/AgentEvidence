import pymupdf


PDF_PATH = "data/research_raw/react/raw.pdf"
PAGE_NUMBER = 2


doc = pymupdf.open(PDF_PATH)

page = doc[PAGE_NUMBER - 1]

blocks = page.get_text("blocks")

print(f"=== Page {PAGE_NUMBER} Blocks ===")
print("count =", len(blocks))

for i, block in enumerate(blocks):
    x0, y0, x1, y1, text, *_ = block

    text = text.strip()

    if not text:
        continue

    print("\n" + "=" * 60)
    print("block =", i)
    print(
        "bbox =",
        round(x0, 1),
        round(y0, 1),
        round(x1, 1),
        round(y1, 1),
    )
    print("chars =", len(text))
    print(text[:1500])

doc.close()