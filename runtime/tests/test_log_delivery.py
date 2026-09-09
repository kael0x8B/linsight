import logging

from edge_agent.app.log_delivery.buffer import BufferedLogHandler, log_record


def test_log_buffer_is_bounded_structured_and_acknowledged_by_entry_id() -> None:
    handler = BufferedLogHandler(capacity=2)
    logger = logging.getLogger("test.edge.log-buffer")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        logger.info("first")
        log_record(
            logger,
            logging.ERROR,
            "task failed password=not-for-output",
            component="TASK",
            task_id=8,
            run_id="11111111-1111-1111-1111-111111111111",
            diagnostic_id="22222222-2222-2222-2222-222222222222",
            error_type="TASK_FAILED",
        )
        logger.warning("third")
        entries = handler.peek()

        assert len(entries) == 2
        assert entries[0]["component"] == "TASK"
        assert entries[0]["level"] == "ERROR"
        assert entries[0]["taskId"] == 8
        assert "TASK_FAILED" in entries[0]["contextJson"]

        handler.acknowledge([entries[0]])
        assert [entry["message"] for entry in handler.peek()] == ["third"]
    finally:
        logger.removeHandler(handler)


def test_success_transport_and_heartbeat_noise_is_not_uploaded():
    handler = BufferedLogHandler()
    for text in ['HTTP Request: POST http://localhost/logs "HTTP/1.1 200 OK"',
                 'Heartbeat accepted nodeId=1 sequence=5']:
        handler.emit(logging.LogRecord('httpx', logging.INFO, '', 0, text, (), None))
    handler.emit(logging.LogRecord('httpx', logging.INFO, '', 0,
                 'HTTP Request: POST http://localhost/logs "HTTP/1.1 500 Error"', (), None))
    assert len(handler.peek()) == 1
    assert '500 Error' in handler.peek()[0]['message']


def test_repeated_warnings_emit_first_immediately_then_counted_summary(monkeypatch):
    import json

    from edge_agent.app.log_delivery import buffer
    clock = [0.0]
    monkeypatch.setattr(buffer.time, 'monotonic', lambda: clock[0])
    handler = BufferedLogHandler(repeat_window_seconds=60)
    for _ in range(200):
        handler.emit(logging.LogRecord('linsight.edge_agent', logging.WARNING, '', 0,
                     'Overlay delivery failed errorType=ConnectTimeout', (), None))
    first = handler.peek()
    assert len(first) == 1
    handler.acknowledge(first)
    clock[0] = 61
    summary = handler.peek()
    assert len(summary) == 1
    assert json.loads(summary[0]['contextJson'])['repeatCount'] == 199
    assert summary[0]['entryId'] != first[0]['entryId']
    assert handler.peek() == summary  # retry keeps the same immutable batch entry


def test_distinct_failures_are_not_merged():
    handler = BufferedLogHandler()
    for text in ['failure A', 'failure B']:
        handler.emit(logging.LogRecord('linsight.edge_agent', logging.ERROR, '', 0, text, (), None))
    assert len(handler.peek()) == 2
