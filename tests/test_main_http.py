"""
HTTP integration tests for main.py
Run locally with: python -m pytest tests/test_main_http.py -v

Requires: pip install fastapi httpx starlette
Cannot run on Claude's server (no FastAPI).
"""

import json
import os
import shutil
import tempfile
import pytest

UTI_RULESET = {
    "condition_id": "urinary_symptoms",
    "presentation": {
        "label": "Urinary symptoms",
        "free_text_prompt": "Tell us about your symptoms and when they started.",
        "pre_form_information": [
            "If you are feeling very unwell, seek urgent medical help."
        ]
    },
    "questions": [
        {
            "question_id": "urinary_symptoms_1",
            "question": "Are you experiencing pain when passing urine?",
            "answer_key": "dysuria_present",
            "answer_type": "Boolean",
            "send_to_encoder": True,
            "encoder_prompt": "Does the response indicate there is pain when passing urine?"
        },
        {
            "question_id": "urinary_symptoms_2",
            "question": "Have you felt like you have had a fever during this episode?",
            "answer_key": "fever_present",
            "answer_type": "Boolean",
            "send_to_encoder": True,
            "encoder_prompt": "Does the response indicate there is fever in this episode?"
        },
        {
            "question_id": "urinary_symptoms_3",
            "question": "When did the symptoms start?",
            "answer_key": "symptom_onset_text",
            "answer_type": "text",
            "send_to_encoder": False,
            "encoder_prompt": None
        }
    ],
    "safety": {
        "rules": {
            "fever_with_urinary_symptoms": {
                "all": [{"is_true": "fever_present"}],
                "message": "You should seek urgent medical advice if you have a fever with urinary symptoms."
            }
        }
    }
}

HEADACHE_RULESET = {
    "condition_id": "headache",
    "presentation": {
        "label": "Headache",
        "free_text_prompt": "Describe your headache.",
    },
    "questions": [
        {
            "question_id": "headache_1",
            "question": "Is this the worst headache of your life?",
            "answer_key": "thunderclap",
            "answer_type": "Boolean",
            "send_to_encoder": False,
            "encoder_prompt": None
        }
    ],
    "safety": {"rules": {}}
}


@pytest.fixture
def client():
    d = tempfile.mkdtemp()
    db_path = os.path.join(d, "test_runtime.db")

    with open(os.path.join(d, "uti1.json"), "w") as f:
        json.dump(UTI_RULESET, f)
    with open(os.path.join(d, "headache.json"), "w") as f:
        json.dump(HEADACHE_RULESET, f)

    import main
    from persistence import RuntimeStateRepository
    from condition_registry import ConditionRegistry

    main.registry = ConditionRegistry(d)
    main.repo = RuntimeStateRepository(db_path)

    from starlette.testclient import TestClient
    c = TestClient(main.app)
    yield c
    shutil.rmtree(d)


# --- Condition discovery ---

def test_get_conditions(client):
    res = client.get("/conditions")
    assert res.status_code == 200
    ids = [c["id"] for c in res.json()["conditions"]]
    assert "urinary_symptoms" in ids
    assert "headache" in ids


def test_get_presentation(client):
    res = client.get("/conditions/urinary_symptoms/presentation")
    assert res.status_code == 200
    data = res.json()
    assert data["label"] == "Urinary symptoms"
    assert "free_text_prompt" in data


def test_get_presentation_unknown(client):
    res = client.get("/conditions/nonexistent/presentation")
    assert res.status_code == 404


# --- Form init ---

def test_form_init(client):
    res = client.post("/form/init", json={
        "condition_id": "urinary_symptoms",
        "free_text": "I have a fever and it burns",
    })
    assert res.status_code == 200
    data = res.json()
    assert "runtime_id" in data
    assert data["version"] == 1
    assert data["client_state"]["condition_label"] == "Urinary symptoms"

    questions = {q["answer_key"]: q for q in data["client_state"]["questions"]}
    assert questions["fever_present"]["suggested"] is True
    assert questions["fever_present"]["current_value"] is True


