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

def load_example():
    st.session_state["source_text"] = EXAMPLE_TEXT


def grade():
    st.session_state.graded = True


def retry_wrong(wrong_questions):
    st.session_state.questions = wrong_questions
    st.session_state.round += 1  # 입력칸 key가 바뀌어 이전 답이 지워진다
    st.session_state.graded = False


# ============================================================
# 6. 화면 구성
# ============================================================

st.set_page_config(page_title="빈칸 문제 생성기", page_icon="📝")
st.markdown(CSS, unsafe_allow_html=True)

if "questions" not in st.session_state:
    st.session_state.questions = []
    st.session_state.terms = {}
    st.session_state.round = 0
    st.session_state.graded = False

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
include_numbers = col3.toggle("연도·숫자 포함", value=True)

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
        top_terms = sorted(st.session_state.terms.items(), key=lambda kv: -kv[1])[:40]
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
        st.markdown(
            f'<div class="score-card"><div class="score-num">{score}'
            f'<span> / {len(questions)}</span></div>'
            f'<div class="score-sub">정답률 {pct}%</div></div>',
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

            if graded and not all(flags):
                mine = ", ".join(u if u.strip() else "(빈칸)" for u in user_answers)
                st.markdown(f'<div class="my-ans">내 답: {esc(mine)}</div>', unsafe_allow_html=True)

    st.write("")
    if not graded:
        st.button("✅ 채점하기", type="primary", use_container_width=True, on_click=grade)
    elif wrong:
        c1, c2 = st.columns(2)
        c1.button("🔁 틀린 문제만 다시 풀기", on_click=retry_wrong, args=(wrong,), use_container_width=True)

        lines = []
        for n, q in enumerate(wrong, start=1):
            plain = re.sub(r"⟦(\d+)⟧", r"( \1 )", q["text"])
            lines.append(f"Q{n}. {plain}")
            lines.append("정답: " + ", ".join(q["answers"]))
            lines.append("")
        c2.download_button(
            "💾 틀린 문제 저장",
            data="\n".join(lines),
            file_name="wrong_questions.txt",
            use_container_width=True,
        )
    else:
        st.success("전부 맞혔어요! 위에서 '문제 만들기'를 다시 눌러 새 문제를 풀어 보세요.")

st.markdown('<div class="footnote">핵심 단어는 자동으로 찾기 때문에 가끔 어색한 빈칸이 나올 수 있어요.</div>', unsafe_allow_html=True)
