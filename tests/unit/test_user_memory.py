import time

from src import api_helpers, user_memory

DAY = 86400


def _fact(text, ts, seen=1, vec=None):
    f = {"text": text, "topic": "other", "ts": ts, "seen": seen}
    if vec is not None:
        f["vec"] = user_memory.encode_vec(vec)
    return f


def test_vec_round_trip_is_normalized():
    out = user_memory.decode_vec(user_memory.encode_vec([3.0, 4.0]))
    assert abs(out[0] - 0.6) < 1e-3 and abs(out[1] - 0.8) < 1e-3


def test_strength_halves_per_half_life_and_confirmations_slow_decay():
    now = time.time()
    old = now - user_memory.HALF_LIFE_DAYS * DAY
    assert abs(user_memory.strength(_fact("x", old), now) - 0.5) < 1e-6
    assert user_memory.strength(_fact("x", old, seen=3), now) > 0.75


def test_apply_updates_confirms_replaces_and_adds():
    now = 1_000_000.0
    facts = [_fact("lives in Karachi", 0), _fact("plays PUBG", 0)]
    updates = {
        "confirm": [2],
        "replace": [{"index": 1, "text": "lives in Lahore", "topic": "location"}],
        "add": [{"text": "likes biryani", "topic": "food"}, {"text": "Plays PUBG", "topic": "games"}],
    }
    out = user_memory.apply_fact_updates(facts, updates, now)
    assert [f["text"] for f in out] == ["lives in Lahore", "plays PUBG", "likes biryani"]
    assert out[1]["seen"] == 2 and out[1]["ts"] == now
    assert facts[0]["text"] == "lives in Karachi"


def test_apply_updates_drops_sensitive_facts():
    updates = {"add": [{"text": "is in therapy", "topic": "other"}, {"text": "supports PTI", "topic": "other"}]}
    assert user_memory.apply_fact_updates([], updates, 0.0) == []


def test_apply_updates_caps_by_strength_not_order():
    now = 1000 * DAY
    facts = [_fact("strong old", now - 10 * DAY, seen=4)] + [_fact(f"f{i}", now - 200 * DAY) for i in range(29)]
    out = user_memory.apply_fact_updates(facts, {"add": [{"text": "new one", "topic": "other"}]}, now)
    texts = [f["text"] for f in out]
    assert len(out) == user_memory.MAX_FACTS
    assert "strong old" in texts and "new one" in texts


def test_parse_fact_updates_rejects_bad_indexes_and_garbage():
    raw = '```json\n{"add": [{"text": "plays Valorant", "topic": "games"}, {"text": 5}], ' \
          '"replace": [{"index": 9, "text": "lives in Multan"}], "confirm": [1, 7, true]}\n```'
    out = api_helpers._parse_fact_updates(raw, 2)
    assert out == {"add": [{"text": "plays Valorant", "topic": "games"}], "replace": [], "confirm": [1]}
    assert api_helpers._parse_fact_updates("not json", 2) == {"add": [], "replace": [], "confirm": []}


async def test_relevant_facts_ranks_by_embedding(monkeypatch):
    profile = {"facts": [_fact("likes biryani", 0, vec=[1, 0]), _fact("is a student", 0, vec=[0, 1])]}

    async def fake_embed(texts):
        return [[0.1, 0.9]]

    monkeypatch.setattr(user_memory, "fetch_embeddings", fake_embed)
    assert (await user_memory.relevant_facts(profile, "uni ke paper", k=1)) == ["is a student"]


async def test_relevant_facts_falls_back_to_keywords(monkeypatch):
    profile = {"facts": [_fact("likes biryani", 0), _fact("plays cricket on sundays", 0)]}

    async def no_embed(texts):
        return None

    monkeypatch.setattr(user_memory, "fetch_embeddings", no_embed)
    assert (await user_memory.relevant_facts(profile, "cricket match today?", k=1)) == ["plays cricket on sundays"]


async def test_refresh_discards_result_if_facts_changed_meanwhile(monkeypatch):
    profile = {"facts": [_fact("plays PUBG", 0)], "recent_quotes": ["i live in lahore now"]}

    async def fake_updates(existing, quotes):
        profile["facts"].pop(0)  # simulates /forget landing mid-refresh
        return {"add": [{"text": "lives in Lahore", "topic": "location"}], "replace": [], "confirm": []}

    async def fake_embed(texts):
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(user_memory, "fetch_fact_updates", fake_updates)
    monkeypatch.setattr(user_memory, "fetch_embeddings", fake_embed)
    await user_memory.refresh_facts(profile)
    assert profile["facts"] == []


async def test_refresh_adds_and_embeds_new_facts(monkeypatch):
    profile = {"facts": [], "recent_quotes": ["kal valorant khela"]}

    async def fake_updates(existing, quotes):
        return {"add": [{"text": "plays Valorant", "topic": "games"}], "replace": [], "confirm": []}

    async def fake_embed(texts):
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(user_memory, "fetch_fact_updates", fake_updates)
    monkeypatch.setattr(user_memory, "fetch_embeddings", fake_embed)
    await user_memory.refresh_facts(profile)
    assert [f["text"] for f in profile["facts"]] == ["plays Valorant"]
    assert profile["facts"][0]["vec"]
