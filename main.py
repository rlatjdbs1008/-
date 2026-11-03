from __future__ import annotations

import html
import json
import os
import random
import re
from collections import Counter

import streamlit as st

# ============================================================
# 1. 기본 설정
# ============================================================

JOSA_LIST = sorted([
    "에서는", "으로서", "에서의", "이라는", "에서", "으로",
    "까지", "부터", "에게", "라는", "에는", "에도",
    "과의", "와의", "로서", "의", "은", "는", "이",
    "가", "을", "를", "에", "로", "와", "과", "도", "만"
], key=len, reverse=True)

VERB_ENDINGS = (
    "다", "하면서", "하며", "하여", "하고",
    "하는", "되는", "되어", "으나", "으며",
    "이며", "면서"
)

STOPWORDS = {
    "그리고", "하지만", "그러나", "때문", "때문에",
    "있는", "없는", "위해", "대한", "통해",
    "이후", "이전", "이러한", "그러한", "따라서",
    "또한", "다른", "같은", "모든", "여러",
    "경우", "당시", "관련", "정도", "내용",
    "부분", "방법", "이유", "다양", "일부",
    "대부분", "전체", "각각", "자신", "현재",
    "오늘날", "한편", "결국", "특히", "이처럼",
    "함께", "모두", "매우", "더욱", "다시",
    "계속", "이미", "아직", "바로", "가장",
    "주로", "실제", "실제로", "하지", "이에"
}

WORD_RE = re.compile(r"(?<![0-9A-Za-z가-힣])[가-힣]{2,}")

DOT_TERM_RE = re.compile(r"(\d+·\d+)\s*([가-힣]{2,})")

NUMBER_RE = re.compile(
    r"\d{4}년대?|\d{1,2}월(?:\s*\d{1,2}일)?|\d+\s*(?:인|명|개|%|퍼센트)"
)

OPENERS = "‘'“\"「『《(["
CLOSERS = "’'”\"」』》)]"

QUOTE_RE = re.compile(
    "[" + re.escape(OPENERS) + "]"
    "([^" + re.escape(OPENERS + CLOSERS) + r"\n]{2,15})"
    "[" + re.escape(CLOSERS) + "]"
)

# ============================================================
# 2. 예시 시험 범위
# ============================================================

EXAMPLE_TEXT = """1919년 3월 1일 전국에서 3·1 운동이 일어났다.
3·1 운동은 민족 대표 33인이 독립 선언서를 발표하면서 시작되었다.
3·1 운동의 영향으로 같은 해 4월 상하이에서 대한민국 임시 정부가 수립되었다.
일제는 1910년대에 헌병 경찰을 앞세워 무단 통치를 실시하였다.
3·1 운동 이후 일제는 문화 통치로 방식을 바꾸었으나 실제로는 민족 분열을 노린 정책이었다.
1920년 김좌진이 이끄는 북로 군정서는 청산리에서 일본군에 큰 승리를 거두었다.
1932년 이봉창과 윤봉길은 한인 애국단 소속으로 의열 투쟁을 전개하였다.
"""

# ============================================================
# 3. 핵심 단어 추출
# ============================================================

def strip_josa(word: str) -> str:
    for josa in JOSA_LIST:
        if word.endswith(josa) and len(word) - len(josa) >= 2:
            return word[:-len(josa)]
    return word


def is_valid_stem(stem: str) -> bool:
    return (
        len(stem) >= 2
        and stem not in STOPWORDS
        and not stem.endswith(VERB_ENDINGS)
    )


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 10]


