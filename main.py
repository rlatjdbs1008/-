"""
📝 시험 범위 빈칸 문제 자동 생성기 (Streamlit)

사용 흐름
1) 교재/필기 내용을 붙여넣는다.
2) 핵심 단어를 고른다. (자동 후보 + 직접 입력)
3) '문제 만들기'를 누르면 핵심 단어가 빈칸이 된 문장이 만들어진다.
4) 답을 입력하고 채점 → 틀린 문제만 다시 풀기 / 파일로 저장

실행 방법:  streamlit run app.py
"""

import random
import re
from collections import Counter

import streamlit as st

# ============================================================
# 1. 기본 설정값
# ============================================================

# 한국어 조사 목록. 단어 끝의 조사를 떼어 내서 "정부는" -> "정부"처럼 만들 때 쓴다.
# 긴 조사부터 검사해야 "에서"가 "서"보다 먼저 처리되므로 길이 순으로 정렬한다.
JOSA_LIST = sorted(
    [
        "에서는", "으로서", "에서의", "이라는", "에서", "으로", "까지", "부터",
        "에게", "라는", "에는", "과의", "와의", "로서", "의", "은", "는", "이",
        "가", "을", "를", "에", "로", "와", "과", "도", "만",
    ],
    key=len,
    reverse=True,
)

# 핵심 단어 후보에서 빼고 싶은 흔한 말
STOPWORDS = {
    "그리고", "하지만", "그러나", "때문에", "있는", "없는", "하는", "되는",
    "위해", "대한", "통해", "이후", "이러한", "그러한", "따라서", "또한",
    "다른", "같은", "모든", "여러", "이를", "그는", "이는", "하여", "하고",
    "것이", "것을", "것은", "수가", "등을", "등의",
}

# 처음 써볼 때 눌러 보는 예시 글 (직접 쓴 요약문)
EXAMPLE_TEXT = """1919년 3월 1일 전국에서 3·1 운동이 일어났다. 3·1 운동은 민족 대표 33인이 독립 선언서를 발표하면서 시작되었다.
3·1 운동의 영향으로 같은 해 4월 상하이에서 대한민국 임시 정부가 수립되었다.
일제는 1910년대에 헌병 경찰을 앞세워 무단 통치를 실시하였다.
3·1 운동 이후 일제는 문화 통치로 방식을 바꾸었으나 실제로는 민족 분열을 노린 기만적인 정책이었다.
1920년 김좌진이 이끄는 북로 군정서는 청산리에서 일본군에 큰 승리를 거두었다.
1932년 이봉창과 윤봉길은 한인 애국단 소속으로 의열 투쟁을 전개하였다."""


# ============================================================
# 2. 텍스트 처리 함수
# ============================================================

def strip_josa(word: str) -> str:
    """단어 끝의 조사를 떼어 낸다. (떼고 나서 2글자 이상 남을 때만)"""
    for josa in JOSA_LIST:
        if word.endswith(josa) and len(word) - len(josa) >= 2:
            return word[: -len(josa)]
    return word


def extract_candidates(text: str, top_n: int = 30) -> list[str]:
    """글에서 자주 나오는 한글 단어를 핵심 단어 후보로 뽑는다.
    (완벽하지 않으므로 사용자가 직접 고르도록 후보로만 보여 준다)"""
    words = re.findall(r"[가-힣]{2,}", text)  # 한글 2글자 이상 덩어리
    stems = []
    for w in words:
        stem = strip_josa(w)
        if stem in STOPWORDS or stem.endswith("다"):  # 불용어, 동사 형태 제외
            continue
        stems.append(stem)
    return [word for word, _ in Counter(stems).most_common(top_n)]


def split_sentences(text: str) -> list[str]:
    """글을 문장 단위로 자른다. (마침표/물음표/느낌표 뒤, 또는 줄바꿈)"""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 10]  # 너무 짧은 건 제외


def normalize(s: str) -> str:
    """채점할 때 띄어쓰기·대소문자 차이는 무시하려고 정리한다."""
    return re.sub(r"\s+", "", s).lower()


# ============================================================
# 3. 문제 만들기
# ============================================================

def make_questions(sentences, keywords, num_questions, blanks_per_q):
    """핵심 단어가 들어 있는 문장을 골라 빈칸 문제로 바꾼다.

    반환: [{"text": "빈칸이 뚫린 문장", "answers": ["정답1", ...]}, ...]
    """
    # (1) 핵심 단어가 하나라도 들어 있는 문장만 모은다.
    pool = []
    for sentence in sentences:
        found = [k for k in keywords if k in sentence]
        if found:
            pool.append((sentence, found))

    random.shuffle(pool)  # 매번 다른 문제가 나오도록 섞기

    # (2) 문장마다 단어를 골라 빈칸으로 바꾼다.
    questions = []
    for sentence, found in pool[:num_questions]:
        chosen = random.sample(found, min(blanks_per_q, len(found)))
        chosen.sort(key=len, reverse=True)  # 긴 단어 먼저 (독립운동 → 독립 순)

        text = sentence
        answers = []
        for keyword in chosen:
            if keyword not in text:  # 앞에서 이미 가려진 경우
                continue
            label = f"( {len(answers) + 1} ) ＿＿＿＿"
            text = text.replace(keyword, label)  # 같은 단어는 전부 가려 힌트 방지
            answers.append(keyword)

        if answers:
            questions.append({"text": text, "answers": answers})

    return questions


# ============================================================
# 4. 버튼을 눌렀을 때 실행되는 함수 (콜백)
# ============================================================

