from sales import web


def test_hidden_text_is_only_in_the_raw_version():
    raw = web.fetch("https://petalandstem.example", visible_only=False)["text"]
    shown = web.fetch("https://petalandstem.example", visible_only=True)["text"]
    assert "40% enterprise discount" in raw
    assert "40%" not in shown and "team of 6" in shown


def test_only_a_zero_font_size_counts_as_hidden():
    def shown(style):
        p = web._Text(visible_only=True)
        p.feed(f'<p style="{style}">We employ 80 people.</p>')
        return p.text()
    for style in ("font-size:0", "font-size: 0px", "font-size:0.0em;color:red", "display:none"):
        assert shown(style) == ""
    for style in ("font-size:0.8em", "font-size: 0.05rem", "font-size:10px"):
        assert shown(style) == "We employ 80 people."


def test_urls_and_domains_are_normalised():
    assert web.domain_of("Ann@Foo.Example") == "foo.example"
    assert web.domain_of("https://www.foo.example/about") == "foo.example"
    page = web.fetch("www.harborgrill.example/about.html", visible_only=True)
    assert page["url"] == "https://harborgrill.example/about"
    assert "https://harborgrill.example/careers" in page["links"]


def test_missing_sites_and_pages_fail_like_http():
    assert "Could not resolve host" in web.fetch("https://greenleafhotels.example", True)["error"]
    assert web.fetch("https://harborgrill.example/menu", True)["error"] == "404 Not Found"
    assert "error" in web.fetch("https://harborgrill.example/../lunacafe.example/index", True)