def extract_terms(
    text: str,
    include_numbers: bool = True
) -> dict[str, int]:

    scores = {}
    unigram = Counter()
    bigram = Counter()

    for sentence in split_sentences(text):

        prev = None

        for m in WORD_RE.finditer(sentence):

            raw = m.group()
            stem = strip_josa(raw)

            if not is_valid_stem(stem):
                prev = None
                continue

            unigram[stem] += 1

            if (
                prev
                and prev[0] == prev[1]
                and m.start() == prev[2] + 1
                and sentence[prev[2]] == " "
            ):
                bigram[f"{prev[0]} {stem}"] += 1

            prev = (stem, raw, m.end())

    # 단일 단어 점수
    for word, count in unigram.items():
        scores[word] = count + (1 if len(word) >= 3 else 0)

    # 두 단어로 이루어진 핵심 용어
    for pair, count in bigram.items():
        if count >= 2:
            scores[pair] = count + 3

    # 3·1 운동 등의 용어
    dot_counts = Counter(
        f"{m.group(1)} {strip_josa(m.group(2))}"
        for m in DOT_TERM_RE.finditer(text)
    )

    for term, count in dot_counts.items():
        scores[term] = count + 3

   
    # 따옴표로 강조된 용어
    for m in QUOTE_RE.finditer(text):
        term = re.sub(r"\s+", " ", m.group(1)).strip()

        if re.search("[가-힣]", term):
            scores[term] = scores.get(term, 0) + 3

    # 숫자 정보
    if include_numbers:

        num_counts = Counter(
            re.sub(r"\s+", " ", m.group()).strip()
            for m in NUMBER_RE.finditer(text)
        )

        for term, count in num_counts.items():
            scores[term] = scores.get(term, 0) + count + 2

    return scores
   # ============================================================
# 4. 빈칸 문제 생성
# ============================================================

def term_regex(term: str) -> re.Pattern:
    parts = [re.escape(p) for p in term.split()]
    return re.compile(
        r"(?<![가-힣0-9])" + r"\s*".join(parts)
    )


def find_terms(sentence, scores, rx_map, min_score):

    found = [
        t for t, sc in scores.items()
        if sc >= min_score and rx_map[t].search(sentence)
    ]

    compact = lambda s: s.replace(" ", "")

    return [
        t for t in found
        if not any(
            t != o and compact(t) in compact(o)
            for o in found
        )
    ]


def weighted_sample(items, weights, k):

    items = list(items)
    weights = list(weights)
    picked = []

    for _ in range(min(k, len(items))):

        idx = random.choices(
            range(len(items)),
            weights=weights
        )[0]

        picked.append(items.pop(idx))
        weights.pop(idx)

    return picked


def blank_out(sentence, terms):

    text = sentence
    answers = []

    for term in sorted(terms, key=len, reverse=True):

        rx = term_regex(term)
        m = rx.search(text)

        if not m:
            continue

        answers.append(m.group(0))

        text = rx.sub(
            f"⟦{len(answers)}⟧",
            text
        )

    order = []

    for n in re.findall(r"⟦(\d+)⟧", text):
        if n not in order:
            order.append(n)

    mapping = {
        old: str(new + 1)
        for new, old in enumerate(order)
    }

    text = re.sub(
        r"⟦(\d+)⟧",
        lambda m: f"⟦{mapping[m.group(1)]}⟧",
        text
    )

    answers = [
        answers[int(old) - 1]
        for old in order
    ]

    return text, answers


def make_questions(
    sentences,
    scores,
    num_questions,
    blanks_per_q
):

    rx_map = {
        t: term_regex(t)
        for t in scores
    }

    strong = []
    weak = []

    for sentence in sentences:

        found = find_terms(
            sentence, scores, rx_map, 2
        )

        if found:
            strong.append((sentence, found))
            continue

        found = find_terms(
            sentence, scores, rx_map, 1
        )

        if found:
            weak.append((sentence, found))

    random.shuffle(strong)
    random.shuffle(weak)

    pool = (strong + weak)[:num_questions]

    random.shuffle(pool)

    questions = []

    for sentence, found in pool:

        chosen = weighted_sample(
            found,
            [scores[t] for t in found],
            blanks_per_q
        )

        text, answers = blank_out(
            sentence, chosen
        )

        if answers:

            questions.append({
                "text": text,
                "answers": answers
            })

    return questions


# ============================================================
# 5. 채점 기능
# ============================================================

def normalize(s: str) -> str:

    return re.sub(
        r"\s+", "", str(s)
    ).lower()


def original_sentence(q: dict) -> str:

    return re.sub(
        r"⟦(\d+)⟧",
        lambda m: q["answers"][int(m.group(1)) - 1],
        q["text"]
    )


def grade():

    st.session_state.graded = True


# ============================================================
# 6. 힌트 기능
# ============================================================

CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def hint_text(answer: str, level: int):

    shown = []
    first_done = False

    for ch in answer:

        if ch == " ":
            shown.append(" ")
            continue

        if "가" <= ch <= "힣":

            masked = CHOSUNG[
                (ord(ch) - 0xAC00) // 588
            ]

        elif ch == "·":
            masked = ch

        else:
            masked = "○"

        if level >= 2 and not first_done:
            masked = ch

        first_done = True
        shown.append(masked)

    return (
        f"{len(answer.replace(' ', ''))}글자 · "
        f"{''.join(shown)}"
    )


def use_hint(key: str):

    hints = st.session_state.hints

    hints[key] = min(
        2,
        hints.get(key, 0) + 1
    )
   # ============================================================
# 7. 비슷한 문제 생성 기능
# ============================================================

CLAUDE_MODEL = os.environ.get(
    "CLAUDE_MODEL",
    "claude-sonnet-4-5"
)


def term_kind(term):

    if re.fullmatch(r"\d{4}년대?", term):
        return "year"

    if re.search(r"\d", term) and re.search(r"월|일", term):
        return "date"

    if re.fullmatch(r"\d+\s*(?:인|명|개|%|퍼센트)", term):
        return "count"

    return "word"


def pick_distractors(target, scores, n=3):

    compact = lambda s: s.replace(" ", "")

    kind = term_kind(target)

    pool = [
        t for t in scores
        if term_kind(t) == kind
        and compact(t) not in compact(target)
        and compact(target) not in compact(t)
    ]

    strong = [
        t for t in pool
        if scores[t] >= 2
    ]

    pool = strong if len(strong) >= n else pool

    picked = weighted_sample(
        pool,
        [scores[t] for t in pool],
        n
    )

    # 연도 오답 보기 보충
    if kind == "year" and len(picked) < n:

        base = int(target[:4])

        step = 10 if target.endswith("대") else 1
        suffix = "년대" if target.endswith("대") else "년"

        near = [
            f"{base + d * step}{suffix}"
            for d in (-3, -2, -1, 1, 2, 3)
        ]

        random.shuffle(near)

        for cand in near:

            if len(picked) >= n:
                break

            if cand != target and cand not in picked:
                picked.append(cand)

    return picked


# ============================================================
# 8. AI 문제 생성
# ============================================================

def get_api_key():

    key = str(
        st.session_state.get("api_key_input", "")
    ).strip()

    if key:
        return key

    try:
        key = str(
            st.secrets.get("ANTHROPIC_API_KEY", "")
        ).strip()
    except Exception:
        key = ""

    return key or os.environ.get(
        "ANTHROPIC_API_KEY", ""
    ).strip()


def parse_ai_item(raw):

    match = re.search(
        r"\{.*\}",
        raw,
        re.S
    )

    if not match:
        raise ValueError("JSON 형식이 아닙니다.")

    data = json.loads(match.group(0))

    kind = data.get("kind")
    prompt = str(data.get("prompt", "")).strip()

    if kind not in ("choice", "ox", "short") or not prompt:
        raise ValueError("문제 형식이 올바르지 않습니다.")

    item = {
        "kind": kind,
        "prompt": prompt,
        "note": str(data.get("note", "")).strip()
    }

    if kind == "choice":

        choices = [
            str(c)
            for c in data.get("choices", [])
        ]

        answer = int(data.get("answer", -1))

        if len(choices) != 4 or not 0 <= answer < 4:
            raise ValueError("4지선다 형식 오류")

        item.update(
            choices=choices,
            answer=answer
        )

    elif kind == "ox":

        if not isinstance(data.get("answer"), bool):
            raise ValueError("O/X 정답 형식 오류")

        item["answer"] = data["answer"]

    else:

        answer = str(
            data.get("answer", "")
        ).strip()

        if not answer:
            raise ValueError("정답이 비어 있습니다.")

        item["answer"] = answer

    return item


