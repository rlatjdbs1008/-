"""
📝 시험 범위 빈칸 문제 생성기 (Streamlit) — 다크 모드 버전

사용 흐름
1) 교재/필기 내용을 붙여넣는다.
2) 문제 수, 문장당 빈칸 수를 정하고 '문제 만들기'를 누른다.
   (핵심 단어는 프로그램이 알아서 찾는다)
3) 답을 입력하고 채점 → 틀린 문제만 다시 풀기 / 파일로 저장

실행 방법:  streamlit run app.py
(.streamlit/config.toml 이 있는 폴더에서 실행해야 다크 테마가 적용돼요)
"""

from __future__ import annotations

import html
import json
import os
import random
import re
from collections import Counter

import streamlit as st

# ============================================================
# 1. 기본 설정값
# ============================================================

# 한국어 조사 목록. "정부는" -> "정부"처럼 단어 끝의 조사를 떼어 낼 때 쓴다.
# 긴 조사부터 검사해야 "에서"가 "서"보다 먼저 처리되므로 길이 순으로 정렬한다.
JOSA_LIST = sorted(
    [
        "에서는", "으로서", "에서의", "이라는", "에서", "으로", "까지", "부터",
        "에게", "라는", "에는", "에도", "과의", "와의", "로서", "의", "은", "는",
        "이", "가", "을", "를", "에", "로", "와", "과", "도", "만",
    ],
    key=len,
    reverse=True,
)

# 동사·접속 표현처럼 핵심 단어가 될 수 없는 끝말 (예: 시작되었다, 발표하면서)
VERB_ENDINGS = (
    "다", "하면서", "하며", "하여", "하고", "하는", "되는", "되어",
    "으나", "으며", "이며", "면서",
)

# 시험 문제로 만들 가치가 낮은 흔한 말
STOPWORDS = {
    "그리고", "하지만", "그러나", "때문", "때문에", "있는", "없는", "위해",
    "대한", "통해", "이후", "이전", "이러한", "그러한", "따라서", "또한",
    "다른", "같은", "모든", "여러", "경우", "당시", "관련", "정도", "내용",
    "부분", "방법", "이유", "다양", "일부", "대부분", "전체", "각각", "자신",
    "현재", "오늘날", "한편", "결국", "특히", "이처럼", "함께", "모두", "매우",
    "더욱", "다시", "계속", "이미", "아직", "바로", "가장", "주로", "실제",
    "실제로", "하지", "그러", "이에", "이로써",
}

# 한글 단어 찾기. 숫자나 글자 바로 뒤에 붙은 한글("33인이")은 제외한다.
WORD_RE = re.compile(r"(?<![0-9A-Za-z가-힣])[가-힣]{2,}")

# 3·1 운동, 6·25 전쟁 처럼 "숫자·숫자 + 한글" 형태의 용어
DOT_TERM_RE = re.compile(r"(\d+·\d+)\s*([가-힣]{2,})")

# 연도·날짜·인원 같은 숫자 정보 (1919년, 3월 1일, 33인 ...)
NUMBER_RE = re.compile(r"\d{4}년대?|\d{1,2}월(?:\s*\d{1,2}일)?|\d+\s*(?:인|명|개|%|퍼센트)")

# 따옴표·괄호로 강조한 용어 (교재에서 중요한 용어를 이렇게 표시하는 경우가 많다)
OPENERS = "‘'“\"「『《(["
CLOSERS = "’'”\"」』》)]"
QUOTE_RE = re.compile(
    "[" + re.escape(OPENERS) + "]"
    "([^" + re.escape(OPENERS + CLOSERS) + r"\n]{2,15})"
    "[" + re.escape(CLOSERS) + "]"
)

EXAMPLE_TEXT = """1919년 3월 1일 전국에서 3·1 운동이 일어났다. 3·1 운동은 민족 대표 33인이 독립 선언서를 발표하면서 시작되었다.
3·1 운동의 영향으로 같은 해 4월 상하이에서 대한민국 임시 정부가 수립되었다.
일제는 1910년대에 헌병 경찰을 앞세워 무단 통치를 실시하였다.
3·1 운동 이후 일제는 문화 통치로 방식을 바꾸었으나 실제로는 민족 분열을 노린 기만적인 정책이었다.
1920년 김좌진이 이끄는 북로 군정서는 청산리에서 일본군에 큰 승리를 거두었다.
1932년 이봉창과 윤봉길은 한인 애국단 소속으로 의열 투쟁을 전개하였다."""


# ============================================================
# 2. 핵심 단어 자동 찾기
# ============================================================

def strip_josa(word: str) -> str:
    """단어 끝의 조사를 떼어 낸다. (떼고 나서 2글자 이상 남을 때만)"""
    for josa in JOSA_LIST:
        if word.endswith(josa) and len(word) - len(josa) >= 2:
            return word[: -len(josa)]
    return word


def is_valid_stem(stem: str) -> bool:
    return len(stem) >= 2 and stem not in STOPWORDS and not stem.endswith(VERB_ENDINGS)


