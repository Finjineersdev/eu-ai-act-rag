from pathlib import Path

import actrag
from actrag.ingest import DATA


def test_data_ships_inside_package():
    assert DATA == Path(actrag.__file__).resolve().parent / "data"
    for name in ("corpus.jsonl", "corpus_meta.json", "index.npz"):
        assert (DATA / name).is_file()
