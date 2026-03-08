
from agentops.graph.state import BugTriageState
from agentops.graph.supervisor import route_from_supervisor


def make_state(**kwargs: object) -> BugTriageState:
    defaults: dict[str, object] = {
        "job_id": "test-123",
        "issue_url": "https://github.com/a/b/issues/1",
    }
    defaults.update(kwargs)
    return BugTriageState(**defaults)


def test_g1_first_iteration_goes_to_investigator() -> None:
    state = make_state(iterations=0)
    assert route_from_supervisor(state) == "investigator"


def test_g3_max_iterations_forces_writer() -> None:
    state = make_state(iterations=10, max_iterations=10, supervisor_next="investigator")
    assert route_from_supervisor(state) == "writer"


def test_g4_no_report_end_forces_writer() -> None:
    state = make_state(iterations=2, supervisor_next="end", report=None)
    assert route_from_supervisor(state) == "writer"


def test_normal_routing_to_writer() -> None:
    state = make_state(iterations=3, supervisor_next="writer")
    assert route_from_supervisor(state) == "writer"


def test_normal_routing_to_investigator() -> None:
    state = make_state(iterations=3, supervisor_next="investigator")
    assert route_from_supervisor(state) == "investigator"
