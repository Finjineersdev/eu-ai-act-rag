from actrag.answer import RefusedError, TruncatedError
from actrag.verify import Result
from evals.run import ask_all


def test_counts_citations_from_every_round():
    rounds = iter(
        [
            Result("answered", "a", raw_citations=2, valid_citations=2),
            Result("answered", "b", raw_citations=3, valid_citations=2, removed_blocks=1),
        ]
    )
    res, err, t = ask_all(["q1", "q2"], None, None, lambda *a: next(rounds))
    assert (res.answer, err) == ("b", None)
    assert t == {"raw": 5, "valid": 4, "removed": 1}


def test_model_errors_are_recorded_not_raised():
    for exc, name in ((TruncatedError(), "truncated"), (RefusedError(), "refused")):

        def boom(*a, exc=exc):
            raise exc

        res, err, _ = ask_all(["q"], None, None, boom)
        assert (res, err) == (None, name)
