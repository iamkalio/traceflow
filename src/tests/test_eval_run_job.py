"""eval_run_job: header-supplied key + groundedness outcome mapping (mocked I/O)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from db.models import EvalRun, Trace


def _session_with_eval_run(run: MagicMock | EvalRun):
    s = MagicMock()
    s.get = MagicMock(return_value=run)
    s.close = MagicMock()
    s.rollback = MagicMock()
    return s


def test_missing_eval_run_returns_missing():
    session = _session_with_eval_run(None)
    session.get.return_value = None
    with patch("traceflow_jobs.handlers.SessionLocal", return_value=session):
        from traceflow_jobs.handlers import eval_run_job

        assert eval_run_job(404, "sk-x") == "missing"


def test_empty_api_key_fails():
    er = MagicMock(spec=EvalRun)
    er.trace_id = "t1"
    er.span_id = "s1"
    er.evaluator_type = "groundedness"
    session = _session_with_eval_run(er)
    with patch("traceflow_jobs.handlers.SessionLocal", return_value=session), patch(
        "traceflow_jobs.handlers.set_eval_run_failed"
    ) as fail:
        from traceflow_jobs.handlers import eval_run_job

        assert eval_run_job(1, "") == "ok"
        fail.assert_called_once()
        assert "no openai api key" in fail.call_args[1]["error"].lower()


def test_completed_maps_to_set_eval_run_completed():
    er = MagicMock(spec=EvalRun)
    er.trace_id = "t1"
    er.span_id = "s1"
    er.evaluator_type = "groundedness_v1"
    session = _session_with_eval_run(er)
    detail = {"kind": "completed", "score": 0.9, "label": "good", "reason": "ok"}
    with patch("traceflow_jobs.handlers.SessionLocal", return_value=session), patch(
        "traceflow_jobs.handlers.set_eval_run_running"
    ), patch("traceflow_jobs.handlers.set_eval_run_completed") as done, patch(
        "traceflow_jobs.handlers.run_groundedness_span_eval", return_value=("ok", detail)
    ):
        from traceflow_jobs.handlers import eval_run_job

        assert eval_run_job(7, "sk-test") == "ok"
        done.assert_called_once()
        assert done.call_args[1]["score"] == 0.9
        assert done.call_args[1]["label"] == "good"


def test_skipped_maps_to_set_eval_run_skipped():
    er = MagicMock(spec=EvalRun)
    er.trace_id = "t1"
    er.span_id = "s1"
    er.evaluator_type = "groundedness"
    session = _session_with_eval_run(er)
    detail = {"kind": "skipped", "reason": "no key"}
    with patch("traceflow_jobs.handlers.SessionLocal", return_value=session), patch(
        "traceflow_jobs.handlers.set_eval_run_running"
    ), patch("traceflow_jobs.handlers.set_eval_run_skipped") as skip, patch(
        "traceflow_jobs.handlers.run_groundedness_span_eval", return_value=("ok", detail)
    ):
        from traceflow_jobs.handlers import eval_run_job

        assert eval_run_job(2, "sk") == "ok"
        skip.assert_called_once()
        assert "no key" in skip.call_args[1]["reasoning"]


def test_picks_last_span_when_span_id_empty():
    er = MagicMock(spec=EvalRun)
    er.trace_id = "t1"
    er.span_id = None
    er.evaluator_type = "groundedness"
    session = _session_with_eval_run(er)
    s1 = MagicMock(spec=Trace)
    s1.span_id = "early"
    s2 = MagicMock(spec=Trace)
    s2.span_id = "last"
    detail = {"kind": "completed", "score": 1.0, "label": "x", "reason": "y"}
    with patch("traceflow_jobs.handlers.SessionLocal", return_value=session), patch(
        "traceflow_jobs.handlers.set_eval_run_running"
    ), patch("traceflow_jobs.handlers.set_eval_run_completed"), patch(
        "traceflow_jobs.handlers.list_spans_for_trace", return_value=[s1, s2]
    ) as lst, patch("traceflow_jobs.handlers.update_eval_run_span_id") as upd, patch(
        "traceflow_jobs.handlers.run_groundedness_span_eval", return_value=("ok", detail)
    ) as rge:
        from traceflow_jobs.handlers import eval_run_job

        assert eval_run_job(3, "sk") == "ok"
        lst.assert_called_once_with(session, "t1")
        upd.assert_called_once_with(session, 3, "last")
        rge.assert_called_once()
        assert rge.call_args[0][1] == "t1"
        assert rge.call_args[0][2] == "last"


def test_unknown_evaluator_type_fails():
    er = MagicMock(spec=EvalRun)
    er.trace_id = "t1"
    er.span_id = "s1"
    er.evaluator_type = "unknown_eval"
    session = _session_with_eval_run(er)
    with patch("traceflow_jobs.handlers.SessionLocal", return_value=session), patch(
        "traceflow_jobs.handlers.set_eval_run_running"
    ), patch("traceflow_jobs.handlers.set_eval_run_failed") as fail, patch(
        "traceflow_jobs.handlers.run_groundedness_span_eval"
    ) as rge:
        from traceflow_jobs.handlers import eval_run_job

        assert eval_run_job(4, "sk") == "ok"
        rge.assert_not_called()
        fail.assert_called_once()
        assert "unknown" in fail.call_args[1]["error"].lower()


def test_transient_openai_error_reraises_for_rq_retry():
    er = MagicMock(spec=EvalRun)
    er.trace_id = "t1"
    er.span_id = "s1"
    er.evaluator_type = "groundedness"
    session = _session_with_eval_run(er)
    err = ConnectionError("timeout")

    with patch("traceflow_jobs.handlers.SessionLocal", return_value=session), patch(
        "traceflow_jobs.handlers.set_eval_run_running"
    ), patch("traceflow_jobs.handlers.run_groundedness_span_eval", side_effect=err), patch(
        "traceflow_jobs.handlers.is_transient_openai_error", return_value=True
    ):
        from traceflow_jobs.handlers import eval_run_job

        with pytest.raises(ConnectionError):
            eval_run_job(5, "sk")
        session.rollback.assert_called()