def make_similar_ai(
    source_text,
    original,
    wrong_terms,
    api_key
):

    import anthropic

    prompt = f"""
너는 고등학교 시험 문제 출제 전문가야.

아래 시험 범위의 사실과 개념만 이용해서
학생이 틀린 문제와 같은 핵심 개념을 묻는
새로운 문제를 하나 만들어 줘.

[중요한 출제 규칙]

1. 시험 범위에 있는 사실만 사용한다.
2. 원래 시험 범위의 문장을 그대로 복사하지 않는다.
3. 단순히 빈칸 위치만 바꾸는 문제를 만들지 않는다.
4. 새로운 문장 구조와 질문 방식을 사용한다.
5. 개념의 의미, 원인, 결과, 특징 등을 활용한다.
6. 시험 범위에 없는 사실은 절대 추가하지 않는다.
7. 정답은 시험 범위에서 명확하게 확인할 수 있어야 한다.
8. 4지선다, O/X, 단답형 중 하나를 선택한다.
9. 오답 보기는 시험 범위의 다른 개념과 혼동할 수 있게 만든다.
10. 문제와 정답은 서로 모순되지 않아야 한다.

[출제 유형]

choice:
{{"kind":"choice","prompt":"문제","choices":["보기1","보기2","보기3","보기4"],"answer":0,"note":"해설"}}

ox:
{{"kind":"ox","prompt":"진술문","answer":true,"note":"해설"}}

short:
{{"kind":"short","prompt":"문제","answer":"정답","note":"해설"}}

choice의 answer는 0~3의 숫자야.

반드시 JSON 하나만 출력해.

[시험 범위]
{source_text[:6000]}

[학생이 틀린 원래 문제]
{original}

[학생이 틀린 핵심 개념]
{', '.join(wrong_terms)}
"""

    client = anthropic.Anthropic(
        api_key=api_key
    )

    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    raw = "".join(
        b.text
        for b in msg.content
        if getattr(b, "type", "") == "text"
    )

    return parse_ai_item(raw)


# ============================================================
# 9. AI 없이 자동으로 문제 만들기
# ============================================================

def make_similar_rule_based(
    q,
    wrong_terms,
    sentences,
    scores
):

    target = random.choice(wrong_terms)

    rx = term_regex(target)

    original = original_sentence(q)

    others = [
        s for s in sentences
        if s != original and rx.search(s)
    ]

    base = random.choice(others) if others else original

    distractors = pick_distractors(
        target,
        scores
    )

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
            "prompt": (
                "다음 문장의 빈칸에 들어갈 말로 "
                "알맞은 것은?\n"
                + rx.sub("( ＿＿＿＿ )", base)
            ),
            "choices": choices,
            "answer": choices.index(target),
            "note": f"시험 범위의 관련 내용: {base}"
        }

    if kind == "ox":

        if random.random() < 0.5:

            fake = rx.sub(
                distractors[0],
                base
            )

            return {
                "kind": "ox",
                "prompt": (
                    "다음 진술이 옳으면 O, "
                    "틀리면 X를 고르세요.\n"
                    + fake
                ),
                "answer": False,
                "note": f"올바른 내용: {base}"
            }

        return {
            "kind": "ox",
            "prompt": (
                "다음 진술이 옳으면 O, "
                "틀리면 X를 고르세요.\n"
                + base
            ),
            "answer": True,
            "note": f"관련 핵심 개념: {target}"
        }

    return {
        "kind": "short",
        "prompt": (
            "다음 설명에서 가리키는 "
            "핵심 개념은 무엇일까요?\n"
            + rx.sub("‘이것’", base)
        ),
        "answer": target,
        "note": f"관련 시험 범위: {base}"
    }


# ============================================================
# 10. 비슷한 문제 통합 생성 함수
# ============================================================

def build_similar(q, flags):

    wrong_terms = [
        answer
        for answer, ok in zip(q["answers"], flags)
        if not ok
    ]

    if not wrong_terms:
        wrong_terms = q["answers"]

    item = None
    warn = ""

    api_key = get_api_key()

    if api_key:

        try:

            item = make_similar_ai(
                st.session_state.source,
                original_sentence(q),
                wrong_terms,
                api_key
            )

            item["source"] = "ai"

        except Exception as e:

            warn = (
                "AI 출제에 실패하여 자동 변형 문제를 "
                f"사용합니다. ({type(e).__name__})"
            )

    if item is None:

        item = make_similar_rule_based(
            q,
            wrong_terms,
            split_sentences(st.session_state.source),
            st.session_state.terms
        )

        item["source"] = "rule"

    item["warn"] = warn

    item["uid"] = random.randint(
        1,
        10**9
    )

    return item


# ============================================================
# 11. 비슷한 문제 정답 확인
# ============================================================

