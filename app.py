"""Dashboard: the answer to each research question from the data collected so far.

Run:  streamlit run app.py
Reload the page after `python -m pipeline.prices --live`. The caches below are keyed on the
silver files' modification times, so a pipeline run invalidates them.
"""
from datetime import datetime

import streamlit as st

from analysis.data import Silver, load_silver, rows_per_game, silver_stamp
from analysis.questions import QUESTIONS, Status, status
from analysis.results import Answer, Question

BADGES = {
    Status.READY: ":green-badge[ready]",
    Status.WAITING: ":orange-badge[waiting for data]",
    Status.NOT_STARTED: ":gray-badge[not started]",
}
QUESTION_BY_ID = {q.id: q for q in QUESTIONS}

st.set_page_config(page_title="TCG market analysis", layout="wide")


@st.cache_resource(max_entries=1)
def silver(stamp: tuple[int, ...]) -> Silver:
    return load_silver()


@st.cache_data(max_entries=32)
def compute(question_id: int, stamp: tuple[int, ...]) -> Answer:
    return QUESTION_BY_ID[question_id].answer(silver(stamp))


def answer_or_error(q: Question, stamp: tuple[int, ...]) -> Answer | Exception:
    try:
        return compute(q.id, stamp)
    except Exception as e:
        return e


def md(text: str) -> str:
    return text.replace("$", r"\$")  # two dollar signs would otherwise turn the text between them into math


def history(q: Question, data: Silver) -> str:
    return f"{data.days} of {q.min_days} days"


def overview_detail(q: Question, state: Status, data: Silver, stamp: tuple[int, ...]) -> str:
    if state is Status.READY:
        result = answer_or_error(q, stamp)
        return f"Error: {result}" if isinstance(result, Exception) else result.headline
    if state is Status.WAITING:
        return history(q, data)
    if q.min_days is None:
        return "No analysis code yet."
    return f"No analysis code yet. Needs {q.min_days} days of history (have {data.days})."


def overview(data: Silver, stamp: tuple[int, ...]) -> None:
    for q in QUESTIONS:
        state = status(q, data)
        with st.container(border=True):
            left, right = st.columns([1, 6])
            left.markdown(f"**Q{q.id}**  \n{BADGES[state]}")
            right.markdown(f"**{md(q.title)}**  \n{md(overview_detail(q, state, data, stamp))}")


def question_page(q: Question, data: Silver, stamp: tuple[int, ...]) -> None:
    state = status(q, data)
    st.header(md(q.title))
    st.markdown(f"{BADGES[state]}  Method: {md(q.method)}")
    if state is Status.NOT_STARTED:
        st.info(overview_detail(q, state, data, stamp))
        return
    if state is Status.WAITING:
        st.progress(data.days / q.min_days, text=history(q, data))
        return
    result = answer_or_error(q, stamp)
    if isinstance(result, Exception):
        st.exception(result)
        return
    st.subheader(md(result.headline))
    st.caption(f"Snapshot of {result.as_of}")
    if result.chart is not None:
        st.altair_chart(result.chart, width="stretch")
    for table in result.tables:
        st.subheader(md(table.title))
        if table.note:
            st.caption(md(table.note))
        config = {col: st.column_config.NumberColumn(format=fmt) for col, fmt in table.formats.items()}
        st.dataframe(table.df, hide_index=True, column_config=config)
    st.subheader("Caveats")
    st.markdown("\n".join(f"- {md(c)}" for c in result.caveats))


st.title("TCG market analysis")
stamp = silver_stamp()
try:
    data = silver(stamp)
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

with st.sidebar:
    st.header("Data")
    st.metric("Last snapshot", str(data.last_day))
    st.metric("Days collected", data.days)
    st.caption(f"Silver tables written {datetime.fromtimestamp(max(stamp) / 1e9):%Y-%m-%d %H:%M}. "
               "Reload the page after a pipeline run.")
    st.dataframe(rows_per_game(data), hide_index=True)
    if data.benchmarks is None:
        st.caption("Benchmarks missing. Run `python -m pipeline.benchmarks`.")

tabs = st.tabs(["Overview"] + [f"Q{q.id}" for q in QUESTIONS])
with tabs[0]:
    overview(data, stamp)
for tab, q in zip(tabs[1:], QUESTIONS):
    with tab:
        question_page(q, data, stamp)
