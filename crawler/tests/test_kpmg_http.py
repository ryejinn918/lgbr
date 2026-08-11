"""KPMG Cludo list helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from crawler.sources.kpmg_http import DEFAULT_QUERY, fetch_list_page, get_catalog


def test_default_query_is_hub_browse() -> None:
    assert DEFAULT_QUERY == "*"
    assert get_catalog("us").query == "*"


def test_fetch_list_page_sends_hub_query_by_default() -> None:
    payload = {
        "TypedDocuments": [],
        "TotalDocument": 0,
    }
    sess = MagicMock()
    with patch(
        "crawler.sources.kpmg_http.get_json", return_value=payload
    ) as get_json:
        items, has_more = fetch_list_page(1, catalog="us", session=sess)

    assert items == []
    assert has_more is False
    params = get_json.call_args.kwargs["params"]
    assert params["query"] == "*"
    assert params["contentType"] == "Insight"
