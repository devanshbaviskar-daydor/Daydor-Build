"""Worker registry: coverage, data-class rules, autonomy ladder, and committed outputs.

The mutation tests prove each rule can actually fail, by breaking a copy of a real record."""
import copy
import json

import pytest

from daydor.agents import registry as R
from daydor.model import load_model


@pytest.fixture(scope="module")
def recs():
    return R.build()


def by_name(recs, name):
    return copy.deepcopy(next(r for r in recs if r["worker"] == name))


def errors_with(recs, record):
    rest = [r for r in recs if r["worker"] != record["worker"]]
    return R.validate(rest + [record])


def test_registry_is_valid(recs):
    assert R.validate(recs) == []


def test_every_model_worker_is_classified_exactly_once(recs):
    assert sorted(r["worker"] for r in recs) == sorted(R.model_workers())
    assert len(recs) == 89


def test_human_actors_are_not_workers(recs):
    assert not {r["worker"] for r in recs} & R.HUMAN_ACTORS


def test_every_flow_step_worker_is_classified(recs):
    names = {r["worker"] for r in recs}
    for f in load_model().flows:
        for step in f["steps"]:
            if step[2] not in R.HUMAN_ACTORS | R.PSEUDO:
                assert R.norm(step[2]) in names, step


def test_derived_scope_matches_the_model_plus_reviewed_extras(recs):
    m = load_model()
    extra = {a["worker"]: a["extra_scope"] for a in R.authored() if "extra_scope" in a}
    for r in recs:
        ex = extra.get(r["worker"], {})
        for t in r["writes"]:
            assert t in ex.get("writes", []) or any(R.norm(w) == r["worker"] for w in m.table(t).writers)
        for t in r["reads"]:
            assert t in ex.get("reads", []) or any(R.norm(w) == r["worker"] for w in m.table(t).readers)


# ---- rule 1: restricted data never reaches a model
def test_model_workers_have_no_restricted_tables_except_flagged(recs):
    for r in recs:
        uses_model = r["kind"] in ("decider", "llm") or r.get("assist")
        if uses_model and r["restricted_tables"]:
            assert set(r["flags"]) & R.POLICY_FLAGS, r["worker"]
    flagged = [r["worker"] for r in recs if set(r.get("flags", [])) & R.POLICY_FLAGS]
    assert flagged == ["candidate-screener"]
    assert "needs-policy-decision" not in {f for r in recs for f in r.get("flags", [])}     # decided: ADR-006


def test_giving_a_model_to_a_c4_worker_is_rejected(recs):
    r = by_name(recs, "case-intake-router")
    assert r["restricted_tables"], "precondition: er_case is restricted"
    r.update(kind="decider", decision={"category": ["a", "b"]})
    errs = errors_with(recs, r)
    assert any("restricted tables" in e for e in errs)
    assert any("flagged no-models but uses a model" in e for e in errs)


def test_model_assist_on_a_c3_worker_is_rejected(recs):
    r = by_name(recs, "punch-validator")
    r["assist"] = [{"type": "decider", "use": "ambiguous punches"}]
    assert any("restricted tables" in e for e in errors_with(recs, r))


def test_no_models_flag_must_be_true(recs):
    r = by_name(recs, "first-day-notifier")
    r["flags"] = ["C4-no-models"]
    assert any("touches no restricted tables" in e for e in errors_with(recs, r))


# ---- rule 3: irreversible effects
def test_irreversible_worker_cannot_run_autonomously(recs):
    r = by_name(recs, "direct-deposit-disburser")
    r["autonomy"] = "auto"
    assert any("needs autonomy=approve" in e for e in errors_with(recs, r))


def test_ungated_irreversible_worker_must_say_so(recs):
    r = by_name(recs, "tax-filing-submitter")
    r["flags"] = [f for f in r["flags"] if f != "no-gate-on-irreversible"]
    assert any("no hard gate covers" in e for e in errors_with(recs, r))


def test_gated_worker_cannot_claim_to_be_ungated(recs):
    r = by_name(recs, "direct-deposit-disburser")
    r["flags"] = r["flags"] + ["no-gate-on-irreversible"]
    assert any("flagged no-gate" in e for e in errors_with(recs, r))


def test_the_four_ungated_irreversible_workers(recs):
    ungated = sorted(r["worker"] for r in recs
                     if r["effect"] == "external_irreversible" and not r["gates_on_written_tables"])
    assert ungated == ["device-purchase-initiator", "i9-e-verify-initiator", "in-country-tax-remitter",
                       "tax-filing-submitter"]


# ---- rule 4 and 5: LLM and decider workers
def test_llm_workers_cannot_take_external_actions(recs):
    r = by_name(recs, "requisition-drafter")
    r["effect"] = "external_reversible"
    assert any("cannot have effect" in e for e in errors_with(recs, r))


def test_llm_messages_cannot_be_autonomous(recs):
    r = by_name(recs, "interview-scheduler")
    r["autonomy"] = "auto"
    assert any("cannot be autonomy=auto" in e for e in errors_with(recs, r))