def test_form_init_unknown_condition(client):
    res = client.post("/form/init", json={
        "condition_id": "nonexistent",
        "free_text": None,
    })
    assert res.status_code == 422


def test_form_init_no_free_text(client):
    res = client.post("/form/init", json={
        "condition_id": "urinary_symptoms",
        "free_text": None,
    })
    assert res.status_code == 200
    questions = {q["answer_key"]: q for q in res.json()["client_state"]["questions"]}
    assert all(q["suggested"] is False for q in questions.values())


# --- Form update ---

def test_form_update_no_safety(client):
    init = client.post("/form/init", json={
        "condition_id": "urinary_symptoms", "free_text": None,
    }).json()

    res = client.post("/form/update", json={
        "runtime_id": init["runtime_id"],
        "base_version": 1,
        "answers": {
            "dysuria_present": True,
            "fever_present": False,
            "symptom_onset_text": "yesterday",
        },
    })
    assert res.status_code == 200
    assert res.json()["version"] == 2
    assert len(res.json()["safety_messages"]) == 0


def test_form_update_safety_trigger(client):
    init = client.post("/form/init", json={
        "condition_id": "urinary_symptoms", "free_text": None,
    }).json()

    res = client.post("/form/update", json={
        "runtime_id": init["runtime_id"],
        "base_version": 1,
        "answers": {
            "dysuria_present": True,
            "fever_present": True,
            "symptom_onset_text": "2 days ago",
        },
    })
    assert res.status_code == 200
    msgs = res.json()["safety_messages"]
    assert len(msgs) == 1
    assert msgs[0]["rule_id"] == "fever_with_urinary_symptoms"


def test_form_update_encoder_override(client):
    """Encoder suggests fever, patient corrects to False."""
    init = client.post("/form/init", json={
        "condition_id": "urinary_symptoms",
        "free_text": "I have a fever",
    }).json()

    # Encoder should have suggested fever=True
    questions = {q["answer_key"]: q for q in init["client_state"]["questions"]}
    assert questions["fever_present"]["current_value"] is True

    # Patient overrides
    res = client.post("/form/update", json={
        "runtime_id": init["runtime_id"],
        "base_version": 1,
        "answers": {
            "dysuria_present": False,
            "fever_present": False,
            "symptom_onset_text": "today",
        },
    })
    assert res.status_code == 200
    assert len(res.json()["safety_messages"]) == 0


# --- Form finish ---

def test_form_finish(client):
    init = client.post("/form/init", json={
        "condition_id": "urinary_symptoms", "free_text": None,
    }).json()

    update = client.post("/form/update", json={
        "runtime_id": init["runtime_id"],
        "base_version": 1,
        "answers": {
            "dysuria_present": True,
            "fever_present": False,
            "symptom_onset_text": "yesterday",
        },
    }).json()

    res = client.post("/form/finish", json={
        "runtime_id": init["runtime_id"],
        "version": update["version"],
    })
    assert res.status_code == 200
    assert "submission_id" in res.json()


def test_session_closed_after_finish(client):
    init = client.post("/form/init", json={
        "condition_id": "urinary_symptoms", "free_text": None,
    }).json()

    update = client.post("/form/update", json={
        "runtime_id": init["runtime_id"],
        "base_version": 1,
        "answers": {
            "dysuria_present": True,
            "fever_present": False,
            "symptom_onset_text": "yesterday",
        },
    }).json()

    client.post("/form/finish", json={
        "runtime_id": init["runtime_id"],
        "version": update["version"],
    })

    # Further update should fail
    res = client.post("/form/update", json={
        "runtime_id": init["runtime_id"],
        "base_version": update["version"],
        "answers": {
            "dysuria_present": False,
            "fever_present": False,
            "symptom_onset_text": "today",
        },
    })
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "SESSION_CLOSED"