from app.document_extract import extract_document


def test_extract_utf8_text_and_normalize_whitespace() -> None:
    assert extract_document("notes.txt", "text/plain", b"  First\r\n\r\nSecond  ") == "First\n\nSecond"


def test_extract_rejects_non_utf8_text() -> None:
    try:
        extract_document("notes.txt", "text/plain", b"\xff")
    except ValueError as error:
        assert "UTF-8" in str(error)
    else:
        raise AssertionError("expected invalid UTF-8 to be rejected")


def test_extract_rejects_unsupported_type() -> None:
    try:
        extract_document("notes.doc", "application/msword", b"text")
    except ValueError as error:
        assert "unsupported" in str(error)
    else:
        raise AssertionError("expected unsupported document type to be rejected")