def test_llm_worker_needs_a_tier(recs):
    r = by_name(recs, "vendor-bill-processor")
    del r["llm_tier"]
    assert any("needs llm_tier" in e for e in errors_with(recs, r))


def test_decider_worker_needs_a_typed_decision_and_a_real_gate(recs):
    r = by_name(recs, "payroll-anomaly-detector")
    del r["decision"]
    assert any("typed decision" in e for e in errors_with(recs, r))
    r = by_name(recs, "payroll-anomaly-detector")
    r["soft_gate"] = "sg_made_up"
    assert any("not registered" in e for e in errors_with(recs, r))


def test_registered_soft_gates_are_owned_by_a_decider_worker(recs):
    owners = {r["soft_gate"] for r in recs if r.get("soft_gate")}
    assert {s.gate_id for s in R.SOFT_GATES} <= owners


def test_mutation_breaks_coverage(recs):
    errs = R.validate([r for r in recs if r["worker"] != "gl-poster"])
    assert any("missing" in e and "gl-poster" in e for e in errs)


# ---- facts the design depends on
def test_tables_with_two_writers_across_a_guard_need_per_worker_grants(recs):
    shared = {}
    for r in recs:
        for t in r["guarded_tables_written"]:
            shared.setdefault(t, []).append(r["worker"])
    assert all(len(ws) == 2 for ws in shared.values()) and len(shared) == 9   # 9 here: this repo also guards cobra_event.notice_sent_at (0022), expense.reimbursed_at and leave_request.fmla_designation (0031)


def test_wave_one_is_the_hire_flow(recs):
    wave1 = {r["worker"] for r in recs if r["wave"] == 1}
    hire = {R.norm(s[2]) for f in load_model().flows if f["id"] == "hire" for s in f["steps"]} - R.HUMAN_ACTORS
    assert wave1 == hire


def test_committed_outputs_match_the_registry(recs):
    assert json.loads(R.GENERATED.read_text()) == json.loads(json.dumps(recs))
    assert R.DOC_MD.read_text() == R.to_markdown(recs)
    assert R.DOC_CSV.read_text() == R.to_csv(recs)


# ---- reviewed extra_scope (docs/registry-scope-proposal.md) and platform actors
def test_extra_scope_and_platform_actors_are_valid():
    assert R.validate_extra_scope() == []


def test_extra_scope_is_merged_into_scope(recs):
    by = {r["worker"]: r for r in recs}
    assert {"job_requisition", "job_profile"} <= set(by["employee-record-writer"]["reads"])
    assert "job_requisition" in by["employee-record-writer"]["writes"]
    assert "checklist_task" in by["termination-checklist-builder"]["writes"]
    assert "payslip_line" in by["payroll-run-builder"]["writes"] and "payslip" not in by["payroll-run-builder"]["writes"]


def test_no_worker_carries_a_combined_scope_any_more(recs):
    """payroll-run-builder's combined scope was retired when run_builder.py was split across its workers."""
    assert [r["worker"] for r in recs if "combined-scope-until-split" in r.get("flags", [])] == []
    builder = next(r for r in recs if r["worker"] == "payroll-run-builder")
    assert not {"payroll_profile", "pt_slab_rule", "statutory_rate_rule", "garnishment_order"} & set(builder["reads"])


def _auth(**patch):
    auth = copy.deepcopy(R.authored())
    w = next(a for a in auth if a["worker"] == "payslip-issuer")
    w["extra_scope"] = {**w["extra_scope"], **patch}
    return auth


def test_mutation_extra_scope_needs_a_reason():
    assert any("needs a why" in e for e in R.validate_extra_scope(_auth(why="")))


def test_mutation_extra_scope_must_name_real_tables():
    assert any("unknown table" in e for e in R.validate_extra_scope(_auth(reads=["no_such_table"])))


def test_mutation_extra_scope_cannot_repeat_the_model():
    assert any("already grants" in e for e in R.validate_extra_scope(_auth(reads=["payroll_run"], writes=["payslip"])))


def test_mutation_extra_scope_cannot_smuggle_restricted_data_to_a_model():
    # An LLM worker given a restricted table through extra_scope must still fail the model rule.
    restricted = next(t.id for t in load_model().tables if any(c.encrypted for c in t.columns))
    recs = copy.deepcopy(R.build())
    w = next(r for r in recs if r["kind"] == "llm" and not set(r.get("flags", [])) & R.POLICY_FLAGS)
    w["restricted_tables"] = sorted(set(w["restricted_tables"]) | {restricted})
    assert any("uses a model but scope has restricted tables" in e for e in R.validate(recs))


def test_mutation_platform_actor_cannot_shadow_a_worker():
    actors = R.platform_actors() + [{"actor": "gl-poster", "reads": [], "writes": []}]
    assert any("collides" in e for e in R.validate_extra_scope(actors=actors))


# ---- ADR-006 decisions
def test_candidate_screener_gets_no_resume_text_and_no_model_assist(recs):
    r = by_name(recs, "candidate-screener")
    assert "c3-inputs-excluded" in r["flags"] and "shadow-only" in r["flags"]
    assert r.get("assist", []) == [] and r["autonomy"] == "approve"


