import html

from redline.align import Delete, Identity, Insert, ParagraphGroup, align_units
from redline.blocks import Block
from redline.render import (
    _render_edit,
    _render_replace,
    _render_token_pair,
    _shorter_side_is_contained,
    _tag_for,
    render_html,
)


def test_identical_words_render_unchanged():
    assert _render_token_pair("Agreement", "Agreement") == html.escape("Agreement")


def test_trailing_punctuation_deletion_only_marks_the_punctuation():
    # Regression test: split_words() glues punctuation to words, so
    # 'technology".' vs 'technology"' used to render as a full word swap.
    result = _render_token_pair('technology".', 'technology"')
    assert f"<del>{html.escape('.')}</del>" in result
    assert "<ins>" not in result
    assert "<del>technology" not in result  # the shared part isn't deleted


def test_trailing_punctuation_swap_marks_only_the_changed_character():
    result = _render_token_pair("incorrect.", 'incorrect"')
    assert result.startswith(html.escape("incorrect"))
    assert f"<del>{html.escape('.')}</del>" in result
    assert f"<ins>{html.escape(chr(34))}</ins>" in result
    assert "<del>incorrect" not in result  # the shared part isn't deleted


def test_unrelated_words_fall_back_to_whole_word_swap():
    result = _render_token_pair("cat", "philosophy")
    assert result == f"<del>{html.escape('cat')}</del> <ins>{html.escape('philosophy')}</ins>"


def test_replace_with_different_token_counts_uses_whole_span():
    # "hello" vs "hi there" is too dissimilar (low character ratio) even
    # once joined into one span, so this must stay a whole-span fallback.
    result = _render_replace(("hello",), ("hi", "there"))
    assert result == f"<del>{html.escape('hello')}</del> <ins>{html.escape('hi there')}</ins>"


def test_replace_with_different_token_counts_clears_threshold_marks_only_the_change():
    # Regression test: a mismatched token count used to always fall back to
    # a whole-span swap, even when the joined spans are mostly identical
    # (e.g. inserting a couple of words plus a punctuation swap). Once
    # joined, "incorrect." vs "now clearly incorrect\"" clears
    # WORD_CHAR_THRESHOLD, so only the actual changes should be marked.
    result = _render_replace(("incorrect.",), ("now", "clearly", 'incorrect"'))
    assert f"<ins>{html.escape('now clearly ')}</ins>" in result
    assert f"<del>{html.escape('.')}</del>" in result
    assert f"<ins>{html.escape(chr(34))}</ins>" in result
    # the shared word itself isn't wrapped in del/ins
    assert "<del>incorrect" not in result
    assert "<ins>incorrect" not in result


def test_replace_with_large_length_disparity_still_marks_only_the_change():
    # Regression test: a short old token ("incorrect.") followed by a much
    # longer new phrase that still opens with "incorrect" used to fall back
    # to a whole-span swap, because sm.ratio() on the joined spans is a
    # character-level ratio that's penalized by the length disparity even
    # though the short side is fully contained in the long side. This is
    # the same size-disparity problem similarity.py's containment blend
    # fixes, just showing up at char-diff granularity instead.
    result = _render_replace(
        ("incorrect.",),
        ("incorrect", "as", "applied", "to", "the", "homomorphic", "encryption", "scheme."),
    )
    assert "<del>incorrect" not in result
    assert "<ins>incorrect" not in result
    assert "<ins>" in result  # the appended clause is still marked
    assert "as applied to the homomorphic encryption scheme" in result


def test_contained_check_rejects_coincidental_character_prefix():
    # "cat" is a character-level prefix of "category", but they're
    # different words -- this must not be treated as containment (that
    # was the false positive a raw character-level containment check,
    # rather than a word-level one, would have introduced).
    assert not _shorter_side_is_contained(("cat",), ("category", "stuff", "here"))


def test_contained_check_accepts_punctuation_stripped_containment():
    assert _shorter_side_is_contained(
        ("incorrect.",),
        ("incorrect", "as", "applied", "to", "the", "homomorphic", "encryption", "scheme."),
    )


def test_end_to_end_punctuation_only_change_is_minimally_marked():
    old = 'No use for old technology".'
    new = 'No use for old technology"'
    ops = align_units(old, new, "word")
    assert len(ops) == 1
    rendered = _render_edit(ops[0])
    assert rendered.count("technology") == 1  # word itself isn't duplicated as del+ins
    assert f"<del>{html.escape('.')}</del>" in rendered
    assert "<ins>" not in rendered


def test_end_to_end_trailing_punctuation_swap_only_marks_the_symbol():
    old = "This is technically incorrect."
    new = 'This is technically incorrect"'
    ops = align_units(old, new, "word")
    assert len(ops) == 1
    rendered = _render_edit(ops[0])
    assert rendered.count("incorrect") == 1
    assert f"<del>{html.escape('.')}</del>" in rendered
    assert f"<ins>{html.escape(chr(34))}</ins>" in rendered


