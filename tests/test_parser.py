from wordwave.script_parser import parse_script, tts_text


def test_sentences_become_scenes():
    scenes = parse_script("Hello world. This is a test.")
    assert len(scenes) == 2
    assert scenes[0].plain_text == "Hello world."


def test_keyword_markup():
    scenes = parse_script("Money loves !speed and !focus.")
    kws = [w.text for w in scenes[0].words if w.keyword]
    assert kws == ["speed", "focus"]


def test_title_card():
    scenes = parse_script("## The Big Idea\nSome body text here.")
    assert scenes[0].title is True
    assert scenes[1].title is False


def test_comments_and_blanks_ignored():
    scenes = parse_script("# note\n\nFirst sentence here.\n\n# other\nSecond one here.")
    assert len(scenes) == 2


def test_pause_tag():
    scenes = parse_script("Think about it. [pause 0.8] Now act fast.")
    assert scenes[0].pause_after == 0.8  # pause extends the previous scene's hold
    assert scenes[1].pause_after == 0.0
    assert "pause" not in tts_text(scenes)  # tags never leak into the voiceover