def test_mutation_c3_inputs_excluded_forbids_a_model_assist(recs):
    r = by_name(recs, "candidate-screener")
    r["assist"] = [{"type": "llm", "use": "resume field extraction"}]
    assert any("c3-inputs-excluded but has model assists" in e for e in errors_with(recs, r))


def test_mutation_c3_inputs_excluded_needs_a_human_and_shadow_only(recs):
    r = by_name(recs, "candidate-screener")
    r["autonomy"] = "review"
    assert any("needs autonomy=approve" in e for e in errors_with(recs, r))
    r = by_name(recs, "candidate-screener")
    r["flags"] = [f for f in r["flags"] if f != "shadow-only"]
    assert any("shadow-only" in e for e in errors_with(recs, r))


def test_unbuilt_irreversible_workers_without_a_gate_are_disabled_by_default(recs):
    off = sorted(r["worker"] for r in recs if r.get("enabled_by_default") is False)
    assert off == ["device-purchase-initiator", "in-country-tax-remitter"]
    for r in recs:
        if (r["effect"] == "external_irreversible" and "no-gate-on-irreversible" in r.get("flags", [])
                and r["wave"] >= 4):
            assert r.get("enabled_by_default") is False, r["worker"]


def test_mutation_an_enabled_unbuilt_irreversible_worker_is_rejected(recs):
    r = by_name(recs, "device-purchase-initiator")
    r["enabled_by_default"] = True
    assert any("must be enabled_by_default=false" in e for e in errors_with(recs, r))
    r = by_name(recs, "device-purchase-initiator")
    r["disabled_why"] = ""
    assert any("needs a disabled_why" in e for e in errors_with(recs, r))


# ---- Phase B: an LLM worker's contract
def llm(recs, name="requisition-drafter"):
    return by_name(recs, name)


def test_every_llm_worker_has_a_contract_and_the_drafter_is_built(recs):
    for r in recs:
        if r["kind"] == "llm":
            assert "contract" in r and r["contract"]["gates_may_request"] == [], r["worker"]
        else:
            assert "contract" not in r, r["worker"]
    assert [r["worker"] for r in recs if r["kind"] == "llm" and r["contract"].get("built")] == ["requisition-drafter"]


def test_mutation_an_llm_worker_without_a_contract_is_rejected(recs):
    r = llm(recs); del r["contract"]
    assert any("needs a contract" in e for e in errors_with(recs, r))


def test_mutation_only_llm_workers_have_a_contract(recs):
    r = by_name(recs, "gl-poster"); r["contract"] = {"built": False, "max_data_class": "C0", "gates_may_request": []}
    assert any("only llm workers have a contract" in e for e in errors_with(recs, r))


def test_mutation_a_model_may_never_open_a_gate(recs):
    r = llm(recs); r["contract"]["gates_may_request"] = ["g_requisition_budget"]
    assert any("never opens gates" in e for e in errors_with(recs, r))


def test_mutation_the_contract_cannot_allow_restricted_data(recs):
    r = llm(recs); r["contract"]["max_data_class"] = "C3"
    assert any("never C3 or C4" in e for e in errors_with(recs, r))
    r = llm(recs); r["contract"]["context"] = r["contract"]["context"] + ["employee.date_of_birth"]
    errs = errors_with(recs, r)
    assert any("restricted data never reaches a model" in e for e in errs) and any("outside the worker's scope" in e for e in errs)


def test_mutation_context_above_the_contracts_class_or_outside_scope_is_rejected(recs):
    r = llm(recs); r["contract"]["context"] = r["contract"]["context"] + ["position.budgeted_cost"]
    assert any("above the contract's max_data_class" in e for e in errors_with(recs, r))
    r = llm(recs); r["contract"]["context"] = ["job_profile.nonexistent"]
    assert any("not a model column" in e for e in errors_with(recs, r))


def test_mutation_a_changed_prompt_must_be_a_new_version(recs):
    r = llm(recs); r["contract"]["prompt_sha256"] = "0" * 64
    assert any("does not match its pinned sha256" in e for e in errors_with(recs, r))
    r = llm(recs); r["contract"]["prompt_version"] = "v99"
    assert any("does not exist" in e for e in errors_with(recs, r))


def test_mutation_budgets_and_schema_must_be_real(recs):
    r = llm(recs); r["contract"]["budgets"] = {**r["contract"]["budgets"], "max_turns": 0}
    assert any("budget max_turns must be a positive number" in e for e in errors_with(recs, r))
    r = llm(recs); r["contract"]["output_schema"] = "nope/1"
    assert any("not in registry/schemas" in e for e in errors_with(recs, r))
    r = llm(recs); r["contract"]["tools"] = ["a", "a"]
    assert any("distinct names" in e for e in errors_with(recs, r))
    r = llm(recs); del r["contract"]["idempotency"]
    assert any("missing idempotency" in e for e in errors_with(recs, r))
