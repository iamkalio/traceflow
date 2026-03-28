"""Regression compare runs inside eval_run_job when evaluator_type is regression_compare_v1 (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from db.models import EvalRun, Trace


def _session_with_eval_run(run: MagicMock | EvalRun):
    s = MagicMock()
    s.get = MagicMock(return_value=run)
    s.close = MagicMock()
    s.rollback = MagicMock()
    return s


def test_completed_regression_maps_to_set_eval_run_completed():
    er = MagicMock(spec=EvalRun)
    er.trace_id = "t1"
    er.span_id = "s1"
    er.evaluator_type = "regression_compare_v1"
    session = _session_with_eval_run(er)
    detail = {
        "kind": "completed",
        "score": 0.4,
        "label": "improved",
        "reason": "clearer answer",
        "snapshot_input": "hi",
        "snapshot_output": "hello",
        "previous_eval_run_id": 9,
        "previous_score": 0.7,
        "latency_ms": 100,
        "cost_usd": 0.001,
    }
    with patch("traceflow_jobs.handlers.SessionLocal", return_value=session), patch(
        "traceflow_jobs.handlers.set_eval_run_running"
    ), patch("traceflow_jobs.handlers.set_eval_run_completed") as done, patch(
        "traceflow_jobs.handlers.run_regression_compare_span_eval", return_value=("ok", detail)
    ), patch("traceflow_jobs.handlers.run_groundedness_span_eval") as gnd:
        from traceflow_jobs.handlers import eval_run_job

        assert eval_run_job(3, "sk-test") == "ok"
        gnd.assert_not_called()
        done.assert_called_once()
        assert done.call_args[1]["score"] == 0.4
        assert done.call_args[1]["label"] == "improved"
        assert done.call_args[1]["extra_context"]["eval_kind"] == "regression_compare"


def test_skipped_regression():
    er = MagicMock(spec=EvalRun)
    er.trace_id = "t1"
    er.span_id = "s1"
    er.evaluator_type = "regression_compare_v1"
    session = _session_with_eval_run(er)
    detail = {"kind": "skipped", "reason": "no baseline"}
    with patch("traceflow_jobs.handlers.SessionLocal", return_value=session), patch(
        "traceflow_jobs.handlers.set_eval_run_running"
    ), patch("traceflow_jobs.handlers.set_eval_run_skipped") as skip, patch(
        "traceflow_jobs.handlers.run_regression_compare_span_eval", return_value=("ok", detail)
    ):
        from traceflow_jobs.handlers import eval_run_job

        assert eval_run_job(2, "sk") == "ok"
        skip.assert_called_once()


def test_picks_last_span_when_span_id_empty_regression():
    er = MagicMock(spec=EvalRun)
    er.trace_id = "t1"
    er.span_id = None
    er.evaluator_type = "regression_compare_v1"
    session = _session_with_eval_run(er)
    s1 = MagicMock(spec=Trace)
    s1.span_id = "early"
    s2 = MagicMock(spec=Trace)
    s2.span_id = "last"
    detail = {"kind": "completed", "score": 0.0, "label": "unchanged", "reason": "x"}
    with patch("traceflow_jobs.handlers.SessionLocal", return_value=session), patch(
        "traceflow_jobs.handlers.set_eval_run_running"
    ), patch("traceflow_jobs.handlers.set_eval_run_completed"), patch(
        "traceflow_jobs.handlers.list_spans_for_trace", return_value=[s1, s2]
    ) as lst, patch("traceflow_jobs.handlers.update_eval_run_span_id") as upd, patch(
        "traceflow_jobs.handlers.run_regression_compare_span_eval", return_value=("ok", detail)
    ) as rce:
        from traceflow_jobs.handlers import eval_run_job

        assert eval_run_job(4, "sk") == "ok"
        lst.assert_called_once_with(session, "t1")
        upd.assert_called_once_with(session, 4, "last")
        rce.assert_called_once()
        assert rce.call_args[0][2] == "last"