def check_similar(checked_key):

    st.session_state[checked_key] = True


def render_similar(rnd, i, q, flags):

    sim_key = f"{rnd}_{i}"

    item = st.session_state.similar.get(
        sim_key
    )

    label = (
        "✨ 비슷한 문제 출제"
        if item is None
        else "🔄 다른 비슷한 문제 출제"
    )

    if st.button(
        label,
        key=f"sim_btn_{sim_key}",
        use_container_width=True
    ):

        with st.spinner("새로운 문제를 출제하고 있어요..."):

            item = build_similar(q, flags)

        st.session_state.similar[sim_key] = item

    if item is None:
        return

    uid = item["uid"]

    ans_key = f"sim_ans_{sim_key}_{uid}"
    chk_key = f"sim_chk_{sim_key}_{uid}"

    checked = st.session_state.get(
        chk_key,
        False
    )

    if item.get("warn"):
        st.warning(item["warn"])

    with st.container(border=True):

        tag = (
            "🤖 AI 새 문제"
            if item["source"] == "ai"
            else "🔧 자동 변형 문제"
        )

        st.markdown(f"**{tag} · 같은 개념의 새로운 유형**")

        st.markdown(item["prompt"])

        if item["kind"] == "choice":

            st.radio(
                "보기",
                [0, 1, 2, 3],
                index=None,
                key=ans_key,
                disabled=checked,
                format_func=lambda k: (
                    f"{'①②③④'[k]} {item['choices'][k]}"
                ),
                label_visibility="collapsed"
            )

        elif item["kind"] == "ox":

            st.radio(
                "O/X",
                ["O", "X"],
                index=None,
                key=ans_key,
                disabled=checked,
                horizontal=True,
                label_visibility="collapsed"
            )

        else:

            st.text_input(
                "정답 입력",
                key=ans_key,
                placeholder="정답을 입력하세요.",
                disabled=checked
            )

        if not checked:

            st.button(
                "정답 확인",
                key=f"sim_ok_{sim_key}_{uid}",
                on_click=check_similar,
                args=(chk_key,)
            )

            return

        picked = st.session_state.get(ans_key)

        if item["kind"] == "choice":

            ok = picked == item["answer"]

            correct_text = (
                f"{'①②③④'[item['answer']]} "
                f"{item['choices'][item['answer']]}"
            )

        elif item["kind"] == "ox":

            ok = (
                picked is not None
                and (picked == "O") == item["answer"]
            )

            correct_text = (
                "O" if item["answer"] else "X"
            )

        else:

            ok = (
                normalize(picked or "")
                == normalize(item["answer"])
            )

            correct_text = item["answer"]

        if ok:
            st.success("정답입니다! 🎉")
        else:
            st.error(
                f"오답입니다. 정답: {correct_text}"
            )

        if item.get("note"):
            st.info(item["note"])
           python
# ============================================================
# 12. 화면 디자인
# ============================================================

CSS = """
<style>
#MainMenu, footer {
    visibility: hidden;
}

.stApp {
    background: radial-gradient(
        1200px 600px at 50% -10%,
        #1a2040 0%,
        #0f1220 55%
    );
}

[data-testid="stHeader"] {
    background: transparent;
}

.block-container {
    max-width: 850px;
    padding-top: 2rem;
    padding-bottom: 4rem;
}

.hero {
    text-align: center;
    padding: 1rem 0 2rem;
}

.hero h1 {
    font-size: 2.3rem;
    font-weight: 800;
    color: #a8baff;
}

.hero p {
    color: #9aa4b8;
}

.step {
    color: #e8ecf4;
    font-weight: 700;
    font-size: 1.1rem;
    margin: 1.5rem 0 .7rem;
}

.q-num {
    color: #7c9cff;
    font-weight: 800;
    font-size: 1rem;
}

.q-text {
    font-size: 1.08rem;
    line-height: 2;
    color: #e8ecf4;
}

.blank {
    display: inline-block;
    min-width: 3rem;
    padding: 0 .5rem;
    margin: 0 .15rem;
    border-bottom: 2px solid #7c9cff;
    background: rgba(124,156,255,.16);
    color: #b9c8ff;
    border-radius: 6px;
    text-align: center;
    font-weight: 700;
}

.blank.ok {
    border-color: #3ddc97;
    color: #7ff0c0;
}

.blank.no {
    border-color: #ff6b81;
    color: #ff9aa9;
}

.score-card {
    text-align: center;
    padding: 1.5rem;
    border-radius: 16px;
    margin: 1rem 0;
    background: rgba(124,156,255,.15);
}

.score-num {
    font-size: 2.5rem;
    font-weight: 800;
    color: #e8ecf4;
}

.score-sub {
    color: #9db4ff;
}

</style>
"""