def split_sentences(text: str) -> list[str]:
    """글을 문장 단위로 자른다. (마침표/물음표/느낌표 뒤, 또는 줄바꿈)"""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 10]


def extract_terms(text: str, include_numbers: bool = True) -> dict[str, int]:
    """글 전체를 훑어서 '핵심 단어 → 중요도 점수' 표를 만든다.

    점수를 올리는 요소
      - 여러 번 나온 단어
      - 3글자 이상의 긴 단어
      - 두 단어가 붙어서 2번 이상 나오는 용어 (예: 문화 통치)
      - 3·1 운동 같은 '숫자·숫자 + 한글' 용어
      - 따옴표·괄호로 강조된 용어
      - 연도·날짜·인원 같은 숫자 (옵션)
    """
    scores: dict[str, int] = {}
    unigram, bigram = Counter(), Counter()

    for sentence in split_sentences(text):
        prev = None  # 바로 앞 단어: (어간, 원래 단어, 끝 위치)
        for m in WORD_RE.finditer(sentence):
            raw = m.group()
            stem = strip_josa(raw)
            if not is_valid_stem(stem):
                prev = None
                continue
            unigram[stem] += 1
            # 앞 단어와 공백 하나로 붙어 있으면 두 단어짜리 용어 후보
            if (
                prev
                and prev[0] == prev[1]  # 앞 단어에 조사가 없어야 함
                and m.start() == prev[2] + 1
                and sentence[prev[2]] == " "
            ):
                bigram[f"{prev[0]} {stem}"] += 1
            prev = (stem, raw, m.end())

    # (1) 한 단어짜리 용어
    for word, count in unigram.items():
        scores[word] = count + (1 if len(word) >= 3 else 0)

    # (2) 두 단어짜리 용어는 2번 이상 나왔을 때만
    for pair, count in bigram.items():
        if count >= 2:
            scores[pair] = count + 3

    # (3) 3·1 운동 같은 용어
    dot_counts = Counter(
        f"{m.group(1)} {strip_josa(m.group(2))}" for m in DOT_TERM_RE.finditer(text)
    )
    for term, count in dot_counts.items():
        scores[term] = count + 3

    # (4) 따옴표·괄호로 강조한 용어
    for m in QUOTE_RE.finditer(text):
        term = re.sub(r"\s+", " ", m.group(1)).strip()
        if re.search("[가-힣]", term):
            scores[term] = scores.get(term, 0) + 3

    # (5) 연도·날짜·인원
    if include_numbers:
        num_counts = Counter(
            re.sub(r"\s+", " ", m.group()).strip() for m in NUMBER_RE.finditer(text)
        )
        for term, count in num_counts.items():
            scores[term] = scores.get(term, 0) + count + 2

    return scores


# ============================================================
# 3. 문제 만들기
# ============================================================

def term_regex(term: str) -> re.Pattern:
    """핵심 단어를 문장에서 찾기 위한 정규식. 띄어쓰기 차이는 무시하고,
    더 큰 단어의 일부(임시정부 속 '정부')는 찾지 않는다."""
    parts = [re.escape(p) for p in term.split()]
    return re.compile(r"(?<![가-힣0-9])" + r"\s*".join(parts))


def find_terms(sentence, scores, rx_map, min_score):
    """한 문장에 들어 있는 핵심 단어들을 찾는다."""
    found = [t for t, sc in scores.items() if sc >= min_score and rx_map[t].search(sentence)]
    # '문화 통치'가 있으면 그 안의 '통치'는 따로 빈칸으로 만들지 않는다.
    compact = lambda s: s.replace(" ", "")
    return [t for t in found if not any(t != o and compact(t) in compact(o) for o in found)]


def weighted_sample(items, weights, k):
    """점수가 높은 단어일수록 잘 뽑히도록 k개를 중복 없이 뽑는다."""
    items, weights, picked = list(items), list(weights), []
    for _ in range(min(k, len(items))):
        idx = random.choices(range(len(items)), weights=weights)[0]
        picked.append(items.pop(idx))
        weights.pop(idx)
    return picked


def blank_out(sentence: str, terms: list[str]):
    """문장에서 terms를 빈칸 표시(⟦1⟧)로 바꾸고 (문장, 정답 목록)을 돌려준다."""
    text, answers = sentence, []
    for term in sorted(terms, key=len, reverse=True):  # 긴 단어 먼저
        rx = term_regex(term)
        m = rx.search(text)
        if not m:
            continue
        answers.append(m.group(0))  # 문장에 쓰인 모양 그대로 정답으로 저장
        text = rx.sub(f"⟦{len(answers)}⟧", text)  # 같은 단어는 전부 가린다(힌트 방지)

    # 문장에 나온 순서대로 번호를 다시 매긴다.
    order = []
    for n in re.findall(r"⟦(\d+)⟧", text):
        if n not in order:
            order.append(n)
    mapping = {old: str(new + 1) for new, old in enumerate(order)}
    text = re.sub(r"⟦(\d+)⟧", lambda m: f"⟦{mapping[m.group(1)]}⟧", text)
    answers = [answers[int(old) - 1] for old in order]
    return text, answers


