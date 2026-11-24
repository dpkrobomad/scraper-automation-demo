from scraper.core import Item, crawl, parse_listing, parse_price
from scraper.store import Store

PAGE1 = """
<ol>
 <li><article class="product_pod">
   <p class="star-rating Three"></p>
   <h3><a href="catalogue/a_1/index.html" title="A Light in the Attic">A Light...</a></h3>
   <p class="price_color">£51.77</p><p class="instock availability">In stock</p>
 </article></li>
 <li><article class="product_pod"><h3><a href="catalogue/broken/index.html" title="No price"></a></h3></article></li>
</ol>
<ul class="pager"><li class="next"><a href="page-2.html">next</a></li></ul>
"""

# Same data after a redesign: different classes, no pager.
PAGE2_REDESIGN = """
<div class="product-card">
  <a title="Tipping the Velvet" href="/catalogue/b_2/index.html">x</a>
  <span class="price">£53.74</span><span class="stock">Out of stock</span>
</div>
"""


def test_parse_price():
    assert parse_price("£1,051.77") == 1051.77
    assert parse_price("n/a") is None


def test_parse_listing_and_validation():
    items, problems, nxt = parse_listing(PAGE1, "https://books.toscrape.com/")
    assert [i.title for i in items] == ["A Light in the Attic"]
    assert items[0].price_gbp == 51.77 and items[0].rating == 3 and items[0].in_stock
    assert len(problems) == 1
    assert nxt == "https://books.toscrape.com/page-2.html"


def test_fallback_selectors_survive_redesign():
    items, problems, nxt = parse_listing(PAGE2_REDESIGN, "https://books.toscrape.com/page-2.html")
    assert items[0].title == "Tipping the Velvet" and items[0].price_gbp == 53.74
    assert items[0].in_stock is False and nxt is None


def test_crawl_follows_pagination():
    pages = {"https://x/": PAGE1, "https://x/page-2.html": PAGE2_REDESIGN}
    items, problems, n = crawl("https://x/", max_pages=5, fetch=pages.__getitem__)
    assert n == 2 and len(items) == 2


def test_change_detection():
    s = Store(":memory:")
    a = Item("u1", "Book", 10.0, True, 4)
    assert s.upsert([a])["new"] == 1
    assert s.upsert([a])["unchanged"] == 1
    counts = s.upsert([Item("u1", "Book", 8.5, False, 4)])
    assert counts["price_changed"] == 1 and counts["stock_changed"] == 1
    kinds = [c["kind"] for c in s.changes()]
    assert kinds == ["price", "stock"]