def esc(s):
    return html.escape(str(s)).replace("$", "&#36;")


def question_html(q, flags=None):

    def replace(m):

        n = int(m.group(1))

        if flags is None:
            return f'<span class="blank">{n}</span>'

        cls = "ok" if flags[n - 1] else "no"

        return (
            f'<span class="blank {cls}">'
            f'{esc(q["answers"][n - 1])}'
            f'</span>'
        )

    return re.sub(
        r"⟦(\d+)⟧",
        replace,
        esc(q["text"])
    )


def load_example():

    st.session_state["source_text"] = EXAMPLE_TEXT


# ============================================================
# 13. Streamlit 기본 설정
# ============================================================

st.set_page_config(
    page_title="시험 범위 빈칸 문제 생성기",
    page_icon="📝",
    layout="centered"
)

st.markdown(
    CSS,
    unsafe_allow_html=True
)

# 세션 초기화

st.session_state.setdefault("questions", [])
st.session_state.setdefault("terms", {})
st.session_state.setdefault("round", 0)
st.session_state.setdefault("graded", False)
st.session_state.setdefault("hints", {})
st.session_state.setdefault("similar", {})
st.session_state.setdefault("source", "")


# ============================================================
# 14. 메인 제목
# ============================================================

st.markdown(
    """
    <div class="hero">
        <h1>📝 빈칸 문제 생성기</h1>
        <p>
        시험 범위를 입력하면 핵심 단어를 자동으로 찾아
        나만의 시험 문제를 만들어 드려요.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# 15. 시험 범위 입력
# ============================================================

st.markdown(
    '<div class="step">① 시험 범위 입력</div>',
    unsafe_allow_html=True
)

st.button(
    "예시 텍스트 넣어 보기",
    on_click=load_example
)

text = st.text_area(
    "시험 범위",
    key="source_text",
    height=220,
    label_visibility="collapsed",
    placeholder="교재나 필기 내용을 붙여넣으세요."
)


# ============================================================
# 16. 문제 설정
# ============================================================

st.markdown(
    '<div class="step">② 문제 설정</div>',
    unsafe_allow_html=True
)

col1, col2 = st.columns(2)

num_questions = col1.slider(
    "문제 수",
    1, 30, 10
)

blanks_per_q = col2.slider(
    "문장당 빈칸 수",
    1, 3, 1
)

include_numbers = st.checkbox(
    "연도 및 숫자 포함",
    value=True
)


# ============================================================
# 17. AI 설정
# ============================================================

with st.expander("🤖 AI 비슷한 문제 출제 설정"):

    st.text_input(
        "Anthropic API 키",
        type="password",
        key="api_key_input",
        placeholder="sk-ant-..."
    )

    st.caption(
        "API 키를 입력하면 시험 범위의 내용을 바탕으로 "
        "새로운 문장과 문제 유형을 생성합니다. "
        "API 키가 없으면 자동 변형 방식으로 출제합니다."
    )


# ============================================================
# 18. 문제 생성 버튼
# ============================================================

if st.button(
    "🎯 문제 만들기",
    type="primary",
    use_container_width=True
):

    if not text.strip():

        st.warning(
            "먼저 시험 범위 내용을 입력해 주세요."
        )

    else:

        scores = extract_terms(
            text,
            include_numbers
        )

        new_questions = make_questions(
            split_sentences(text),
            scores,
            num_questions,
            blanks_per_q
        )

        if not new_questions:

            st.error(
                "문제를 만들 수 있는 문장을 찾지 못했어요."
            )

        else:

            st.session_state.questions = new_questions
            st.session_state.terms = scores
            st.session_state.source = text

            st.session_state.round += 1
            st.session_state.graded = False

            st.session_state.similar = {}


# ============================================================
# 19. 문제 풀이 및 채점
# ============================================================

questions = st.session_state.questions
rnd = st.session_state.round
graded = st.session_state.graded

if questions:

    st.markdown(
        '<div class="step">③ 문제 풀기</div>',
        unsafe_allow_html=True
    )

    with st.expander("🔍 자동으로 찾은 핵심 단어"):

        top_terms = sorted(
            st.session_state.terms.items(),
            key=lambda kv: -kv[1]
        )[:40]

        for term, score in top_terms:

            st.write(
                f"• {term}  (중요도: {score})"
            )

    all_flags = []
    wrong = []
    score = 0

    for i, q in enumerate(questions):

        user_answers = [
            st.session_state.get(
                f"ans_{rnd}_{i}_{j}",
                ""
            )
            for j in range(len(q["answers"]))
        ]

        flags = [
            normalize(u) == normalize(a)
            for u, a in zip(
                user_answers,
                q["answers"]
            )
        ]

        all_flags.append(
            (user_answers, flags)
        )

        if all(flags):
            score += 1
        else:
            wrong.append(i)

    # 채점 결과

    if graded:

        pct = round(
            score / len(questions) * 100
        )

        st.markdown(
            f"""
            <div class="score-card">
                <div class="score-num">
                    {score} / {len(questions)}
                </div>
                <div class="score-sub">
                    정답률 {pct}%
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.progress(
            score / len(questions)
        )

    # 각각의 문제 출력

    for i, q in enumerate(questions):

        user_answers, flags = all_flags[i]

        with st.container(border=True):

            st.markdown(
                f"### Q{i + 1}"
            )

            st.markdown(
                question_html(
                    q,
                    flags if graded else None
                ),
                unsafe_allow_html=True
            )

            cols = st.columns(
                len(q["answers"])
            )

            for j, col in enumerate(cols):

                col.text_input(
                    f"{j + 1}번 빈칸",
                    key=f"ans_{rnd}_{i}_{j}",
                    placeholder="정답 입력",
                    disabled=graded
                )

                hint_key = f"{rnd}_{i}_{j}"

                level = st.session_state.hints.get(
                    hint_key,
                    0
                )

                if level > 0:

                    col.info(
                        hint_text(
                            q["answers"][j],
                            level
                        )
                    )

                if not graded:

                    col.button(
                        "💡 힌트",
                        key=f"hint_{hint_key}",
                        on_click=use_hint,
                        args=(hint_key,),
                        disabled=level >= 2,
                        use_container_width=True
                    )

            # 채점 후 틀린 문제에만 기능 표시

            if graded and not all(flags):

                st.error("오답입니다.")

                mine = ", ".join(
                    u if u.strip() else "(빈칸)"
                    for u in user_answers
                )

                st.caption(
                    f"내 답: {mine}"
                )

                # 핵심 기능:
                # 각 틀린 문제마다 개별 비슷한 문제 출제

                render_similar(
                    rnd,
                    i,
                    q,
                    flags
                )

    # ========================================================
    # 20. 채점 버튼
    # ========================================================

    st.write("")

    if not graded:

        st.button(
            "✅ 채점하기",
            type="primary",
            use_container_width=True,
            on_click=grade
        )

    # ========================================================
    # 21. 틀린 문제 저장 기능
    # ========================================================

    elif wrong:

        lines = []

        for n, i in enumerate(wrong, start=1):

            q = questions[i]

            plain = re.sub(
                r"⟦(\d+)⟧",
                r"( \1 )",
                q["text"]
            )

            lines.append(
                f"Q{n}. {plain}"
            )

            lines.append(
                "정답: " + ", ".join(q["answers"])
            )

            lines.append("")

        st.download_button(
            "💾 틀린 문제 저장",
            data="\n".join(lines),
            file_name="wrong_questions.txt",
            mime="text/plain",
            use_container_width=True
        )

    else:

        st.success(
            "🎉 모든 문제를 맞혔어요!"
        )


# ============================================================
# 22. 하단 안내
# ============================================================

st.markdown(
    """
    <div style="
        text-align:center;
        color:#6c7690;
        margin-top:35px;
        font-size:13px;
    ">
        시험 범위 기반 자동 문제 생성 학습 도구
    </div>
    """,
    unsafe_allow_html=True
)