def test_end_to_end_appended_clause_after_incorrect_is_minimally_marked():
    # End-to-end reproduction of the reported bug, through align_units.
    old = "This statement is technically incorrect."
    new = "This statement is technically incorrect as applied to the homomorphic encryption scheme."
    ops = align_units(old, new, "word")
    assert len(ops) == 1
    rendered = _render_edit(ops[0])
    assert rendered.count("incorrect") == 1
    assert "<del>incorrect" not in rendered
    assert "as applied to the homomorphic encryption scheme" in rendered


# --- style_by_text / heading rendering (added 2026-07-12, Option A) ---


def test_tag_for_returns_p_with_no_style_map():
    assert _tag_for("1 Intro", None) == "p"


def test_tag_for_returns_p_for_non_heading_style():
    assert _tag_for("Some body text.", {"Some body text.": "Normal"}) == "p"


def test_tag_for_maps_heading_level_to_hn_tag():
    assert _tag_for("2.3 Foo", {"2.3 Foo": "Heading 2"}) == "h2"


def test_tag_for_defaults_to_h1_for_non_numeric_heading_style():
    assert _tag_for("Abstract", {"Abstract": "Heading"}) == "h1"


def test_render_html_wraps_identity_paragraph_matching_style_map_in_heading_tag():
    items = [ParagraphGroup([Identity("1 Intro")])]
    out = render_html(items, {"1 Intro": "Heading 1"})
    assert "<h1 class='identity'>1 Intro</h1>" in out
    assert "<p class='identity'>1 Intro</p>" not in out


def test_render_html_wraps_insert_and_delete_heading_text_in_heading_tag():
    items = [ParagraphGroup([Insert("2 Method")]), ParagraphGroup([Delete("3 Results")])]
    style_by_text = {"2 Method": "Heading 1", "3 Results": "Heading 1"}
    out = render_html(items, style_by_text)
    assert "<h1><ins>2 Method</ins></h1>" in out
    assert "<h1><del>3 Results</del></h1>" in out


def test_render_html_leaves_non_heading_paragraphs_as_p_even_with_style_map():
    items = [ParagraphGroup([Identity("Ordinary body text.")])]
    out = render_html(items, {"1 Intro": "Heading 1"})
    assert "<p class='identity'>Ordinary body text.</p>" in out


def test_render_html_without_style_map_renders_plain_paragraphs():
    items = [ParagraphGroup([Identity("1 Intro")])]
    out = render_html(items)
    assert "<p class='identity'>1 Intro</p>" in out
    assert "<h1" not in out


def test_render_html_block_exact_match_uses_heading_tag_when_styled():
    block = Block(index_a=range(0, 1), index_b=range(0, 1), text_a="1 Intro", text_b="1 Intro", transform="exact")
    out = render_html([block], {"1 Intro": "Heading 1"})
    assert "<h1 class='identity'>1 Intro</h1>" in out


# --- ParagraphGroup rendering (added 2026-07-21, sentence-flattening rework) ---


def test_paragraph_group_renders_mixed_ops_inline_in_one_p_tag():
    # A group with an unchanged sentence followed by an edited one should
    # render as ONE <p>, with each sentence's markup inline -- not one <p>
    # per sentence.
    from redline.align import Edit

    edit = Edit("Old sentence.", "New sentence.", ("Old", "sentence."), ("New", "sentence."),
                (("replace", 0, 1, 0, 1), ("equal", 1, 2, 1, 2)))
    group = ParagraphGroup([Identity("Kept sentence."), edit])
    out = render_html([group])
    assert out.count("<p>") == 1
    assert "Kept sentence." in out
    assert "<del>Old</del>" in out
    assert "<ins>New</ins>" in out


def test_paragraph_group_all_identity_gets_identity_class():
    group = ParagraphGroup([Identity("First."), Identity("Second.")])
    out = render_html([group])
    assert "<p class='identity'>First. Second.</p>" in out


def test_paragraph_group_with_any_change_has_no_identity_class():
    group = ParagraphGroup([Identity("Unchanged."), Insert("New clause.")])
    out = render_html([group])
    assert "class='identity'" not in out


# --- moved-content rendering (added 2026-07-22) ---


def test_moved_away_renders_a_direction_marker_without_the_full_text():
    from redline.moves import MovedAway

    group = ParagraphGroup([MovedAway("Relocated sentence.", "below")])
    out = render_html([group])
    assert "<span class='moved'>{moved below}</span>" in out
    assert "Relocated sentence." not in out


def test_moved_here_renders_the_full_text_with_a_direction_marker():
    from redline.moves import MovedHere

    group = ParagraphGroup([MovedHere("Relocated sentence.", "above")])
    out = render_html([group])
    assert "<span class='moved'>{moved from above} Relocated sentence.</span>" in out
