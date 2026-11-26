from src import special_people as sp

OUTSIDER = 42


def test_ownership_questions_are_detected():
    for text in [
        "tera owner kaun hai",
        "who made you",
        "is bot ka malik kon hai",
        "kisne banaya tujhe",
        "who owns this bot?",
        "your creator?",
    ]:
        assert sp.is_ownership_question(text), text
    for text in ["owner of the house came today", "kal match kaun jeeta", "made biryani today"]:
        assert not sp.is_ownership_question(text), text


def test_roast_target_found_by_mention_or_name():
    assert sp.protected_target_of_roast("roast this guy", [sp.AALU_ID]) == sp.AALU_ID
    assert sp.protected_target_of_roast("wahab ki bezti karo", []) == sp.NAAMWAHAB_ID
    assert sp.protected_target_of_roast("mina ko roast kar", []) == sp.MINA_ID
    assert sp.protected_target_of_roast("roast this guy", [OUTSIDER]) is None
    assert sp.protected_target_of_roast("aalu is cool", []) is None


def test_owners_never_roasted_mina_one_in_ten():
    assert not sp.allow_roast_of(sp.NAAMWAHAB_ID, roll=0.0)
    assert not sp.allow_roast_of(sp.AALU_ID, roll=0.0)
    assert sp.allow_roast_of(sp.MINA_ID, roll=0.05)
    assert not sp.allow_roast_of(sp.MINA_ID, roll=0.5)
    assert sp.allow_roast_of(OUTSIDER, roll=0.99)


def test_gentle_and_rules_agree_on_the_same_roll():
    for roll in (0.05, 0.5):
        gentle = sp.gentle_with(sp.MINA_ID, roll)
        rules = sp.reply_rules(sp.MINA_ID, roll)
        assert gentle == ("No roasting" in rules)
    assert sp.gentle_with(sp.AALU_ID, 0.0)
    assert not sp.gentle_with(OUTSIDER, 0.5)
    assert "one of your owners" in sp.reply_rules(sp.NAAMWAHAB_ID)
    assert sp.reply_rules(OUTSIDER).strip() == sp.GLOBAL_RULES


def test_roast_redirect_targets_the_asker():
    assert "roast Ali instead" in sp.roast_redirect_rules("Ali", OUTSIDER, sp.AALU_ID)
    assert "genuinely good about aalu" in sp.roast_redirect_rules("wahab", sp.NAAMWAHAB_ID, sp.AALU_ID)


def test_owner_answer_names_both_owners():
    for answer in sp.OWNER_ANSWERS:
        assert "naamwahab" in answer and "aalu" in answer
