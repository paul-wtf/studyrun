from studyrun.main import create_app

SCHEMAS = [
    "RunOut",
    "CurrentRunOut",
    "IntroEntryOut",
    "ItemEntryOut",
    "ObjectiveResultOut",
    "FreeResultOut",
    "GradingUnavailableOut",
    "RunSummaryOut",
    "DoneOut",
    "FlaggedOut",
]


def test_run_schemas_are_declared():
    names = create_app().openapi()["components"]["schemas"]
    for name in SCHEMAS:
        assert name in names, name


def test_booklet_status_is_a_literal():
    status = create_app().openapi()["components"]["schemas"]["BookletOut"]["properties"]["status"]
    assert status["enum"] == ["processing", "ready", "failed"]


def test_start_run_declares_response_schema():
    ok = create_app().openapi()["paths"]["/api/runs"]["post"]["responses"]["200"]
    assert ok["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/RunOut"}