def make_questions(sentences, scores, num_questions, blanks_per_q):
    """문장 목록에서 빈칸 문제를 만든다.
    반환: [{"text": "빈칸이 있는 문장", "answers": ["정답1", ...]}, ...]
    """
    rx_map = {t: term_regex(t) for t in scores}

    strong, weak = [], []  # 핵심 단어가 확실한 문장 / 약한 문장
    for sentence in sentences:
        found = find_terms(sentence, scores, rx_map, min_score=2)
        if found:
            strong.append((sentence, found))
            continue
        found = find_terms(sentence, scores, rx_map, min_score=1)
        if found:
            weak.append((sentence, found))

    random.shuffle(strong)
    random.shuffle(weak)
    pool = (strong + weak)[:num_questions]  # 확실한 문장부터 사용
    random.shuffle(pool)

    questions = []
    for sentence, found in pool:
        chosen = weighted_sample(found, [scores[t] for t in found], blanks_per_q)
        text, answers = blank_out(sentence, chosen)
        if answers:
            questions.append({"text": text, "answers": answers})
    return questions


def normalize(s: str) -> str:
    """채점할 때 띄어쓰기·대소문자 차이는 무시한다."""
    return re.sub(r"\s+", "", s).lower()


# ============================================================
# 3-2. 비슷한 문제 만들기
#   - 틀린 문제와 같은 개념(틀린 핵심 단어)을 다른 모양으로 다시 묻는다.
#   - 시험 범위 문장을 그대로 빈칸만 뚫어 내지 않고,
#     ① AI가 새 문장으로 써 주거나(API 키가 있을 때)
#     ② 4지선다 / O·X / 설명→용어 로 모양을 바꿔서 만든다.
#   - 내용은 항상 붙여넣은 시험 범위에서만 가져온다.
# ============================================================

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")


def original_sentence(q: dict) -> str:
    """빈칸 문제를 정답으로 채워서 원래 문장으로 되돌린다."""
    return re.sub(r"⟦(\d+)⟧", lambda m: q["answers"][int(m.group(1)) - 1], q["text"])


def term_kind(term: str) -> str:
    """핵심 단어의 종류. 같은 종류끼리 오답 보기로 쓰려고 나눈다."""
    if re.fullmatch(r"\d{4}년대?", term):
        return "year"
    if re.search(r"\d", term) and re.search(r"월|일", term):
        return "date"
    if re.fullmatch(r"\d+\s*(?:인|명|개|%|퍼센트)", term):
        return "count"
    return "word"


def pick_distractors(target: str, scores: dict, n: int = 3, avoid_text: str = "") -> list[str]:
    """정답과 같은 종류의 다른 핵심 단어를 오답 보기로 뽑는다.
    avoid_text(문제 문장)에 이미 들어 있는 단어는 오답 보기로 쓰지 않는다."""
    compact = lambda s: s.replace(" ", "")
    kind = term_kind(target)
    pool = [
        t for t in scores
        if term_kind(t) == kind
        and compact(t) not in compact(target)
        and compact(target) not in compact(t)
        and compact(t) not in compact(avoid_text)
    ]
    # 점수가 높은 단어(진짜 용어일 가능성이 큰 단어)가 훨씬 잘 뽑히도록 점수를 세제곱해서 가중치로 쓴다.
    picked = weighted_sample(pool, [scores[t] ** 3 for t in pool], n)

    # 연도는 글에 없어도 가까운 연도로 오답 보기를 만들 수 있다.
    if kind == "year" and len(picked) < n:
        base = int(target[:4])
        step, suffix = (10, "년대") if target.endswith("대") else (1, "년")
        near = [f"{base + d * step}{suffix}" for d in (-3, -2, -1, 1, 2, 3)]
        random.shuffle(near)
        for cand in near:
            if len(picked) >= n:
                break
            if cand != target and cand not in picked:
                picked.append(cand)
    return picked


JOSA_PAIRS = {
    "은": ("은", "는"), "는": ("은", "는"), "이": ("이", "가"), "가": ("이", "가"),
    "을": ("을", "를"), "를": ("을", "를"), "과": ("과", "와"), "와": ("과", "와"),
}


def fix_josa(text: str, word: str) -> str:
    """word 바로 뒤의 조사를 받침 유무에 맞게 고친다. (김좌진는 → 김좌진은)"""
    last = word[-1]
    if not "가" <= last <= "힣":
        return text
    has_batchim = (ord(last) - 0xAC00) % 28 != 0

    def repl(m):
        with_b, without_b = JOSA_PAIRS[m.group(1)]
        return word + (with_b if has_batchim else without_b)

    return re.sub(re.escape(word) + r"(은|는|이|가|을|를|과|와)(?![가-힣])", repl, text)


