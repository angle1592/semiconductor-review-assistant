from app.desktop.windows_session import SessionEndHandler


def test_query_end_session_requests_graceful_shutdown():
    stopped: list[bool] = []
    handler = SessionEndHandler(lambda: stopped.append(True))

    result = handler.handle(SessionEndHandler.WM_QUERYENDSESSION, 1)

    assert result == 1
    assert stopped == [True]


def test_unrelated_window_message_is_not_handled():
    handler = SessionEndHandler(lambda: None)
    assert handler.handle(0x0010, 0) is None
