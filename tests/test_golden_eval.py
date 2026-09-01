from __future__ import annotations

from pathlib import Path

from docq import golden_eval, search, store, indexer, tokens


def _make_hit(path="test.pdf", start=1, end=1, score=1.0) -> search.Hit:
    return search.Hit(
        chunk_id="c1", path=path, location="p.1",
        start_page=start, end_page=end, score=score, snippet="text",
    )


class TestIsCorrect:
    def test_path_and_page_match(self):
        assert golden_eval.is_correct(_make_hit("a.pdf", 2, 4), "a.pdf", 3)

    def test_page_at_start_boundary(self):
        assert golden_eval.is_correct(_make_hit("a.pdf", 2, 4), "a.pdf", 2)

    def test_page_at_end_boundary(self):
        assert golden_eval.is_correct(_make_hit("a.pdf", 2, 4), "a.pdf", 4)

    def test_single_page_chunk(self):
        assert golden_eval.is_correct(_make_hit("a.pdf", 3, 3), "a.pdf", 3)

    def test_wrong_path(self):
        assert not golden_eval.is_correct(_make_hit("a.pdf", 1, 1), "b.pdf", 1)

    def test_page_out_of_range(self):
        assert not golden_eval.is_correct(_make_hit("a.pdf", 2, 4), "a.pdf", 5)

    def test_page_before_range(self):
        assert not golden_eval.is_correct(_make_hit("a.pdf", 2, 4), "a.pdf", 1)


class TestValidateGoldenSet:
    def test_valid_set(self):
        queries = [
            golden_eval.GoldenQuery("a1", "q1", "doc.pdf", 1),
            golden_eval.GoldenQuery("a2", "q2", "doc.pdf", 2),
        ]
        corpus = {"doc.pdf": "page1\n%%PAGE%%\npage2"}
        assert golden_eval.validate_golden_set(queries, corpus) == []

    def test_duplicate_anchor(self):
        queries = [
            golden_eval.GoldenQuery("dup", "q1", "doc.pdf", 1),
            golden_eval.GoldenQuery("dup", "q2", "doc.pdf", 1),
        ]
        corpus = {"doc.pdf": "page1"}
        errors = golden_eval.validate_golden_set(queries, corpus)
        assert any("重複" in e for e in errors)

    def test_missing_path(self):
        queries = [golden_eval.GoldenQuery("a1", "q1", "missing.pdf", 1)]
        corpus = {"doc.pdf": "page1"}
        errors = golden_eval.validate_golden_set(queries, corpus)
        assert any("missing.pdf" in e for e in errors)

    def test_page_exceeds_count(self):
        queries = [golden_eval.GoldenQuery("a1", "q1", "doc.pdf", 3)]
        corpus = {"doc.pdf": "p1\n%%PAGE%%\np2"}
        errors = golden_eval.validate_golden_set(queries, corpus)
        assert any("ページ数" in e for e in errors)


class TestEvaluateMetrics:
    def _run(self, tmp_path, pages_text, queries):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas as cv

        try:
            pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
        except Exception:
            pass

        pdf = tmp_path / "doc.pdf"
        c = cv.Canvas(str(pdf), pagesize=A4)
        for i, text in enumerate(pages_text):
            c.setFont("HeiseiMin-W3", 12)
            c.drawString(72, 800, text)
            if i < len(pages_text) - 1:
                c.showPage()
        c.save()

        db = tmp_path / "index.sqlite"
        conn = store.open_store(db)
        try:
            indexer.index_one_file(conn, tmp_path, pdf)
            return golden_eval.evaluate(
                conn,
                [golden_eval.GoldenQuery(**q) for q in queries],
                top_k=5,
                max_tokens=800,
            )
        finally:
            conn.close()

    def test_all_correct(self, tmp_path):
        result = self._run(
            tmp_path,
            ["東京の天気", "大阪の天気"],
            [
                {"anchor": "tokyo", "query": "東京", "expected_path": "doc.pdf", "expected_page": 1},
                {"anchor": "osaka", "query": "大阪", "expected_path": "doc.pdf", "expected_page": 2},
            ],
        )
        assert result.top1 == 1.0
        assert result.topk == 1.0
        assert result.mrr_at_k == 1.0

    def test_all_miss(self, tmp_path):
        result = self._run(
            tmp_path,
            ["東京の天気"],
            [
                {"anchor": "miss", "query": "存在しないxyz", "expected_path": "doc.pdf", "expected_page": 1},
            ],
        )
        assert result.top1 == 0.0
        assert result.topk == 0.0
        assert result.mrr_at_k == 0.0

    def test_token_counter_recorded(self, tmp_path):
        result = self._run(
            tmp_path,
            ["テスト"],
            [{"anchor": "t", "query": "テスト", "expected_path": "doc.pdf", "expected_page": 1}],
        )
        assert result.token_counter == tokens.counter_name()

    def test_elapsed_ms_non_negative(self, tmp_path):
        result = self._run(
            tmp_path,
            ["テスト"],
            [{"anchor": "t", "query": "テスト", "expected_path": "doc.pdf", "expected_page": 1}],
        )
        assert result.elapsed_ms >= 0.0


