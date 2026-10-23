"""A book's table of contents must never be served as a source."""

from chavruta.corpus.quality import is_index_page

# The shape of the chunk that reached a lesson's source sheet (ws: layer, 136 lines / 150 words).
TOC = "\n\n".join(
    ["פרשת בראשית", "פרק א", "פרק ב", "פרק ג", "פרק ד", "פרק ה", "פרק ו (1)", "פרשת נח", "פרק ו (2)",
     "פרק ז", "פרק ח", "פרק ט", "פרק י", "פרק יא", "פרשת לך־לך", "פרק יב", "פרק יג"]
)


def test_table_of_contents_is_an_index_page():
    assert is_index_page(TOC)


def test_prose_is_not():
    rashi = ("בראשית ברא. אמר רבי יצחק לא היה צריך להתחיל את התורה אלא מהחדש הזה לכם, שהיא מצוה ראשונה "
             "שנצטוו בה ישראל, ומה טעם פתח בבראשית, משום כח מעשיו הגיד לעמו לתת להם נחלת גוים.")
    assert not is_index_page(rashi)


def test_a_short_heading_block_is_not():
    # a passage may open with a couple of headings; that is not an index
    assert not is_index_page("פרק א\n\nהלכה א\n\nמאימתי קורין את שמע בערבית")


def test_poetry_with_short_lines_is_not():
    psalm = "\n".join(["אשרי האיש אשר לא הלך", "בעצת רשעים ובדרך חטאים", "לא עמד ובמושב לצים",
                       "לא ישב כי אם בתורת ה׳", "חפצו ובתורתו יהגה", "יומם ולילה והיה כעץ",
                       "שתול על פלגי מים", "אשר פריו יתן בעתו"])
    assert not is_index_page(psalm)


def test_empty():
    assert not is_index_page("")
    assert not is_index_page(None)
