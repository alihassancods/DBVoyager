import v2


def test_extract_access_token_accepts_neon_response_shapes() -> None:
    assert v2.extract_access_token({"token": "token-0"}) == "token-0"
    assert v2.extract_access_token({"session": {"access_token": "token-1"}}) == "token-1"
    assert v2.extract_access_token({"data": {"session": {"accessToken": "token-2"}}}) == "token-2"


def test_main_logs_in_when_signup_user_already_exists(monkeypatch) -> None:
    monkeypatch.setattr(v2, "validate_configuration", lambda: None)
    monkeypatch.setattr(v2, "wait_for_analysis", lambda *args: {})
    requests = iter(
        [
            v2.ApiError(422, '{"code":"USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL"}'),
            ({"token": "opaque"}, {"set-cookie": "session=cookie; Secure"}),
            ({"session": {}}, {"set-auth-jwt": "jwt"}),
            {"connection_id": "connection", "analysis_run_id": "run"},
        ]
    )
    monkeypatch.setattr(v2, "request_json", lambda *args, **kwargs: next(requests))

    v2.main()