class TestGenerateCorpus:
    def test_generates_pdfs(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        (corpus_dir / "a.txt").write_text("行1\n行2\n", encoding="utf-8")
        out = tmp_path / "out"
        out.mkdir()
        pdfs = golden_eval.generate_corpus(corpus_dir, out)
        assert len(pdfs) == 1
        assert pdfs[0].name == "a.pdf"
        assert pdfs[0].exists()

    def test_page_split(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        (corpus_dir / "b.txt").write_text("p1\n%%PAGE%%\np2\n", encoding="utf-8")
        out = tmp_path / "out"
        out.mkdir()
        pdfs = golden_eval.generate_corpus(corpus_dir, out)
        assert len(pdfs) == 1

        conn = store.open_store(tmp_path / "db.sqlite")
        try:
            indexer.index_one_file(conn, out, pdfs[0])
            chunks = store.all_chunks(conn)
            pages = {r["start_page"] for r in chunks}
            assert 1 in pages
            assert 2 in pages
        finally:
            conn.close()

    def test_deterministic(self, tmp_path):
        import hashlib

        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        (corpus_dir / "c.txt").write_text("決定的テスト\n", encoding="utf-8")

        hashes = []
        for i in range(2):
            out = tmp_path / f"out{i}"
            out.mkdir()
            golden_eval.generate_corpus(corpus_dir, out)
            h = hashlib.sha1((out / "c.pdf").read_bytes(), usedforsecurity=False).hexdigest()
            hashes.append(h)
        assert hashes[0] == hashes[1]

    def test_width_overflow_raises(self, tmp_path):
        import pytest

        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        long_line = "あ" * 200
        (corpus_dir / "wide.txt").write_text(long_line + "\n", encoding="utf-8")
        out = tmp_path / "out"
        out.mkdir()
        with pytest.raises(ValueError, match="描画領域"):
            golden_eval.generate_corpus(corpus_dir, out)


class TestCheckBaseline:
    def test_pass(self):
        result = golden_eval.EvalResult(
            top1=0.5, topk=0.8, mrr_at_k=0.6,
            total_queries=10, token_counter="x", details=[], elapsed_ms=0.0,
        )
        baseline = {"top1": 0.5, "topk": 0.8, "mrr_at_k": 0.6}
        assert golden_eval.check_baseline(result, baseline) == []

    def test_above_passes(self):
        result = golden_eval.EvalResult(
            top1=0.6, topk=0.9, mrr_at_k=0.7,
            total_queries=10, token_counter="x", details=[], elapsed_ms=0.0,
        )
        baseline = {"top1": 0.5, "topk": 0.8, "mrr_at_k": 0.6}
        assert golden_eval.check_baseline(result, baseline) == []

    def test_below_fails(self):
        result = golden_eval.EvalResult(
            top1=0.4, topk=0.8, mrr_at_k=0.6,
            total_queries=10, token_counter="x", details=[], elapsed_ms=0.0,
        )
        baseline = {"top1": 0.5, "topk": 0.8, "mrr_at_k": 0.6}
        failures = golden_eval.check_baseline(result, baseline)
        assert len(failures) == 1
        assert failures[0][0] == "top1"

    def test_missing_key_fails(self):
        result = golden_eval.EvalResult(
            top1=0.5, topk=0.8, mrr_at_k=0.6,
            total_queries=10, token_counter="x", details=[], elapsed_ms=0.0,
        )
        baseline = {"top1": 0.5, "topk": 0.8}
        failures = golden_eval.check_baseline(result, baseline)
        assert len(failures) == 1
        assert failures[0][0] == "mrr_at_k"
