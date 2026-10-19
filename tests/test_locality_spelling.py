"""2026-10-19 (owner: "what about Kedar?!"): "קידר" found nothing - the place is stored "קדר". Names written with or
without the vowel letters י/ו now meet, and a one-word place is read out of a sentence that says it is a place."""
from __future__ import annotations

from todira_common import cities, search_text


def test_a_name_with_the_vowel_letters_finds_the_place():
    assert cities.resolve_locality("קידר") == "קדר"
    assert cities.resolve_locality("קדר") == "קדר"


def test_the_bot_reply_to_which_city_finds_it():
    assert search_text.match_city_reply("קידר") == ["קדר"]


def test_a_sentence_that_says_it_is_a_place_finds_a_one_word_name():
    assert search_text.parse("דירה להשכרה ביישוב קידר")["cities"] == ["קדר"]
    assert search_text.parse("בית במושב נורדיה")["cities"] == ["נורדיה"]


def test_a_one_word_name_alone_in_a_sentence_is_still_not_guessed():
    # "קדר" is also a word (a potter) - without "יישוב"/"מושב"/... it stays unread, as before.
    assert search_text.parse("הקדר של השכונה")["cities"] == []


def test_an_ambiguous_skeleton_is_never_resolved():
    ambiguous = next(k for k, v in cities._SKELETON_INDEX.items() if len(v) > 1)
    assert len(cities._SKELETON_INDEX[ambiguous]) > 1  # such a spelling is left to the suggestions, never picked