def fix_this_josa(text: str) -> str:
    """‘이것’은 받침이 있으므로 뒤에 오는 조사를 은/이/을/과로 맞춘다."""
    fixed = {"은": "은", "는": "은", "이": "이", "가": "이", "을": "을", "를": "을", "과": "과", "와": "과"}
    return re.sub(r"‘이것’(은|는|이|가|을|를|과|와)(?![가-힣])", lambda m: "‘이것’" + fixed[m.group(1)], text)


def make_similar_rule_based(q: dict, wrong_terms: list[str], sentences: list[str], scores: dict) -> dict:
    """AI 없이 만드는 비슷한 문제. 문제 모양을 바꾸고, 가능하면 다른 문장을 쓴다."""
    target = random.choice(wrong_terms)
    rx = term_regex(target)
    original = original_sentence(q)

    # 같은 단어가 들어 있는 '다른' 문장이 있으면 그 문장으로 새로 출제한다.
    others = [s for s in sentences if s != original and rx.search(s)]
    base = random.choice(others) if others else original

    distractors = pick_distractors(target, scores, avoid_text=base)
    kinds = ["short"]
    if distractors:
        kinds.append("ox")
    if len(distractors) >= 3:
        kinds.append("choice")
    kind = random.choice(kinds)

    if kind == "choice":
        choices = [target] + distractors[:3]
        random.shuffle(choices)
        return {
            "kind": "choice",
            "prompt": "다음 문장의 빈칸에 들어갈 말로 알맞은 것은?\n" + rx.sub("( ＿＿＿＿ )", base),
            "choices": choices,
            "answer": choices.index(target),
            "note": f"원래 문장: {base}",
        }

    if kind == "ox":
        if random.random() < 0.5:  # 단어를 바꿔치기한 '틀린 진술'
            fake = fix_josa(rx.sub(distractors[0], base), distractors[0])  # 바꾼 단어에 맞게 조사 수정
            return {
                "kind": "ox",
                "prompt": "다음 진술이 옳으면 O, 틀리면 X를 고르세요.\n" + fake,
                "answer": False,
                "note": f"옳은 내용: {base}",
            }
        return {
            "kind": "ox",
            "prompt": "다음 진술이 옳으면 O, 틀리면 X를 고르세요.\n" + base,
            "answer": True,
            "note": f"‘{target}’에 대한 옳은 설명이에요.",
        }

    return {
        "kind": "short",
        "prompt": "다음 설명이 가리키는 것은 무엇일까요?\n" + fix_this_josa(rx.sub("‘이것’", base)),
        "answer": target,
        "note": f"원래 문장: {base}",
    }


def get_api_key() -> str:
    """AI 문제 출제에 쓸 API 키. 화면에 입력한 값 → secrets → 환경변수 순서로 찾는다."""
    key = str(st.session_state.get("api_key_input", "")).strip()
    if key:
        return key
    try:
        key = str(st.secrets.get("ANTHROPIC_API_KEY", "")).strip()
    except Exception:
        key = ""
    return key or os.environ.get("ANTHROPIC_API_KEY", "").strip()


