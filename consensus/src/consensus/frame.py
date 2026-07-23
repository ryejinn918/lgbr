"""Multi-document consensus frame from report compress views."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from consensus.llm import DEFAULT_MODEL, chat, log


def build_consensus(
    compress_cards: list[dict[str, Any]],
    *,
    question: str,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    joined = "\n\n========\n\n".join(
        f"### COMPRESS: {c['slug']} | {Path(c.get('source_pdf') or '').name}\n"
        f"{c['compress']}"
        for c in compress_cards
    )
    log(f"consensus: reports={len(compress_cards)} chars={len(joined):,}")

    prompt = f"""아래는 여러 증권 리포트를 압축한 뷰다.
가장 어려운 일을 해라: 이 묶음 전체를 담을 수 있는 **컨센서스 큰 틀(프레임)** 을 잠가라.

질문: {question}

이게 하는 일 / 아닌 일:
- 하는 일: 여러 관점이 합의·수렴하는 지붕과 큰 칸을 정한다. 세부 수치를 다 채우지 않아도 된다.
- 아닌 일: 리포트별 요약 나열, 임원용 한 장짜리 빈약한 불릿 나열, 특정 산업 템플릿 강제.

규칙:
- 지붕 1개 + 큰 칸 2~4개 (같은 지붕의 다른 면)
- 각 칸: 왜 이 칸이 틀에 필요한지 + 어떤 세부(본문)를 나중에 넣을 자리인지
- 리포트 간 겹침(컨센서스)과 차이(한쪽에만 있는 각도)를 명시
- 큰 틀이 나중에 세부로 볼륨을 키울 수 있게 '슬롯'을 남겨라
- 압축본에 없는 사실 창작 금지
- 출처로 slug를 적어라

압축 뷰들:
{joined}

출력:
# 컨센서스 프레임 (큰 틀)

## 지붕
...

## 왜 이 틀이 묶음 전체를 담는지
...

## 큰 칸
### 1. ...
- 칸의 역할:
- 컨센서스(어느 압축본이 받침):
- 나중에 채울 슬롯:
### 2. ...
### 3. ...

## 틀 밖의 각도(옆/약한 것)
...

## 본문 재조사 우선순위(키워드)
1. ...
"""
    content, _ = chat(
        [
            {
                "role": "system",
                "content": (
                    "Lock a consensus FRAME from compressed multi-report views. "
                    "Structure over detail. Korean. No invented facts."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0.2,
        label="consensus",
        out_dir=out_dir,
    )
    if "본문 재조사 우선순위" not in content or "큰 칸" not in content:
        (out_dir / "04_consensus_frame.partial.md").write_text(content, encoding="utf-8")
        raise RuntimeError("consensus incomplete; saved partial")
    (out_dir / "04_consensus_frame.md").write_text(content, encoding="utf-8")
    log("consensus DONE")
    return content