def load_example():
    st.session_state["source_text"] = EXAMPLE_TEXT


def grade():
    st.session_state.graded = True


def retry_wrong(wrong_questions):
    """틀린 문제만 새 문제 세트로 바꾼다."""
    st.session_state.questions = wrong_questions
    st.session_state.round += 1  # 입력칸 key가 바뀌어서 이전 답이 지워진다
    st.session_state.graded = False


# ============================================================
# 5. 화면 구성
# ============================================================

st.set_page_config(page_title="빈칸 문제 생성기", page_icon="📝")

# 앱이 다시 실행되어도 값이 유지되도록 session_state에 저장해 둔다.
if "questions" not in st.session_state:
    st.session_state.questions = []
    st.session_state.round = 0
    st.session_state.graded = False

st.title("📝 시험 범위 빈칸 문제 생성기")
st.caption("교재 내용을 붙여넣으면 핵심 단어가 빈칸인 문제를 자동으로 만들어 줘요.")

# ---------- 사이드바: 설정 ----------
with st.sidebar:
    st.header("⚙️ 설정")
    num_questions = st.slider("문제 수", 1, 30, 10)
    blanks_per_q = st.radio("문장당 빈칸 수", [1, 2], horizontal=True)
    st.caption("빈칸 2개는 한 문장에 핵심 단어가 2개 이상 있을 때만 적용돼요.")

# ---------- 1단계: 글 붙여넣기 ----------
st.subheader("① 시험 범위 내용")
st.button("예시 텍스트 넣어 보기", on_click=load_example)
text = st.text_area(
    "교재나 필기 내용을 붙여넣으세요",
    key="source_text",
    height=250,
    label_visibility="collapsed",
    placeholder="여기에 시험 범위 내용을 붙여넣으세요.",
)

# ---------- 2단계: 핵심 단어 고르기 ----------
st.subheader("② 핵심 단어 고르기")
candidates = extract_candidates(text) if text.strip() else []
selected = st.multiselect(
    "자동으로 찾은 후보 (필요 없는 건 x로 지우세요)",
    candidates,
    default=candidates[:10],
)
manual_input = st.text_input(
    "직접 넣을 핵심 용어 (쉼표로 구분)",
    placeholder="예: 3·1 운동, 문화 통치, 한인 애국단",
)
st.caption("자동 후보는 완벽하지 않아요. 중요한 용어는 직접 입력하는 게 가장 정확해요.")

manual = [w.strip() for w in manual_input.split(",") if w.strip()]
keywords = list(dict.fromkeys(manual + selected))  # 중복 제거(순서 유지)

# ---------- 3단계: 문제 만들기 ----------
if st.button("🎯 문제 만들기", type="primary"):
    if not text.strip():
        st.warning("먼저 시험 범위 내용을 붙여넣어 주세요.")
    elif not keywords:
        st.warning("핵심 단어를 하나 이상 골라 주세요.")
    else:
        new_questions = make_questions(
            split_sentences(text), keywords, num_questions, blanks_per_q
        )
        if not new_questions:
            st.error("핵심 단어가 들어 있는 문장을 찾지 못했어요. 단어를 다시 확인해 주세요.")
        else:
            st.session_state.questions = new_questions
            st.session_state.round += 1
            st.session_state.graded = False

# ---------- 4단계: 문제 풀기 / 채점 ----------
questions = st.session_state.questions
rnd = st.session_state.round
graded = st.session_state.graded

if questions:
    st.divider()
    st.subheader(f"문제 ({len(questions)}개)")

    score = 0
    wrong = []

    for i, q in enumerate(questions):
        st.markdown(f"**Q{i + 1}.** {q['text']}")

        # 빈칸 개수만큼 입력칸을 가로로 만든다.
        cols = st.columns(len(q["answers"]))
        for j, col in enumerate(cols):
            col.text_input(
                f"( {j + 1} ) 정답",
                key=f"ans_{rnd}_{i}_{j}",
                disabled=graded,  # 채점 후에는 수정 불가
            )

        # 채점 결과 표시
        if graded:
            user_answers = [
                st.session_state.get(f"ans_{rnd}_{i}_{j}", "")
                for j in range(len(q["answers"]))
            ]
            is_correct = all(
                normalize(u) == normalize(a) for u, a in zip(user_answers, q["answers"])
            )
            if is_correct:
                score += 1
                st.success("정답!")
            else:
                wrong.append(q)
                answer_text = " / ".join(
                    f"({k + 1}) {a}" for k, a in enumerate(q["answers"])
                )
                st.error(f"오답 · 정답: {answer_text}")

    st.divider()

    if not graded:
        st.button("✅ 채점하기", type="primary", on_click=grade)
    else:
        st.metric("점수", f"{score} / {len(questions)}")

        if wrong:
            col1, col2 = st.columns(2)
            col1.button(
                "🔁 틀린 문제만 다시 풀기",
                on_click=retry_wrong,
                args=(wrong,),
            )

            # 틀린 문제를 텍스트 파일로 저장 (프린트해서 풀기 좋음)
            lines = []
            for n, q in enumerate(wrong, start=1):
                lines.append(f"Q{n}. {q['text']}")
                lines.append("정답: " + ", ".join(q["answers"]))
                lines.append("")
            col2.download_button(
                "💾 틀린 문제 저장",
                data="\n".join(lines),
                file_name="wrong_questions.txt",
            )
        else:
            st.balloons()
            st.success("전부 맞혔어요! 새 문제를 만들어 보세요.")