def parse_ai_item(raw: str) -> dict:
    """AI가 돌려준 JSON 글을 읽어서 문제 형식이 맞는지 검사한다."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("JSON 형식의 답이 아니에요")
    data = json.loads(m.group(0))

    kind, prompt = data.get("kind"), str(data.get("prompt", "")).strip()
    if kind not in ("choice", "ox", "short") or not prompt:
        raise ValueError("문제 형식이 올바르지 않아요")

    item = {"kind": kind, "prompt": prompt, "note": str(data.get("note", "")).strip()}
    if kind == "choice":
        choices = [str(c) for c in data.get("choices", [])]
        answer = int(data.get("answer", -1))
        if len(choices) != 4 or not 0 <= answer < 4:
            raise ValueError("4지선다 형식이 올바르지 않아요")
        item.update(choices=choices, answer=answer)
    elif kind == "ox":
        if not isinstance(data.get("answer"), bool):
            raise ValueError("O/X 형식이 올바르지 않아요")
        item["answer"] = data["answer"]
    else:
        answer = str(data.get("answer", "")).strip()
        if not answer:
            raise ValueError("정답이 비어 있어요")
        item["answer"] = answer
    return item


def make_similar_ai(source_text: str, original: str, wrong_terms: list[str], api_key: str) -> dict:
    """Claude에게 시험 범위를 보여 주고, 같은 개념을 묻는 새 문제를 쓰게 한다."""
    import anthropic  # 설치되어 있지 않으면 ImportError → 자동 변형 문제로 대신한다.

    prompt = (
        "너는 고등학교 시험 문제 출제자야. 아래 [시험 범위]에 있는 내용만 사용해서, "
        "[틀린 문제]와 같은 개념을 묻는 비슷한 문제 1개를 새로 만들어 줘.\n\n"
        "규칙:\n"
        "- [시험 범위]의 문장을 그대로 베끼지 말고 새로운 문장으로 다시 써라.\n"
        "- 사실은 [시험 범위]와 일치해야 하고, 범위에 없는 내용을 지어내지 마라.\n"
        "- 형식은 choice(4지선다), ox(O/X), short(단답형) 중 하나를 골라라.\n"
        "- 아래 JSON 한 개만 출력해라. 설명이나 마크다운은 쓰지 마라.\n"
        '  choice: {"kind":"choice","prompt":"문제","choices":["보기1","보기2","보기3","보기4"],"answer":0,"note":"한 줄 해설"}\n'
        '  ox: {"kind":"ox","prompt":"진술문","answer":true,"note":"한 줄 해설"}\n'
        '  short: {"kind":"short","prompt":"문제","answer":"정답","note":"한 줄 해설"}\n'
        "  (choice의 answer는 0~3 번호)\n\n"
        f"[시험 범위]\n{source_text[:6000]}\n\n"
        f"[틀린 문제]\n{original}\n\n"
        f"[학생이 틀린 핵심 단어]\n{', '.join(wrong_terms)}"
    )
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return parse_ai_item(raw)


def build_similar(q: dict, flags: list[bool]) -> dict:
    """틀린 문제 하나에 대한 비슷한 문제를 만든다. (AI 우선, 실패하면 자동 변형)"""
    wrong_terms = [a for a, ok in zip(q["answers"], flags) if not ok] or q["answers"]
    item, warn = None, ""

    api_key = get_api_key()
    if api_key:
        try:
            item = make_similar_ai(st.session_state.source, original_sentence(q), wrong_terms, api_key)
            item["source"] = "ai"
        except Exception as e:  # 키 오류, 네트워크 오류, 형식 오류 등
            warn = f"AI 출제에 실패해서 자동 변형 문제로 만들었어요. ({type(e).__name__}: {str(e)[:80]})"

    if item is None:
        item = make_similar_rule_based(
            q, wrong_terms, split_sentences(st.session_state.source), st.session_state.terms
        )
        item["source"] = "rule"

    item["warn"] = warn
    item["uid"] = random.randint(1, 10**9)  # 위젯 key가 겹치지 않도록
    return item


# ============================================================
# 4. 화면 꾸미기 (HTML / CSS)
# ============================================================

CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.stApp {background: radial-gradient(1200px 600px at 50% -10%, #1a2040 0%, #0f1220 55%);}
[data-testid="stHeader"] {background: transparent;}
.block-container {max-width: 800px; padding-top: 2.2rem; padding-bottom: 4rem;}

.hero {text-align: center; padding: .6rem 0 1.4rem;}
.hero-badge {display: inline-block; padding: .2rem .8rem; border-radius: 999px;
  background: rgba(124,156,255,.15); color: #9db4ff; font-size: .75rem;
  font-weight: 700; letter-spacing: .12em; margin-bottom: .7rem;}
.hero h1 {margin: 0; padding: 0; font-size: 2.3rem; font-weight: 800;
  background: linear-gradient(90deg, #7c9cff, #c18bff);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;}
.hero p {margin: .6rem 0 0; color: #9aa4b8; font-size: 1rem;}

.step {display: flex; align-items: center; gap: .5rem; margin: 1.6rem 0 .5rem;
  color: #e8ecf4; font-weight: 700; font-size: 1.05rem;}
.step span {display: inline-flex; width: 1.6rem; height: 1.6rem; border-radius: 50%;
  align-items: center; justify-content: center; background: #7c9cff; color: #0f1220;
  font-size: .85rem; font-weight: 800;}

.q-head {display: flex; align-items: center; justify-content: space-between; margin-bottom: .3rem;}
.q-num {color: #7c9cff; font-weight: 800; font-size: .95rem; letter-spacing: .05em;}
.q-text {font-size: 1.08rem; line-height: 2.1; color: #e8ecf4; margin-bottom: .4rem;}
.badge {padding: .1rem .6rem; border-radius: 999px; font-size: .78rem; font-weight: 700;}
.badge.ok {background: rgba(61,220,151,.16); color: #5fe9b0;}
.badge.no {background: rgba(255,107,129,.16); color: #ff8fa1;}
.my-ans {color: #8590a6; font-size: .85rem; margin-bottom: .3rem;}
.sim-head {color: #c9a6ff; font-weight: 700; font-size: .88rem; margin-bottom: .35rem;}
.sim-head span {color: #8590a6; font-weight: 500; margin-left: .4rem;}
.sim-text {color: #e8ecf4; line-height: 1.9; font-size: 1.02rem; margin-bottom: .4rem;}
.sim-note {color: #8590a6; font-size: .85rem; margin-top: .2rem;}
.hint {margin: .1rem 0 .35rem; padding: .25rem .6rem; border-radius: 8px; font-size: .88rem;
  background: rgba(255,200,87,.12); color: #ffd98a; letter-spacing: .06em;}

.blank {display: inline-block; min-width: 3.4rem; padding: 0 .55rem; margin: 0 .15rem;
  border-bottom: 2px solid #7c9cff; background: rgba(124,156,255,.16); color: #b9c8ff;
  border-radius: 6px; text-align: center; font-weight: 700;}
.blank.ok {border-color: #3ddc97; background: rgba(61,220,151,.16); color: #7ff0c0;}
.blank.no {border-color: #ff6b81; background: rgba(255,107,129,.16); color: #ff9aa9;}

.score-card {text-align: center; padding: 1.4rem 1rem; border-radius: 16px; margin: 1.2rem 0 .6rem;
  background: linear-gradient(135deg, rgba(124,156,255,.18), rgba(193,139,255,.14));
  border: 1px solid rgba(124,156,255,.3);}
.score-num {font-size: 2.6rem; font-weight: 800; color: #e8ecf4;}
.score-num span {font-size: 1.3rem; color: #8590a6; font-weight: 600;}
.score-sub {color: #9db4ff; font-weight: 600;}

.chip {display: inline-block; margin: .15rem; padding: .15rem .7rem; border-radius: 999px;
  background: rgba(124,156,255,.14); color: #b9c8ff; font-size: .85rem;}
.chip small {color: #7f8aa3; margin-left: .25rem;}
.footnote {text-align: center; color: #6c7690; font-size: .8rem; margin-top: 2rem;}
</style>
"""


def esc(s: str) -> str:
    """HTML에 넣어도 안전하도록 특수문자를 바꾼다."""
    return html.escape(s).replace("$", "&#36;")


def question_html(q: dict, flags: list[bool] | None) -> str:
    """빈칸 표시(⟦1⟧)를 예쁜 칩 모양 HTML로 바꾼다.
    flags가 있으면(채점 후) 정답을 채워서 초록/빨강으로 보여 준다."""

    def replace(m):
        n = int(m.group(1))
        if flags is None:
            return f'<span class="blank">{n}</span>'
        cls = "ok" if flags[n - 1] else "no"
        return f'<span class="blank {cls}">{esc(q["answers"][n - 1])}</span>'

    return re.sub(r"⟦(\d+)⟧", replace, esc(q["text"]))


# ============================================================
# 5. 버튼 콜백
# ============================================================

CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def hint_text(answer: str, level: int) -> str:
    """정답으로 힌트 문구를 만든다.
    1단계: 글자 수 + 초성   (예: 통치 → 2글자 · ㅌㅊ)
    2단계: 첫 글자까지 공개 (예: 통치 → 2글자 · 통ㅊ)
    숫자·영어는 정답이 그대로 드러나지 않게 ○로 가린다."""
    shown, first_done = [], False
    for ch in answer:
        if ch == " ":
            shown.append(" ")
            continue
        if "가" <= ch <= "힣":
            masked = CHOSUNG[(ord(ch) - 0xAC00) // 588]  # 한글 글자 → 초성
        elif ch == "·":
            masked = ch
        else:
            masked = "○"
        if level >= 2 and not first_done:
            masked = ch  # 2단계에서는 첫 글자를 그대로 보여 준다
        first_done = True
        shown.append(masked)
    return f"{len(answer.replace(' ', ''))}글자 · {''.join(shown)}"


def use_hint(key: str):
    """힌트 버튼을 누르면 단계가 한 칸 올라간다. (최대 2단계)"""
    hints = st.session_state.hints
    hints[key] = min(2, hints.get(key, 0) + 1)


def load_example():
    st.session_state["source_text"] = EXAMPLE_TEXT


def grade():
    st.session_state.graded = True


def check_similar(checked_key: str):
    """비슷한 문제의 '정답 확인' 버튼을 눌렀다고 기록한다."""
    st.session_state[checked_key] = True


def render_similar(rnd: int, i: int, q: dict, flags: list[bool]):
    """틀린 문제 아래에 '비슷한 문제' 버튼과, 만들어진 비슷한 문제를 보여 준다."""
    sim_key = f"{rnd}_{i}"
    item = st.session_state.similar.get(sim_key)

    label = "🔄 비슷한 문제 풀어보기" if item is None else "🔄 다른 비슷한 문제"
    if st.button(label, key=f"sim_btn_{sim_key}", use_container_width=True):
        with st.spinner("비슷한 문제를 만드는 중..."):
            item = build_similar(q, flags)
        st.session_state.similar[sim_key] = item

    if item is None:
        return

    uid = item["uid"]
    ans_key = f"sim_ans_{sim_key}_{uid}"
    chk_key = f"sim_chk_{sim_key}_{uid}"
    checked = st.session_state.get(chk_key, False)

    if item.get("warn"):
        st.warning(item["warn"])

    with st.container(border=True):
        tag = "🤖 AI가 새로 쓴 문제" if item["source"] == "ai" else "🔧 자동 변형 문제"
        body = esc(item["prompt"]).replace("\n", "<br>")
        st.markdown(
            f'<div class="sim-head">{tag}<span>같은 개념 · 비슷한 유형</span></div>'
            f'<div class="sim-text">{body}</div>',
            unsafe_allow_html=True,
        )

        if item["kind"] == "choice":
            st.radio(
                "보기", [0, 1, 2, 3], index=None, key=ans_key, disabled=checked,
                format_func=lambda k: f"{'①②③④'[k]} {item['choices'][k]}",
                label_visibility="collapsed",
            )
        elif item["kind"] == "ox":
            st.radio(
                "O/X", ["O", "X"], index=None, key=ans_key, disabled=checked,
                horizontal=True, label_visibility="collapsed",
            )
        else:
            st.text_input("정답", key=ans_key, placeholder="정답 입력", disabled=checked)

        if not checked:
            st.button(
                "정답 확인", key=f"sim_ok_{sim_key}_{uid}",
                on_click=check_similar, args=(chk_key,),
            )
            return

        # ----- 정답 확인 후 -----
        picked = st.session_state.get(ans_key)
        if item["kind"] == "choice":
            ok = picked == item["answer"]
            correct_text = f"{'①②③④'[item['answer']]} {item['choices'][item['answer']]}"
        elif item["kind"] == "ox":
            ok = picked is not None and (picked == "O") == item["answer"]
            correct_text = "O" if item["answer"] else "X"
        else:
            ok = normalize(str(picked or "")) == normalize(item["answer"])
            correct_text = item["answer"]

        if ok:
            st.success("정답!")
        else:
            st.error(f"오답 · 정답: {correct_text}")
        if item.get("note"):
            st.markdown(f'<div class="sim-note">{esc(item["note"])}</div>', unsafe_allow_html=True)


# ============================================================
# 6. 화면 구성
# ============================================================

st.set_page_config(page_title="빈칸 문제 생성기", page_icon="📝")
st.markdown(CSS, unsafe_allow_html=True)

# 값마다 따로 초기화한다. (예전 버전 세션이 남아 있어도 오류가 나지 않도록)
st.session_state.setdefault("questions", [])
st.session_state.setdefault("terms", {})
st.session_state.setdefault("round", 0)
st.session_state.setdefault("graded", False)
st.session_state.setdefault("hints", {})  # {"라운드_문제번호_빈칸번호": 힌트 단계(0~2)}
st.session_state.setdefault("similar", {})  # {"라운드_문제번호": 비슷한 문제}
st.session_state.setdefault("source", "")  # 문제를 만들 때 사용한 시험 범위 글

st.markdown(
    """
    <div class="hero">
      <div class="hero-badge">STUDY TOOL</div>
      <h1>빈칸 문제 생성기</h1>
      <p>시험 범위를 붙여넣으면 핵심 단어를 자동으로 찾아<br>빈칸 문제로 만들어 드려요</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------- STEP 1: 글 붙여넣기 ----------
st.markdown('<div class="step"><span>1</span>시험 범위 붙여넣기</div>', unsafe_allow_html=True)
st.button("예시 텍스트 넣어 보기", on_click=load_example)
text = st.text_area(
    "시험 범위",
    key="source_text",
    height=220,
    label_visibility="collapsed",
    placeholder="교재나 필기 내용을 여기에 붙여넣으세요.",
)

# ---------- STEP 2: 설정 ----------
st.markdown('<div class="step"><span>2</span>문제 설정</div>', unsafe_allow_html=True)
col1, col2, col3 = st.columns([2, 2, 1.4])
num_questions = col1.slider("문제 수", 1, 30, 10)
blanks_per_q = col2.slider("문장당 빈칸 수", 1, 3, 1)
# st.toggle은 비교적 최신 기능이라, 없는 버전에서는 체크박스로 대신한다.
include_numbers = getattr(st, "toggle", st.checkbox)("연도·숫자 포함", value=True)

with st.expander("🤖 AI로 비슷한 문제 만들기 (선택)"):
    st.text_input("Anthropic API 키", type="password", key="api_key_input", placeholder="sk-ant-...")
    st.caption(
        "틀린 문제 옆의 '비슷한 문제' 버튼을 누르면, 키가 있을 땐 AI가 시험 범위를 바탕으로 새 문장으로 써 주고, "
        "비워 두면 자동으로 모양을 바꾼 문제(4지선다·O/X·설명→용어)가 나와요. "
        "입력한 키는 이 접속 중에만 쓰이고 화면을 닫으면 사라져요."
    )

if st.button("🎯 문제 만들기", type="primary", use_container_width=True):
    if not text.strip():
        st.warning("먼저 시험 범위 내용을 붙여넣어 주세요.")
    else:
        scores = extract_terms(text, include_numbers)
        new_questions = make_questions(split_sentences(text), scores, num_questions, blanks_per_q)
        if not new_questions:
            st.error("문제를 만들 수 있는 문장을 찾지 못했어요. 내용을 조금 더 길게 붙여넣어 보세요.")
        else:
            st.session_state.questions = new_questions
            st.session_state.terms = scores
            st.session_state.source = text  # 비슷한 문제를 만들 때 이 글을 기준으로 쓴다
            st.session_state.round += 1
            st.session_state.graded = False

# ---------- STEP 3: 문제 풀기 / 채점 ----------
questions = st.session_state.questions
rnd = st.session_state.round
graded = st.session_state.graded

if questions:
    st.markdown('<div class="step"><span>3</span>문제 풀기</div>', unsafe_allow_html=True)

    # 자동으로 찾은 핵심 단어 보여 주기
    with st.expander("🔍 자동으로 찾은 핵심 단어 보기"):
        top_terms = sorted(st.session_state.get("terms", {}).items(), key=lambda kv: -kv[1])[:40]
        chips = "".join(f'<span class="chip">{esc(t)}<small>{sc}</small></span>' for t, sc in top_terms)
        st.markdown(chips, unsafe_allow_html=True)
        st.caption("숫자는 중요도 점수예요. 점수가 높은 단어가 빈칸으로 더 자주 나와요.")

    # 채점 결과를 미리 계산해 둔다. (점수 카드를 맨 위에 보여 주려고)
    all_flags, wrong = [], []
    score = 0
    for i, q in enumerate(questions):
        user_answers = [st.session_state.get(f"ans_{rnd}_{i}_{j}", "") for j in range(len(q["answers"]))]
        flags = [normalize(u) == normalize(a) for u, a in zip(user_answers, q["answers"])]
        all_flags.append((user_answers, flags))
        if all(flags):
            score += 1
        else:
            wrong.append(q)

    if graded:
        pct = round(score / len(questions) * 100)
        # 이번 라운드에서 힌트를 누른 횟수
        hints_used = sum(
            level for key, level in st.session_state.hints.items() if key.startswith(f"{rnd}_")
        )
        hint_note = f" · 힌트 {hints_used}번 사용" if hints_used else " · 힌트 없이 풀었어요"
        st.markdown(
            f'<div class="score-card"><div class="score-num">{score}'
            f'<span> / {len(questions)}</span></div>'
            f'<div class="score-sub">정답률 {pct}%{hint_note}</div></div>',
            unsafe_allow_html=True,
        )
        st.progress(score / len(questions))

    for i, q in enumerate(questions):
        user_answers, flags = all_flags[i]
        with st.container(border=True):
            badge = ""
            if graded:
                badge = '<span class="badge ok">정답</span>' if all(flags) else '<span class="badge no">오답</span>'

            st.markdown(
                f'<div class="q-head"><span class="q-num">Q{i + 1}</span>{badge}</div>'
                f'<div class="q-text">{question_html(q, flags if graded else None)}</div>',
                unsafe_allow_html=True,
            )

            cols = st.columns(len(q["answers"]))
            for j, col in enumerate(cols):
                col.text_input(
                    f"{j + 1}번 빈칸",
                    key=f"ans_{rnd}_{i}_{j}",
                    placeholder="정답 입력",
                    disabled=graded,
                )

                # 힌트: 누를 때마다 1단계(초성) → 2단계(첫 글자) 순서로 공개
                hint_key = f"{rnd}_{i}_{j}"
                level = st.session_state.hints.get(hint_key, 0)
                if level > 0:
                    col.markdown(
                        f'<div class="hint">💡 {esc(hint_text(q["answers"][j], level))}</div>',
                        unsafe_allow_html=True,
                    )
                if not graded:
                    col.button(
                        "💡 힌트" if level == 0 else ("💡 힌트 더 보기" if level == 1 else "힌트 끝"),
                        key=f"hint_{hint_key}",
                        on_click=use_hint,
                        args=(hint_key,),
                        disabled=(level >= 2),
                        use_container_width=True,
                    )

            if graded and not all(flags):
                mine = ", ".join(u if u.strip() else "(빈칸)" for u in user_answers)
                st.markdown(f'<div class="my-ans">내 답: {esc(mine)}</div>', unsafe_allow_html=True)
                render_similar(rnd, i, q, flags)

    st.write("")
    if not graded:
        st.button("✅ 채점하기", type="primary", use_container_width=True, on_click=grade)
    elif wrong:
        lines = []
        for n, q in enumerate(wrong, start=1):
            plain = re.sub(r"⟦(\d+)⟧", r"( \1 )", q["text"])
            lines.append(f"Q{n}. {plain}")
            lines.append("정답: " + ", ".join(q["answers"]))
            lines.append("")
        st.download_button(
            "💾 틀린 문제 저장",
            data="\n".join(lines),
            file_name="wrong_questions.txt",
            use_container_width=True,
        )
    else:
        st.success("전부 맞혔어요! 위에서 '문제 만들기'를 다시 눌러 새 문제를 풀어 보세요.")

st.markdown('<div class="footnote">핵심 단어는 자동으로 찾기 때문에 가끔 어색한 빈칸이 나올 수 있어요.</div>', unsafe_allow_html=True)
